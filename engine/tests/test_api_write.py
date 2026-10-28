import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from proving_ground.api.app import create_app
from proving_ground.files import save_scenario
from proving_ground.generate.client import GenerationError, ToolCall
from proving_ground.models import Scenario

BASE = "http://127.0.0.1:7357"
ORIGIN = {"origin": BASE}
MIX = "typical=1,failure=1,imaginary=1"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "shop"
    r.mkdir()
    (r / "app.py").write_text("print('hi')\n")
    return r


def client(root: Path) -> TestClient:
    return TestClient(create_app(root, user_skills_dir=root / "none"), base_url=BASE)


def test_intake_scans_the_repo(root):
    c = client(root)
    assert c.get("/api/project").json()["scanned"] is False
    body = c.post("/api/intake", headers=ORIGIN).json()
    assert body["scanned"] is True and body["scan"]["languages"] == {"Python": 1}


def test_upload_sources(root, tmp_path):
    c = client(root)
    files = [
        ("files", ("notes.md", b"# Refunds\nOver $1,000 needs a manager.\n", "text/markdown")),
        ("files", ("../../evil.md", b"# x\n", "text/markdown")),
        ("files", ("tool.exe", b"MZ", "application/octet-stream")),
    ]
    body = c.post("/api/sources", files=files, headers=ORIGIN).json()
    assert body["added"] == [["md", "notes.md"], ["md", "evil.md"]]
    assert body["skipped"] == ["tool.exe"]
    up = root / ".proving-ground" / "uploads"
    assert sorted(p.name for p in up.iterdir()) == ["evil.md", "notes.md"]
    assert not (tmp_path / "evil.md").exists()
    assert "uploads/" in (root / ".proving-ground" / ".gitignore").read_text()
    kinds = {(s["kind"], s["name"]) for s in c.get("/api/project").json()["sources"]}
    assert ("md", "notes.md") in kinds


