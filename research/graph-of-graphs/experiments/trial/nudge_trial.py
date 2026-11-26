#!/usr/bin/env python3
"""Nudge trial (Finding 19): does telling an agent about a graph, and how, change what it does?

The graph is Graphify's own graph of dagger. Every run happens in a new sandbox directory that holds only what the
condition gives the agent; the repository itself is read through --add-dir, so nothing in the clone is modified.

  N0  graph present (graphify-out/ in the working directory), no mention anywhere
  N1  the CLAUDE.md section that `graphify claude install` writes
  N2  the PreToolUse hooks that `graphify claude install` writes
  N3  both (the installer default)
  N4  N3 plus a calibration rule appended to CLAUDE.md
  N5  the opt-in strict install, `graphify install --project --strict` (the first raw Read per session is denied once)

The sandbox files are produced by running the real installer, then removing the parts a condition does not get, so the
test is of the installed product and not of a copy of its text. Hooks are wrapped in a logger so a run records whether
they fired; a run whose hooks never fired in N2-N4 is reported as invalid, not as a zero.

Commands (run from the folder that holds the clones and `_graphs/`, which is `projects/llm-test` in the lab):
  python3 experiments/trial/nudge_trial.py run --dry-run         print the commands and the sandbox plan; free
  python3 experiments/trial/nudge_trial.py run --pilot           one paid run (N3) to confirm the hook fires
  python3 experiments/trial/nudge_trial.py run --reps 3          the full trial (resumable)
  python3 experiments/trial/nudge_trial.py score                 aggregate saved JSON; no model

User-level instructions still load in every condition equally (a known, symmetric confound).
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
import trial  # noqa: E402  (parse_stream, parse_unverified, prf, SUFFIX live there)

LAB = trial.LAB
REPO = "dagger"
CONDS = ["N0", "N1", "N2", "N3", "N4", "N5"]
CALIBRATION = (
    "\n- The graph lists candidate files. It does not see annotation-driven or reflection-wired uses and it can miss "
    "some static references. Treat its list as a starting point: verify with at least one search before you answer, "
    "and name in the UNVERIFIED line anything you did not confirm.\n"
)
ONE_COMMAND = " Run one command per tool call (no cd, shell variables, pipes or loops)."
HOOK_SCRIPT = """#!/usr/bin/env bash
# Logs each hook invocation, then runs the real guard. Output of the guard is passed through unchanged.
kind="$*"
input="$(cat)"
log="$(dirname "$0")/hooks.log"
out="$(printf '%s' "$input" | {graphify} hook-guard $kind)"
printf '%s\\t%s\\t%s\\n' "$kind" "$(printf '%s' "$input" | tr -d '\\n' | cut -c1-200)" "$(printf '%s' "$out" | tr -d '\\n' | cut -c1-120)" >> "$log"
printf '%s' "$out"
"""


def make_sandbox(cond: str) -> Path:
    """New directory holding exactly what the condition gives the agent."""
    sandbox = Path(tempfile.mkdtemp(prefix=f"nudge-{cond}-"))
    graph_out = LAB / "_graphs" / REPO / "graphify-out"
    (sandbox / "graphify-out").symlink_to(graph_out)
    graphify = shutil.which("graphify") or "graphify"
    if cond == "N0":
        return sandbox
    subprocess.run(["git", "init", "-q", str(sandbox)], check=True)
    if cond == "N5":  # project-scoped strict install; HOME is redirected so the user's own ~/.claude is untouched
        home = tempfile.mkdtemp(prefix="nudge-home-")
        subprocess.run([graphify, "install", "--project", "--strict", "--platform", "claude"], cwd=sandbox,
                       env={**os.environ, "HOME": home}, capture_output=True, text=True, check=True)  # fmt: skip
        shutil.rmtree(home, ignore_errors=True)
    else:
        subprocess.run([graphify, "claude", "install"], cwd=sandbox, capture_output=True, text=True, check=True)
    claude_md, settings = sandbox / "CLAUDE.md", sandbox / ".claude" / "settings.json"
    if cond == "N1":
        shutil.rmtree(sandbox / ".claude")
    elif cond == "N2":
        claude_md.unlink()
    if cond in ("N2", "N3", "N4", "N5"):
        script = sandbox / "hook_log.sh"
        script.write_text(HOOK_SCRIPT.replace("{graphify}", graphify))
        script.chmod(0o755)
        data = json.loads(settings.read_text())
        for entry in data["hooks"]["PreToolUse"]:
            for hook in entry["hooks"]:
                kind = hook["command"].split("hook-guard ", 1)[1]  # "search", "read" or "read --strict"
                hook["command"] = f"bash {script} {kind}"
        settings.write_text(json.dumps(data, indent=2))
    if cond == "N4":
        claude_md.write_text(claude_md.read_text().rstrip("\n") + "\n" + CALIBRATION)
    return sandbox


def build_cmd(model: str, cap: float) -> list[str]:
    return [
        "claude", "-p", "--model", model, "--output-format", "stream-json", "--verbose", "--max-budget-usd", str(cap),
        "--no-session-persistence", "--permission-mode", "dontAsk", "--add-dir", str(LAB / REPO),
        "--tools", "Read,Grep,Glob,Bash", "--allowedTools", "Read", "Grep", "Glob", "Bash(graphify:*)", "Bash(ls:*)",
    ]  # fmt: skip


def prompt_for(q: dict) -> str:
    root = str(LAB / REPO)
    base = q["prompt"] + trial.SUFFIX.format(root=root) + ONE_COMMAND
    return base.replace(
        "Reply with the final list only:",
        "Reply with the final list, then one last line `UNVERIFIED: <what you could not confirm, or none>`. List format:",
    )


def run(args) -> None:
    questions = json.loads(Path(args.questions).read_text())[REPO]
    results = Path(args.results_dir)
    results.mkdir(parents=True, exist_ok=True)
    jobs = [(qi, rep, c) for qi in range(len(questions)) for rep in range(args.reps) for c in args.conds.split(",")]
    if args.pilot:
        jobs = [j for j in jobs if j[0] == 0 and j[1] == 0 and j[2] == "N3"]
    if args.offset:  # start part-way through the list so parallel workers do not begin on the same run
        jobs = jobs[args.offset :] + jobs[: args.offset]
    total = 0.0
    for qi, rep, cond in jobs:
        out = results / f"{cond}__{REPO}__q{qi}__r{rep}.json"
        if out.exists():
            continue
        prompt = prompt_for(questions[qi])
        if args.dry_run:
            print(cond, f"q{qi} r{rep}", " ".join(build_cmd(args.model, args.cap)), "<<<", prompt.replace("\n", " | ")[-110:])
            continue
        sandbox = make_sandbox(cond)
        try:
            proc = subprocess.run(
                build_cmd(args.model, args.cap), input=prompt, capture_output=True, text=True, cwd=sandbox, timeout=600
            )
            parsed = trial.parse_stream(proc.stdout) if proc.stdout else {"is_error": True, "stderr": proc.stderr[-500:]}
            log = sandbox / "hooks.log"
            parsed["hook_log"] = log.read_text().splitlines() if log.exists() else []
            parsed["condition"] = cond
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)
        out.write_text(json.dumps(parsed))
        total += float(parsed.get("total_cost_usd") or 0)
        denied = len(parsed.get("permission_denials") or [])
        fired = len(parsed["hook_log"])
        note = f"   hooks fired: {fired}" + (f"   DENIED: {denied}" if denied else "")
        print(f"{out.name}: running cost ${total:.3f}{note}")
        if cond in ("N2", "N3", "N4", "N5") and not fired and not parsed.get("is_error"):
            print("   WARNING: hooks never fired in a hook condition; this run is invalid")
        if denied and args.stop_on_denial:
            sys.exit(f"stopping: {out.name} had {denied} denied call(s); check the allow-rule, then use a fresh --results-dir")
        if total > args.total_cap:
            sys.exit(f"stopping: total cost ${total:.2f} exceeded --total-cap {args.total_cap}")


def graph_call(c: dict) -> bool:
    return c.get("tool") == "Bash" and "graphify" in c.get("arg", "")


def summarize(d: dict, ref: set) -> dict:
    text = d.get("result") or ""
    root = f"{LAB / REPO}/"
    answer = {m.strip().removeprefix(root).removeprefix("./") for m in re.findall(r"FILE:\s*`?([^\s`]+)", text)}
    p, r, f1 = trial.prf(answer, ref)
    calls = d.get("tool_calls") or []
    first_graph = next((i for i, c in enumerate(calls) if graph_call(c)), None)
    after = calls[first_graph + 1 :] if first_graph is not None else calls
    stated, says_none = trial.parse_unverified(text)
    u = d.get("usage") or {}
    return {
        "cond": d.get("condition", ""),
        "cost": d.get("total_cost_usd") or 0,
        "turns": d.get("num_turns") or 0,
        "in": sum(u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
        "p": p, "r": r, "f1": f1,  # noqa: E701
        "graph": first_graph is not None,
        "graph_first": first_graph == 0,
        "graph_calls": sum(1 for c in calls if graph_call(c)),
        "searches_after": sum(1 for c in after if c.get("tool") in ("Grep", "Glob")),
        "reads_after": sum(1 for c in after if c.get("tool") == "Read"),
        "hooks": len(d.get("hook_log") or []),
        "denied": len(d.get("permission_denials") or []),
        "err": bool(d.get("is_error")),
        "unv": stated is not None,
        "says_complete": says_none,
        "missed": r < 1.0,
        "flagged_when_missed": r < 1.0 and stated is not None and not says_none,
        "overconfident": r < 0.8 and says_none,
    }


def score(args) -> None:
    ref_by_q = {i: set(q["reference"]) for i, q in enumerate(json.loads(Path(args.questions).read_text())[REPO])}
    rows = collections.defaultdict(list)
    for f in sorted(Path(args.results_dir).glob("*.json")):
        cond, _repo, q, _rep = f.stem.split("__")
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        d.setdefault("condition", cond)
        s = summarize(d, ref_by_q[int(q[1:])])
        s["invalid"] = cond in ("N2", "N3", "N4", "N5") and s["hooks"] == 0
        rows[cond].append(s)
    head = (f"{'cond':4} {'n':>2} {'inval':>5} {'den':>3} {'graph':>5} {'first':>5} {'gcalls':>6} {'srch+':>5} {'read+':>5} "
            f"{'hooks':>5} {'flag/miss':>9} {'overconf':>8} {'cost$':>6} {'turns':>5} {'prec':>5} {'rec':>5} {'F1 med (min-max)':>18}")  # fmt: skip
    print(head)
    for cond in CONDS:
        rs = [x for x in rows.get(cond, []) if not x["invalid"]]
        if not rs:
            print(f"{cond:4} {len(rows.get(cond, [])):>2} {len(rows.get(cond, [])):>5}  (no valid runs)" if rows.get(cond) else f"{cond:4}  0")
            continue
        med = lambda k, rs=rs: statistics.median(x[k] for x in rs)  # noqa: E731
        missed = sum(x["missed"] for x in rs)
        f1s = [x["f1"] for x in rs]
        print(f"{cond:4} {len(rs):>2} {len(rows[cond]) - len(rs):>5} {sum(x['denied'] > 0 for x in rs):>3} "
              f"{sum(x['graph'] for x in rs):>5} {sum(x['graph_first'] for x in rs):>5} {med('graph_calls'):>6.0f} "
              f"{med('searches_after'):>5.0f} {med('reads_after'):>5.0f} {med('hooks'):>5.0f} "
              f"{sum(x['flagged_when_missed'] for x in rs):>4}/{missed:<4} {sum(x['overconfident'] for x in rs):>8} "
              f"{med('cost'):>6.3f} {med('turns'):>5.0f} {med('p'):>5.2f} {med('r'):>5.2f} "
              f"{statistics.median(f1s):>7.2f} ({min(f1s):.2f}-{max(f1s):.2f})")  # fmt: skip
    if args.csv:
        cols = ["cond", "cost", "turns", "in", "p", "r", "f1", "graph", "graph_first", "graph_calls", "searches_after",
                "reads_after", "hooks", "denied", "err", "unv", "says_complete", "invalid"]  # fmt: skip
        lines = [",".join(cols)]
        for cond in CONDS:
            for x in rows.get(cond, []):
                lines.append(",".join(f"{x[c]:.4g}" if isinstance(x[c], float) else str(x[c]) for c in cols))
        Path(args.csv).write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "score"):
        p = sub.add_parser(name)
        p.add_argument("--results-dir", default=str(HERE / "results-nudge"))
        p.add_argument("--questions", default=str(HERE / "questions_flow_v2.json"))
        if name == "score":
            p.add_argument("--csv", default=None, help="one row per run, no paths")
        else:
            p.add_argument("--model", default="haiku")
            p.add_argument("--cap", type=float, default=0.15, help="hard USD cap per run")
            p.add_argument("--total-cap", type=float, default=3.0, help="stop the whole trial above this USD")
            p.add_argument("--reps", type=int, default=3)
            p.add_argument("--conds", default=",".join(CONDS))
            p.add_argument("--pilot", action="store_true", help="one N3 run, to confirm the hook fires")
            p.add_argument("--offset", type=int, default=0, help="rotate the job list; start parallel workers at different offsets")
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--stop-on-denial", action="store_true")
    a = ap.parse_args()
    {"run": run, "score": score}[a.cmd](a)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONHASHSEED", "0")
    main()
