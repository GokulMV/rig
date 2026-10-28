from proving_ground.models import ScenarioKind
from proving_ground.report import format_summary
from proving_ground.stats import summarize
from proving_ground.trial import TrialOutcome


def t(sid, arm, rep, outcome, kind=ScenarioKind.TYPICAL):
    return TrialOutcome(sid, kind, arm, rep, outcome, cost_usd=0.5)


def test_helps_report():
    trials = [t("a", "with", r, "pass") for r in range(40)]
    trials += [t("a", "without", r, "pass" if r < 30 else "fail") for r in range(40)]
    out = format_summary(summarize(trials))
    assert out.splitlines()[0] == "Verdict: HELPS"
    assert "With: 100.0%   Without: 75.0%   Pairs: 40" in out
    assert "Difference: +25.0 pts (95% CI" in out
    assert "Cost: $20.00 with, $20.00 without" in out


def test_inconclusive_report_says_how_many_pairs():
    trials = [t("a", "with", r, "pass" if r < 3 else "fail") for r in range(4)]
    trials += [t("a", "without", r, "pass" if r < 2 else "fail") for r in range(4)]
    out = format_summary(summarize(trials))
    assert out.startswith("Verdict: INCONCLUSIVE")
    assert "About" in out and "pairs would detect a difference this size" in out


def test_synthetic_and_unreliable_lines():
    trials = [
        t("d", arm, r, "pass", ScenarioKind.IMAGINARY)
        for r in range(3)
        for arm in ("with", "without")
    ]
    trials += [t("e", "with", 0, "errored"), t("e", "without", 0, "pass")]
    out = format_summary(summarize(trials))
    assert "No complete real pairs yet." in out
    assert "Synthetic (imaginary tasks, not in the verdict): 3 pairs" in out
    assert "Unreliable: 1 of 8 trials errored" in out
