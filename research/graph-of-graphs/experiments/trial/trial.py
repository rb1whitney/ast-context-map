#!/usr/bin/env python3
"""Experiment 4: a small measured agent trial (real model runs, hard dollar cap per run).

Design: 2 repos x 3 questions x 2 conditions x N repeats.
  A = Read/Grep/Glob only.   B = the same plus a prebuilt code graph queried through one allowed command.
Question: "which non-test source files use / depend on <symbol>?", scored against `git grep -w` (independent of the graph).

Commands (run from research/graph-of-graphs):
  python3 experiments/trial/trial.py prepare                     free: pick symbols, write questions.json
  python3 experiments/trial/trial.py run --pilot --dry-run       print the commands only
  python3 experiments/trial/trial.py run --pilot                 2 paid runs to price a typical run
  python3 experiments/trial/trial.py run --reps 3 --cap 0.15     the full trial (resumable; skips finished runs)
  python3 experiments/trial/trial.py score                       aggregate; reads only the saved JSON, no model

Runs happen in a throwaway working directory outside the repos so no project instructions are loaded.
User-level instructions still load for both conditions equally (a known, symmetric confound).
"""
import argparse
import collections
import json
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]  # research/graph-of-graphs (clones and graphs live here, gitignored)
TOOL = (LAB.parents[1] / "scripts/semantic_query.py").resolve()
REPOS = {"gson": ".java", "yapf": ".py", "dagger": ".java"}
AUTO = (LAB.parents[1] / "scripts/auto_context.py").resolve()
FLOW_ENTRIES = {
    "dagger": [
        "dagger-compiler/main/java/dagger/internal/codegen/bindinggraphvalidation/MissingBindingValidator.java",
        "hilt-android/main/java/dagger/hilt/android/internal/lifecycle/HiltViewModelFactory.java",
        "hilt-android/main/java/dagger/hilt/android/internal/managers/ActivityRetainedComponentManager.java",
    ]
}
TEST = re.compile(r"(^|/)(tests?|testing|testdata|test_data|benchmarks?|examples?)(/|$)|(Test|_test)\.\w+$|test_", re.I)
TEMPLATES = [
    "List the non-test source files that use `{sym}`.",
    "Which non-test source files would need review if the public API of `{sym}` changed?",
    "List the non-test source files that depend on `{sym}`, excluding the file that defines it.",
]
SUFFIX = (
    "\n\nRepository root: {root}\nReply with the final list only: one line per file, formatted `FILE: <path relative to the "
    "repository root>`. Do not modify anything."
)
TOOL_DOC = (
    "\n\nA prebuilt code graph of this repository is available. Query it with:\n  python3 {tool} --graph {graph} "
    "<find-definition|find-usages|impact> <Name>\nRun exactly one command per call (no cd, shell variables, pipes or loops: compound commands are blocked). Use it first; verify with search when unsure."
)


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", str(LAB / repo), *args], capture_output=True, text=True).stdout


def reference(repo: str, sym: str) -> list[str]:
    ext = REPOS[repo]
    files = git(repo, "grep", "-w", "-l", "--", sym, "--", f"*{ext}").split()
    return sorted(f for f in files if not TEST.search(f))


def definition_file(repo: str, sym: str, files: list[str]) -> str | None:
    pat = re.compile(rf"\b(class|interface|enum)\s+{re.escape(sym)}\b")
    for f in files:
        try:
            if pat.search((LAB / repo / f).read_text(errors="ignore")):
                return f
        except OSError:
            pass
    return None


STRONG = (
    "\n\nBefore you search or read any source file, run a graph query first. Then verify with search or by reading only "
    "the files the graph points to."
)
CLOSURE_DOC = (
    "\n\nA prebuilt code graph of this repository is available. For a question about what a class depends on, start with:\n"
    "  python3 {tool} --graph {graph} closure <ClassName> --depth 2 --limit 40\n"
    "It lists the files within two hops, nearest first, and ends with a coverage note that says what the graph cannot see "
    "and what to verify. Other queries: python3 {tool} --graph {graph} <find-definition|find-usages|impact|trace-dependencies> "
    "<Name>. Run exactly one command per call (no cd, shell variables, pipes or loops: compound commands are blocked). "
    "Use it first; verify with search when unsure."
)
FLOW_PROMPT = (
    "Starting from the class `{sym}`, list the main-source files that take part in what it does: the files of the classes it "
    "uses, and the files of the classes those use (two steps from `{sym}`). Exclude tests and the file of `{sym}` itself."
)
FLOW_DOC = (
    "\n\nA prebuilt code graph of this repository is available. Rank the files related to a task with:\n  python3 {auto} "
    "\"<describe the task, naming the class>\" --graph {graph} --top 40 --json\nOther queries: python3 {tool} --graph {graph} "
    "<find-definition|find-usages|impact|trace-dependencies> <Name>\nRun exactly one command per call (no cd, shell variables, pipes or loops: compound commands are blocked). Use it first; verify with search when unsure."
)


