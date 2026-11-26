import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/graph-of-graphs/experiments/trial"))

import agy_nudge_trial as at  # noqa: E402
import nudge_trial as nt  # noqa: E402


def stream(events):
    return "\n".join(json.dumps(e) for e in events)


def tool(idx, name, **params):
    return {"event": "step_update", "step_update": {"step_index": idx, "state": "DONE", "step_type": "tool",
                                                    "tool_name": name, "tool_info": {"parameters": params}}}  # fmt: skip  # noqa: E501


def text(idx, delta):
    return {
        "event": "step_update",
        "step_update": {"step_index": idx, "state": "DONE", "step_type": "agent_response", "text_delta": delta},
    }


RESULT = {"event": "result", "result": {"status": "SUCCESS", "response": "ignored", "num_turns": 2,
                                        "usage": {"input_tokens": 100, "output_tokens": 10, "cache_read_tokens": 900, "total_tokens": 110}}}  # fmt: skip  # noqa: E501


def test_parse_events_maps_tools_and_picks_the_last_answer_with_files():
    out = at.parse_events(stream([
        tool(2, "run_command", CommandLine='graphify query "X"'),
        tool(4, "grep_search", Query="X"),
        tool(6, "read_file", Path="/a/A.java"),
        text(7, "FILE: draft.java\n"),
        text(9, "FILE: a/A.java\nUNVERIFIED: none"),
        RESULT,
    ]))  # fmt: skip
    assert [c["tool"] for c in out["tool_calls"]] == ["Bash", "Grep", "Read"]
    assert out["result"].startswith("FILE: a/A.java")
    assert out["total_tokens"] == 1010 and not out["is_error"]


def test_summarize_reads_agy_runs_through_the_shared_scorer():
    parsed = at.parse_events(stream([tool(2, "run_command", CommandLine='graphify query "X"'), tool(4, "grep_search", Query="X"),  # noqa: E501
                                     text(5, "FILE: a/A.java\nUNVERIFIED: none"), RESULT]))  # fmt: skip
    s = nt.summarize(parsed, {"a/A.java", "b/B.java"})
    assert (s["graph"], s["graph_first"], s["searches_after"]) == (True, True, 1)
    assert s["overconfident"] is True and s["r"] == 0.5  # says "none" while missing half the files


def test_missing_result_event_is_an_error():
    assert at.parse_events(stream([text(1, "hello")]))["is_error"] is True
