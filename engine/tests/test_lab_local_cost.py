"""The Lab on a local model refuses cost as the metric, as a repo's Measure does: a local model
costs nothing, so there is nothing to compare. A single bench and a suite alike, refused before
anything runs or is written."""

from pathlib import Path

from test_api_workspace import ORIGIN
from test_bench import _lab_client, _starter, _wait

from proving_ground import local_models as lm

COST = lm.L["repo"]["cost_metric"]


def _local(tmp_path: Path) -> lm.LocalModel:
    reg = lm.Registry(tmp_path / "home" / "local-models.json")
    m = lm.make("http://127.0.0.1:11434", "qwen3:8b", "ollama")
    return reg.add(lm.LocalModel(m.id, m.label, m.base, m.model, m.kind, True))


def test_a_bench_run_on_a_local_model_is_refused_on_cost(tmp_path: Path, monkeypatch):
    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0, env={})
    m = _local(tmp_path)
    wf = _starter(c, "Fix a bug")
    body = {"workflow": wf, "bench": "qa", "budget": 5, "auto": False, "local_model": m.id}
    r = c.post("/api/lab/run", json=body | {"metric": "cost"}, headers=ORIGIN)
    assert r.status_code == 422 and r.json()["detail"] == COST
    assert calls == [] and not (tmp_path / "home" / "benches" / "qa" / ".proving-ground").exists()
    # Tokens and time still compare on one, and cost on the sign-in is untouched.
    r = c.post("/api/lab/run", json=body | {"metric": "tokens"}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert _wait(c, 1)[0]["metric"] == "tokens"


def test_a_suite_on_a_local_model_is_refused(tmp_path: Path, monkeypatch):
    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    m = _local(tmp_path)
    wf = _starter(c, "Fix a bug")
    body = {"workflow": wf, "budget": 5, "local_model": m.id}
    r = c.post("/api/lab/suite", json=body | {"metric": "cost"}, headers=ORIGIN)
    assert r.status_code == 422 and r.json()["detail"] == COST
    # Any other metric: a suite runs on the sign-in only, never silently there instead.
    r = c.post("/api/lab/suite", json=body | {"metric": "tokens"}, headers=ORIGIN)
    assert r.status_code == 422
    assert r.json()["detail"] == lm.L["suite_local"].format(agent="Claude Code")
    assert calls == []
    # The words the Lab shows before the start come with the local models.
    got = c.get("/api/local-models").json()
    assert got["repo"]["cost_metric"] == COST and got["suite_local"] == lm.L["suite_local"]