def flow_closure(repo: str, entry: str, depth: int = 2) -> list[str]:
    """Independent reference: identifier-reference closure over main-source classes with unique names (no graph, comments stripped)."""
    files = [f for f in git(repo, "ls-files", "--", "*.java").split() if not TEST.search(f)]
    simple = collections.defaultdict(list)
    for f in files:
        simple[f.rsplit("/", 1)[-1][:-5]].append(f)
    uniq = {k: v[0] for k, v in simple.items() if len(v) == 1 and len(k) >= 5}
    tok = re.compile(r"\b[A-Z][A-Za-z0-9]{4,}\b")
    edges = {}
    for f in files:
        text = (LAB / repo / f).read_text(errors="ignore")
        text = re.sub(r"//.*", "", re.sub(r"/\*.*?\*/", "", text, flags=re.S))
        me = f.rsplit("/", 1)[-1][:-5]
        edges[f] = {uniq[x] for x in set(tok.findall(text)) if x in uniq and x != me}
    seen, frontier = {entry}, {entry}
    for _ in range(depth):
        frontier = set().union(*(edges.get(u, set()) for u in frontier)) - seen
        seen |= frontier
    return sorted(seen - {entry})


def prepare_flow() -> None:
    out = {}
    for repo, entries in FLOW_ENTRIES.items():
        out[repo] = []
        for entry in entries:
            sym = entry.rsplit("/", 1)[-1][:-5]
            ref = flow_closure(repo, entry)
            out[repo].append({"type": "flow", "symbol": sym, "entry_file": entry, "reference": ref,
                              "prompt": FLOW_PROMPT.format(sym=sym)})
            print(repo, sym, len(ref))
    (HERE / "questions_flow.json").write_text(json.dumps(out, indent=2))


def prepare() -> None:
    sys.path.insert(0, str(LAB / "experiments"))
    import importlib.util

    spec = importlib.util.spec_from_file_location("sim", LAB / "experiments" / "simulate_cost.py")
    sim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sim)
    out = {}
    for repo in REPOS:
        graph = json.loads((LAB / "_graphs" / repo / "graphify-out" / "graph.json").read_text())
        picked = []
        for node in sim.hubs(graph, 60):
            sym = node["label"]
            ref = reference(repo, sym)
            if 5 <= len(ref) <= 25:
                picked.append({"symbol": sym, "reference": ref, "definition_file": definition_file(repo, sym, ref)})
            if len(picked) == 3:
                break
        for i, q in enumerate(picked):
            q["prompt"] = TEMPLATES[i].format(sym=q["symbol"])
            if i == 2 and q["definition_file"]:
                q["reference"] = [f for f in q["reference"] if f != q["definition_file"]]
        out[repo] = picked
        print(repo, [(q["symbol"], len(q["reference"])) for q in picked])
    (HERE / "questions.json").write_text(json.dumps(out, indent=2))


def build_cmd(cond: str, model: str, cap: float, repo: str) -> list[str]:
    cmd = ["claude", "-p", "--model", model, "--output-format", "stream-json", "--verbose", "--max-budget-usd", str(cap),
           "--no-session-persistence", "--permission-mode", "dontAsk", "--add-dir", str(LAB / repo)]
    if cond == "A":
        cmd += ["--tools", "Read,Grep,Glob", "--allowedTools", "Read", "Grep", "Glob"]
    else:
        cmd += ["--tools", "Read,Grep,Glob,Bash", "--allowedTools", "Read", "Grep", "Glob", f"Bash(python3 {TOOL}:*)",
                f"Bash(python3 {AUTO}:*)"]
    return cmd