def test_generate_dry_run_and_errors(root, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    c = client(root)
    r = c.post("/api/generate", json={"mix": MIX, "dry_run": True}, headers=ORIGIN)
    assert r.status_code == 422 and "pg intake" not in r.json()["detail"]
    c.put("/api/usecase", json={"text": "Handle refunds."}, headers=ORIGIN)
    body = c.post("/api/generate", json={"mix": MIX, "dry_run": True}, headers=ORIGIN).json()
    assert body["included"] == ["usecase:use-case"]
    assert body["model"] == "claude-opus-5-5" and body["tokens_est"] > 1000
    assert body["mix"] == {"typical": 1, "failure": 1, "imaginary": 1}
    bad = c.post("/api/generate", json={"mix": "nope=1", "dry_run": True}, headers=ORIGIN)
    assert bad.status_code == 422 and "bad mix entry" in bad.json()["detail"]
    nokey = c.post("/api/generate", json={"mix": MIX}, headers=ORIGIN)
    assert nokey.status_code == 400 and "Anthropic API key" in nokey.json()["detail"]


def test_generate_writes_and_reports_problems(root, monkeypatch, plan_data):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    calls = []

    class Fake:
        def call(self, prompt, tool, model, max_tokens):
            calls.append(model)
            return ToolCall(copy.deepcopy(plan_data), "tool_use", 100, 200)

    monkeypatch.setattr("proving_ground.generate.client.make_client", Fake)
    c = client(root)
    c.put("/api/usecase", json={"text": "Handle refunds."}, headers=ORIGIN)
    body = c.post(
        "/api/generate", json={"mix": MIX, "model": "claude-sonnet-5-5"}, headers=ORIGIN
    ).json()
    assert calls == ["claude-sonnet-5-5"]
    assert body["workflow"]["id"] == "support"
    assert [s["id"] for s in body["scenarios"]] == [
        "refund-basic",
        "config-missing",
        "future-scale",
    ]
    assert body["tokens"] == {"in": 100, "out": 200}
    again = c.post("/api/generate", json={"mix": MIX}, headers=ORIGIN)
    assert again.status_code == 422
    assert "already exists" in " ".join(again.json()["problems"])

    def fails():
        class F:
            def call(self, *a):
                raise GenerationError("The Claude API call failed: overloaded")

        return F()

    monkeypatch.setattr("proving_ground.generate.client.make_client", fails)
    r = c.post("/api/generate", json={"mix": "edge=1"}, headers=ORIGIN)
    assert r.status_code == 502 and "overloaded" in r.json()["detail"]


def test_generate_writes_from_a_draft_goal_without_saving_it(root, monkeypatch, plan_data):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    prompts = []

    class Fake:
        def call(self, prompt, tool, model, max_tokens):
            prompts.append(prompt.content[0]["text"])
            return ToolCall(copy.deepcopy(plan_data), "tool_use", 100, 200)

    monkeypatch.setattr("proving_ground.generate.client.make_client", Fake)
    c = client(root)
    # No saved goal yet: the draft alone is enough to write from (dry run and real).
    est = c.post(
        "/api/generate",
        json={"mix": MIX, "dry_run": True, "use_case": "Ship invoices."},
        headers=ORIGIN,
    ).json()
    assert est["included"] == ["usecase:use-case"]
    c.put("/api/usecase", json={"text": "Handle refunds."}, headers=ORIGIN)
    body = c.post(
        "/api/generate", json={"mix": MIX, "use_case": "  Ship invoices on time.  "}, headers=ORIGIN
    ).json()
    assert "Ship invoices on time." in prompts[0] and "Handle refunds." not in prompts[0]
    # Written for the draft: not "goal changed" against it, but against the saved goal it is.
    assert all(s["goal_changed"] is False for s in body["scenarios"])
    listed = c.get("/api/scenarios").json()
    assert listed and all(s["goal_changed"] is True for s in listed)
    # Nothing persisted: the saved goal and the sources are as they were.
    project = c.get("/api/project").json()
    assert project["use_case"] == "Handle refunds."
    assert sum(s["kind"] == "usecase" for s in project["sources"]) == 1
    # Blank means the saved goal (the plan's ids are taken by now; the prompt was still sent).
    c.post("/api/generate", json={"mix": "edge=1", "use_case": "  "}, headers=ORIGIN)
    assert "Handle refunds." in prompts[-1] and "Ship invoices" not in prompts[-1]


def test_approve(root):
    save_scenario(root, Scenario(id="a", instruction="x", check="true"))
    save_scenario(root, Scenario(id="b", instruction="x"))
    c = client(root)
    ok = c.post("/api/scenarios/a/approve", headers=ORIGIN).json()
    assert ok["check_status"] == "approved" and ok["runnable"] is True
    assert c.post("/api/scenarios/b/approve", headers=ORIGIN).status_code == 422
    assert c.post("/api/scenarios/zz/approve", headers=ORIGIN).status_code == 404


def test_a_goal_from_a_template_keeps_its_metric(root):
    from proving_ground import skills

    c = client(root)
    t = next(x for x in skills.value("repo-goals", "templates") if x["id"] == "fewer-tokens")
    got = c.put("/api/usecase", json={"text": t["text"], "template": t["id"]}, headers=ORIGIN)
    assert got.json()["goal_metric"] == "tokens"
    p = c.get("/api/project").json()
    assert (p["goal_template"], p["goal_metric"]) == ("fewer-tokens", "tokens")
    # Words added after the template's text keep it; a rewrite drops it, and so does a typed goal.
    more = t["text"] + " Mostly in the refund code."
    c.put("/api/usecase", json={"text": more, "template": t["id"]}, headers=ORIGIN)
    assert c.get("/api/project").json()["goal_metric"] == "tokens"
    c.put("/api/usecase", json={"text": "Cut tokens.", "template": t["id"]}, headers=ORIGIN)
    p = c.get("/api/project").json()
    assert (p["goal_template"], p["goal_metric"]) == (None, None)
    c.put("/api/usecase", json={"text": t["text"]}, headers=ORIGIN)
    assert c.get("/api/project").json()["goal_metric"] is None
    # An unknown template is just a typed goal.
    c.put("/api/usecase", json={"text": t["text"], "template": "nope"}, headers=ORIGIN)
    assert c.get("/api/project").json()["goal_template"] is None


def test_the_web_reads_the_shared_rules(root):
    from proving_ground import skills

    c = client(root)
    m = c.get("/api/rules/measurability").json()
    assert m == skills.load("measurability").values
    g = c.get("/api/rules/repo-goals").json()
    assert {"agent_words", "templates", "metrics"} <= set(g)
    assert {t["metric"] for t in g["templates"]} <= set(g["metrics"])
    assert 4 <= len(g["templates"]) <= 6
    assert "token" in g["agent_words"] and "cost" in g["agent_words"]
    # Only those two: no other skill's values (prompts, keys of other rules) through here.
    assert c.get("/api/rules/rig-score").status_code == 404


def test_a_prose_check_is_rewritten_as_a_command(root):
    c = client(root)
    save_scenario(
        root,
        Scenario(id="token-cost", title="Token cost", kind="typical", instruction="Keep it down.",
                 check="the agent should reduce the token cost", origin="user", check_status="approved"),
    )  # fmt: skip
    before = next(s for s in c.get("/api/scenarios").json() if s["id"] == "token-cost")
    assert before["check_problem"]
    bad = c.put("/api/scenarios/token-cost/check", json={"check": "reduce the tokens"}, headers=ORIGIN)
    assert bad.status_code == 422 and "isn't a command" in bad.json()["detail"]
    ok = c.put("/api/scenarios/token-cost/check", json={"check": "pytest -q"}, headers=ORIGIN)
    assert ok.status_code == 200 and ok.json()["check"] == "pytest -q"
    after = next(s for s in c.get("/api/scenarios").json() if s["id"] == "token-cost")
    assert after["check_problem"] is None and after["runnable"] is True
    assert c.put("/api/scenarios/nope/check", json={"check": "pytest"}, headers=ORIGIN).status_code == 404
