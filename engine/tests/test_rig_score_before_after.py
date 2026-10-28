"""The Rig score of a code change measured before and after: the same numbers, and every line
that names an arm says "after" and "before" (rig-score by_kind.before_after), on the pass rate
and on tokens, cost or time."""

import re

import pytest

from proving_ground import priors, skills, validity
from proving_ground.models import ScenarioKind
from proving_ground.rig_score import (
    WORDS,
    arms,
    evidence_from_row,
    ledger,
    ledger_text,
    rig_score,
    words,
)
from proving_ground.stats import summarize
from proving_ground.trial import TrialOutcome

R = skills.load("rig-score").values
BA = R["by_kind"]["before_after"]
# An arm named the way an agent change names it. Placeholders ({with_}) are not words.
ARM_WORDS = re.compile(r'\bwith\b|\bwithout\b|plain agent|agent alone|"with"', re.I)
# Lines a before/after run never says: Followed reads no logs for it (followed.before_after),
# and a run of the repo's own code can't have skipped a skill or an MCP server.
NEVER_SAID = {
    "text.followed.workflow",
    "text.followed.workflow_unsized",
    "text.followed.skill",
    "text.followed.drag_skill",
    "text.followed.mcp",
    "text.followed.drag_mcp",
    "verdict.text.not_applied",
    "verdict.text.mcp_unused",
    # "the agent sometimes fails": the agent, which runs on both sides.
    "verdict.text.each_same_next",
}


def leaves(d, path=()):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from leaves(v, (*path, k))
    elif isinstance(d, str):
        yield ".".join(path), d


def bare(s: str) -> str:
    return re.sub(r"\{[^}]*\}", "", s)


def lines(w):
    yield from leaves(w.t, ("text",))
    yield from leaves(w.vt, ("verdict", "text"))
    yield from leaves(w.mt, ("metric", "text"))


# ---------- the words ----------


def test_every_line_that_names_an_arm_has_its_before_after_words():
    plain, ba = dict(lines(words(None))), dict(lines(words("before_after")))
    named = {k for k, s in plain.items() if ARM_WORDS.search(bare(s))}
    assert len(named) > 30  # the check has something to check
    left = {k for k in named - NEVER_SAID if ARM_WORDS.search(bare(ba[k]))}
    assert left == set(), f"still says with / without in a before/after run: {sorted(left)}"
    # Each replacement keeps the line's placeholders, so it is filled from the same numbers.
    for k, s in ba.items():
        if s != plain.get(k) and k in plain and not k.endswith("unsolved_one"):
            assert set(re.findall(r"\{(\w+)", s)) <= set(re.findall(r"\{(\w+)", plain[k])), k


def test_by_kind_only_replaces_lines_that_exist():
    plain = dict(lines(words(None)))
    over = dict(leaves(BA.get("text", {}), ("text",)))
    over |= dict(leaves(BA.get("verdict", {}).get("text", {}), ("verdict", "text")))
    over |= dict(leaves(BA.get("metric", {}).get("text", {}), ("metric", "text")))
    new = {k for k in over if k not in plain}
    assert new == {"metric.text.arm_words.with", "metric.text.arm_words.without"}
    # Any other kind keeps the lines as they were.
    assert set(WORDS) == {"before_after"}
    assert words("skill") == words(None) == words({"kind": "workflow"})
    assert words("skill").t is R["text"]


# ---------- on the pass rate ----------


def ev(**kw):
    """A code change that helps: 16 of 20 after, 8 of 20 before, priced on both sides."""
    base = {
        "kind": "before_after",
        "n_pairs": 20,
        "diff": 0.4,
        "ci_low": 0.15,
        "ci_high": 0.6,
        "verdict": "helps",
        "pass_with": 0.8,
        "pass_without": 0.4,
        "costs": {
            "with": {"spent_usd": 6.0, "solved": 16, "tasks": 20},
            "without": {"spent_usd": 2.0, "solved": 8, "tasks": 20},
        },
        "local": False,
        "holds_up": None,
        "ledger": {
            "total": 40, "with": 20, "without": 20, "pairs": 20, "logs_read": 20,
            "clean": 38, "timed_out": 2, "errored": 0, "broken": 0,
        },
        "judge": None,
    }  # fmt: skip
    return base | kw


def part(out, pid):
    return next(p for p in out["parts"] if p["id"] == pid)