def parse_stream(stdout: str) -> dict:
    """Final result event plus the list of tool calls made (name and a short argument) from `--output-format stream-json`."""
    final, calls = {}, []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use":
                    args = block.get("input") or {}
                    arg = args.get("command") or args.get("pattern") or args.get("file_path") or args.get("path") or ""
                    calls.append({"tool": block.get("name"), "arg": str(arg)[:300]})
        elif event.get("type") == "result":
            final = event
    final["tool_calls"] = calls
    return final


def run(args) -> None:
    questions = json.loads(Path(args.questions).read_text())
    results = Path(args.results_dir)
    results.mkdir(parents=True, exist_ok=True)
    jobs = []
    for repo, qs in questions.items():
        for qi, q in enumerate(qs):
            for rep in range(args.reps):
                for cond in args.conds.split(","):
                    jobs.append((repo, qi, q, rep, cond))
    if args.pilot:
        first = next(iter(questions))
        jobs = [j for j in jobs if j[0] == first and j[1] == 0 and j[3] == 0]
    total = 0.0
    for repo, qi, q, rep, cond in jobs:
        out = results / f"{cond}__{repo}__q{qi}__r{rep}.json"
        if out.exists():
            continue
        root = str(LAB / repo)
        prompt = q["prompt"] + SUFFIX.format(root=root)
        if cond in ("B", "C", "D"):
            graph = HERE / "graphs" / f"{repo}{args.graph_suffix}" / "relationship_graph.json"
            if cond == "D":
                prompt += CLOSURE_DOC.format(tool=TOOL, graph=graph)
            else:
                doc = FLOW_DOC.format(auto=AUTO, tool=TOOL, graph=graph) if q.get("type") == "flow" else None
                prompt += doc or TOOL_DOC.format(tool=TOOL, graph=graph)
        if cond == "C":
            prompt += STRONG
        if args.uncertainty:
            prompt = prompt.replace(
                "Reply with the final list only:",
                "Reply with the final list, then one last line `UNVERIFIED: <what you could not confirm, or none>`. List format:",
            )
        cmd = build_cmd(cond, args.model, args.cap, repo)
        if args.dry_run:
            print(" ".join(cmd), "<<<", prompt.replace("\n", " | ")[:140])
            continue
        with tempfile.TemporaryDirectory() as cwd:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd, timeout=600)
        parsed = parse_stream(proc.stdout) if proc.stdout else {"is_error": True, "stderr": proc.stderr[-500:]}
        out.write_text(json.dumps(parsed))
        denied = 0
        try:
            data = parsed
            total += float(data.get("total_cost_usd") or 0)
            denied = len(data.get("permission_denials") or [])
        except (json.JSONDecodeError, ValueError):
            pass
        print(f"{out.name}: running cost ${total:.3f}" + (f"   DENIED TOOL CALLS: {denied}" if denied else ""))
        if denied and args.stop_on_denial:
            sys.exit(f"stopping: {out.name} had {denied} denied tool call(s); fix the allow-rule, then use a fresh --results-dir")
        if total > args.total_cap:
            sys.exit(f"stopping: total cost ${total:.2f} exceeded --total-cap {args.total_cap}")


UNVERIFIED = re.compile(r"^\s*UNVERIFIED:\s*(.*)$", re.M | re.I)
NONE_WORDS = ("", "none", "nothing", "n/a", "no")


def parse_unverified(text: str):
    """The agent's own statement of what it could not confirm: (text, says_complete). (None, False) if absent."""
    found = UNVERIFIED.findall(text or "")
    if not found:
        return None, False
    stated = found[-1].strip().strip("`.").strip()
    return stated, stated.lower().split(" ")[0].strip(".,;") in NONE_WORDS


