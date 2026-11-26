#!/usr/bin/env python3
"""Independent reference for "who uses X": class dependencies from compiled classes (jdeps), not from text search.

Reproduce the input (gson main sources; three generated or external types are stubbed in experiments/jdeps/stubs):
  mkdir out && javac -proc:none -Xlint:none -d out $(find gson/gson/src/main/java -name '*.java' ! -name module-info.java) \
      $(find experiments/jdeps/stubs -name '*.java')
  jdeps -verbose:class -filter:none out > gson-jdeps.txt

Then:
  python3 experiments/jdeps_reference.py --jdeps gson-jdeps.txt --clone gson --questions questions.json \
      --graph before=graphs/gson/relationship_graph.json --graph after=graphs/gson-v2/relationship_graph.json \
      --results trial/results

Everything is restricted to the module that was compiled (--scope), so files in other modules do not count against anyone.
"""

import argparse
import collections
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import eval_score  # noqa: E402

DEP = re.compile(r"^\s+(\S+)\s+->\s+(\S+)\s+\S+$")


def jdeps_dependents(text: str, scope: str, clone: Path) -> dict[str, set]:
    """Map each class name (outer name, no $) to the set of source files whose compiled classes depend on it."""
    deps: dict[str, set] = collections.defaultdict(set)
    for line in text.splitlines():
        m = DEP.match(line)
        if not m:
            continue
        src, dst = (c.split("$")[0] for c in m.groups())
        src_file = f"{scope}{src.replace('.', '/')}.java"
        if src != dst and (clone / src_file).exists():
            deps[dst].add(src_file)
    return deps


def graph_dependents(graph: dict, symbol: str, scope: str) -> set:
    """Files with an edge that points at the symbol (or one of its members), excluding the symbol's own file."""
    own = (graph["nodes"].get(symbol) or {}).get("file")
    out = set()
    for edge in graph["edges"]:
        target = edge["to"]
        if (target == symbol or target.startswith(symbol + ".")) and edge.get("file") != own:
            out.add(edge["file"])
    return {f for f in out if f.startswith(scope)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jdeps", required=True)
    ap.add_argument("--clone", required=True, help="clone directory of the repository")
    ap.add_argument("--questions", required=True)
    ap.add_argument("--repo", default="gson")
    ap.add_argument("--scope", default="gson/src/main/java/", help="source prefix that was compiled")
    ap.add_argument("--graph", action="append", default=[], metavar="NAME=PATH")
    ap.add_argument("--results", help="directory of saved trial runs to rescore")
    a = ap.parse_args()
    clone = Path(a.clone)
    questions = json.loads(Path(a.questions).read_text())[a.repo]
    deps = jdeps_dependents(Path(a.jdeps).read_text(), a.scope, clone)
    graphs = {n: json.loads(Path(p).read_text()) for n, p in (g.split("=", 1) for g in a.graph)}

    print(f"{'symbol':20} {'jdeps':>5} {'grep':>5} | grep P / R vs jdeps" + "".join(f" | {n} P / R" for n in graphs))
    refs = {}
    for i, q in enumerate(questions):
        fq = next((c for c in deps if c.endswith("." + q["symbol"])), None)
        truth = deps.get(fq, set()) - {f"{a.scope}{fq.replace('.', '/')}.java"} if fq else set()
        grep = {f for f in q["reference"] if f.startswith(a.scope)}
        refs[i] = (truth, grep)
        gp, gr, _ = eval_score.prf(grep, truth)
        row = f"{q['symbol']:20} {len(truth):>5} {len(grep):>5} | {gp:>6.2f} / {gr:.2f}   "
        for graph in graphs.values():
            p, r, _ = eval_score.prf(graph_dependents(graph, q["symbol"], a.scope), truth)
            row += f"| {p:>6.2f} / {r:.2f}  "
        print(row)

    if a.results:
        print(
            "\nSaved agent answers rescored (answers restricted to the compiled module so other modules do not count)"
        )
        print(f"{'cond':4} {'n':>2} {'F1 vs grep ref':>15} {'F1 vs jdeps ref':>16} {'recall vs jdeps':>16}")
        by_cond = collections.defaultdict(list)
        for f in sorted(Path(a.results).glob(f"*__{a.repo}__*.json")):
            cond, _, q, _rep = f.stem.split("__")
            truth, grep = refs[int(q[1:])]
            text = json.loads(f.read_text()).get("result") or ""
            answer = {
                x
                for x in eval_score.parse_answer(text, a.repo, str(clone.resolve()), grep | truth)
                if x.startswith(a.scope)
            }
            by_cond[cond].append((eval_score.prf(answer, grep)[2], eval_score.prf(answer, truth)))
        for cond, rows in sorted(by_cond.items()):
            print(
                f"{cond:4} {len(rows):>2} {statistics.median(r[0] for r in rows):>15.2f} "
                f"{statistics.median(r[1][2] for r in rows):>16.2f} {statistics.median(r[1][1] for r in rows):>16.2f}"
            )


if __name__ == "__main__":
    main()
