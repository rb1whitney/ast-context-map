import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "graph-of-graphs" / "experiments" / "trial"))
import crossover_trial as ct  # noqa: E402

Q = {"package": "pkg/x", "reference": ["a/b", "c/d"], "grep_files": 300}


def test_prompt_mentions_map_only_in_M():
    assert "semantic_query.py" in ct.prompt_for(Q, "M")
    for cond in ("S", "H", "H+"):
        assert "semantic_query" not in ct.prompt_for(Q, cond)


def test_summarize_scores_and_counts():
    root = f"{ct.REPO_DIR}/"
    d = {
        "condition": "H",
        "result": f"PKG: {root}a/b/\nPKG: `c/d`\nPKG: e/f",
        "tool_calls": [
            {"tool": "Grep", "arg": "x"},
            {"tool": "Bash", "arg": "python3 s/semantic_query.py --graph g find-usages go:pkg/x"},
            {"tool": "Read", "arg": "f"},
        ],
        "hook_log": ["t\tdenied(300)", "t\tmap-command"],
        "total_cost_usd": 0.02,
    }
    s = ct.summarize(d, Q)
    assert (round(s["p"], 2), s["r"]) == (0.67, 1.0)
    assert s["high"] and s["map"] and s["map_calls"] == 1 and s["searches"] == 1 and s["reads"] == 1
    assert s["denied"] == 1 and not s["invalid"]


def test_hook_condition_without_firing_is_invalid():
    d = {"condition": "H+", "result": "PKG: a/b", "tool_calls": [], "hook_log": []}
    assert ct.summarize(d, Q)["invalid"]
