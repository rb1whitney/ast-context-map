#!/usr/bin/env python3
"""Experiment 1: what does `graphify merge-graphs` actually give you?

Merges per-repo Graphify graphs into <out-dir>/merged.json (never uses the global graph),
then reports size, cross-repo connectivity, the nodes that bridge repos, and hierarchy sizes.

Usage:
  python3 experiments/merge_stats.py --out-dir <new-empty-dir> [--repos gson yapf ...]
"""
import argparse
import collections
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_REPOS = ["gson", "yapf", "brotli", "zx", "ax", "magika", "langextract", "libphonenumber", "googletest"]
STDLIB = re.compile(r"^(java|javax|jdk|sun|android)_")
TEST = re.compile(r"^(org_junit|junit|org_hamcrest|org_mockito|com_google_truth|gtest|testing)")
THIRD = re.compile(r"^(com_google_common_|com_google_protobuf|com_google_errorprone|org_checkerframework)")


PY_STD = set(sys.stdlib_module_names)
C_STD = {"stdint", "stdio", "stdlib", "string", "errno", "assert", "limits", "math", "stddef", "stdbool", "stdarg", "time", "ctype", "signal"}
JAVA_STD = {"ioexception", "arraylist", "list", "map", "set", "hashmap", "hashset", "string", "object", "exception", "runtimeexception", "collection", "collections", "iterator", "optional", "supplier", "biconsumer", "function", "stringbuilder", "integer", "long", "boolean", "override", "deprecated", "nullable", "inputstream", "outputstream", "reader", "writer", "file", "path", "paths", "files", "instant", "duration", "atomicinteger", "pattern", "matcher"}


def category(node_id: str) -> str:
    if node_id in PY_STD or node_id in C_STD or node_id in JAVA_STD or STDLIB.match(node_id):
        return "stdlib-or-generic"
    if TEST.match(node_id):
        return "test-framework"
    if THIRD.match(node_id):
        return "third-party"
    return "other"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graphs-dir", default=str(Path(__file__).resolve().parents[1] / "_graphs"))
    ap.add_argument("--repos", nargs="+", default=DEFAULT_REPOS)
    ap.add_argument("--out-dir", required=True, help="must not exist or be empty")
    args = ap.parse_args()

    out = Path(args.out_dir)
    if out.exists() and any(out.iterdir()):
        sys.exit(f"refusing to use non-empty out-dir: {out}")
    out.mkdir(parents=True, exist_ok=True)
    graphify = shutil.which("graphify") or sys.exit("graphify CLI not found")

    paths = [Path(args.graphs_dir) / r / "graphify-out" / "graph.json" for r in args.repos]
    per_repo = {r: json.loads(p.read_text()) for r, p in zip(args.repos, paths)}
    in_nodes = sum(len(g["nodes"]) for g in per_repo.values())
    in_edges = sum(len(g["links"]) for g in per_repo.values())

    merged_path = out / "merged.json"
    t0 = time.time()
    subprocess.run([graphify, "merge-graphs", *map(str, paths), "--out", str(merged_path)], check=True, capture_output=True)
    wall = time.time() - t0
    merged = json.loads(merged_path.read_text())

    repo_of = {n["id"]: n.get("repo") for n in merged["nodes"]}
    same = cross = touching = 0
    neighbors = collections.defaultdict(set)
    for link in merged["links"]:
        a, b = repo_of.get(link["source"]), repo_of.get(link["target"])
        if a and b:
            if a == b:
                same += 1
            else:
                cross += 1
        else:
            touching += 1
        for x, y in ((link["source"], link["target"]), (link["target"], link["source"])):
            if not repo_of.get(x) and repo_of.get(y):
                neighbors[x].add(repo_of[y])
    bridges = {n: rs for n, rs in neighbors.items() if len(rs) > 1}
    pairs = collections.Counter()
    for rs in neighbors.values():
        rs = sorted(rs)
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                pairs[(rs[i], rs[j])] += 1
    cats = collections.Counter(category(n) for n in bridges)

    communities = collections.defaultdict(lambda: collections.defaultdict(list))
    for r, g in per_repo.items():
        for n in g["nodes"]:
            communities[r][n.get("community")].append(n["label"])
    level0 = [{"repo": r, "nodes": sum(len(v) for v in c.values()), "communities": len(c)} for r, c in communities.items()]
    level1 = [{"repo": r, "community": c, "size": len(ls), "sample": ls[:3]} for r, cs in communities.items() for c, ls in cs.items()]
    n_possible = len(args.repos) * (len(args.repos) - 1) // 2

    report = {
        "repos": args.repos,
        "inputs": {"nodes": in_nodes, "edges": in_edges},
        "merged": {"nodes": len(merged["nodes"]), "edges": len(merged["links"]), "bytes": merged_path.stat().st_size, "wall_s": round(wall, 2)},
        "nodes_without_repo": sum(1 for v in repo_of.values() if not v),
        "edges": {"same_repo": same, "direct_cross_repo": cross, "touching_shared_node": touching},
        "bridge_nodes_touching_2plus_repos": len(bridges),
        "bridge_categories": dict(cats),
        "repo_pairs_linked": f"{len(pairs)} of {n_possible}",
        "top_pairs": [[list(p), c] for p, c in pairs.most_common(5)],
        "hierarchy_bytes": {
            "level0_repos": len(json.dumps(level0)),
            "level1_communities": len(json.dumps(level1)),
            "union": merged_path.stat().st_size,
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