def prf(answer: set, ref: set) -> tuple[float, float, float]:
    hit = len(answer & ref)
    p, r = hit / len(answer) if answer else 0.0, hit / len(ref) if ref else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def score(args) -> None:
    questions = json.loads(Path(args.questions).read_text())
    rows = collections.defaultdict(list)
    allrows = []
    for f in sorted(Path(args.results_dir).glob("*.json")):
        cond, repo, q, _rep = f.stem.split("__")
        ref = set(questions[repo][int(q[1:])]["reference"])
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        text = d.get("result") or ""
        root = f"{LAB / repo}/"
        answer = {m.strip().removeprefix(root).removeprefix("./") for m in re.findall(r"FILE:\s*`?([^\s`]+)", text)}
        # Path-format slips (an extra leading repo-name folder) are not wrong files; same rule for both conditions.
        answer = {a if a in ref or a.removeprefix(f"{repo}/") not in ref else a.removeprefix(f"{repo}/") for a in answer}
        p, r, f1 = prf(answer, ref)
        u = d.get("usage") or {}
        tokens_in = sum(u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        allrows.append((cond, repo, q, _rep))
        rows[(cond, repo)].append({
            "cost": d.get("total_cost_usd") or 0, "turns": d.get("num_turns") or 0, "sec": (d.get("duration_ms") or 0) / 1000,
            "in": tokens_in, "out": u.get("output_tokens", 0), "p": p, "r": r, "f1": f1, "err": bool(d.get("is_error")), "den": bool(d.get("permission_denials")),
            "unv": parse_unverified(text)[0] is not None,
            "none": parse_unverified(text)[1],
            "over": parse_unverified(text)[1] and r < 0.8,
            "gq": sum(1 for c in (d.get("tool_calls") or []) if "semantic_query.py" in c.get("arg", "") or "auto_context.py" in c.get("arg", "")),
        })
    if args.csv:
        cols = ["cost", "turns", "sec", "in", "out", "p", "r", "f1", "err"]
        lines = ["condition,repo,question,rep," + ",".join(cols)]
        flat = [x for k in sorted(rows) for x in rows[k]]
        for (cond, repo, q, rep), x in zip(sorted(allrows, key=lambda t: (t[0], t[1])), flat):
            lines.append(",".join([cond, repo, q, rep.lstrip("r")] + [f"{x[c]:.4g}" if isinstance(x[c], float) else str(x[c]) for c in cols]))
        Path(args.csv).write_text("\n".join(lines) + "\n")
    print(f"{'cond':4} {'repo':6} {'n':>2} {'err':>3} {'den':>3} {'used':>4} {'unv':>3} {'none':>4} {'over':>4} {'cost$ med':>9} {'turns':>6} {'in-tok med':>11} {'out-tok':>8} {'prec':>5} {'rec':>5} {'F1 med (min-max)':>18}")
    for (cond, repo), rs in sorted(rows.items()):
        med = lambda k: statistics.median(x[k] for x in rs)
        f1s = [x["f1"] for x in rs]
        print(f"{cond:4} {repo:6} {len(rs):>2} {sum(x['err'] for x in rs):>3} {sum(x['den'] for x in rs):>3} {sum(1 for x in rs if x['gq']):>4} {sum(x['unv'] for x in rs):>3} {sum(x['none'] for x in rs):>4} {sum(x['over'] for x in rs):>4} {med('cost'):>9.3f} {med('turns'):>6.0f} {med('in'):>11.0f} "
              f"{med('out'):>8.0f} {med('p'):>5.2f} {med('r'):>5.2f} {statistics.median(f1s):>7.2f} ({min(f1s):.2f}-{max(f1s):.2f})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    sub.add_parser("prepare-flow")
    for name in ("run", "score"):
        p = sub.add_parser(name)
        p.add_argument("--results-dir", default=str(HERE / "results"))
        p.add_argument("--questions", default=str(HERE / "questions.json"))
        if name == "score":
            p.add_argument("--csv", default=None, help="also write one row per run (no paths)")
        if name == "run":
            p.add_argument("--model", default="haiku")
            p.add_argument("--cap", type=float, default=0.15, help="hard USD cap per run")
            p.add_argument("--total-cap", type=float, default=6.0, help="stop the whole trial above this USD")
            p.add_argument("--reps", type=int, default=3)
            p.add_argument("--pilot", action="store_true")
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--uncertainty", action="store_true", help="ask for a final UNVERIFIED: line; use a fresh --results-dir")
            p.add_argument("--graph-suffix", default="", help="use graphs/<repo><suffix>; write it with an equals sign when it starts with a dash, e.g. --graph-suffix=-v3")
            p.add_argument("--conds", default="A,B", help="A search only, B graph soft nudge, C graph strong nudge, D graph with closure and coverage footer")
            p.add_argument("--stop-on-denial", action="store_true", help="stop at the first run with a denied tool call")
    a = ap.parse_args()
    {"prepare": lambda: prepare(), "prepare-flow": lambda: prepare_flow(), "run": lambda: run(a), "score": lambda: score(a)}[a.cmd]()


if __name__ == "__main__":
    main()
