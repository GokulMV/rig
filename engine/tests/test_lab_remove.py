import threading
from pathlib import Path

from test_api_workspace import ORIGIN
from test_bench import _lab_client, _starter, _wait


def test_saved_list_holds_only_what_you_saved_and_can_be_cleared(tmp_path: Path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    a = _starter(c, "Fix a bug")
    # A measured run compiles the workflow too, but that isn't saving it.
    c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "qa", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    _wait(c, 1)
    assert c.get("/api/lab").json()["saved"] == []
    c.post("/api/lab/save", json=a, headers=ORIGIN)
    assert [w["id"] for w in c.get("/api/lab").json()["saved"]] == [a["id"]]
    # Measuring a saved workflow compiles it again: it stays saved.
    c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "qa", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    _wait(c, 2)
    assert [w["id"] for w in c.get("/api/lab").json()["saved"]] == [a["id"]]
    assert c.delete(f"/api/lab/saved/{a['id']}", headers=ORIGIN).status_code == 200
    assert c.get("/api/lab").json()["saved"] == []
    assert c.delete(f"/api/lab/saved/{a['id']}", headers=ORIGIN).status_code == 404


def test_a_measured_result_can_be_forgotten(tmp_path: Path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    a = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "qa", "budget": 5, "auto": False},
        headers=ORIGIN,
    ).json()
    _wait(c, 1)
    assert c.delete(f"/api/lab/results/qa/{r['id']}", headers=ORIGIN).status_code == 200
    assert c.get("/api/lab/results").json() == []
    assert c.delete(f"/api/lab/results/qa/{r['id']}", headers=ORIGIN).status_code == 404


def test_a_run_stops_after_the_trial_in_progress(tmp_path: Path, monkeypatch):
    gate = threading.Event()
    started = threading.Event()

    def reward(req):
        started.set()
        gate.wait(5)  # hold the first trial until the stop is asked for
        return 1.0

    c, calls = _lab_client(tmp_path, monkeypatch, reward)
    a = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "bugfix", "budget": 5, "auto": True},
        headers=ORIGIN,
    ).json()
    assert started.wait(5)
    s = c.post(f"/api/lab/runs/bugfix/{r['id']}/stop", headers=ORIGIN)
    assert s.status_code == 200
    gate.set()
    events = c.get(f"/api/lab/runs/bugfix/{r['id']}/events").text
    assert '"type": "stopped"' in events
    ran = [q for q in calls if q.agent != "nop"]
    assert len(ran) == 1  # the one in progress finished; nothing after it
    assert c.post(f"/api/lab/runs/bugfix/{r['id']}/stop", headers=ORIGIN).status_code == 404


def test_only_added_benches_can_be_removed(tmp_path: Path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 0.0)
    assert c.delete("/api/lab/benches/bugfix", headers=ORIGIN).status_code == 422
    suite = tmp_path / "suite" / "t1"
    (suite / "environment").mkdir(parents=True)
    (suite / "tests").mkdir()
    for f, t in {"task.toml": "", "instruction.md": "Do it.", "tests/test.sh": "true"}.items():
        (suite / f).write_text(t)
    c.post(
        "/api/lab/benches/import", json={"path": str(suite.parent), "name": "Mine"}, headers=ORIGIN
    )
    assert any(b["id"] == "imp-mine" for b in c.get("/api/lab/benches").json())
    assert c.delete("/api/lab/benches/imp-mine", headers=ORIGIN).status_code == 200
    assert not any(b["id"] == "imp-mine" for b in c.get("/api/lab/benches").json())
