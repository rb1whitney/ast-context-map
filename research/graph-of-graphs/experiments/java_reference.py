#!/usr/bin/env python3
"""A text-based Java dependency reference that resolves names the way javac does (no compiler needed).

A token such as `Binding` is resolved, in order, through the file's single-type imports, its own package, and its
wildcard imports; a static import `a.b.C.m` counts as a reference to C when `m` appears in the code. Comments, string
literals and import lines are ignored, so a name that appears only there is not a dependency. Two classes with the
same simple name in different packages stay separate, which the earlier unique-name reference could not do.

  python3 experiments/java_reference.py --clones DIR --repo dagger --questions questions_flow.json \
      --out questions_flow_v2.json [--graph NAME=relationship_graph.json ...] [--results DIR]
"""

import argparse
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import eval_score  # noqa: E402

TEST = re.compile(r"(^|/)(test|tests|javatests|examples?|benchmarks?|third_party)(/|$)|Test\.java$", re.I)
IMPORT = re.compile(r"^\s*import\s+(static\s+)?([\w.]+?)(\.\*)?\s*;", re.M)
PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
TOKEN = re.compile(r"\b[A-Z][A-Za-z0-9_]*\b")
IDENT = re.compile(r"\b[A-Za-z_]\w*\b")


def strip(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    text = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', text)
    return re.sub(r"'(?:\\.|[^'\\\n])'", "''", text)


def build_edges(root: Path) -> tuple[dict, dict]:
    files = [
        f
        for f in subprocess.run(
            ["git", "-C", str(root), "ls-files", "--", "*.java"], capture_output=True, text=True
        ).stdout.split()
        if not TEST.search(f) and not f.endswith("package-info.java") and not f.endswith("module-info.java")
    ]
    by_pkg: dict[str, dict[str, list]] = collections.defaultdict(lambda: collections.defaultdict(list))
    by_fqn: dict[str, list] = collections.defaultdict(list)
    meta = {}
    for f in files:
        text = (root / f).read_text(errors="ignore")
        pkg = (PACKAGE.search(text) or [None, ""])[1]
        stem = f.rsplit("/", 1)[-1][:-5]
        by_pkg[pkg][stem].append(f)
        by_fqn[f"{pkg}.{stem}" if pkg else stem].append(f)
        meta[f] = (pkg, stem, text)

    def nearest(cands, referrer: str):
        """Several trees can declare one class (guava and android/guava): take the one sharing the most leading path."""
        if not cands:
            return None
        mine = referrer.split("/")

        def shared(f: str) -> int:
            n = 0
            for a, b in zip(mine, f.split("/")):
                if a != b:
                    break
                n += 1
            return n

        return max(cands, key=shared)  # ties keep the first listed, as before

    def class_file(fqn: str, referrer: str):
        parts = fqn.split(".")
        for i in range(len(parts), 0, -1):  # a.b.Outer.Inner -> a.b.Outer
            hit = nearest(by_fqn.get(".".join(parts[:i])), referrer)
            if hit:
                return hit
        return None

    edges: dict[str, set] = {}
    for f, (pkg, stem, text) in meta.items():
        singles, wild, statics = {}, [], []
        for static, name, star in IMPORT.findall(text):
            if static:
                if not star:
                    statics.append(name.rsplit(".", 1))
            elif star:
                wild.append(name)
            else:
                singles[name.rsplit(".", 1)[-1]] = name
        code = IMPORT.sub(" ", PACKAGE.sub(" ", strip(text)))
        out = set()
        for tok in set(TOKEN.findall(code)) - {stem}:
            hit = class_file(singles[tok], f) if tok in singles else nearest(by_pkg[pkg].get(tok), f)
            if hit is None:
                hit = next((nearest(by_pkg[w][tok], f) for w in wild if tok in by_pkg.get(w, {})), None)
            if hit:
                out.add(hit)
        idents = set(IDENT.findall(code))
        for cls_path, member in statics:
            if member in idents:
                hit = class_file(cls_path, f)
                if hit:
                    out.add(hit)
        edges[f] = out - {f}
    return edges, by_fqn


def closure(edges: dict, entry: str, depth: int = 2) -> set:
    seen, frontier = {entry}, {entry}
    for _ in range(depth):
        frontier = set().union(*(edges.get(u, set()) for u in frontier)) - seen
        seen |= frontier
    return seen - {entry}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clones", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--graph", action="append", default=[], metavar="NAME=PATH")
    ap.add_argument("--results")
    a = ap.parse_args()
    root = Path(a.clones) / a.repo
    questions = json.loads(Path(a.questions).read_text())
    edges, _ = build_edges(root)
    new = {a.repo: []}
    print(f"{'entry':34} {'old ref':>7} {'new ref':>7} {'in both':>7} {'only old':>8} {'only new':>8}")
    for q in questions[a.repo]:
        old, ref = set(q["reference"]), closure(edges, q["entry_file"])
        new[a.repo].append({**q, "reference_v1": q["reference"], "reference": sorted(ref)})
        print(
            f"{q['symbol']:34} {len(old):>7} {len(ref):>7} {len(old & ref):>7} {len(old - ref):>8} {len(ref - old):>8}"
        )
        print("   only new, e.g.:", [f.rsplit("/", 1)[-1] for f in sorted(ref - old)[:6]])
        print("   only old, e.g.:", [f.rsplit("/", 1)[-1] for f in sorted(old - ref)[:6]])
    Path(a.out).write_text(json.dumps(new, indent=1))

    if a.graph:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import graph_ceiling

        print("\nTwo-hop recall ceiling against the new reference")
        for spec in a.graph:
            name, path = spec.split("=", 1)
            out, in_graph = graph_ceiling.file_graph(json.loads(Path(path).read_text()))
            cells = []
            for q in new[a.repo]:
                ref = set(q["reference"])
                cells.append(f"{len(closure(out, q['entry_file']) & ref)}/{len(ref)}")
            print(f"  {name:14}", "  ".join(cells))
    if a.results:
        print("\nSaved agent answers against the new reference (median per condition)")
        runs, grouped = eval_score.batch(new, Path(a.results), lambda r: str((Path(a.clones) / r).resolve()))
        eval_score.print_table(grouped)


if __name__ == "__main__":
    main()
