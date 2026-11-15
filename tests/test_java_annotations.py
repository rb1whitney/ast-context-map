import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import graph_builder  # noqa: E402


def build(tmp_path, files):
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return graph_builder.GraphBuilder(str(tmp_path)).build_graph()


def test_annotation_types_become_nodes_and_uses_become_edges(tmp_path):
    graph = build(
        tmp_path,
        {
            "src/Mark.java": "package p;\npublic @interface Mark {}\n",
            "src/A.java": "package p;\n@Mark\npublic class A {\n  @Mark void run() {}\n}\n",
        },
    )
    assert graph["nodes"]["Mark"]["file"].endswith("Mark.java")
    edges = {(e["from"], e["to"], e["type"]) for e in graph["edges"]}
    assert ("A", "Mark", "annotated-by") in edges
    assert ("A.run", "Mark", "annotated-by") in edges
    assert graph["stats"]["java_annotation_types"] == 1


def test_jdk_annotations_add_no_edges(tmp_path):
    graph = build(
        tmp_path,
        {"src/B.java": 'package p;\npublic class B {\n  @Override public String toString() { return ""; }\n}\n'},
    )
    assert not [e for e in graph["edges"] if e["type"] == "annotated-by"]


def test_gap_counters_report_dynamic_call_sites(tmp_path):
    source = (
        'package p;\npublic class C {\n  Object f() throws Exception { return Class.forName("x").newInstance(); }\n}\n'
    )
    graph = build(tmp_path, {"src/C.java": source})
    assert graph["stats"]["java_dynamic_call_sites"] == 2
    assert graph["stats"]["java_files_with_dynamic_sites"] == 1


UTIL = (
    "package p;\npublic final class Util {\n"
    "  public static int twice(int x) { return x * 2; }\n"
    "  public static int thrice(int x) { return x * 3; }\n}\n"
)


def test_static_imported_call_creates_an_edge(tmp_path):
    user = "package q;\nimport static p.Util.twice;\npublic class User {\n  int run() { return twice(3); }\n}\n"
    graph = build(tmp_path, {"src/Util.java": UTIL, "src/User.java": user})
    edges = {(e["from"], e["to"], e["type"]) for e in graph["edges"]}
    assert ("User.run", "Util.twice", "calls") in edges
    assert graph["stats"]["java_static_import_calls"] == 1


def test_wildcard_static_import_resolves_only_existing_methods(tmp_path):
    user = (
        "package q;\nimport static p.Util.*;\npublic class User {\n  int run() { return thrice(3) + missing(1); }\n}\n"
    )
    graph = build(tmp_path, {"src/Util.java": UTIL, "src/User.java": user})
    edges = {(e["from"], e["to"], e["type"]) for e in graph["edges"]}
    assert ("User.run", "Util.thrice", "calls") in edges
    assert not [e for e in graph["edges"] if e["to"].endswith(".missing")]


def test_local_method_shadows_a_static_import(tmp_path):
    user = (
        "package q;\nimport static p.Util.twice;\npublic class User {\n"
        "  int twice(int x) { return x; }\n  int run() { return twice(3); }\n}\n"
    )
    graph = build(tmp_path, {"src/Util.java": UTIL, "src/User.java": user})
    edges = {(e["from"], e["to"], e["type"]) for e in graph["edges"]}
    assert ("User.run", "User.twice", "calls") in edges
    assert ("User.run", "Util.twice", "calls") not in edges
