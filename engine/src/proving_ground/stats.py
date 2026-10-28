"""Paired with/without statistics: Wilson, Newcombe method 10, MDE, verdicts; and, for checks
that count items (RIG_ITEMS), a paired t interval on the item score."""

from __future__ import annotations

import math
import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from proving_ground import skills
from proving_ground.models import ScenarioKind
from proving_ground.trial import TrialOutcome

Z95 = 1.959963984540054
Z_POWER80 = 0.8416212335729143
J = skills.load("judge-experiment").values
VAR_FLOOR = J["var_floor"]  # keeps MDE meaningful when the baseline is near 0% or 100%
UNRELIABLE_ERROR_RATE = J["unreliable_error_rate"]


@dataclass(frozen=True)
class PairCounts:
    both_pass: int
    with_only: int
    without_only: int
    both_fail: int

    @property
    def n(self) -> int:
        return self.both_pass + self.with_only + self.without_only + self.both_fail


def wilson(x: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= x <= n:
        raise ValueError("x must be between 0 and n")
    p = x / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def paired_diff_ci(c: PairCounts, z: float = Z95) -> tuple[float, float, float]:
    """Newcombe (1998) method 10 for a difference of paired proportions."""
    n = c.n
    if n == 0:
        raise ValueError("no pairs")
    a, b, cc, d = c.both_pass, c.with_only, c.without_only, c.both_fail
    p1, p2 = (a + b) / n, (a + cc) / n
    l1, u1 = wilson(a + b, n, z)
    l2, u2 = wilson(a + cc, n, z)
    denom = (a + b) * (cc + d) * (a + cc) * (b + d)
    # Continuity-corrected phi (Newcombe 1998, p. 2639): without it, arms that always
    # agree give phi = 1 and a zero-width interval.
    cross = a * d - b * cc
    if cross > n / 2:
        cross -= n / 2
    elif cross > 0:
        cross = 0
    phi = 0.0 if denom == 0 else cross / math.sqrt(denom)
    diff = p1 - p2
    lo = diff - math.sqrt(
        max(0.0, (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2)
    )
    hi = diff + math.sqrt(
        max(0.0, (p2 - l2) ** 2 - 2 * phi * (p2 - l2) * (u1 - p1) + (u1 - p1) ** 2)
    )
    return diff, max(-1.0, lo), min(1.0, hi)


def _var(p_base: float) -> float:
    return max(p_base * (1 - p_base), VAR_FLOOR)


def mde(p_base: float, n_pairs: int) -> float:
    """Smallest difference detectable at 95% confidence and 80% power.

    Uses the unpaired normal approximation, which is conservative for paired data.
    """
    return (Z95 + Z_POWER80) * math.sqrt(2 * _var(p_base) / n_pairs)


def noise_half_width(n_pairs: int, p_base: float) -> float:
    """About how far either side of 0 the 95% interval reaches with no real difference: an
    effect smaller than this can't be told from noise. The unpaired normal approximation, as
    `mde` uses (conservative for paired data)."""
    return Z95 * math.sqrt(2 * _var(p_base) / n_pairs)


def pairs_for_half_width(half_width: float, p_base: float) -> int:
    """The fewest pairs whose noise_half_width is at most `half_width`: below this many pairs,
    an effect that size can't be told from noise."""
    if half_width <= 0:
        raise ValueError("half_width must be positive")
    n = math.ceil(2 * _var(p_base) * (Z95 / half_width) ** 2 - 1e-9)
    return max(1, n)


def required_pairs(diff: float, p_base: float) -> int | None:
    if abs(diff) < 1e-9:
        return None
    return math.ceil((Z95 + Z_POWER80) ** 2 * 2 * _var(p_base) / diff**2)


class Verdict(StrEnum):
    HELPS = "helps"
    HURTS = "hurts"
    INCONCLUSIVE = "inconclusive"


def verdict(low: float, high: float) -> Verdict:
    if low > 0:
        return Verdict.HELPS
    if high < 0:
        return Verdict.HURTS
    return Verdict.INCONCLUSIVE


@dataclass(frozen=True)
class ArmPairStats:
    n_pairs: int
    pass_with: float
    pass_without: float
    diff: float
    ci_low: float
    ci_high: float


@dataclass(frozen=True)
class ItemStats:
    """Partial credit over the headline's pairs: each trial scores right/total, and the
    difference is the mean of the per-pair differences (with minus without)."""

    n_pairs: int
    score_with: float
    score_without: float
    diff: float
    ci_low: float
    ci_high: float
    right_with: int
    total_with: int
    right_without: int
    total_without: int

    def as_json(self) -> dict:
        """The `items` key of a result row."""
        return {
            "with": self.score_with,
            "without": self.score_without,
            "diff": self.diff,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "n": self.n_pairs,
            "right_with": self.right_with,
            "total_with": self.total_with,
            "right_without": self.right_without,
            "total_without": self.total_without,
        }


# Student t, two-sided 95% (0.975 quantile), for 1..30 degrees of freedom.
_T975 = (
    12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
    2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
    2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042,
)  # fmt: skip


def t975(df: int) -> float:
    """The 0.975 quantile of Student's t: a table to 30 degrees of freedom, then the Cornish-
    Fisher expansion about the normal (Abramowitz & Stegun 26.7.5; within 0.001 beyond 30)."""
    if df < 1:
        raise ValueError("df must be at least 1")
    if df <= len(_T975):
        return _T975[df - 1]
    z, v = Z95, float(df)
    g1 = (z**3 + z) / 4
    g2 = (5 * z**5 + 16 * z**3 + 3 * z) / 96
    g3 = (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / 384
    g4 = (79 * z**9 + 776 * z**7 + 1482 * z**5 - 1920 * z**3 - 945 * z) / 92160
    return z + g1 / v + g2 / v**2 + g3 / v**3 + g4 / v**4


def _t_central(t: float, df: int) -> float:
    """P(|T| <= t) for Student's t on whole `df`: the finite sums of Abramowitz & Stegun
    26.7.3 (odd df) and 26.7.4 (even df)."""
    th = math.atan(t / math.sqrt(df))
    c, sn = math.cos(th), math.sin(th)
    if df % 2:
        term, total = c, (c if df > 1 else 0.0)
        for k in range(3, df - 1, 2):  # cos θ (1 + 2/3 cos² θ + 2·4/(3·5) cos⁴ θ + ...)
            term *= (k - 1) / k * c * c
            total += term
        return 2 / math.pi * (th + sn * total)
    term = total = 1.0
    for k in range(2, df - 1, 2):  # 1 + 1/2 cos² θ + 1·3/(2·4) cos⁴ θ + ...
        term *= (k - 1) / k * c * c
        total += term
    return sn * total


def t_two_sided(df: int, level: float) -> float:
    """The t whose two-sided interval holds `level` (0.95 → t975(df) unrounded), by bisection
    on the exact distribution: for a stricter interval than the 95% the table covers."""
    if df < 1:
        raise ValueError("df must be at least 1")
    lo, hi = 0.0, 1.0
    while _t_central(hi, df) < level:
        hi *= 2
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _t_central(mid, df) < level else (lo, mid)
    return hi


def task_totals(trials: Iterable[TrialOutcome]) -> dict[str, int]:
    """Each task's item total, from any of its pass/fail trials whose check printed a count."""
    out: dict[str, int] = {}
    for t in trials:
        if t.outcome in ("pass", "fail") and t.items_right is not None and t.items_total:
            out[t.scenario_id] = max(out.get(t.scenario_id, 0), t.items_total)
    return out


def _counted(t: TrialOutcome, totals: dict[str, int]) -> tuple[int, int] | None:
    """A trial's (right, total). With no count of its own on an item-based task (its total
    known from another trial): a fail produced nothing gradable, 0 of the total; a pass is
    never turned into a failure, all of it."""
    if t.items_right is not None and t.items_total:
        return t.items_right, t.items_total
    total = totals.get(t.scenario_id)
    if total is None:
        return None
    return (total if t.outcome == "pass" else 0), total


def item_stats(
    pairs: list[dict[str, TrialOutcome]], totals: dict[str, int] | None = None, z: float = Z95
) -> ItemStats | None:
    """Paired t interval on the per-pair item-score differences, or None when some task in the
    pairs has no count on any trial (it isn't item-based). `totals` (task_totals over every
    trial of the run) fills in a trial whose check printed no count; by default, the pairs'.

    Paired t, not a bootstrap: it is deterministic (no seed in the result) and, with scores
    bounded in [0, 1], the mean difference is close to normal at the pair counts Rig runs.
    Two guards: one pair says nothing about spread, so its interval is the whole [-1, 1]; and
    when every pair differs by exactly the same amount the t interval would shrink to a point,
    so the per-pair spread is floored at half of one item (0.5 / items in the task). `z`: a
    stricter interval than the 95% one (auto-extend's stop rule), at the t of that level."""
    if not pairs:
        return None
    if totals is None:
        totals = task_totals(t for g in pairs for t in g.values())
    counts: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for g in pairs:
        w, wo = _counted(g["with"], totals), _counted(g["without"], totals)
        if w is None or wo is None:
            return None
        counts.append((w, wo))
    n = len(counts)
    d = [w[0] / w[1] - wo[0] / wo[1] for w, wo in counts]
    mean = sum(d) / n
    if n < 2:
        lo, hi = -1.0, 1.0
    else:
        sd = math.sqrt(sum((x - mean) ** 2 for x in d) / (n - 1))
        floor = 0.5 / (sum(w[1] + wo[1] for w, wo in counts) / (2 * n))
        t = t975(n - 1) if z == Z95 else t_two_sided(n - 1, level_of(z))
        half = t * max(sd, floor) / math.sqrt(n)
        lo, hi = max(-1.0, mean - half), min(1.0, mean + half)
    return ItemStats(
        n_pairs=n,
        score_with=sum(w[0] / w[1] for w, _ in counts) / n,
        score_without=sum(wo[0] / wo[1] for _, wo in counts) / n,
        diff=mean,
        ci_low=lo,
        ci_high=hi,
        right_with=sum(w[0] for w, _ in counts),
        total_with=sum(w[1] for w, _ in counts),
        right_without=sum(wo[0] for _, wo in counts),
        total_without=sum(wo[1] for _, wo in counts),
    )


def level_of(z: float) -> float:
    """The two-sided confidence a normal z stands for: 1.96 → 0.95, 2.576 → 0.99."""
    return math.erf(z / math.sqrt(2))


def paired_ratio_ci(
    pairs: list[tuple[float, int, float, int]],
    resamples: int,
    seed: int,
    min_pairs: int = 2,
    level: float = 0.95,
) -> tuple[float, float | None, float | None]:
    """with ÷ without of a measure per solved task, and its percentile-bootstrap interval.

    `pairs`: per complete pair, (value with, solved with 0/1, value without, solved without).
    Each arm's figure is its total value ÷ the tasks it solved; the ratio is with ÷ without.
    Whole pairs are resampled (paired), with a fixed `seed`, so the same pairs always give the
    same interval. A resample in which an arm solved nothing has no figure for that arm and
    counts as an infinite ratio: against the change, never a saving. Under `min_pairs` pairs
    the interval is (None, None). Raises ValueError when an arm solved nothing at all."""
    return stratified_ratio_ci([pairs], resamples, seed, min_pairs, level)


def stratified_ratio_ci(
    strata: list[list[tuple[float, int, float, int]]],
    resamples: int,
    seed: int,
    min_pairs: int = 2,
    level: float = 0.95,
) -> tuple[float, float | None, float | None]:
    """paired_ratio_ci over pairs that come in fixed groups (a suite's benches): the ratio is
    over every pair, and each resample draws each group's own number of pairs from that group
    alone, so every resample keeps the groups' sizes as they ran. With one group it is
    paired_ratio_ci, draw for draw. `min_pairs` counts the pairs of every group together."""
    strata = [g for g in strata if g]
    pairs = [p for g in strata for p in g]
    n = len(pairs)
    vw = sum(p[0] for p in pairs)
    sw = sum(p[1] for p in pairs)
    vwo = sum(p[2] for p in pairs)
    swo = sum(p[3] for p in pairs)
    if not sw or not swo or vwo <= 0:
        raise ValueError("an arm solved nothing, or the without arm recorded nothing")
    ratio = (vw / sw) / (vwo / swo)
    if n < min_pairs:
        return ratio, None, None
    rng = random.Random(seed)
    got: list[float] = []
    for _ in range(resamples):
        a = b = c = d = 0.0
        for g in strata:
            k = len(g)
            for _ in range(k):
                w, s1, wo, s2 = g[rng.randrange(k)]
                a += w
                b += s1
                c += wo
                d += s2
        got.append(math.inf if not b or not d or c <= 0 else (a / b) / (c / d))
    got.sort()
    tail = (1 - level) / 2
    lo = got[max(0, math.floor(tail * resamples + 1e-9))]
    hi = got[min(resamples - 1, math.ceil((1 - tail) * resamples - 1e-9) - 1)]
    return ratio, lo, hi


@dataclass(frozen=True)
class ResultSummary:
    headline: ArmPairStats | None
    verdict: Verdict
    mde: float | None
    required_pairs: int | None
    by_kind: dict[str, ArmPairStats] = field(default_factory=dict)
    synthetic: ArmPairStats | None = None
    errored: int = 0
    broken: int = 0
    total: int = 0
    unreliable: bool = False
    cost_with: float = 0.0
    cost_without: float = 0.0
    # Partial credit over the headline's pairs; None when a task in them never counted items.
    items: ItemStats | None = None


Pair = dict[str, TrialOutcome]


def _complete_pairs(trials: list[TrialOutcome]) -> list[Pair]:
    groups: dict[tuple[str, int], Pair] = {}
    for tr in trials:
        groups.setdefault((tr.scenario_id, tr.repeat), {})[tr.arm] = tr
    return [
        g
        for g in groups.values()
        if set(g) == {"with", "without"} and all(x.outcome in ("pass", "fail") for x in g.values())
    ]


def real_pairs(trials: Iterable[TrialOutcome]) -> list[Pair]:
    """The complete pairs the headline counts: both arms finished, imaginary tasks left out."""
    return [
        g for g in _complete_pairs(list(trials)) if g["with"].kind is not ScenarioKind.IMAGINARY
    ]


def _stats(pairs: list[Pair], z: float = Z95) -> ArmPairStats | None:
    if not pairs:
        return None
    counts = [0, 0, 0, 0]
    for g in pairs:
        w, wo = g["with"].outcome == "pass", g["without"].outcome == "pass"
        counts[0 if w and wo else 1 if w else 2 if wo else 3] += 1
    c = PairCounts(*counts)
    diff, lo, hi = paired_diff_ci(c, z)
    return ArmPairStats(
        n_pairs=c.n,
        pass_with=(c.both_pass + c.with_only) / c.n,
        pass_without=(c.both_pass + c.without_only) / c.n,
        diff=diff,
        ci_low=lo,
        ci_high=hi,
    )


def summarize(trials: Iterable[TrialOutcome]) -> ResultSummary:
    trials = list(trials)
    pairs = _complete_pairs(trials)
    real = [g for g in pairs if g["with"].kind is not ScenarioKind.IMAGINARY]
    synthetic = [g for g in pairs if g["with"].kind is ScenarioKind.IMAGINARY]
    headline = _stats(real)
    by_kind = {}
    for kind in ScenarioKind:
        if kind is ScenarioKind.IMAGINARY:
            continue
        st = _stats([g for g in real if g["with"].kind is kind])
        if st is not None:
            by_kind[kind.value] = st
    errored = sum(tr.outcome == "errored" for tr in trials)
    total = len(trials)
    if headline is None:
        v, m, req = Verdict.INCONCLUSIVE, None, None
    else:
        v = verdict(headline.ci_low, headline.ci_high)
        m = mde(headline.pass_without, headline.n_pairs)
        req = (
            required_pairs(headline.diff, headline.pass_without)
            if v is Verdict.INCONCLUSIVE
            else None
        )
    return ResultSummary(
        headline=headline,
        verdict=v,
        mde=m,
        required_pairs=req,
        by_kind=by_kind,
        synthetic=_stats(synthetic),
        errored=errored,
        broken=sum(tr.outcome == "broken" for tr in trials),
        total=total,
        unreliable=total > 0 and errored / total > UNRELIABLE_ERROR_RATE,
        cost_with=sum(tr.cost_usd for tr in trials if tr.arm == "with"),
        cost_without=sum(tr.cost_usd for tr in trials if tr.arm == "without"),
        items=item_stats(real, task_totals(trials)),
    )


def stop_verdict(trials: Iterable[TrialOutcome], z: float) -> tuple[Verdict, int]:
    """The verdict at a stricter interval (z), for deciding when to stop adding pairs.

    Looking again after every batch makes a lucky "helps" likelier; a wider interval for the
    stop decision keeps that in check. The reported result still uses the 95% interval.
    """
    pairs = [
        g for g in _complete_pairs(list(trials)) if g["with"].kind is not ScenarioKind.IMAGINARY
    ]
    st = _stats(pairs, z)
    if st is None:
        return Verdict.INCONCLUSIVE, 0
    return verdict(st.ci_low, st.ci_high), st.n_pairs


def stop_quality(trials: Iterable[TrialOutcome], z: float) -> tuple[float, float, int] | None:
    """The quality a saving's guard is judged on (items right when every task counts them, else
    the pass rate), as (low, high, pairs) at a stricter interval (z), for deciding when to stop
    adding pairs to a run scored on a saving. None with no pairs."""
    trials = list(trials)
    pairs = real_pairs(trials)
    it = item_stats(pairs, task_totals(trials), z)
    if it is not None:
        return it.ci_low, it.ci_high, it.n_pairs
    st = _stats(pairs, z)
    return None if st is None else (st.ci_low, st.ci_high, st.n_pairs)
