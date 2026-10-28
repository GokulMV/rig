from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from proving_ground.api.app import create_app
from proving_ground.files import save_scenario, save_workflow
from proving_ground.intake import run_intake
from proving_ground.models import Scenario, ScenarioKind, Workflow, treatment_from_path
from proving_ground.store import Store
from proving_ground.trial import TrialOutcome

BASE = "http://127.0.0.1:7357"
SKILL = "---\nname: release-notes\ndescription: Writes release notes\n---\nBody\n"


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


@pytest.fixture
def project(tmp_path: Path):
    root = tmp_path / "shop"
    write(
        root,
        {
            "app.py": "print('hi')\n",
            "pyproject.toml": "[project]\nname='shop'\ndependencies=['fastapi']\n",
            ".claude/skills/release-notes/SKILL.md": SKILL,
            ".proving-ground/checks/refund/check.sh": "set -e\ngrep -q ok out.txt\n",
            ".proving-ground/fixtures/refund/tickets.json": "[]\n",
            ".proving-ground/suggestions/support.yaml": "- name: tdd\n  kind: skill\n  why: Fixes need tests\n",
        },
    )
    user = tmp_path / "user-skills"
    write(user, {"tdd/SKILL.md": "---\nname: tdd\ndescription: Test first\n---\nx\n"})
    save_workflow(
        root,
        Workflow(id="support", name="Support", steps=[{"name": "fix", "type": "code"}]),
    )
    save_scenario(
        root,
        Scenario(
            id="refund",
            kind="typical",
            title="Refund",
            instruction="Refund T-1.",
            check="bash /tests/checks/refund/check.sh",
            step="fix",
            origin="generated",
        ),
    )
    store = Store.for_project(root)
    run_intake(store, root)
    return root, user


def client(root: Path, user: Path) -> TestClient:
    return TestClient(create_app(root, user_skills_dir=user), base_url=BASE)


