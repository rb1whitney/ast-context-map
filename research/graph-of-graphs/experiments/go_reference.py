#!/usr/bin/env python3
"""Answer key for Go "which packages import P" questions, built from import lines only.

Go requires every cross-package reference to go through an explicit import, so the set of directories whose
non-test, non-vendor files import P's import path is an exact answer to "which packages directly depend on P".
This is independent of the mapper (`graph_builder.py`), so agreement between the two is a check on both.
The unit of the answer is the importing directory, which is also the graph's node.

  python3 experiments/go_reference.py --root DIR --package pkg/features [--graph graph.json]
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

SKIP = re.compile(r"(^|/)(vendor|testdata|third_party)(/|$)|_test\.go$")
BLOCK = re.compile(r"^\s*import\s*\((.*?)\)", re.M | re.S)
SINGLE = re.compile(r'^\s*import\s+(?:[\w.]+\s+)?"([^"]+)"', re.M)
LINE = re.compile(r'^\s*(?:[\w.]+\s+)?"([^"]+)"', re.M)


def imports(text: str) -> set[str]:
    found = set(SINGLE.findall(text))
    for block in BLOCK.findall(text):
        found.update(LINE.findall(block))
    return found


def module_path(root: Path) -> str:
    m = re.search(r"^module\s+(\S+)", (root / "go.mod").read_text(), re.M)
    return m.group(1) if m else ""


def nested_modules(root: Path) -> dict[str, str]:
    """Directory of each nested go.mod -> its module path (kubernetes keeps its libraries under staging/)."""
    out = {}
    for f in subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", "*/go.mod"], capture_output=True, text=True
    ).stdout.split():
        m = re.search(r"^module\s+(\S+)", (root / f).read_text(), re.M)
        if m:
            out[str(Path(f).parent)] = m.group(1)
    return out


def import_paths(root: Path, directory: str) -> set[str]:
    """Every import path a directory is known by: via the root module and via a nested module."""
    paths = {f"{module_path(root)}/{directory}"}
    for mod_dir, mod in nested_modules(root).items():
        if directory == mod_dir or directory.startswith(mod_dir + "/"):
            paths.add(mod + directory[len(mod_dir) :])
    return paths


def importers(root: Path, directory: str) -> set[str]:
    wanted = import_paths(root, directory)
    files = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", "*.go"], capture_output=True, text=True
    ).stdout.split()
    out = set()
    for f in files:
        if SKIP.search(f):
            continue
        parent = str(Path(f).parent)
        if parent == directory:
            continue
        if wanted & imports((root / f).read_text(errors="ignore")):
            out.add(parent)
    return out


def grep_noise(root: Path, directory: str) -> int:
    """Files a plain `git grep -l` on the import path returns (tests included), the cost an agent would face."""
    hits: set[str] = set()
    for p in import_paths(root, directory):
        out = subprocess.run(
            ["git", "-C", str(root), "grep", "-l", "-F", f'"{p}"', "--", "*.go"], capture_output=True, text=True
        ).stdout.split()
        hits.update(out)
    return len(hits)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--package", action="append", required=True, help="directory relative to root; repeatable")
    ap.add_argument("--graph", help="mapper graph JSON; reports agreement")
    ap.add_argument("--out", help="write a questions file")
    args = ap.parse_args()
    root = Path(args.root)
    graph = json.load(open(args.graph)) if args.graph else None
    questions = []
    for d in args.package:
        key = importers(root, d)
        row = {"package": d, "importers": len(key), "grep_files": grep_noise(root, d)}
        if graph:
            node = f"go:{d}"
            got = {e["from"][3:] for e in graph["edges"] if e["type"] == "imports" and e["to"] == node}
            row.update(graph=len(got), graph_only=len(got - key), key_only=len(key - got))
        print(json.dumps(row))
        questions.append({"package": d, "reference": sorted(key), **{k: v for k, v in row.items() if k != "package"}})
    if args.out:
        Path(args.out).write_text(json.dumps(questions, indent=1))


if __name__ == "__main__":
    main()
