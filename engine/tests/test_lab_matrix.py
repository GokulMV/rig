"""The Lab matrix: every workflow measured on one bench, per task, with held-out titles hidden."""

from pathlib import Path

from test_api_workspace import ORIGIN
from test_bench import _lab_client, _starter, _wait


def test_matrix_is_empty_before_a_run_and_404s_an_unknown_bench(tmp_path: Path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 0.0)
    m = c.get("/api/lab/matrix", params={"bench": "qa"}).json()
    assert m["rows"] == [] and m["latest"] is None and len(m["tasks"]) >= 2
    assert all(t["id"] and t["title"] for t in m["tasks"])
    assert c.get("/api/lab/matrix", params={"bench": "nope"}).status_code == 404


def test_matrix_reports_each_workflow_per_task_against_the_baseline(tmp_path: Path, monkeypatch):
    # The workflow passes every task it is handed to; the baseline passes none.
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    a = _starter(c, "Fix a bug")
    assert (
        c.post(
            "/api/lab/run",
            json={"workflow": a, "bench": "qa", "budget": 5, "auto": False},
            headers=ORIGIN,
        ).status_code
        == 200
    )
    results = _wait(c, 1)
    m = c.get("/api/lab/matrix", params={"bench": "qa"}).json()
    assert m["bench"] == "qa" and len(m["rows"]) == 1 and m["latest"]
    row = m["rows"][0]
    assert row["experiment_id"] == results[0]["id"]
    assert row["workflow"] == "Fix a bug" and row["agent"] == "claude-code"
    assert row["diff"] == 1.0 and row["pass_with"] == 1.0 and row["pass_without"] == 0.0
    assert row["n_pairs"] >= 1 and row["ci_low"] is not None and row["ci_high"] is not None
    assert row["cost_per_trial_usd"] == 0.02  # the fake agent reports $0.02 a trial
    assert row["mean_duration_s"] is not None
    # Every task the workflow ran has its own rates, and the baseline shows zero on each.
    assert row["per_task"]
    for sid, cell in row["per_task"].items():
        assert sid in {t["id"] for t in m["tasks"]}
        assert cell["with"] == 1.0 and cell["without"] == 0.0 and cell["n"] >= 1


def test_matrix_hides_held_out_titles_but_keeps_their_column(tmp_path: Path, monkeypatch):
    c, _ = _lab_client(
        tmp_path,
        monkeypatch,
        lambda req: 1.0 if req.skills and "q4-batch" not in str(req.task_dir) else 0.0,
    )
    a = _starter(c, "Fix a bug")
    c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "finance", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    _wait(c, 1)
    m = c.get("/api/lab/matrix", params={"bench": "finance"}).json()
    hidden = [t for t in m["tasks"] if t["title"] == "Held-out task"]
    assert len(hidden) == 1 and hidden[0]["id"].startswith("held-out-")
    assert "q4" not in str(m)
    cell = m["rows"][0]["per_task"][hidden[0]["id"]]
    assert cell["with"] == 0.0 and cell["without"] == 0.0
