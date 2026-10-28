"""Slim this workflow: variants, contributions, and a job end to end on the fake executor."""

import time
from pathlib import Path

from test_bench import _lab_client, _starter, _wait

from proving_ground import ablation, lab


def _wf(steps, edges=(), loops=()):
    sts = [lab.Step(i, i.upper(), "x", k, "claude-sonnet-5-5") for i, k in steps]
    wf = lab.Workflow(
        "p1", "Parent", "pattern", "custom", sts, edges=[list(e) for e in edges],
        loops=[list(x) for x in loops],
    )  # fmt: skip
    return lab._price(lab.normalize(wf))


def _drop(wf, sid):
    return next(v for v in ablation.plan(wf) if v.key == sid).workflow


def test_drop_rewires_a_diamond():
    wf = _wf(
        [("a", "think"), ("b", "do"), ("c", "do"), ("d", "check")],
        [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
    )
    v = _drop(wf, "b")
    assert [s.id for s in v.steps] == ["a", "c", "d"]
    assert sorted(v.edges) == [["a", "c"], ["a", "d"], ["c", "d"]]  # a also feeds d directly
    top = _drop(wf, "a")  # nothing led into it: its followers become starts
    assert sorted(top.edges) == [["b", "d"], ["c", "d"]]
    assert lab.levels(top) == [["b", "c"], ["d"]]
    mid = _wf([("a", "do"), ("m", "think"), ("z", "do")], [("a", "m"), ("m", "z")])
    assert _drop(mid, "m").edges == [["a", "z"]]


def test_drop_removes_loops_through_the_step_and_keeps_others():
    wf = _wf(
        [("p", "think"), ("w", "do"), ("t", "check"), ("r", "judge")],
        loops=[("t", "w", 2), ("r", "p", 1)],
    )
    v = _drop(wf, "t")
    assert v.loops == [["r", "p", 1]] and v.loop == ["r", "p", 1]
    assert v.edges == [["p", "w"], ["w", "r"]]
    assert _drop(wf, "p").loops == [["t", "w", 2]]


def test_variants_kinds_ids_names_and_the_cap():
    wf = _wf([("p", "think"), ("w", "do"), ("t", "check")], loops=[("t", "w", 2)])
    wf.steps[0].model = "claude-opus-5-5"
    got = ablation.plan(wf)
    assert [(v.kind, v.key) for v in got] == [
        ("drop", "p"),
        ("drop", "t"),  # the only "do" step is never dropped
        ("loop", "loop:t:w"),
        ("model", "model:p"),  # Opus to Sonnet
        ("model", "model:t"),  # a Sonnet check to Haiku
    ]
    assert got[0].workflow.name == "Parent − P"
    assert {v.workflow.id for v in got} == {lab._wid("p1", v.label) for v in got}
    assert got[4].workflow.steps[2].model == "claude-haiku-5-5"
    assert [s.model for s in got[3].workflow.steps][0] == "claude-sonnet-5-5"
    assert [v.label for v in got] == [lab_ for lab_, _ in ablation.variants(wf)]
    assert ablation.plan(wf)[0].workflow.id == ablation.plan(wf)[0].workflow.id  # stable
    big = _wf([(f"s{i}", "do") for i in range(8)] + [("k", "check")], loops=[("k", "s7", 1)])
    chosen = ablation.planned(big)
    assert len(chosen) == 8 and all(v.kind == "drop" for v in chosen)


def _row(diff, lo, hi, cost=0.1, **kw):
    return {"diff": diff, "ci_low": lo, "ci_high": hi,
            "costs": {"with": {"spent_usd": cost * 10, "tasks": 10}}, **kw}  # fmt: skip


def test_contributions_classify_with_honest_intervals():
    parent = _row(0.5, 0.3, 0.7, cost=0.10)
    rows = [
        _row(0.1, -0.05, 0.25, cost=0.06, key="ess", kind="drop"),  # +40 pts, apart
        _row(0.49, 0.2, 0.75, cost=0.05, key="dead", kind="drop"),  # +1, cheaper
        _row(0.5, 0.3, 0.7, cost=0.10, key="neutral", kind="drop"),  # +0, no saving
        _row(0.8, 0.7, 0.95, cost=0.12, key="bad", kind="drop"),  # -30, apart
        _row(0.25, 0.0, 0.5, cost=0.06, key="fuzzy", kind="drop"),  # +25 but overlapping
        _row(None, None, None, key="none", kind="drop"),
    ]
    c = ablation.contributions(parent, rows)
    assert {k: v["verdict"] for k, v in c.items()} == {
        "ess": "essential",
        "dead": "dead weight",
        "neutral": "neutral",
        "bad": "harmful",
        "fuzzy": "unclear",
        "none": "unclear",
    }
    assert c["ess"]["marginal_pts"] == 40.0 and c["ess"]["saved_cost_usd"] == 0.04
    assert c["bad"]["marginal_pts"] == -30.0


def test_ablation_job_reuses_the_parents_baseline(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    import proving_ground.runner.harbor as harbor

    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    inner = harbor.harbor_executor

    def pricier_with_more_steps(req):
        r = inner(req)
        if req.skills:
            import json

            n = len(json.loads((Path(req.skills[0]) / "workflow.json").read_text())["steps"])
            r.agent_result.cost_usd = 0.01 * n
        return r

    monkeypatch.setattr(harbor, "harbor_executor", pricier_with_more_steps)
    wf = _starter(c, "Fix a bug")
    run = {"workflow": wf, "bench": "qa", "budget": 5, "auto": False}
    assert c.post("/api/lab/run", json=run, headers=ORIGIN).status_code == 200
    _wait(c, 1)
    before = len([q for q in calls if q.agent != "nop" and not q.skills])
    pre = c.post("/api/lab/ablate/preview", json=wf, headers=ORIGIN).json()
    assert pre["count"] == len(pre["variants"]) >= 2

    r = c.post(
        "/api/lab/ablate",
        json={"workflow": wf, "bench": "qa", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    jid = r.json()["id"]
    for _ in range(600):
        job = c.get(f"/api/lab/ablate/{jid}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    assert [v["status"] for v in job["variants"]] == ["done"] * pre["count"]
    after = len([q for q in calls if q.agent != "nop" and not q.skills])
    assert after == before, "a variant paid for the baseline again"
    con = job["contributions"]
    assert set(con) == {v["key"] for v in job["variants"]}
    assert all(v["marginal_pts"] == 0.0 for v in con.values())  # the fake gives every variant 100%
    drops = [v for v in job["variants"] if v["kind"] == "drop"]
    assert drops and all(con[v["key"]]["saved_cost_usd"] > 0 for v in drops)
    assert all(con[v["key"]]["verdict"] == "dead weight" for v in drops)
    assert job["spent_usd"] <= 5
    # one job at a time, and a stopped job skips the rest
    assert c.post(f"/api/lab/ablate/{jid}/stop", headers=ORIGIN).status_code == 404
    assert (
        c.post(
            "/api/lab/ablate",
            json={"workflow": _starter(c, "Refactor safely"), "bench": "qa"},
            headers=ORIGIN,
        ).status_code
        == 422
    )  # never measured: nothing to compare with


def test_stopping_a_job_stops_the_current_run_and_skips_the_rest():
    stopped, started = [], []

    def start(args):
        started.append(args["workflow"]["id"])
        return {"id": len(started)}

    jobs = ablation.Jobs(
        start=start,
        finished=lambda b, e: bool(stopped),  # runs until stopped
        spent=lambda b, e: 0.5,
        stop_run=lambda b, e: stopped.append(e) or True,
        busy=lambda: None,
        poll=0.01,
    )
    wf = _wf([("p", "think"), ("w", "do"), ("t", "check")])
    job = jobs.create(wf, "qa", 5.0, "claude-code")
    for _ in range(200):
        if started:
            break
        time.sleep(0.01)
    assert jobs.stop(job.id)
    for _ in range(200):
        if job.status != "running":
            break
        time.sleep(0.01)
    assert job.status == "stopped" and stopped == [1] and len(started) == 1
    st = [v["status"] for v in job.dump()["variants"]]
    assert st[0] == "stopped" and set(st[1:]) == {"skipped"}
    assert not jobs.stop(job.id)
