import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import graph_builder  # noqa: E402
import semantic_query  # noqa: E402

FILES = {
    "src/A.java": 'package p;\npublic class A {\n  B b;\n  Object load() throws Exception { return Class.forName("x").newInstance(); }\n}\n',
    "src/B.java": "package p;\npublic class B {\n  C c;\n  D d;\n}\n",
    "src/C.java": "package p;\npublic class C {\n  E e;\n}\n",
    "src/D.java": "package p;\n@Module\npublic class D {}\n",
    "src/E.java": "package p;\npublic class E {}\n",
    "src/F.java": "package p;\npublic class F {}\n",
}


def graph(tmp_path):
    for rel, text in FILES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return graph_builder.GraphBuilder(str(tmp_path)).build_graph()


def test_closure_follows_hops_and_leaves_out_unrelated_files(tmp_path):
    out = semantic_query.SemanticQuery.from_dict(graph(tmp_path)).closure("A", depth=2, limit=30)
    assert "src/B.java" in out and "src/C.java" in out and "src/D.java" in out
    assert "src/E.java" not in out  # three hops away
    assert "src/F.java" not in out  # unrelated
    assert out.index("hop 1") < out.index("hop 2")


def test_depth_one_stops_at_direct_dependencies(tmp_path):
    out = semantic_query.SemanticQuery.from_dict(graph(tmp_path)).closure("A", depth=1)
    assert "src/B.java" in out and "src/C.java" not in out


def test_limit_hides_files_and_says_how_to_see_them(tmp_path):
    out = semantic_query.SemanticQuery.from_dict(graph(tmp_path)).closure("A", depth=2, limit=1)
    assert "2 more files within 2 hops are not shown: rerun with --limit 3" in out


def test_footer_names_reflection_and_injection_blind_spots(tmp_path):
    query = semantic_query.SemanticQuery.from_dict(graph(tmp_path))
    footer = query.coverage_footer({"A", "D"}, "A")
    assert "reflection call sites in 1 (A)" in footer
    assert "framework-wired, bindings not followed, in 1 (D)" in footer
    assert "git grep -lw A" in footer


def test_cli_prints_the_footer_on_find_usages_and_closure(tmp_path):
    graph_file = tmp_path / "g.json"
    graph_file.write_text(json.dumps(graph(tmp_path / "repo")))
    for args in (["find-usages", "B"], ["closure", "A"]):
        run = subprocess.run(
            [sys.executable, str(SCRIPTS / "semantic_query.py"), "--graph", str(graph_file), *args],
            capture_output=True,
            text=True,
        )
        assert run.returncode == 0, run.stderr
        assert "-- coverage --" in run.stdout and "git grep -lw" in run.stdout
