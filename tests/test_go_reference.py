import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "graph-of-graphs" / "experiments"))
import go_reference as gr  # noqa: E402


def test_imports_block_single_alias_and_blank():
    text = 'package a\n\nimport "fmt"\nimport al "x/y"\nimport (\n\t"p/q"\n\tz "r/s"\n\t_ "t/u"\n)\n'
    assert gr.imports(text) == {"fmt", "x/y", "p/q", "r/s", "t/u"}


def test_comment_and_string_not_import():
    assert gr.imports('package a\n// import "no/way"\nvar s = "p/q"\n') == set()


def _git(tmp_path, files):
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)


def test_importers_skip_tests_vendor_and_resolve_nested_module(tmp_path):
    _git(
        tmp_path,
        {
            "go.mod": "module ex.com/app\n",
            "pkg/a/a.go": "package a\n",
            "pkg/b/b.go": 'package b\nimport "ex.com/app/pkg/a"\n',
            "pkg/c/c_test.go": 'package c\nimport "ex.com/app/pkg/a"\n',
            "vendor/v/v.go": 'package v\nimport "ex.com/app/pkg/a"\n',
            "staging/lib/go.mod": "module ex.org/lib\n",
            "staging/lib/lib.go": "package lib\n",
            "pkg/d/d.go": 'package d\nimport "ex.org/lib"\n',
        },
    )
    assert gr.importers(tmp_path, "pkg/a") == {"pkg/b"}
    assert gr.importers(tmp_path, "staging/lib") == {"pkg/d"}
    assert gr.grep_noise(tmp_path, "pkg/a") == 3
