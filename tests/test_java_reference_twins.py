"""The answer key must resolve a duplicated class inside the referring file's own source tree."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "graph-of-graphs" / "experiments"))

import java_reference  # noqa: E402


def test_twin_source_trees_do_not_cross(tmp_path):
    for root in ("android/lib/src", "lib/src"):
        (tmp_path / root / "p").mkdir(parents=True)
        (tmp_path / root / "p" / "Box.java").write_text("package p; public class Box {}")
        (tmp_path / root / "p" / "User.java").write_text("package p; class User { Box b; }")
        (tmp_path / root / "q").mkdir()
        (tmp_path / root / "q" / "Other.java").write_text("package q;\nimport p.Box;\nclass Other { Box b; }\n")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)

    edges, _ = java_reference.build_edges(tmp_path)

    for root in ("android/lib/src", "lib/src"):
        assert edges[f"{root}/p/User.java"] == {f"{root}/p/Box.java"}
        assert edges[f"{root}/q/Other.java"] == {f"{root}/p/Box.java"}
