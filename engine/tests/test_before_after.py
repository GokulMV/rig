"""A code change measured before and after: two git snapshots as the two arms (beforeafter.py)."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from proving_ground import beforeafter, skills
from proving_ground.api.app import create_app
from proving_ground.beforeafter import BeforeAfterError, resolve
from proving_ground.files import ensure_pg_dir, save_scenario
from proving_ground.models import Scenario, TreatmentKind
from proving_ground.sandbox.snapshot import snapshot_rev

BASE = "http://127.0.0.1:7357"
ORIGIN = {"origin": BASE}
V = skills.value("measurability", "before_after")


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def make_repo(root: Path) -> Path:
    """v1 on main; a `split` branch that moves the limits into their own module."""
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    (root / "app.py").write_text("LIMIT = 100\n")
    (root / ".gitignore").write_text("build/\n")
    ensure_pg_dir(root)
    save_scenario(root, Scenario(id="a", instruction="Fix.", check="true", check_status="approved"))
    git(root, "add", "-A")
    git(root, "commit", "-qm", "v1")
    git(root, "checkout", "-q", "-b", "split")
    (root / "app.py").write_text("from limits import LIMIT\n")
    (root / "limits.py").write_text("LIMIT = 100\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "split the limits out")
    git(root, "checkout", "-q", "main")
    return root


def test_resolve_a_branch_names_both_sides_and_the_files(tmp_path: Path):
    root = make_repo(tmp_path / "repo")
    c = resolve(root, "HEAD", "split")
    assert c.base.sha == git(root, "rev-parse", "main")
    assert c.after.sha == git(root, "rev-parse", "split")
    assert c.files == ("app.py", "limits.py")
    assert c.base.label == f"HEAD ({c.base.sha[:7]})"
    assert c.after.label == f"split ({c.after.sha[:7]})"
    assert c.after.subject == "split the limits out"
    t = c.treatment(root)
    assert t.kind is TreatmentKind.BEFORE_AFTER and t.name == c.name
    assert resolve(root, "main", "split").treatment(root).content_hash == t.content_hash


def test_snapshots_are_each_commit_never_the_live_checkout(tmp_path: Path):
    root = make_repo(tmp_path / "repo")
    (root / "app.py").write_text("LIMIT = 'uncommitted'\n")
    c = resolve(root, "HEAD", "split")
    before = snapshot_rev(root, c.base.sha, tmp_path / "before")
    after = snapshot_rev(root, c.after.sha, tmp_path / "after")
    assert (before / "app.py").read_text() == "LIMIT = 100\n"
    assert not (before / "limits.py").exists()
    assert (after / "app.py").read_text() == "from limits import LIMIT\n"
    assert (after / "limits.py").is_file()
    assert not (before / ".proving-ground").exists() and not (after / ".proving-ground").exists()
    # The checkout is as it was: same branch, the edit still there, nothing staged.
    assert git(root, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert (root / "app.py").read_text() == "LIMIT = 'uncommitted'\n"


def test_the_working_tree_is_the_after_side_without_touching_the_index(tmp_path: Path):
    root = make_repo(tmp_path / "repo")
    (root / "app.py").write_text("LIMIT = 200\n")
    (root / "new.py").write_text("x = 1\n")
    (root / "build").mkdir()
    (root / "build" / "out.bin").write_text("ignored")
    status = git(root, "status", "--porcelain")
    c = resolve(root, "HEAD", None)
    assert c.after.sha is None and c.after.label == V["working_tree"]
    assert c.files == ("app.py", "new.py")  # build/ is ignored by git, so it's in neither arm
    snap = snapshot_rev(root, c.after.tree, tmp_path / "after")
    assert (snap / "app.py").read_text() == "LIMIT = 200\n"
    assert (snap / "new.py").is_file() and not (snap / "build").exists()
    assert git(root, "status", "--porcelain") == status  # nothing staged, nothing changed
    assert git(root, "diff", "--cached", "--name-only") == ""


def test_refusals_same_code_unknown_ref_and_not_git(tmp_path: Path):
    root = make_repo(tmp_path / "repo")
    with pytest.raises(BeforeAfterError, match="has the same code as"):
        resolve(root, "HEAD", "main")
    with pytest.raises(BeforeAfterError, match="has the same code as"):
        resolve(root, "HEAD", None)  # a clean checkout: nothing uncommitted
    # Only Rig's own folder changed: still the same code.
    (root / ".proving-ground" / "notes.txt").write_text("x")
    with pytest.raises(BeforeAfterError, match="has the same code as"):
        resolve(root, "HEAD", None)
    with pytest.raises(BeforeAfterError, match="isn't a commit or branch"):
        resolve(root, "HEAD", "no-such-branch")
    with pytest.raises(BeforeAfterError, match="isn't a commit or branch"):
        resolve(root, "--output=/tmp/x", "split")  # never an option to git
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "a.py").write_text("x")
    with pytest.raises(BeforeAfterError, match="isn't a git repo"):
        resolve(plain, "HEAD", None)
    assert beforeafter.refs(plain) == {"git": False, "says": V["not_git"]}
    # compare says "same" rather than refusing, so Measure can show both sides.
    same = beforeafter.compare(root, "HEAD", "main")
    assert same["same"] is True and same["says"].startswith("main (")


def test_refs_lists_head_branches_commits_and_dirty(tmp_path: Path):
    root = make_repo(tmp_path / "repo")
    r = beforeafter.refs(root)
    assert r["git"] is True and r["head"]["branch"] == "main" and r["dirty"] is False
    assert {b["name"] for b in r["branches"]} == {"main", "split"}
    assert [x["subject"] for x in r["commits"]] == ["v1"]
    (root / "app.py").write_text("changed\n")
    assert beforeafter.refs(root)["dirty"] is True


def fake_result(reward: float):
    return SimpleNamespace(
        exception_info=None,
        verifier_result=SimpleNamespace(rewards={"reward": reward}),
        agent_result=SimpleNamespace(n_input_tokens=10, n_output_tokens=5, cost_usd=0.1),
        started_at=None,
        finished_at=None,
        trial_name="t",
    )


def events(c: TestClient, eid: int) -> list[dict]:
    out = []
    with c.stream("GET", f"/api/experiments/{eid}/events") as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    root = make_repo(tmp_path / "repo")
    seen: list[tuple[str, str]] = []

    def executor(req):
        code = (req.task_dir / "environment" / "repo" / "app.py").read_text()
        seen.append((req.task_dir.parent.name, code))
        if req.agent == "nop":
            return fake_result(0.0)
        return fake_result(1.0 if req.task_dir.parent.name == "tasks-with" else 0.0)

    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", executor)
    return TestClient(create_app(root), base_url=BASE), root, seen


def test_api_runs_the_tasks_on_each_commit_and_keeps_the_kind(client):
    c, root, seen = client
    refs = c.get("/api/before-after/refs").json()
    assert refs["head"]["branch"] == "main"
    cmp = c.post(
        "/api/before-after/compare", json={"base": "HEAD", "after": "split"}, headers=ORIGIN
    ).json()
    assert cmp["same"] is False and cmp["files"] == ["app.py", "limits.py"]
    assert cmp["files_text"] == V["files"].format(n=2)
    body = {"before_after": {"base": "HEAD", "after": "split"}, "n": 4, "budget": 100}
    r = c.post("/api/experiments", json=body, headers=ORIGIN)
    assert r.status_code == 200, r.text
    started = r.json()
    assert started["before_after"]["after"]["sha"] == git(root, "rev-parse", "split")
    evs = events(c, started["id"])
    assert evs[-1]["type"] == "finished", evs[-1]
    # Every "without" trial ran the base code, every "with" trial the split, preflight on both.
    assert {code for arm, code in seen if arm == "tasks"} == {"LIMIT = 100\n"}
    assert {code for arm, code in seen if arm == "tasks-with"} == {"from limits import LIMIT\n"}
    meta = json.loads((root / ".proving-ground" / "runs" / "1" / "meta.json").read_text())
    assert meta["commit"] == git(root, "rev-parse", "main") and meta["dirty"] is False
    assert meta["before_after"]["base"]["sha"] == meta["commit"]
    assert meta["before_after"]["after"]["working_tree"] is False
    d = c.get(f"/api/experiments/{started['id']}").json()
    assert d["treatment_kind"] == "before_after"
    assert d["before_after"]["n_files"] == 2
    assert d["summary"]["verdict"] == "helps"
    fol = next(p for p in d["rig"]["parts"] if p["id"] == "followed")
    assert fol["score"] is None and "in the code itself" in fol["detail"]
    row = next(x for x in c.get("/api/experiments").json() if x["id"] == started["id"])
    assert row["before_after"]["after"]["label"].startswith("split (")
    # The checkout is untouched.
    assert git(root, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert (root / "app.py").read_text() == "LIMIT = 100\n"


def test_api_measures_the_uncommitted_working_tree(client):
    c, root, seen = client
    (root / "app.py").write_text("LIMIT = 'edited'\n")
    body = {"before_after": {"base": "HEAD", "after": None}, "n": 2, "budget": 100}
    r = c.post("/api/experiments", json=body, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert events(c, r.json()["id"])[-1]["type"] == "finished"
    assert {code for arm, code in seen if arm == "tasks-with"} == {"LIMIT = 'edited'\n"}
    assert {code for arm, code in seen if arm == "tasks"} == {"LIMIT = 100\n"}
    d = c.get(f"/api/experiments/{r.json()['id']}").json()
    assert d["before_after"]["after"]["working_tree"] is True
    assert d["before_after"]["after"]["label"] == V["working_tree"]


def test_api_refuses_before_writing_anything(client, tmp_path: Path, monkeypatch):
    c, root, _ = client
    for after, why in (("main", "has the same code as"), ("nope", "isn't a commit or branch")):
        body = {"before_after": {"base": "HEAD", "after": after}, "n": 2, "budget": 100}
        r = c.post("/api/experiments", json=body, headers=ORIGIN)
        assert r.status_code == 422 and why in r.json()["detail"]
    assert (
        c.post("/api/before-after/compare", json={"after": "nope"}, headers=ORIGIN).status_code
        == 422
    )
    r = c.post("/api/experiments", json={"n": 2, "budget": 100}, headers=ORIGIN)
    assert r.status_code == 422 and "Pick a change" in r.json()["detail"]
    assert c.get("/api/experiments").json() == []
    assert not (root / ".proving-ground" / "runs").exists()
    # A folder that isn't a git repo: nothing to measure before and after.
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "a.py").write_text("x")
    save_scenario(
        plain, Scenario(id="a", instruction="Fix.", check="true", check_status="approved")
    )
    pc = TestClient(create_app(plain), base_url=BASE)
    assert pc.get("/api/before-after/refs").json()["git"] is False
    body = {"before_after": {"base": "HEAD", "after": None}, "n": 2, "budget": 100}
    r = pc.post("/api/experiments", json=body, headers=ORIGIN)
    assert r.status_code == 422 and "isn't a git repo" in r.json()["detail"]


def test_a_check_the_after_code_passes_alone_tests_nothing(client, monkeypatch):
    c, root, _ = client

    def executor(req):  # the split already makes the check pass, with no agent at all
        return fake_result(1.0 if req.task_dir.parent.name == "tasks-with" else 0.0)

    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", executor)
    body = {"before_after": {"base": "HEAD", "after": "split"}, "n": 2, "budget": 100}
    r = c.post("/api/experiments", json=body, headers=ORIGIN)
    assert r.status_code == 200, r.text
    last = events(c, r.json()["id"])[-1]
    assert last["type"] == "error" and "pass with no agent" in last["detail"]
    assert c.get(f"/api/experiments/{r.json()['id']}").json()["status"] == "failed_preflight"
