#!/usr/bin/env python3
"""Crossover trial (Finding 20): when does a code map beat plain search, and can a hook decide when to use it?

Question type: "which Go packages directly import package P?" on kubernetes, answered exactly by import lines, and by the
mapper's package graph (`semantic_query.py find-usages go:<dir>`), which agrees with the key (go_reference.py). So the graph is
correct by construction here and the trial measures cost and search noise, not graph accuracy. Four low-noise and four
high-noise packages, chosen from `git grep` hit counts before any run.

  S   search only (no map command is allowed or mentioned)
  M   map command allowed, named in the prompt (soft nudge), search also allowed
  H   noise gate (hooks/noise_gate.py): a search matching more than --min-hits files is denied once with the map command
      named in the reason; the prompt says nothing about the map
  H+  H, and the denial adds: search inside the files the map lists to confirm

Harnesses: `--harness claude` (Claude Code, hook in .claude/settings.json) and `--harness agy` (Antigravity, hook in
.agents/hooks.json). Run from the folder that holds the clones and graphs.

  python3 experiments/trial/crossover_trial.py run --harness claude --dry-run
  python3 experiments/trial/crossover_trial.py run --harness claude --pilot
  python3 experiments/trial/crossover_trial.py run --harness claude --reps 2
  python3 experiments/trial/crossover_trial.py score --harness claude
"""

import argparse
import collections
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import agy_nudge_trial as agy  # noqa: E402  (parse_events)
import trial  # noqa: E402  (parse_stream, prf)

LAB = trial.LAB
REPO = "kubernetes"
# A native-filesystem clone at the same commit: on the lab's mounted drive one search of kubernetes takes 8 to 13 seconds.
REPO_DIR = Path(os.environ.get("CROSS_REPO_DIR") or Path.home() / "trial-clones" / REPO)
if not REPO_DIR.exists():
    REPO_DIR = LAB / REPO
CONDS = ["S", "M", "H", "H+"]
SQ = trial.TOOL  # scripts/semantic_query.py
GRAPH = LAB / "experiments" / "trial" / "graphs" / "kubernetes-go" / "relationship_graph.json"
GATE = (HERE.parents[3] / "hooks" / "noise_gate.py").resolve()
if not GATE.exists():  # lab copy sits next to the flat repo
    GATE = (LAB.parent / "ast-context-map" / "hooks" / "noise_gate.py").resolve()
MAP_CMD = f"python3 {SQ} --graph {GRAPH} find-usages go:<directory>"
HIGH_NOISE = 200  # grep files; the eight questions fall at 6 to 53 and 227 to 587
PLUS_NOTE = "The map lists direct importers; confirm the list with a search inside those files before you answer."
SEARCH_WORD = re.compile(r"(^|[\s;&|(])(grep|egrep|fgrep|rg|ag|ack|find|git\s+grep)\s")
ONE_COMMAND = " Run one command per tool call (no cd, shell variables, pipes or loops)."


def prompt_for(q: dict, cond: str) -> str:
    root = REPO_DIR
    p = q["package"]
    text = (
        f"In the Go repository at {root}, which Go packages directly import the package in directory `{p}` "
        f"(import path `k8s.io/kubernetes/{p}`)? A directory counts if any non-test .go file in it imports the package; "
        "ignore vendor/ and testdata/ and the package itself. Reply with the final list only, one line per directory: "
        "`PKG: <directory relative to the repository root>`."
    )
    if cond == "M":
        text += f" A code graph of the repository is available: `{MAP_CMD}` lists direct importers (lines `Used in go:<directory>`)."
    return text + ONE_COMMAND


def noise_env(sandbox: Path, cond: str, min_hits: int) -> str:
    env = (
        f"NOISE_REPO={REPO_DIR} NOISE_STATE={sandbox}/noise.state NOISE_LOG={sandbox}/noise.log NOISE_MIN_HITS={min_hits} "
        f"NOISE_GLOB='*.go' NOISE_CMD_RE=semantic_query NOISE_HINT='{MAP_CMD}'"
    )
    if cond == "H+":
        env += f" NOISE_NOTE='{PLUS_NOTE}'"
    return env


def make_sandbox(cond: str, harness: str, min_hits: int) -> Path:
    sandbox = Path(tempfile.mkdtemp(prefix=f"cross-{harness}-{cond}-"))
    if cond not in ("H", "H+"):
        return sandbox
    command = f"{noise_env(sandbox, cond, min_hits)} python3 {GATE}"
    if harness == "claude":
        settings = {"hooks": {"PreToolUse": [{"matcher": "Grep|Bash", "hooks": [{"type": "command", "command": command}]}]}}
        (sandbox / ".claude").mkdir()
        (sandbox / ".claude" / "settings.json").write_text(json.dumps(settings, indent=2))
    else:
        subprocess.run(["git", "init", "-q", str(sandbox)], check=True)
        hooks = {"hooks": {"PreToolUse": [{"matcher": "run_command|grep_search|find_by_name",
                                           "hooks": [{"type": "command", "command": command, "timeout": 20}]}]}}  # fmt: skip
        (sandbox / ".agents").mkdir()
        (sandbox / ".agents" / "hooks.json").write_text(json.dumps(hooks, indent=2))
    return sandbox


