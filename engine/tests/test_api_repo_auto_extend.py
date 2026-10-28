"""A repo's run on Measure with "Keep going until it's decided", as the Lab's: the same stop rule
(judge-experiment: auto_extend) for a skill and for a code change before and after, on the pass
rate and on a saving; and the estimate says what it may grow to, which is where a free run on a
local model stops. Harbor is faked."""

import json

from test_api_local_repo import ORIGIN, env  # noqa: F401 - the fixture


def events(c, eid: int) -> list[dict]:
    with c.stream("GET", f"/api/experiments/{eid}/events") as s:
        return [json.loads(x[6:]) for x in s.iter_lines() if x.startswith("data: ")]


def start(c, body: dict) -> list[dict]:
    r = c.post("/api/experiments", json=body, headers=ORIGIN)
    assert r.status_code == 200, r.text
    ev = events(c, r.json()["id"])
    assert ev[-1]["type"] == "finished", ev[-1]
    return ev


def estimate(c, **kw) -> dict:
    body = {"pairs": 2, "agent": "claude-code", "size": "pilot", "tasks": 2, "auto": True} | kw
    r = c.post("/api/runs/estimate", json=body, headers=ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_free_run_keeps_going_to_the_cap_the_estimate_names(env):  # noqa: F811
    c = env.c
    # Every trial passes both ways: the pass rate never settles, so only the caps stop it, and a
    # local model has no budget to stop it sooner: 2 pairs, then a pair per task for 5 looks.
    got = estimate(c, local=True)["extends"]
    assert got == {
        "max_pairs": 12,
        "usd": None,
        "pairs_in_budget": 12,
        "line": "With \"Keep going until it's decided\" on, it may grow to 12 pairs while it's "
        "undecided, its cap: a local model has no budget to stop it sooner.",
    }
    body = {"treatment_path": str(env.sk), "n": 2, "budget": 1, "scenario_ids": ["a", "b"]}
    ev = start(c, body | {"local_model": env.m.id, "auto": True})
    assert [e["pairs"] for e in ev if e["type"] == "extended"] == [2, 4, 6, 8, 10]
    settled = [e for e in ev if e["type"] == "settled"]
    assert settled == [{"type": "settled", "reason": "5 extra looks", "pairs": 12, "looks": 5}]
    # Off, as before: the planned pairs and no more.
    ev = start(c, body | {"local_model": env.m.id})
    assert not [e for e in ev if e["type"] in ("extended", "settled")]


def test_a_code_change_on_tokens_waits_for_the_saving_and_its_guard(env):  # noqa: F811
    c = env.c
    # The after side uses a third of the tokens, every trial passing: the cut is shown at once,
    # the guard waits; a look adds 5 repeats (10 pairs) until both are decided at 62 (60 needed).
    assert estimate(c, local=True, metric="tokens")["extends"]["max_pairs"] == 92
    ev = start(
        c,
        {
            "before_after": {"base": "HEAD", "after": "split"},
            "n": 2,
            "budget": 1,
            "metric": "tokens",
            "local_model": env.m.id,
            "auto": True,
        },
    )
    grew = [e for e in ev if e["type"] == "extended"]
    assert [e["pairs"] for e in grew] == [2, 12, 22, 32, 42, 52]
    assert all(e["waiting"] == "the pass-rate guard" for e in grew)
    settled = next(e for e in ev if e["type"] == "settled")
    assert settled["pairs"] == 62
    assert settled["reason"] == (
        "the cut in tokens per solved task and the pass-rate guard are both decided at the "
        "stricter interval"
    )


def test_a_paid_runs_estimate_says_what_the_budget_stops_it_at(env):  # noqa: F811
    c = env.c
    f = estimate(c, budget=500)
    pair = f["per_pair"]
    assert f["extends"]["max_pairs"] == 12 and f["extends"]["pairs_in_budget"] == 12
    assert f["extends"]["line"] == (
        f"With \"Keep going until it's decided\" on, it may grow to 12 pairs "
        f"(≈ ${pair * 12:.2f}) while it's undecided, and still stops at $500.00."
    )
    # A budget for 5 pairs: the budget, not the cap, is where it stops.
    short = estimate(c, budget=round(pair * 5 + 0.001, 4))["extends"]
    assert short["pairs_in_budget"] == 5
    assert "to about 5 pairs before $" in short["line"] and "(12 pairs at most)" in short["line"]
    # Off: nothing about growing.
    assert "extends" not in estimate(c, budget=500, auto=False)
