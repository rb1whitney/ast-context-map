#!/usr/bin/env python3
"""agy (Antigravity CLI) nudge trial, the counterpart of nudge_trial.py (Finding 19).

Graph: Graphify's own graph of dagger. Each run gets a new sandbox directory holding only what the condition gives the agent.

  G0  graph present, no mention anywhere
  G1  the always-on rule that `graphify antigravity install` writes (Graphify ships no hook for Antigravity)
  G2  the generic PreToolUse gate (hooks/agy/graph_gate.py): the first search waits for one graph query
  G3  the gate, plus a denial note and an always-on rule that stress the map's gaps
  G4  the gaps rule only, no gate

Known confound, accepted: the user's global ~/.gemini/AGENTS.md and the globally installed graphify skill load in every run.
Results describe "agy with these global rules", not a clean agy. Output is in tokens only (agy reports no dollar cost), so the
caps are a per-run wall-clock timeout and a trial-wide token total. The clone is checked for changes after every run because
agy's print mode runs in `always-proceed` permission mode.

Commands (run from the folder that holds the clones and `_graphs/`, `projects/llm-test` in the lab):
  python3 experiments/trial/agy_nudge_trial.py run --dry-run
  python3 experiments/trial/agy_nudge_trial.py run --pilot          one run (G2) to confirm the gate fires
  python3 experiments/trial/agy_nudge_trial.py run --reps 3
  python3 experiments/trial/agy_nudge_trial.py score
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
import nudge_trial as nt  # noqa: E402  (summarize and prompt pieces)
import trial  # noqa: E402

LAB = trial.LAB
REPO = "dagger"
CONDS = ["G0", "G1", "G2", "G3", "G4"]
GATE = (HERE.parents[3] / "hooks" / "agy" / "graph_gate.py").resolve()
if not GATE.exists():  # lab copy sits next to the flat repo
    GATE = (LAB.parent / "ast-context-map" / "hooks" / "agy" / "graph_gate.py").resolve()

GAPS_RULE = """---
trigger: always_on
description: A code graph is a map with gaps. Verify before you answer.
---

## The graph is a map, not the territory

- The graph lists candidate files. It does not see everything: annotation-driven wiring, reflection, generated code and some
  static references are missing from it, and a name that appears in the graph may stand for several classes.
- Never present a graph answer as complete. After the graph query, confirm with at least one search or by reading the key files.
- End your answer with a line `UNVERIFIED: <what you could not confirm>`. Write `none` only if you checked every file you listed
  and searched for files the graph might have missed.
"""
GAPS_NOTE = (
    "Remember the graph is a map with gaps: it misses annotation-driven and reflection-wired uses and some static references. "
    "Treat its list as candidates, verify with a search, and name what you could not confirm on the UNVERIFIED line."
)
DENY_RE = "denied"


def graphify_rule(tmp_home: Path) -> str:
    """The rule file the real installer writes. HOME is redirected so nothing is written to the user's ~/.gemini."""
    work = Path(tempfile.mkdtemp(prefix="agy-rule-"))
    try:
        subprocess.run(["git", "init", "-q", str(work)], check=True)
        env = {**os.environ, "HOME": str(tmp_home)}
        subprocess.run(
            [shutil.which("graphify") or "graphify", "antigravity", "install"],
            cwd=work, env=env, capture_output=True, text=True, check=True,
        )  # fmt: skip
        return (work / ".agents" / "rules" / "graphify.md").read_text()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def make_sandbox(cond: str, rule_text: str) -> Path:
    sandbox = Path(tempfile.mkdtemp(prefix=f"agy-{cond}-"))
    (sandbox / "graphify-out").symlink_to(LAB / "_graphs" / REPO / "graphify-out")
    if cond == "G0":
        return sandbox
    subprocess.run(["git", "init", "-q", str(sandbox)], check=True)
    rules = sandbox / ".agents" / "rules"
    rules.mkdir(parents=True)
    if cond == "G1":
        (rules / "graphify.md").write_text(rule_text)
    if cond in ("G3", "G4"):
        (rules / "graph-gaps.md").write_text(GAPS_RULE)
    if cond in ("G2", "G3"):
        env = f"GRAPH_GATE_LOG={sandbox}/gate.log"
        if cond == "G3":
            env += f' GRAPH_GATE_NOTE="{GAPS_NOTE}"'
        hooks = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "run_command|grep_search|find_by_name",
                        "hooks": [{"type": "command", "command": f"{env} python3 {GATE}", "timeout": 10}],
                    }
                ]
            }
        }
        (sandbox / ".agents" / "hooks.json").write_text(json.dumps(hooks, indent=2))
    return sandbox


