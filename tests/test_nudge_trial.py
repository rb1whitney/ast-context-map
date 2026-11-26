import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/graph-of-graphs/experiments/trial"))

import nudge_trial as nt  # noqa: E402

REF = {"a/A.java", "b/B.java", "c/C.java", "d/D.java", "e/E.java"}


def run(result, calls, hooks=(), denied=0):
    return {
        "condition": "N3",
        "result": result,
        "tool_calls": calls,
        "hook_log": list(hooks),
        "permission_denials": [{}] * denied,
        "total_cost_usd": 0.01,
        "num_turns": 3,
    }


def test_graph_first_then_search_counts_calls_after_the_graph():
    calls = [
        {"tool": "Bash", "arg": 'graphify query "X"'},
        {"tool": "Grep", "arg": "X"},
        {"tool": "Read", "arg": "a/A.java"},
    ]
    s = nt.summarize(run("FILE: a/A.java\nUNVERIFIED: none", calls, hooks=["h"]), REF)
    assert (s["graph"], s["graph_first"], s["graph_calls"]) == (True, True, 1)
    assert (s["searches_after"], s["reads_after"], s["hooks"]) == (1, 1, 1)


def test_no_graph_call_means_all_calls_count_as_after():
    s = nt.summarize(run("FILE: a/A.java\nUNVERIFIED: none", [{"tool": "Grep", "arg": "X"}]), REF)
    assert (s["graph"], s["graph_first"], s["searches_after"]) == (False, False, 1)


def test_overconfident_is_a_low_recall_answer_that_says_complete():
    s = nt.summarize(run("FILE: a/A.java\nUNVERIFIED: none", []), REF)
    assert s["r"] == 0.2 and s["overconfident"] and s["missed"]
    assert not s["flagged_when_missed"]


def test_flagging_uncertainty_when_missing_files_is_not_overconfident():
    s = nt.summarize(run("FILE: a/A.java\nUNVERIFIED: did not check reflection uses", []), REF)
    assert s["flagged_when_missed"] and not s["overconfident"]


def test_full_recall_is_never_overconfident():
    text = "\n".join(f"FILE: {p}" for p in sorted(REF)) + "\nUNVERIFIED: none"
    s = nt.summarize(run(text, []), REF)
    assert s["f1"] == 1.0 and not s["missed"] and not s["overconfident"]
