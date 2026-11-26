#!/usr/bin/env python3
"""Held-out check of the mapper's recall ceiling: entry classes drawn at random, not chosen or tuned on.

The mapper fixes of Findings 11 to 14 were found on three dagger entry classes, so the 0.84 ceiling is a development-set number. This
draws other entry classes uniformly at random (fixed seed, no use of graph connectivity), keeps those whose two-hop reference closure has at
least --min-ref files so there is something to find, and reports the graph's two-hop ceiling against the name-resolving key (java_reference).
No model is involved. Use `--exclude` for entry files that were used in development.

  python3 experiments/heldout_ceiling.py --root DIR --graph G.json [--n 12] [--seed 20] [--min-ref 8] [--exclude FILE ...]
"""

import argparse
import json
import random
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import graph_ceiling as gc  # noqa: E402
import java_reference as jr  # noqa: E402


def ceilings(root: Path, graph_path: Path, n: int, seed: int, min_ref: int, exclude: set[str]) -> list[dict]:
    edges, _ = jr.build_edges(root)
    graph = json.loads(graph_path.read_text())
    out, in_graph = gc.file_graph(graph)
    pool = sorted(f for f in edges if f not in exclude and not re.search(r"(^|/)(package-info|module-info)\.java$", f))
    random.Random(seed).shuffle(pool)
    rows = []
    for entry in pool:
        ref = jr.closure(edges, entry)
        if len(ref) < min_ref:
            continue
        seen, frontier = {entry}, {entry}
        for _ in range(2):
            frontier = set().union(*(out.get(u, set()) for u in frontier)) - seen
            seen |= frontier
        reach = seen - {entry}
        rows.append({"entry": entry, "ref": len(ref), "in_graph": len(ref & in_graph), "hit": len(ref & reach)})
        if len(rows) == n:
            break
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=20)
    ap.add_argument("--min-ref", type=int, default=8)
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--out", help="write the rows as JSON (no absolute paths)")
    a = ap.parse_args()
    rows = ceilings(Path(a.root), Path(a.graph), a.n, a.seed, a.min_ref, set(a.exclude))
    print(f"{'entry':58} {'ref':>4} {'in graph':>8} {'ceiling d2':>10}")
    for r in rows:
        print(f"{r['entry'][-58:]:58} {r['ref']:>4} {r['in_graph'] / r['ref']:>8.2f} {r['hit'] / r['ref']:>10.2f}")
    per = [r["hit"] / r["ref"] for r in rows]
    print(f"entries {len(rows)}  median ceiling {statistics.median(per):.2f}  min {min(per):.2f}  max {max(per):.2f}  "
          f"pooled {sum(r['hit'] for r in rows)}/{sum(r['ref'] for r in rows)} = {sum(r['hit'] for r in rows) / sum(r['ref'] for r in rows):.2f}")  # fmt: skip
    if a.out:
        Path(a.out).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