def build_cmd(model: str, timeout: str, prompt: str) -> list[str]:
    return ["agy", "--output-format", "stream-json", "--model", model, "--print-timeout", timeout, f"-p={prompt}"]


def prompt_for(q: dict) -> str:
    return nt.prompt_for(q)  # same question, answer format and UNVERIFIED line as the Claude trial


TOOL_MAP = {
    "run_command": "Bash",
    "grep_search": "Grep",
    "find_by_name": "Glob",
    "read_file": "Read",
    "view_file": "Read",
}


def parse_events(stdout: str) -> dict:
    """agy stream-json to the shape nudge_trial.summarize expects."""
    calls, texts, result = [], {}, {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        step = event.get("step_update") or {}
        if step.get("step_type") == "tool" and step.get("state") == "DONE":
            params = (step.get("tool_info") or {}).get("parameters") or {}
            arg = params.get("CommandLine") or params.get("Query") or params.get("Pattern") or params.get("Path") or ""
            calls.append({"tool": TOOL_MAP.get(step.get("tool_name"), step.get("tool_name")), "arg": str(arg)[:300]})
        if step.get("step_type") == "agent_response" and step.get("text_delta"):
            texts[step["step_index"]] = texts.get(step["step_index"], "") + step["text_delta"]
        if event.get("event") == "result":
            result = event.get("result") or {}
    with_files = [t for _, t in sorted(texts.items()) if "FILE:" in t]
    final = with_files[-1] if with_files else (result.get("response") or "")
    usage = result.get("usage") or {}
    return {
        "result": final,
        "tool_calls": calls,
        "is_error": result.get("status") not in (None, "SUCCESS") or not result,
        "num_turns": result.get("num_turns") or 0,
        "total_cost_usd": 0,
        "usage": {
            "input_tokens": usage.get("input_tokens", 0),
            "cache_read_input_tokens": usage.get("cache_read_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        },
        "total_tokens": usage.get("total_tokens", 0) + usage.get("cache_read_tokens", 0),
    }


def clone_state() -> str:
    """`git status --porcelain` of the clone. Compared against a baseline taken at the start, so old untracked files do not matter."""
    return subprocess.run(
        ["git", "-C", str(LAB / REPO), "status", "--porcelain"], capture_output=True, text=True
    ).stdout


def run(args) -> None:
    questions = json.loads(Path(args.questions).read_text())[REPO]
    results = Path(args.results_dir)
    results.mkdir(parents=True, exist_ok=True)
    jobs = [(qi, rep, c) for qi in range(len(questions)) for rep in range(args.reps) for c in args.conds.split(",")]
    if args.pilot:
        jobs = [j for j in jobs if j[0] == 0 and j[1] == 0 and j[2] == "G2"]
    baseline = clone_state()
    if baseline.strip():
        print(f"note: {LAB / REPO} already has changes, used as the baseline: {baseline.strip()[:120]!r}")
    tmp_home = Path(tempfile.mkdtemp(prefix="agy-home-"))
    rule_text = "" if args.dry_run else graphify_rule(tmp_home)
    shutil.rmtree(tmp_home, ignore_errors=True)
    total = 0
    for qi, rep, cond in jobs:
        out = results / f"{cond}__{REPO}__q{qi}__r{rep}.json"
        if out.exists():
            continue
        prompt = prompt_for(questions[qi])
        if args.dry_run:
            print(cond, f"q{qi} r{rep}", "agy ... --model", args.model, "<<<", prompt.replace("\n", " | ")[-100:])
            continue
        sandbox = make_sandbox(cond, rule_text)
        try:
            proc = subprocess.run(
                build_cmd(args.model, args.timeout, prompt), capture_output=True, text=True, cwd=sandbox,
                timeout=args.hard_timeout,
            )  # fmt: skip
            parsed = parse_events(proc.stdout) if proc.stdout else {"is_error": True, "stderr": proc.stderr[-500:]}
            log = sandbox / "gate.log"
            parsed["hook_log"] = log.read_text().splitlines() if log.exists() else []
            parsed["condition"] = cond
        except subprocess.TimeoutExpired:
            parsed = {"is_error": True, "stderr": "hard timeout", "hook_log": [], "condition": cond}
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)
        out.write_text(json.dumps(parsed))
        total += int(parsed.get("total_tokens") or 0)
        denied = sum(1 for x in parsed["hook_log"] if x.split("\t")[-2:-1] == [DENY_RE])
        print(
            f"{out.name}: tokens {parsed.get('total_tokens', 0)} (running {total}) gate lines {len(parsed['hook_log'])} denied {denied}",
            flush=True,
        )
        if clone_state() != baseline:
            sys.exit(f"stopping: {LAB / REPO} changed during {out.name}; inspect it before continuing")
        if total > args.total_tokens:
            sys.exit(f"stopping: {total} tokens exceeded --total-tokens {args.total_tokens}")


def score(args) -> None:
    refs = {i: set(q["reference"]) for i, q in enumerate(json.loads(Path(args.questions).read_text())[REPO])}
    rows = collections.defaultdict(list)
    for f in sorted(Path(args.results_dir).glob("*.json")):
        cond, _repo, q, _rep = f.stem.split("__")
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        s = nt.summarize(d, refs[int(q[1:])])
        s["tokens"] = d.get("total_tokens") or 0
        s["denies"] = sum(1 for x in d.get("hook_log", []) if x.split("\t")[2:3] == [DENY_RE])
        s["invalid"] = bool(d.get("is_error")) or not (d.get("result") and "FILE:" in d["result"])
        rows[cond].append(s)
    print(f"{'cond':4} {'n':>2} {'inval':>5} {'graph':>5} {'first':>5} {'denies':>6} {'srch+':>5} {'read+':>5} {'flag/miss':>9} {'overconf':>8} {'tokens':>8} {'prec':>5} {'rec':>5} {'F1 med (min-max)':>18}")  # fmt: skip
    for cond in CONDS:
        allr = rows.get(cond, [])
        rs = [x for x in allr if not x["invalid"]]
        if not rs:
            print(f"{cond:4} {len(allr):>2} {len(allr):>5}  (no valid runs)" if allr else f"{cond:4}  0")
            continue
        med = lambda k, rs=rs: statistics.median(x[k] for x in rs)  # noqa: E731
        f1s = [x["f1"] for x in rs]
        print(f"{cond:4} {len(rs):>2} {len(allr) - len(rs):>5} {sum(x['graph'] for x in rs):>5} {sum(x['graph_first'] for x in rs):>5} "
              f"{sum(x['denies'] for x in rs):>6} {med('searches_after'):>5.0f} {med('reads_after'):>5.0f} "
              f"{sum(x['flagged_when_missed'] for x in rs):>4}/{sum(x['missed'] for x in rs):<4} {sum(x['overconfident'] for x in rs):>8} "
              f"{med('tokens'):>8.0f} {med('p'):>5.2f} {med('r'):>5.2f} {statistics.median(f1s):>7.2f} ({min(f1s):.2f}-{max(f1s):.2f})")  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "score"):
        p = sub.add_parser(name)
        p.add_argument("--results-dir", default=str(HERE / "results-agy"))
        p.add_argument("--questions", default=str(HERE / "questions_flow_v2.json"))
        if name == "run":
            p.add_argument("--model", default="gemini-3.8-flash-low")
            p.add_argument("--timeout", default="6m", help="agy --print-timeout, with a unit")
            p.add_argument("--hard-timeout", type=int, default=480, help="seconds before the process is killed")
            p.add_argument(
                "--total-tokens",
                type=int,
                default=6_000_000,
                help="stop above this many tokens (input, cache and output)",
            )
            p.add_argument("--reps", type=int, default=3)
            p.add_argument("--conds", default=",".join(CONDS))
            p.add_argument("--pilot", action="store_true")
            p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    {"run": run, "score": score}[a.cmd](a)


if __name__ == "__main__":
    main()