def test_project_summary(project, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    root, user = project
    body = client(root, user).get("/api/project").json()
    assert body["name"] == "shop"
    assert body["key_set"] is False
    assert body["scan"]["languages"] == {"Python": 1}
    assert "FastAPI" in body["scan"]["stack"]
    assert body["scan"]["skills"] == [
        {
            "name": "release-notes",
            "description": "Writes release notes",
            "path": ".claude/skills/release-notes/SKILL.md",
        }
    ]
    assert body["sources"][0]["kind"] == "repo"
    assert body["counts"] == {
        "scenarios": 1,
        "approved": 0,
        "runnable": 0,
        "not_command": [],
        "workflows": 1,
        "experiments": 0,
    }
    assert body["use_case"] is None


def test_an_approved_scenario_with_prose_for_a_check_is_not_runnable(project):
    """evidence-validity: approved but its check isn't a command, so it counts as approved and
    never as runnable, with its name, wherever scenarios are counted."""
    from proving_ground import validity
    from proving_ground.files import load_scenarios, save_scenario
    from proving_ground.models import Scenario

    root, user = project
    save_scenario(
        root,
        Scenario(id="token-cost", title="Token cost", instruction="Keep it cheap.",
                 check="token cost", check_status="approved"),
    )
    counts = client(root, user).get("/api/project").json()["counts"]
    assert (counts["scenarios"], counts["approved"], counts["runnable"]) == (2, 1, 0)
    assert counts["not_command"] == ["Token cost"]
    save_scenario(
        root,
        Scenario(id="ok", title="Works", instruction="Do it.", check="pytest -q",
                 check_status="approved"),
    )
    items = load_scenarios(root)
    assert [s.id for s in items if validity.can_run(s)] == ["ok"]
    assert validity.counts(items) | {"scenarios": 0} == {
        "scenarios": 0, "approved": 2, "runnable": 1, "not_command": ["Token cost"]
    }


def test_scenarios_include_check_files_and_fixtures(project):
    root, user = project
    [s] = client(root, user).get("/api/scenarios").json()
    assert s["id"] == "refund" and s["check_status"] == "unreviewed" and s["runnable"] is False
    assert s["file"] == ".proving-ground/scenarios/refund.yaml"
    assert s["check_files"] == [
        {
            "path": ".proving-ground/checks/refund/check.sh",
            "content": "set -e\ngrep -q ok out.txt\n",
        }
    ]
    assert s["fixtures"] == [".proving-ground/fixtures/refund/tickets.json"]


def test_broken_scenario_file_is_a_422(project):
    root, user = project
    (root / ".proving-ground" / "scenarios" / "bad.yaml").write_text("id: [")
    r = client(root, user).get("/api/scenarios")
    assert r.status_code == 422
    assert "bad.yaml" in r.json()["detail"]


def test_workflows(project):
    root, user = project
    [w] = client(root, user).get("/api/workflows").json()
    assert w["id"] == "support" and w["steps"][0]["name"] == "fix"


def test_treatments_with_evidence(project):
    root, user = project
    store = Store.for_project(root)
    pid = store.ensure_project(str(root.resolve()))
    t = treatment_from_path(user / "tdd")
    eid = store.create_experiment(pid, t, "m", 2, 10.0, 0)
    for rep in range(4):
        for arm, outcome in (("with", "pass"), ("without", "fail")):
            store.record_trial(
                eid, TrialOutcome("refund", ScenarioKind.TYPICAL, arm, rep, outcome, cost_usd=0.1)
            )
    store.set_status(eid, "done")
    body = client(root, user).get("/api/treatments").json()
    assert [t["name"] for t in body["repo"]] == ["release-notes"]
    assert body["repo"][0]["path"] == str((root / ".claude/skills/release-notes").resolve())
    assert body["repo"][0]["evidence"] is None
    [tdd] = body["user"]
    assert tdd["evidence"]["experiment_id"] == eid
    assert tdd["evidence"]["verdict"] == "helps"
    assert body["suggested"] == [
        {"name": "tdd", "kind": "skill", "why": "Fixes need tests", "workflow": "support"}
    ]


def test_experiments_list_and_detail(project):
    root, user = project
    store = Store.for_project(root)
    pid = store.ensure_project(str(root.resolve()))
    eid = store.create_experiment(pid, treatment_from_path(user / "tdd"), "m", 1, 5.0, 0)
    store.record_trial(
        eid, TrialOutcome("refund", ScenarioKind.TYPICAL, "with", 0, "pass", cost_usd=0.25)
    )
    store.record_trial(
        eid, TrialOutcome("refund", ScenarioKind.TYPICAL, "without", 0, "fail", cost_usd=0.5)
    )
    c = client(root, user)
    [row] = c.get("/api/experiments").json()
    assert row["id"] == eid and row["treatment_name"] == "tdd" and row["spent_usd"] == 0.75
    assert row["verdict"] == "inconclusive"
    d = c.get(f"/api/experiments/{eid}").json()
    assert d["summary"]["verdict"] == "inconclusive"
    assert d["summary"]["headline"]["n_pairs"] == 1
    assert d["summary"]["cost_with"] == 0.25
    assert len(d["trials"]) == 2
    assert c.get("/api/experiments/99").status_code == 404


def test_doctor(project, monkeypatch):
    root, user = project
    monkeypatch.setattr(
        "proving_ground.api.app.run_checks",
        lambda runs_dir: [type("C", (), {"name": "Docker", "ok": True, "detail": "29.5"})()],
    )
    assert client(root, user).get("/api/doctor").json() == [
        {"name": "Docker", "ok": True, "detail": "29.5"}
    ]


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1.evil.example"])
def test_foreign_host_is_refused(project, host):
    root, user = project
    r = client(root, user).get("/api/project", headers={"host": host})
    assert r.status_code == 403


def test_writes_need_a_local_origin(project):
    root, user = project
    c = client(root, user)
    assert c.put("/api/usecase", json={"text": "x"}).status_code == 403
    bad = c.put("/api/usecase", json={"text": "x"}, headers={"origin": "https://evil.example"})
    assert bad.status_code == 403
    ok = c.put("/api/usecase", json={"text": "x"}, headers={"origin": "http://localhost:5173"})
    assert ok.status_code == 200


def test_only_skills_an_agent_loads_reach_the_canvas_and_an_older_scan_is_read_again(project):
    root, user = project
    write(
        root,
        {
            "engine/src/shop/skills/rig-score/SKILL.md": SKILL.replace(
                "release-notes", "rig-score"
            ),
            ".agents/skills/codex-notes/SKILL.md": SKILL.replace("release-notes", "codex-notes"),
        },
    )
    store = Store.for_project(root)
    pid = store.ensure_project(str(root.resolve()))
    # A scan from before the rule: it listed every SKILL.md.
    store.add_source(
        pid,
        "repo",
        f"{root.name}/",
        "old",
        {
            "languages": {"Python": 1},
            "skill_details": [
                {
                    "name": "rig-score",
                    "description": "",
                    "path": "engine/src/shop/skills/rig-score/SKILL.md",
                }
            ],
        },
    )
    c = client(root, user)
    names = [t["name"] for t in c.get("/api/treatments").json()["repo"]]
    assert names == ["codex-notes", "release-notes"]
    assert [s["name"] for s in c.get("/api/project").json()["scan"]["skills"]] == names


def test_a_go_skill_on_a_python_repo_is_marked_last_and_goes_with_the_agent_setup(project):
    root, user = project
    write(
        user,
        {
            "go-naming/SKILL.md": "---\nname: go-naming\ndescription: Go naming conventions for "
            "Go code.\n---\nx\n",
            "zz-tests/SKILL.md": "---\nname: zz-tests\ndescription: Test first.\n---\nx\n",
        },
    )
    c = client(root, user)
    mine = c.get("/api/treatments").json()["user"]
    assert [t["name"] for t in mine][-1] == "go-naming"
    assert mine[-1]["fit_note"] == "For Go; this repo has none."
    assert all("fit_note" not in t for t in mine[:-1])
    placed = c.post(
        "/api/place",
        json={
            "name": "go-naming",
            "description": "Go naming conventions for Go code.",
            "category": "skill",
        },
        headers={"origin": BASE},
    ).json()
    assert [t["id"] for t in placed["targets"]] == ["setup:CLAUDE.md"]
    assert placed["reason"].endswith("so it goes with CLAUDE.md. For Go; this repo has none.")
