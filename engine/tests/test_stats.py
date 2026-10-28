import random

import pytest

from proving_ground.models import ScenarioKind
from proving_ground.stats import (
    PairCounts,
    Verdict,
    mde,
    paired_diff_ci,
    required_pairs,
    summarize,
    verdict,
    wilson,
)
from proving_ground.trial import TrialOutcome


# statsmodels 0.14 proportion_confint(x, n, method="wilson")
@pytest.mark.parametrize(
    "x,n,lo,hi",
    [
        (30, 40, 0.59806, 0.858129),
        (0, 10, 0.0, 0.277533),
        (10, 10, 0.722467, 1.0),
        (7, 20, 0.181192, 0.567146),
    ],
)
def test_wilson_matches_statsmodels(x, n, lo, hi):
    got = wilson(x, n)
    assert got == pytest.approx((lo, hi), abs=1e-6)


def test_wilson_rejects_bad_input():
    with pytest.raises(ValueError):
        wilson(1, 0)
    with pytest.raises(ValueError):
        wilson(5, 4)


def test_paired_equals_unpaired_newcombe_when_phi_is_zero():
    # a=9,b=3,c=3,d=1 -> ad == bc; statsmodels confint_proportions_2indep(12,16,12,16,"newcomb")
    diff, lo, hi = paired_diff_ci(PairCounts(9, 3, 3, 1))
    assert diff == pytest.approx(0.0)
    assert (lo, hi) == pytest.approx((-0.286311, 0.286311), abs=1e-6)


@pytest.mark.parametrize(
    "counts,expected",
    [
        ((20, 12, 4, 4), (0.2, 0.002839, 0.377858)),
        ((36, 12, 2, 0), (0.2, 0.05693, 0.340428)),
        ((10, 5, 5, 20), (0.0, -0.156767, 0.156767)),
        ((0, 40, 0, 0), (1.0, 0.876084, 1.0)),
        ((25, 0, 0, 15), (0.0, -0.051676, 0.051676)),
    ],
)
# Cross-checked against an independent implementation of the NCSS PASS formulas for
# Newcombe method 10 (continuity-corrected phi); agreement within 1e-15 on 20k tables.
def test_paired_regression_values(counts, expected):
    assert paired_diff_ci(PairCounts(*counts)) == pytest.approx(expected, abs=1e-6)


def test_paired_rejects_empty():
    with pytest.raises(ValueError, match="no pairs"):
        paired_diff_ci(PairCounts(0, 0, 0, 0))


def test_paired_coverage_near_nominal():
    rng = random.Random(1)
    true_diff, hits, reps = 0.07, 0, 2000
    for _ in range(reps):
        a = b = c = d = 0
        for _ in range(40):
            u = rng.random()
            if u < 0.55:
                a += 1
            elif u < 0.70:
                b += 1
            elif u < 0.78:
                c += 1
            else:
                d += 1
        _, lo, hi = paired_diff_ci(PairCounts(a, b, c, d))
        hits += lo <= true_diff <= hi
    assert hits / reps >= 0.94


def test_verdict_boundaries():
    assert verdict(0.01, 0.2) is Verdict.HELPS
    assert verdict(-0.2, -0.01) is Verdict.HURTS
    assert verdict(-0.01, 0.2) is Verdict.INCONCLUSIVE
    assert verdict(0.0, 0.2) is Verdict.INCONCLUSIVE


def test_mde_and_required_pairs():
    assert mde(0.75, 40) == pytest.approx(0.271263, abs=1e-5)
    assert mde(0.75, 1000) < mde(0.75, 200) < mde(0.75, 40)
    assert mde(1.0, 40) == pytest.approx(
        mde(0.95, 40)
    )  # variance floor keeps MDE meaningful at extremes
    assert required_pairs(0.0, 0.75) is None
    assert required_pairs(0.05, 0.75) == 1178


def t(sid, arm, rep, outcome, kind=ScenarioKind.TYPICAL, cost=0.0):
    return TrialOutcome(
        scenario_id=sid, kind=kind, arm=arm, repeat=rep, outcome=outcome, cost_usd=cost
    )


def test_summarize_pairs_and_excludes_errored():
    trials = [
        t("a", "with", 0, "pass", cost=0.1),
        t("a", "without", 0, "fail", cost=0.1),
        t("a", "with", 1, "pass"),
        t("a", "without", 1, "pass"),
        t("b", "with", 0, "errored"),
        t("b", "without", 0, "pass"),
        t("b", "with", 1, "fail"),  # unpaired: budget stop mid-pair
    ]
    s = summarize(trials)
    assert s.headline.n_pairs == 2
    assert s.headline.pass_with == 1.0
    assert s.headline.pass_without == 0.5
    assert s.errored == 1
    assert s.total == 7
    assert s.unreliable is True  # 1/7 > 10%
    assert s.cost_with == pytest.approx(0.1)
    assert s.cost_without == pytest.approx(0.1)


def test_summarize_keeps_imaginary_out_of_headline():
    trials = [t("real", arm, r, "pass") for r in range(5) for arm in ("with", "without")]
    trials += [t("dream", "with", r, "pass", kind=ScenarioKind.IMAGINARY) for r in range(5)] + [
        t("dream", "without", r, "fail", kind=ScenarioKind.IMAGINARY) for r in range(5)
    ]
    s = summarize(trials)
    assert s.headline.n_pairs == 5
    assert s.headline.diff == 0.0
    assert s.synthetic.n_pairs == 5
    assert s.synthetic.diff == 1.0
    assert "imaginary" not in s.by_kind
    assert s.by_kind["typical"].n_pairs == 5


def test_summarize_verdict_and_required_pairs():
    trials = []
    for r in range(40):
        trials.append(t("a", "with", r, "pass"))
        trials.append(t("a", "without", r, "pass" if r < 30 else "fail"))
    s = summarize(trials)
    assert s.verdict is Verdict.HELPS
    assert s.required_pairs is None
    small = summarize(trials[:8])
    assert small.verdict is Verdict.INCONCLUSIVE


def test_summarize_with_nothing_complete():
    s = summarize([t("a", "with", 0, "broken"), t("a", "without", 0, "broken")])
    assert s.headline is None
    assert s.verdict is Verdict.INCONCLUSIVE
    assert s.broken == 2
    assert s.mde is None


def test_identical_arms_do_not_give_zero_width_interval():
    # 20 pairs where both arms always agree: the method-10 continuity correction on phi
    # (Newcombe 1998, p. 2639) must keep the interval from collapsing to [0, 0].
    _, lo, hi = paired_diff_ci(PairCounts(10, 0, 0, 10))
    assert lo < -0.01 and hi > 0.01


def test_phi_correction_is_zero_inside_half_n():
    # a=4,b=4,c=3,d=5: B = ad - bc = 8 <= n/2 = 8, so corrected phi = 0 and the interval
    # equals the independent (phi = 0) Newcombe interval for 8/16 vs 7/16.
    _, lo, hi = paired_diff_ci(PairCounts(4, 4, 3, 5))
    p1, p2 = 8 / 16, 7 / 16
    l1, u1 = wilson(8, 16)
    l2, u2 = wilson(7, 16)
    assert lo == pytest.approx((p1 - p2) - ((p1 - l1) ** 2 + (u2 - p2) ** 2) ** 0.5)
    assert hi == pytest.approx((p1 - p2) + ((p2 - l2) ** 2 + (u1 - p1) ** 2) ** 0.5)
