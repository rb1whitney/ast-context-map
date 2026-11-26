import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "trial", Path(__file__).resolve().parents[1] / "research" / "graph-of-graphs" / "experiments" / "trial" / "trial.py"
)
trial = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trial)


def test_absent_line_is_not_a_claim():
    assert trial.parse_unverified("FILE: a.java\nFILE: b.java") == (None, False)


def test_none_means_the_agent_claims_completeness():
    for line in ("none", "None.", "nothing", "n/a", ""):
        assert trial.parse_unverified(f"FILE: a.java\nUNVERIFIED: {line}")[1] is True


def test_a_stated_gap_is_not_a_completeness_claim():
    stated, complete = trial.parse_unverified("FILE: a.java\nUNVERIFIED: could not check the generated sources")
    assert stated == "could not check the generated sources" and complete is False


def test_the_last_unverified_line_wins():
    assert trial.parse_unverified("UNVERIFIED: x\nFILE: a\nUNVERIFIED: none")[1] is True
