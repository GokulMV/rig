from dataclasses import dataclass
from pathlib import Path

from proving_ground import priors


def test_measurements_move_the_guess_by_pairs_and_similarity():
    f = {"kind:do", "kind:check", "loop"}
    # Nothing measured, or nothing similar enough: no learned number at all.
    assert priors.learn("a", f, 5.0, []) is None
    far = {"id": "b", "features": {"kind:judge", "parallel"}, "diff": -30.0, "pairs": 40}
    assert priors.learn("a", f, 5.0, [far]) is None
    # Its own measurement: the guess counts as 10 pairs, 30 measured pairs at +25 weigh 3x.
    own = {"id": "a", "features": f, "diff": 25.0, "pairs": 30}
    got = priors.learn("a", f, 5.0, [own])
    assert got.prior == 20.0 and got.runs == 1 and got.pairs == 30 and got.guess == 5.0
    # A similar one counts less than the same one.
    near = {"id": "c", "features": {"kind:do", "kind:check"}, "diff": 25.0, "pairs": 30}
    assert 5.0 < priors.learn("a", f, 5.0, [near]).prior < got.prior
    # Too few pairs, or still undecided with no number: ignored.
    assert priors.learn("a", f, 5.0, [own | {"pairs": 1}]) is None
    assert priors.learn("a", f, 5.0, [own | {"diff": None}]) is None


@dataclass
class T:
    arm: str
    outcome: str
    cost_usd: float
    reused_from: int | None = None
    scenario_id: str = "s"


def test_cost_per_solved_task_counts_reused_trials_at_what_they_cost():
    trials = [
        T("with", "pass", 0.30),
        T("with", "pass", 0.30),
        T("with", "fail", 0.40),
        T("without", "pass", 0.0, reused_from=7),
        T("without", "fail", 0.0, reused_from=7),
        T("without", "errored", 9.99),  # didn't run to an answer: not counted
    ]
    c = priors.cost_per_solved(trials, lambda t: 0.20)
    assert c["with"] == {"spent_usd": 1.0, "solved": 2, "tasks": 3, "per_solved_usd": 0.5}
    assert c["without"] == {"spent_usd": 0.4, "solved": 1, "tasks": 2, "per_solved_usd": 0.4}
    # Per trial: with costs 0.333 and solves 0.667; without 0.2 and 0.5. 0.133 / 0.167 = 0.8.
    assert c["per_extra_solved_usd"] == 0.8
    worse = priors.cost_per_solved([T("with", "fail", 1.0), T("without", "pass", 0.5)], lambda t: 0)
    assert worse["per_extra_solved_usd"] is None and worse["with"]["per_solved_usd"] is None