def claude_cmd(model: str, cap: float, cond: str) -> list[str]:
    allow = ["Read", "Grep", "Glob", "Bash(ls:*)"]
    if cond != "S":
        allow.append(f"Bash(python3 {SQ}:*)")
    return [
        "claude", "-p", "--model", model, "--output-format", "stream-json", "--verbose", "--max-budget-usd", str(cap),
        "--no-session-persistence", "--permission-mode", "dontAsk", "--add-dir", str(REPO_DIR),
        "--tools", "Read,Grep,Glob,Bash", "--allowedTools", *allow,
    ]  # fmt: skip


def agy_cmd(model: str, timeout: str, prompt: str) -> list[str]:
    return ["agy", "--output-format", "stream-json", "--model", model, "--print-timeout", timeout, f"-p={prompt}"]


def run(args) -> None:
    questions = json.loads(Path(args.questions).read_text())
    results = Path(args.results_dir or HERE / f"results-cross-{args.harness}")
    results.mkdir(parents=True, exist_ok=True)
    jobs = [(qi, rep, c) for qi in range(len(questions)) for rep in range(args.reps) for c in args.conds.split(",")]
    if args.pilot:  # a high-noise question under the gate, to confirm the hook fires and the map command runs
        jobs = [j for j in jobs if j[0] == 4 and j[1] == 0 and j[2] == "H"]
    if args.offset:
        jobs = jobs[args.offset :] + jobs[: args.offset]
    total = 0.0
    tokens = 0
    for qi, rep, cond in jobs:
        out = results / f"{cond}__{REPO}__q{qi}__r{rep}.json"
        if out.exists():
            continue
        prompt = prompt_for(questions[qi], cond)
        model = args.model or ("haiku" if args.harness == "claude" else "gemini-4-hydrogen-medium")
        if args.dry_run:
            cmd = claude_cmd(model, args.cap, cond) if args.harness == "claude" else agy_cmd(model, args.timeout, "<prompt>")
            print(cond, f"q{qi} r{rep}", " ".join(cmd)[:150], "<<<", prompt[:90].replace("\n", " "))
            continue
        sandbox = make_sandbox(cond, args.harness, args.min_hits)
        try:
            if args.harness == "claude":
                proc = subprocess.run(claude_cmd(model, args.cap, cond), input=prompt, capture_output=True, text=True,
                                      cwd=sandbox, timeout=900)  # fmt: skip
                parsed = trial.parse_stream(proc.stdout) if proc.stdout else {"is_error": True, "stderr": proc.stderr[-500:]}
            else:
                proc = subprocess.run(agy_cmd(model, args.timeout, prompt), capture_output=True, text=True, cwd=sandbox,
                                      timeout=args.hard_timeout)  # fmt: skip
                parsed = agy.parse_events(proc.stdout) if proc.stdout else {"is_error": True, "stderr": proc.stderr[-500:]}
            log = sandbox / "noise.log"
            parsed["hook_log"] = log.read_text().splitlines() if log.exists() else []
        except subprocess.TimeoutExpired:
            parsed = {"is_error": True, "stderr": "timeout", "hook_log": []}
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)
        parsed["condition"] = cond
        out.write_text(json.dumps(parsed))
        total += float(parsed.get("total_cost_usd") or 0)
        tokens += int(parsed.get("total_tokens") or 0)
        denied = sum(1 for x in parsed["hook_log"] if "denied" in x)
        print(f"{out.name}: cost ${total:.3f} tokens {tokens} hook lines {len(parsed['hook_log'])} denied {denied}", flush=True)
        if cond in ("H", "H+") and not parsed["hook_log"] and not parsed.get("is_error"):
            print("   WARNING: the hook never fired in a hook condition; this run is invalid")
        if total > args.total_cap or tokens > args.total_tokens:
            sys.exit(f"stopping: cost ${total:.2f} / {tokens} tokens exceeded the total cap")


def map_call(c: dict) -> bool:
    return c.get("tool") == "Bash" and "semantic_query" in c.get("arg", "")


