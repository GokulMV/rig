"""A Lab run's metric, as a repo run's: chosen on Measure, kept in the run's meta.json, scored on
in its Rig score, and a full run on a saving sized for the pass-rate guard."""

import json
from types import SimpleNamespace

from test_api_workspace import ORIGIN
from test_bench import _lab_client, _starter, _wait

import proving_ground.runner.harbor as harbor
from proving_ground import rig_score


def tokens_fake(req):
    """Every task passes both ways; the workflow uses a third of the tokens."""
    tokens = 0 if req.agent == "nop" else 10_000 if req.skills else 30_000
    return SimpleNamespace(
        exception_info=None,
        verifier_result=SimpleNamespace(rewards={"reward": 0.0 if req.agent == "nop" else 1.0}),
        agent_result=SimpleNamespace(n_input_tokens=tokens, n_output_tokens=0, cost_usd=0.02),
        started_at=None,
        finished_at=None,
        trial_name="fake",
    )


def lab_meta(tmp_path, bench: str, eid: int) -> dict:
    run = tmp_path / "home" / "benches" / bench / ".proving-ground" / "runs" / str(eid)
    return json.loads((run / "meta.json").read_text())


def test_a_lab_run_on_tokens_is_kept_and_scored_on_tokens(tmp_path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    monkeypatch.setattr(harbor, "harbor_executor", tokens_fake)
    wf = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "bugfix", "budget": 5, "auto": False, "metric": "tokens"},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["metric"] == "tokens"
    row = _wait(c, 1)[0]
    assert lab_meta(tmp_path, "bugfix", row["id"])["metric"] == "tokens"
    assert row["metric"] == "tokens"
    m = row["rig"]["metric"]
    assert m["id"] == "tokens" and abs(m["ratio"] - 1 / 3) < 0.01
    assert m["headline"].startswith("Tokens per Solved Task: with ")
    # A pilot is too few pairs for the guard: no saving is credited yet.
    assert m["noninferior"] is False
    # The run's own page (Runs) carries the same.
    one = c.get(f"/api/lab/results/bugfix/{row['id']}").json()
    assert one["metric"] == "tokens" and one["rig"]["metric"]["id"] == "tokens"


def test_a_lab_run_is_on_the_pass_rate_by_default(tmp_path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    wf = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "bugfix", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    row = _wait(c, 1)[0]
    assert lab_meta(tmp_path, "bugfix", row["id"])["metric"] == "pass_rate"
    assert row["metric"] == "pass_rate" and "metric" not in row["rig"]
    assert c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "bugfix", "budget": 5, "metric": "vibes"},
        headers=ORIGIN,
    ).status_code == 422  # fmt: skip


def test_a_full_lab_run_on_a_saving_plans_the_guards_pairs(tmp_path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    wf = _starter(c, "Fix a bug")
    tasks = len(next(b for b in c.get("/api/lab/benches").json() if b["id"] == "bugfix")["scenarios"])
    need = rig_score.metric_guard_pairs()
    body = {"pairs": tasks, "agent": "claude-code", "bench": "bugfix", "workflow": wf, "tasks": tasks}
    est = c.post(
        "/api/runs/estimate",
        json=body | {"size": "full", "budget": 500, "metric": "time"},
        headers=ORIGIN,
    ).json()
    plain = c.post(
        "/api/runs/estimate", json=body | {"size": "full", "budget": 500}, headers=ORIGIN
    ).json()
    # The estimate and the start plan the same pairs: whole repeats reaching the guard's, more
    # than the pass rate's own full run.
    assert est["pairs"] >= need > plain["pairs"] and est["metric_plan"]["enough"] is True
    r = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "bugfix", "budget": 500, "size": "full", "auto": False, "metric": "time"},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["trials"] == 2 * est["pairs"]
    c.post(f"/api/lab/runs/bugfix/{r.json()['id']}/stop", headers=ORIGIN)
    _wait(c, 1)