def test_lab_learns_from_a_measured_run(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN
    from test_bench import _lab_client, _starter, _wait

    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    a = _starter(c, "Fix a bug")
    assert a.get("learned") is None
    c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "qa", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    row = _wait(c, 1)[0]
    assert row["costs"]["with"]["solved"] == 2 and row["costs"]["per_extra_solved_usd"] is not None
    lab = c.get("/api/lab").json()
    dev = next(d for d in lab["disciplines"] if d["id"] == "development")
    fix = next(w for w in dev["workflows"] if w["name"] == "Fix a bug")
    # +100 points on 2 valid pairs: fewer than min_learned_pairs, so it stays the guess from shape.
    assert row["validity"]["status"] == "valid"
    got = fix["learned"]
    assert got["basis"] == "shape" and got["runs"] == 1 and got["pairs"] == 2
    assert got["prior"] == fix["prior"] and got["need_pairs"] == 6
    # With the bar at 2 pairs, the same run moves the guess (against a guess worth 10 pairs).
    monkeypatch.setitem(priors.P, "min_learned_pairs", 2)
    lab = c.get("/api/lab").json()
    fix = next(w for d in lab["disciplines"] for w in d["workflows"] if w["name"] == "Fix a bug")
    assert fix["learned"]["basis"] == "learned" and fix["learned"]["prior"] > fix["prior"]
    priced = c.post("/api/lab/price", json=fix, headers=ORIGIN).json()
    assert priced["learned"]["prior"] == fix["learned"]["prior"]


def test_a_run_that_is_not_evidence_never_moves_a_guess(tmp_path: Path, monkeypatch):
    """Both arms always pass: no task could be won or lost. It is listed as uninformative, kept
    off PROVEN.md, and every similar workflow keeps its guess, with the run counted as ignored."""
    from test_api_workspace import ORIGIN
    from test_bench import _lab_client, _starter, _wait

    monkeypatch.setitem(priors.P, "min_learned_pairs", 2)
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    a = _starter(c, "Fix a bug")
    c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "qa", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    row = _wait(c, 1)[0]
    assert row["validity"] == {
        "status": "uninformative",
        "badge": "Uninformative: both always pass",
        "reason": "No task could be won or lost, so it says nothing.",
        "cause": "both_pass",
    }
    fix = _starter(c, "Fix a bug")
    assert fix["learned"]["basis"] == "shape" and fix["learned"]["runs"] == 0
    assert fix["learned"]["ignored"] == 1 and fix["learned"]["prior"] == fix["prior"]
    m = c.get("/api/lab/matrix", params={"bench": "qa"}).json()
    assert m["rows"][0]["validity"]["status"] == "uninformative"


def test_invalid_runs_are_skipped_and_too_few_pairs_stay_a_guess():
    f = {"kind:do", "kind:check"}
    good = {"id": "a", "features": f, "diff": 25.0, "pairs": 30, "valid": True}
    bad = {"id": "a", "features": f, "diff": 90.0, "pairs": 300, "valid": False}
    got = priors.learn("a", f, 5.0, [good, bad])
    assert got.prior == 20.0 and got.runs == 1 and got.ignored == 1 and got.basis == "learned"
    # Only invalid evidence: the guess, from shape, saying one run was ignored.
    only_bad = priors.learn("a", f, 5.0, [bad])
    assert (only_bad.basis, only_bad.prior, only_bad.runs, only_bad.ignored) == ("shape", 5.0, 0, 1)
    # Fewer valid pairs than min_learned_pairs (6): the guess, however far the measurement.
    few = priors.learn("a", f, 5.0, [good | {"pairs": 4}])
    assert (few.basis, few.prior, few.pairs, few.need_pairs) == ("shape", 5.0, 4, 6)


def test_model_tier():
    assert priors.model_tier("local:qwen3") == "local"
    assert priors.model_tier("claude-haiku-4-5") == "cloud_fast"
    assert priors.model_tier("gpt-5-mini") == "cloud_fast"
    assert priors.model_tier("gemini-2.5-FLASH") == "cloud_fast"
    assert priors.model_tier("claude-opus-5-5") == "cloud_frontier"
    assert priors.model_tier("local:haiku-clone") == "local"


def test_tiers_and_disciplines_weigh_differently():
    f = {"kind:do", "kind:check"}
    run = {"id": "a", "features": f, "diff": 25.0, "pairs": 30, "discipline": "code"}
    base = priors.learn("a", f, 5.0, [run | {"tier": "cloud_frontier"}], "cloud_frontier", "code")
    assert base.prior == 20.0  # same tier, same discipline: factor 1
    # Fast vs frontier: half the weight (15 of 25 effective pairs -> 5 + 20 * 15/25).
    half = priors.learn("a", f, 5.0, [run | {"tier": "cloud_fast"}], "cloud_frontier", "code")
    assert half.prior == 17.0 and half.runs == 1
    # Local vs cloud, either way: never pooled.
    assert priors.learn("a", f, 5.0, [run | {"tier": "local"}], "cloud_frontier", "code") is None
    assert priors.learn("a", f, 5.0, [run | {"tier": "cloud_fast"}], "local", "code") is None
    # Another bench discipline: 0.75 (22.5 of 32.5 -> 5 + 20 * 22.5/32.5).
    other = priors.learn("a", f, 5.0, [run | {"tier": "cloud_frontier"}], "cloud_frontier", "docs")
    assert other.prior == 18.8
    # No target tier or discipline given: nothing is down-weighted.
    assert priors.learn("a", f, 5.0, [run | {"tier": "local"}]).prior == 20.0