def test_helps_says_after_and_before_with_the_same_numbers():
    out = rig_score(ev())
    skill = rig_score(ev(kind="skill", opened={"read": 20, "opened": 20}))
    v = out["verdict"]
    assert v["id"] == "helps"
    assert v["reason"] == (
        "16 of 20 passed after vs 8 of 20 passed before (+40 pts, 95% interval +15 to +60)."
    )
    assert v["next"] == (
        "Next: keep the change, and measure again when the model or the tasks change."
    )
    assert v["facts"] == [
        "Quality: 16 of 20 passed after, 8 of 20 passed before (+40 pts, 95% interval +15 to +60)"
    ]
    assert skill["verdict"]["reason"].startswith("16 of 20 passed with vs 8 of 20 passed without")
    assert part(out, "cost")["detail"] == "1.5× the cost of the code before, per solved task"
    assert part(skill, "cost")["detail"] == "1.5× the plain agent's cost per solved task"
    assert part(out, "reliable")["detail"] == "38 of 40 trials ran cleanly (20 after, 20 before)"
    assert out["ledger_text"] == (
        "40 trials (20 after, 20 before) · 20 complete pairs · 38 ran cleanly, 2 timed out"
        ' · logs read for 20 of the 20 "after" trials'
    )
    # Only the words differ: Cost and Reliable score as they would for any change.
    for pid in ("lift", "cost", "reliable"):
        assert part(out, pid)["score"] == part(skill, pid)["score"]


def test_a_change_that_costs_more_names_the_code_before():
    out = rig_score(ev(costs={"with": {"spent_usd": 40.0, "solved": 16, "tasks": 20},
                              "without": {"spent_usd": 2.0, "solved": 8, "tasks": 20}}))  # fmt: skip
    assert out["reason"].startswith("Costs 10× the code before;")


def test_hurts_says_after_and_before_and_keeps_the_code_before():
    out = rig_score(ev(diff=-0.4, ci_low=-0.6, ci_high=-0.15, verdict="hurts", pass_with=0.4,
                       pass_without=0.8))  # fmt: skip
    assert out["label"] == "Doesn't Work — does worse than the code before (-40 pts)"
    v = out["verdict"]
    assert v["reason"] == (
        "It does worse: 8 of 20 passed after vs 16 of 20 passed before"
        " (-40 pts, 95% interval -60 to -15)."
    )
    assert v["next"] == (
        'Next: keep the code before, or read the failing "after" trials to see what the change'
        " breaks."
    )


def test_not_settled_and_few_pairs_say_after_and_before():
    out = rig_score(ev(ci_low=-0.05, verdict="inconclusive"))
    assert out["verdict"]["reason"].startswith(
        "16 of 20 passed after vs 8 of 20 passed before (+40 pts, 95% interval -5 to +60 over 20"
        " pairs): not settled"
    )
    few = rig_score(ev(n_pairs=5, ledger=ev()["ledger"] | {"pairs": 5}))
    assert few["verdict"]["reason"].startswith(
        "Looks like it helps (4 of 5 passed after vs 2 of 5 passed before,"
    )


def test_the_code_before_passing_everything_is_said_so():
    out = rig_score(ev(pass_with=0.8, pass_without=1.0, diff=-0.2, ci_low=-0.4, ci_high=0.05,
                       verdict="inconclusive"))  # fmt: skip
    assert out["label"] == "Doesn't Work — the code before already passes every task"
    assert out["verdict"]["reason"].startswith(
        "The code before already passes every task; after the change it passes 16 of 20"
    )
    assert out["verdict"]["next"] == "Next: a harder bench, or keep the code before."


def tr(sid, arm, outcome, cost, secs, rep=0):
    return TrialOutcome(
        sid, ScenarioKind.TYPICAL, arm, rep, outcome, cost_usd=cost, duration_s=secs
    )


def judged(trials):
    s = summarize(trials)
    h = s.headline
    row = {
        "n_pairs": h.n_pairs,
        "diff": h.diff,
        "ci_low": h.ci_low,
        "ci_high": h.ci_high,
        "verdict": s.verdict.value,
        "pass_with": h.pass_with,
        "pass_without": h.pass_without,
        "validity": validity.judge(trials, None, None, None),
        "ledger": ledger(trials),
        "costs": priors.cost_per_solved(trials, lambda t: t.cost_usd),
        "arms": arms(trials),
    }
    return rig_score(evidence_from_row(row, "before_after"))


def test_cost_time_and_reliability_facts_name_after_and_before():
    ids = ["a", "b", "c", "d", "e"]
    trials = [tr(i, "without", "pass", 0.04, 40) for i in ids]
    trials += [tr(i, "with", "pass" if i in "ab" else "fail", 0.4, 200) for i in ids]
    v = judged(trials)["verdict"]
    q, c, t, rel = v["facts"]
    assert q.startswith("Quality: 2 of 5 passed after, 5 of 5 passed before")
    assert c.startswith("Cost: $0.40 after vs $0.040 before per trial (10×)")
    assert t == "Time: 3.3 min after vs 40 s before per trial (5.0×)"
    assert rel == "Reliability: after, all 5 ran cleanly; before, all 5 ran cleanly"
    assert v["reason"].startswith("The code before already passes every task; after the change")


