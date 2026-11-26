import json
import subprocess
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / "hooks/agy/graph_gate.py"


def call(tmp_path, tool, args, with_graph=True, **env):
    graph = tmp_path / "graphify-out" / "graph.json"
    graph.parent.mkdir(exist_ok=True)
    if with_graph:
        graph.write_text("{}")
    full_env = {
        "GRAPH_GATE_FILE": str(graph),
        "GRAPH_GATE_STATE": str(tmp_path / "state.json"),
        "GRAPH_GATE_LOG": str(tmp_path / "gate.log"),
        "PATH": "/usr/bin:/bin",
        **env,
    }
    done = subprocess.run(
        [sys.executable, str(GATE)],
        input=json.dumps({"toolCall": {"name": tool, "args": args}}),
        capture_output=True,
        text=True,
        env=full_env,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_first_search_is_denied_then_allowed_after_graph_command(tmp_path):
    first = call(tmp_path, "grep_search", {"Query": "Foo"})
    assert first["decision"] == "deny" and "graphify query" in first["reason"]
    assert call(tmp_path, "run_command", {"CommandLine": 'graphify query "Foo"'})["decision"] == "allow"
    assert call(tmp_path, "grep_search", {"Query": "Foo"})["decision"] == "allow"


def test_deny_limit_prevents_a_deadlock_when_the_graph_command_never_runs(tmp_path):
    assert call(tmp_path, "run_command", {"CommandLine": "rg Foo ."})["decision"] == "deny"
    assert call(tmp_path, "run_command", {"CommandLine": "rg Foo ."})["decision"] == "allow"


def test_no_graph_file_means_no_gate(tmp_path):
    assert call(tmp_path, "grep_search", {"Query": "Foo"}, with_graph=False)["decision"] == "allow"


def test_non_search_tools_and_commands_are_allowed(tmp_path):
    assert call(tmp_path, "view_file", {"AbsolutePath": "/x"})["decision"] == "allow"
    assert call(tmp_path, "run_command", {"CommandLine": "ls -la"})["decision"] == "allow"
    assert call(tmp_path, "run_command", {"CommandLine": "date"})["decision"] == "allow"


def test_custom_hint_note_and_graph_regex(tmp_path):
    out = call(
        tmp_path,
        "run_command",
        {"CommandLine": "git grep -w Foo"},
        GRAPH_GATE_HINT="python3 semantic_query.py closure <Class>",
        GRAPH_GATE_NOTE="Verify before answering.",
    )
    assert (
        out["decision"] == "deny"
        and "closure <Class>" in out["reason"]
        and out["reason"].endswith("Verify before answering.")
    )
    ok = call(tmp_path, "run_command", {"CommandLine": "python3 scripts/semantic_query.py closure Foo"})
    assert ok["decision"] == "allow"
    assert call(tmp_path, "grep_search", {"Query": "Foo"})["decision"] == "allow"


def test_unreadable_payload_is_allowed(tmp_path):
    done = subprocess.run([sys.executable, str(GATE)], input="not json", capture_output=True, text=True)
    assert json.loads(done.stdout) == {"decision": "allow"}


def test_decisions_are_logged(tmp_path):
    call(tmp_path, "grep_search", {"Query": "Foo"})
    assert "denied" in (tmp_path / "gate.log").read_text()


def test_relative_graph_path_resolves_against_payload_workspace(tmp_path):
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}")
    done = subprocess.run(
        [sys.executable, str(GATE)],
        input=json.dumps({"workspacePaths": [str(tmp_path)], "toolCall": {"name": "grep_search", "args": {}}}),
        capture_output=True,
        text=True,
        cwd="/",
        env={"PATH": "/usr/bin:/bin"},
    )
    assert json.loads(done.stdout)["decision"] == "deny"
    assert (tmp_path / ".graph_gate_state").exists()
