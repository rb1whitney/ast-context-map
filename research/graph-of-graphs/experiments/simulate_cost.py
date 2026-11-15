#!/usr/bin/env python3
"""Experiment 3: simulate the context cost of two agents on the same questions. No model is used.

Question set: for each repo, the top-N hub symbols from its Graphify graph, asked as
"what depends on <symbol> and where is it defined?" (the obvious keyword is the symbol name).

Baseline agent  : `git grep -w <symbol>`, then reads the top-K matching files.
                  upper bound = whole files; lower bound = windows around the first matches.
Graph agent     : asks the graph for the symbol's neighbours (capped at a node budget), then reads a window
                  around the definition.
Cost            : characters / CHARS_PER_TOKEN (default 4, an approximation; use --chars-per-token to vary).
Reference set   : files that contain the symbol as a whole word (independent of the graph).
                  coverage  = share of reference files the graph answer names
                  precision = share of graph-named files that are in the reference set
Read-only: only git grep and file reads. Usage: python3 experiments/simulate_cost.py gson yapf brotli zx
"""
import argparse
import collections
import json
import re
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRUCT = {"calls", "references", "inherits", "imports", "method"}
WINDOW = 30


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT / repo), *args], capture_output=True, text=True).stdout


def line_no(loc) -> int:
    m = re.search(r"(\d+)", str(loc or ""))
    return int(m.group(1)) if m else 1


def window(repo: str, rel: str, center: int) -> str:
    try:
        lines = (ROOT / repo / rel).read_text(errors="ignore").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[max(0, center - WINDOW) : center + WINDOW])


def hubs(graph: dict, n: int) -> list[dict]:
    indeg = collections.Counter(l["target"] for l in graph["links"] if l.get("relation") in STRUCT)
    out = []
    for node in graph["nodes"]:
        sf, label = node.get("source_file") or "", node.get("label") or ""
        if node.get("file_type") != "code" or not node.get("_callable_class"):
            continue
        if re.search(r"(test|bench|example)", sf, re.I) or not re.fullmatch(r"[A-Za-z_]\w{3,}", label):
            continue
        out.append((indeg[node["id"]], node))
    out.sort(key=lambda t: -t[0])
    seen, picked = set(), []
    for _, node in out:
        if node["label"] not in seen:
            seen.add(node["label"])
            picked.append(node)
        if len(picked) == n:
            break
    return picked


def simulate(repo: str, n_symbols: int, k_files: int, budget: int, cpt: float) -> list[dict]:
    graph = json.loads((ROOT / "_graphs" / repo / "graphify-out" / "graph.json").read_text())
    by_id = {n["id"]: n for n in graph["nodes"]}
    inbound = collections.defaultdict(list)
    for l in graph["links"]:
        if l.get("relation") in STRUCT:
            inbound[l["target"]].append(l)
    rows = []
    for node in hubs(graph, n_symbols):
        sym = node["label"]
        counts = collections.Counter()
        for line in git(repo, "grep", "-w", "-c", "--", sym).splitlines():
            f, _, c = line.rpartition(":")
            if c.isdigit():
                counts[f] = int(c)
        if not counts:
            continue
        ranked = [f for f, _ in counts.most_common()]
        grep_out = "\n".join(git(repo, "grep", "-n", "-w", "--", sym).splitlines()[:50])
        upper = len(grep_out) + sum(len((ROOT / repo / f).read_text(errors="ignore")) for f in ranked[:k_files] if (ROOT / repo / f).exists())
        lower = len(grep_out)
        for f in ranked[:3]:
            hits = [int(x.split(":")[1]) for x in git(repo, "grep", "-n", "-w", "--", sym, "--", f).splitlines()[:3]]
            lower += sum(len(window(repo, f, h)) for h in hits[:1])
        dep_links = sorted(inbound[node["id"]], key=lambda l: -float(l.get("weight") or 1))[:budget]
        lines, dep_files = [], set()
        for l in dep_links:
            src = by_id.get(l["source"], {})
            sf = src.get("source_file") or ""
            dep_files.add(sf)
            lines.append(f"{src.get('label')} {l.get('relation')} {sf}:{line_no(l.get('source_location'))}")
        answer = f"{sym} defined at {node.get('source_file')}:{line_no(node.get('source_location'))}\n" + "\n".join(lines)
        graph_cost = len(answer) + len(window(repo, node.get("source_file") or "", line_no(node.get("source_location"))))
        ref = set(ranked)
        rows.append({
            "symbol": sym, "ref_files": len(ref),
            "baseline_upper": upper / cpt, "baseline_lower": lower / cpt, "graph": graph_cost / cpt,
            "coverage": len(dep_files & ref) / max(1, len(ref - {node.get("source_file")})),
            "precision": len(dep_files & ref) / max(1, len(dep_files)),
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repos", nargs="+")
    ap.add_argument("--symbols", type=int, default=10)
    ap.add_argument("--k-files", type=int, default=5)
    ap.add_argument("--budget", type=int, default=15)
    ap.add_argument("--chars-per-token", type=float, default=4.0)
    a = ap.parse_args()
    print(f"{'repo':12} {'n':>3} {'base-upper':>11} {'base-lower':>11} {'graph':>8} {'vs upper':>9} {'vs lower':>9} {'cover':>6} {'prec':>5}   (median tokens per question)")
    for repo in a.repos:
        rows = simulate(repo, a.symbols, a.k_files, a.budget, a.chars_per_token)
        if not rows:
            print(f"{repo:12} no usable questions")
            continue
        med = lambda k: statistics.median(r[k] for r in rows)
        print(f"{repo:12} {len(rows):>3} {med('baseline_upper'):>11.0f} {med('baseline_lower'):>11.0f} {med('graph'):>8.0f} "
              f"{med('baseline_upper') / med('graph'):>8.1f}x {med('baseline_lower') / med('graph'):>8.1f}x {med('coverage'):>6.2f} {med('precision'):>5.2f}")


if __name__ == "__main__":
    main()