@pytest.mark.parametrize("call", ["worse", "better", "mixed"])
def test_both_always_pass_says_after_the_change(call):
    ids = ["a", "b", "c", "d", "e"]  # 10 pairs: enough to call a saving
    w_cost, w_secs = {"worse": (0.4, 40), "better": (0.004, 40), "mixed": (0.004, 400)}[call]
    trials = [tr(i, "without", "pass", 0.04, 40, r) for i in ids for r in (0, 1)]
    trials += [
        tr(i, "with", "pass", w_cost * (1 + r / 10), w_secs * (1 + r / 10), r)
        for i in ids
        for r in (0, 1)
    ]
    out = judged(trials)
    assert out["verdict"]["id"] == {"worse": "doesnt", "better": "helps", "mixed": "cant"}[call]
    reason = out["verdict"]["reason"]
    assert "after the change it" in reason, reason
    assert not ARM_WORDS.search(reason)
    if call == "worse":
        assert out["verdict"]["next"].startswith("Next: keep the code before")


# ---------- on tokens, cost or time ----------


def mev(mid="tokens", **kw):
    m = {
        "id": mid, "n": 40, "with": 21_400.0, "without": 44_100.0, "ratio": 21_400 / 44_100,
        "low": 0.42, "high": 0.55, "solved_with": 32, "solved_without": 32,
    }  # fmt: skip
    base = ev(
        n_pairs=40, diff=0.0, ci_low=-0.07, ci_high=0.07, verdict="inconclusive", pass_with=0.8,
        pass_without=0.8, ledger=ev()["ledger"] | {"pairs": 40}, metric=m,
    )  # fmt: skip
    return base | kw


@pytest.mark.parametrize(
    ("mid", "line"),
    [
        ("tokens", "Tokens per Solved Task: after 21.4k vs before 44.1k (-51%"),
        ("cost", "Cost per Solved Task: after $21400.00 vs before $44100.00 (-51%"),
        ("time", "Time per Solved Task: after 356.7 min vs before 735.0 min (-51%"),
    ],
)
def test_a_saving_says_after_and_before_on_each_metric(mid, line):
    out = rig_score(mev(mid))
    assert out["metric"]["headline"].startswith(line)
    assert out["metric"]["guard"] == (
        "Pass rate: 32 of 40 passed after vs 32 of 40 passed before (+0 pts; at worst -7 pts,"
        " within the 10-pt margin)"
    )
    v = out["verdict"]
    assert v["id"] == "helps"
    assert v["reason"] == (
        out["metric"]["headline"] + ", and the pass rate holds (32 of 40 passed after vs 32 of 40"
        " passed before; at worst -7 pts, margin 10)."
    )
    assert v["next"].startswith("Next: keep the change for the saving")
    assert not ARM_WORDS.search(bare(v["reason"] + v["next"] + " ".join(v["facts"])))


def test_no_interval_says_after_and_before():
    out = rig_score(mev(n_pairs=1, metric=mev()["metric"] | {"n": 1, "low": None, "high": None}))
    assert out["metric"]["headline"] == (
        "Tokens per Solved Task: after 21.4k vs before 44.1k (-51%; an interval needs 2 pairs)"
    )


def test_using_more_and_the_guard_not_met_say_after_and_before():
    more = rig_score(mev(metric=mev()["metric"] | {"ratio": 1.4, "low": 1.2, "high": 1.6}))
    assert more["verdict"]["next"] == (
        'Next: keep the code before, or read the "after" trials to see where the tokens go.'
    )
    ni = rig_score(mev(ci_low=-0.2))
    assert (
        "(32 of 40 passed after vs 32 of 40 passed before; the margin is 10)"
        in ni["verdict"]["reason"]
    )
    drop = rig_score(mev(diff=-0.12, ci_low=-0.3, ci_high=0.05, pass_with=0.68))
    assert (
        "(27 of 40 passed after vs 32 of 40 passed before), past the 10-pt margin"
        in drop["verdict"]["reason"]
    )
    hurts = rig_score(mev(diff=-0.3, ci_low=-0.5, ci_high=-0.1, verdict="hurts", pass_with=0.5))
    assert hurts["label"] == "Doesn't Work — does worse than the code before (-30 pts)"
    assert hurts["verdict"]["reason"].startswith(
        "It does worse on the pass rate: 20 of 40 passed after vs 32 of 40 passed before"
    )
    assert hurts["verdict"]["next"].startswith("Next: keep the code before, or read the failing")
    small = rig_score(mev(metric=mev()["metric"] | {"ratio": 0.99, "low": 0.97, "high": 1.02}))
    assert small["verdict"]["next"].startswith("Next: keep the code before, or measure the change")


def test_one_side_solving_nothing_names_that_side():
    for solved, side in (({"solved_with": 0, "solved_without": 2}, "after"),
                         ({"solved_with": 2, "solved_without": 0}, "before")):  # fmt: skip
        out = rig_score(mev(metric={"id": "tokens", "n": 3, "missing": "unsolved"} | solved))
        assert out["reason"] == (
            f"The code {side} solved no task, so tokens per solved task can't be compared."
        )
        assert out["verdict"]["reason"] == out["reason"]


def test_the_ledger_line_by_kind():
    ld = ev()["ledger"]
    assert ledger_text(ld).startswith("40 trials (20 with, 20 without)")
    assert ledger_text(ld, "before_after").startswith("40 trials (20 after, 20 before)")
