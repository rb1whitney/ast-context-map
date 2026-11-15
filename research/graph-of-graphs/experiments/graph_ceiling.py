#!/usr/bin/env python3
"""The recall ceiling of a mapper graph on flow questions: what a perfect agent could find from the graph alone.

For each question's entry file, follow file-level dependencies (an edge's source file to the file of its target class)
for 1 to 3 hops and compare with the reference set. Also reports how much of the reference is in the graph at all, and
a variant that drops annotation files whose retention is SOURCE (class-file tools such as jdeps cannot see those).

  python3 experiments/graph_ceiling.py --graph G.json --questions questions_flow.json --clones DIR --repo dagger
"""

import argparse
import json
import re
from pathlib import Path

RETENTION = re.compile(r"@Retention\s*\(\s*(?:RetentionPolicy\s*\.\s*)?(SOURCE|CLASS|RUNTIME)\s*\)")


def annotation_retention(path: Path) -> str | None:
    """RUNTIME/CLASS/SOURCE for an annotation type file; CLASS is the Java default; None if not an annotation type."""
    text = path.read_text(errors="ignore")
    if "@interface" not in text:
        return None
    match = RETENTION.search(text)
    return match.group(1) if match else "CLASS"


def file_graph(graph: dict) -> tuple[dict, set]:
    class_file = {k: v["file"] for k, v in graph["nodes"].items() if str(v.get("file", "")).endswith(".java")}

    def file_of(name: str):
        parts = name.split(".")
        for i in range(len(parts), 0, -1):
            candidate = ".".join(parts[:i])
            if candidate in class_file:
                return class_file[candidate]
        return None

    out: dict[str, set] = {}
    for edge in graph["edges"]:
        src, dst = edge.get("file"), file_of(edge["to"])
        if src and dst and src != dst:
            out.setdefault(src, set()).add(dst)
    return out, {v.get("file") for v in graph["nodes"].values() if v.get("file")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--clones", required=True)
    ap.add_argument("--repo", required=True)
    a = ap.parse_args()
    graph = json.loads(Path(a.graph).read_text())
    questions = json.loads(Path(a.questions).read_text())[a.repo]
    out, in_graph = file_graph(graph)
    root = Path(a.clones) / a.repo
    print(
        f"{'entry':34} {'ref':>3} {'in graph':>8} {'ceil d1':>7} {'d2':>5} {'d3':>5} | visible ref {'in graph':>8} {'d2':>5}"
    )
    for q in questions:
        ref, entry = set(q["reference"]), q["entry_file"]
        seen, frontier, reach = {entry}, {entry}, {}
        for depth in (1, 2, 3):
            frontier = set().union(*(out.get(u, set()) for u in frontier)) - seen
            seen |= frontier
            reach[depth] = set(seen) - {entry}
        visible = {f for f in ref if annotation_retention(root / f) != "SOURCE"}

        def ceiling(depth: int, target: set) -> float:
            return len(reach[depth] & target) / len(target) if target else 0.0

        cov = sum(1 for f in ref if f in in_graph) / len(ref)
        vcov = sum(1 for f in visible if f in in_graph) / len(visible) if visible else 0.0
        print(
            f"{q['symbol']:34} {len(ref):>3} {cov:>8.2f} {ceiling(1, ref):>7.2f} {ceiling(2, ref):>5.2f} {ceiling(3, ref):>5.2f}"
            f" | {len(visible):>11} {vcov:>8.2f} {ceiling(2, visible):>5.2f}"
        )


if __name__ == "__main__":
    main()
