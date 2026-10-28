"""Try it on a local model, as Measure's run on one: Claude Code pointed at the local server, no
sign-in and no cost, a longer time limit, a skill handed over. Harbor is faked."""

from pathlib import Path

from test_tryit import ORIGIN, WF, api, wait  # noqa: F401  (api: the fixture)

from proving_ground import local_models as lm
from proving_ground import tryit


def add(home: Path, anthropic: bool = True) -> lm.LocalModel:
    reg = lm.Registry(home / "local-models.json")
    m = lm.make("http://127.0.0.1:11434", "qwen3:8b", "ollama")
    return reg.add(lm.LocalModel(m.id, m.label, m.base, m.model, m.kind, anthropic))


def test_a_repo_skill_is_tried_on_a_local_model_with_no_sign_in(api, monkeypatch):  # noqa: F811
    m = add(api.home)
    seen = {}  # read while the try's folders exist: they are removed when it ends

    def executor(req):
        seen["toml"] = (req.task_dir / "task.toml").read_text()
        seen["prompts"] = [p.name for p in (Path(req.trials_dir) / "prompts").glob("*.j2")]
        return api.ex(req)

    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", executor)
    body = {"skill_path": str(api.skill), "local_model": m.id}
    p = api.c.post("/api/try/price", json=body | {"n": 2, "budget_usd": 2}, headers=ORIGIN).json()
    assert p["free"] is True and p["total_usd"] == 0 and p["model"] == m.id
    assert p["model_label"] == "qwen3:8b · ollama (local)"
    # Nobody is signed in (api.creds has nothing): a local try still starts.
    r = api.c.post(
        "/api/try", json=body | {"inputs": ["Bug: two invoices"], "budget_usd": 2}, headers=ORIGIN
    )
    assert r.status_code == 202, r.text
    v = wait(api.c, r.json()["id"])
    assert v["status"] == "done" and v["model"] == m.id
    assert v["spent_usd"] == 0  # the fake agent reports $0.30
    req = api.ex.requests[0]
    assert dict(req.env)["ANTHROPIC_BASE_URL"] == "http://host.docker.internal:11434"
    assert dict(req.env)["ANTHROPIC_API_KEY"] == "local" and req.model == "qwen3:8b"
    # 3x the try's own time limit (try-it timeout_s, local-models timeout_factor).
    limit = tryit.T["timeout_s"] * lm.L["timeout_factor"]
    assert f"[agent]\ntimeout_sec = {limit}" in seen["toml"]
    # A small local model never opens a skill it is only offered: it is handed over.
    assert seen["prompts"] == ["tone.j2"]


def test_a_workflow_is_tried_on_a_local_model_too(api):  # noqa: F811
    m = add(api.home)
    body = {"workflow": WF, "local_model": m.id, "inputs": ["Refund please"], "budget_usd": 2}
    v = wait(api.c, api.c.post("/api/try", json=body, headers=ORIGIN).json()["id"])
    assert v["status"] == "done" and v["model"] == m.id


def test_a_local_try_is_refused_where_it_cant_run(api):  # noqa: F811
    body = {"skill_path": str(api.skill), "inputs": ["x"], "budget_usd": 2}
    r = api.c.post("/api/try", json=body | {"local_model": "local:nope"}, headers=ORIGIN)
    assert r.status_code == 404
    m = add(api.home, anthropic=False)
    r = api.c.post("/api/try", json=body | {"local_model": m.id}, headers=ORIGIN)
    assert r.status_code == 422 and "Anthropic's Messages API" in r.json()["detail"]
    m = add(api.home)
    r = api.c.post(
        "/api/try",
        json=body | {"local_model": m.id, "agent": "codex", "accept_no_cap": True},
        headers=ORIGIN,
    )
    assert r.status_code == 422
    assert api.ex.requests == []
