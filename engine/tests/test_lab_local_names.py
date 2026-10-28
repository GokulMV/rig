"""A Lab run on a local model is named by the model's label wherever the Lab names a run's model:
the live run's start, the results, the frontier, the comparison's standing and the bench's
"too easy" line. Its record keeps the id."""

from pathlib import Path

from test_api_workspace import ORIGIN
from test_bench import _lab_client, _starter, _wait

from proving_ground import local_models as lm


def test_a_local_run_is_named_by_its_label(tmp_path: Path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0, env={})
    reg = lm.Registry(tmp_path / "home" / "local-models.json")
    m = lm.make("http://127.0.0.1:11434", "qwen3:8b", "ollama")
    m = reg.add(lm.LocalModel(m.id, m.label, m.base, m.model, m.kind, True))
    shown = {"id": m.id, "label": "qwen3:8b · ollama"}
    wf = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "qa", "budget": 5, "auto": False, "local_model": m.id},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["model"] == m.id and r.json()["local_model"] == shown
    row = _wait(c, 1)[0]
    assert row["model"] == m.id and row["local_model"] == shown

    matrix = c.get("/api/lab/matrix", params={"bench": "qa"}).json()
    assert matrix["rows"][0]["local_model"] == shown

    # Ranked by its current (Claude) session model, the local result is another model's: named.
    got = c.post(
        "/api/lab/compare/standing", json={"bench": "qa", "workflows": [wf]}, headers=ORIGIN
    ).json()
    res = got["workflows"][0]["result"]
    assert res["local_model"] == shown
    assert res["other_model"]["label"] == "qwen3:8b · ollama (local)"
    assert "local:" not in res["other_model"]["text"]

    # Every trial passed both ways: too easy for the local model, said by its label.
    bench = next(b for b in c.get("/api/lab/benches").json() if b["id"] == "qa")
    seen = bench["baseline"]["standard"][m.id]
    assert seen["model_label"] == "qwen3:8b · ollama (local)"
    assert "local:" not in seen["text"]