def summarize(d: dict, q: dict) -> dict:
    text = d.get("result") or ""
    root = f"{REPO_DIR}/"
    answer = {m.strip().removeprefix(root).removeprefix("./").rstrip("/") for m in re.findall(r"PKG:\s*`?([^\s`]+)", text)}
    p, r, f1 = trial.prf(answer, set(q["reference"]))
    calls = d.get("tool_calls") or []
    first_map = next((i for i, c in enumerate(calls) if map_call(c)), None)
    u = d.get("usage") or {}
    hooks = d.get("hook_log") or []
    return {
        "cond": d.get("condition", ""),
        "high": q["grep_files"] >= HIGH_NOISE,
        "cost": d.get("total_cost_usd") or 0,
        "tokens": d.get("total_tokens")
        or sum(u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
        "turns": d.get("num_turns") or 0,
        "p": p, "r": r, "f1": f1,  # noqa: E701
        "map": first_map is not None,
        "map_calls": sum(1 for c in calls if map_call(c)),
        "searches": sum(1 for c in calls if c.get("tool") in ("Grep", "Glob") or (c.get("tool") == "Bash" and not map_call(c) and SEARCH_WORD.search(c.get("arg", "")))),
        "reads": sum(1 for c in calls if c.get("tool") == "Read"),
        "hooks": len(hooks),
        "denied": sum(1 for x in hooks if "denied" in x),
        "err": bool(d.get("is_error")),
        "invalid": bool(d.get("is_error")) or not answer or (d.get("condition") in ("H", "H+") and not hooks),
    }


def score(args) -> None:
    questions = json.loads(Path(args.questions).read_text())
    rows = collections.defaultdict(list)
    for f in sorted(Path(args.results_dir or HERE / f"results-cross-{args.harness}").glob("*.json")):
        cond, _repo, qn, _rep = f.stem.split("__")
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        d.setdefault("condition", cond)
        s = summarize(d, questions[int(qn[1:])])
        rows[(cond, s["high"])].append(s)
    unit = "cost$" if args.harness == "claude" else "tokens"
    print(f"{'cond':4} {'noise':5} {'n':>2} {'inval':>5} {'map':>3} {'denied':>6} {'srch':>4} {'read':>4} {unit:>7} {'turns':>5} {'prec':>5} {'rec':>5} {'F1 med (min-max)':>18}")  # fmt: skip
    cols = ["cond", "high", "cost", "tokens", "turns", "p", "r", "f1", "map", "map_calls", "searches", "reads", "hooks", "denied", "invalid"]
    lines = [",".join(cols)]
    for high in (False, True):
        for cond in CONDS:
            allr = rows.get((cond, high), [])
            lines += [",".join(f"{x[c]:.4g}" if isinstance(x[c], float) else str(x[c]) for c in cols) for x in allr]
            rs = [x for x in allr if not x["invalid"]]
            label = "high" if high else "low"
            if not rs:
                print(f"{cond:4} {label:5} {len(allr):>2} {len(allr):>5}  (no valid runs)")
                continue
            med = lambda k, rs=rs: statistics.median(x[k] for x in rs)  # noqa: E731
            f1s = [x["f1"] for x in rs]
            spend = med("cost") if args.harness == "claude" else med("tokens")
            print(f"{cond:4} {label:5} {len(rs):>2} {len(allr) - len(rs):>5} {sum(x['map'] for x in rs):>3} {sum(x['denied'] > 0 for x in rs):>6} "
                  f"{med('searches'):>4.0f} {med('reads'):>4.0f} {spend:>7.3f} {med('turns'):>5.0f} {med('p'):>5.2f} {med('r'):>5.2f} "
                  f"{statistics.median(f1s):>7.2f} ({min(f1s):.2f}-{max(f1s):.2f})")  # fmt: skip
    if args.csv:
        Path(args.csv).write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "score"):
        p = sub.add_parser(name)
        p.add_argument("--harness", choices=["claude", "agy"], required=True)
        p.add_argument("--results-dir", default=None)
        p.add_argument("--questions", default=str(HERE / "questions_go_imports.json"))
        if name == "score":
            p.add_argument("--csv", default=None, help="one row per run, no paths")
        else:
            p.add_argument("--model", default=None)
            p.add_argument("--cap", type=float, default=0.15, help="Claude: hard USD cap per run")
            p.add_argument("--total-cap", type=float, default=4.0, help="Claude: stop the trial above this USD")
            p.add_argument("--total-tokens", type=int, default=30_000_000, help="agy: stop the trial above this many tokens")
            p.add_argument("--timeout", default="8m", help="agy --print-timeout")
            p.add_argument("--hard-timeout", type=int, default=720)
            p.add_argument("--reps", type=int, default=2)
            p.add_argument("--conds", default=",".join(CONDS))
            p.add_argument("--min-hits", type=int, default=100, help="gate threshold: files a search may match")
            p.add_argument("--pilot", action="store_true")
            p.add_argument("--offset", type=int, default=0)
            p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    {"run": run, "score": score}[a.cmd](a)


if __name__ == "__main__":
    main()
