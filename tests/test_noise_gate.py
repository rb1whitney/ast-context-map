import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
import noise_gate as ng  # noqa: E402


def repo(tmp_path, n):
    r = tmp_path / "r"
    r.mkdir()
    for i in range(n):
        (r / f"f{i}.go").write_text('import "a/b"\n')
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True)
    return r


def env(tmp_path, r, **kw):
    e = {"NOISE_REPO": str(r), "NOISE_STATE": str(tmp_path / "s.json"), "NOISE_MIN_HITS": "3", "NOISE_HINT": "MAP"}
    e.update(kw)
    return e


def claude(pattern):
    return {"tool_name": "Grep", "tool_input": {"pattern": pattern}}


def test_quiet_search_allowed(tmp_path):
    r = repo(tmp_path, 2)
    assert ng.decide(claude('"a/b"'), env(tmp_path, r))[0] is False


def test_noisy_search_denied_once_then_allowed(tmp_path):
    r = repo(tmp_path, 5)
    e = env(tmp_path, r)
    deny, reason, label = ng.decide(claude("a/b"), e)
    assert deny and "5 files" in reason and "MAP" in reason and label == "denied(5)"
    assert ng.decide(claude("a/b"), e)[0] is False  # limit reached


def test_map_command_clears_gate(tmp_path):
    r = repo(tmp_path, 5)
    e = env(tmp_path, r)
    assert ng.decide({"tool_name": "Bash", "tool_input": {"command": "python3 x/semantic_query.py find-usages a"}}, e)[2] == "map-command"
    assert ng.decide(claude("a/b"), e)[2] == "map-already-used"


def test_non_search_ignored(tmp_path):
    r = repo(tmp_path, 5)
    assert ng.decide({"tool_name": "Read", "tool_input": {"file_path": "x"}}, env(tmp_path, r))[2] == "not-a-search"
    assert ng.decide({"tool_name": "Bash", "tool_input": {"command": "ls dir"}}, env(tmp_path, r))[2] == "not-a-search"


def test_pattern_parsing_for_shell_searches():
    assert ng.pattern_of("Bash", {"command": 'git grep -l "k8s.io/x" -- "*.go"'}) == "k8s.io/x"
    assert ng.pattern_of("run_command", {"CommandLine": 'rg -l "k8s.io/x" /repo'}) == "k8s.io/x"
    assert ng.pattern_of("Bash", {"command": "grep -rn -e foo -e bar ."}) == "bar"
    assert ng.pattern_of("Bash", {"command": "ls"}) is None


def test_agy_payload_shape(tmp_path):
    r = repo(tmp_path, 5)
    p = {"toolCall": {"name": "run_command", "args": {"CommandLine": 'rg -l "a/b" .'}}, "workspacePaths": [str(r)]}
    assert ng.decide(p, env(tmp_path, r))[0] is True
