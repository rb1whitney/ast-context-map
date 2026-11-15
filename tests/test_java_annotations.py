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
