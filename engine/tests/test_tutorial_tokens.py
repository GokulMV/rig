"""The repo tutorial (tutorial-tokens skill): a tiny repo whose checks really tell a done task from
an untouched one, a recorded run scored on tokens that adds up, words filled from the app's own
skills, and an endpoint that reads only the example, never the person's workspace, repos, runs
or store."""

import shutil
import subprocess
from pathlib import Path

import pytest
from bench_solutions.tutorial_textkit import SOLUTION
from fastapi.testclient import TestClient

from proving_ground import rig_score, skills, validity
from proving_ground.api.app import create_app
from proving_ground.files import load_scenarios
from proving_ground.store import Store
from proving_ground.tutorial import fewer_tokens
from proving_ground.workspace import Workspace

BASE = "http://127.0.0.1:7357"
STEPS = ["describe", "design", "build", "measure", "ship"]


def _passes(tmp_path: Path, solved: bool) -> dict[str, bool]:
    repo = tmp_path / "textkit"
    shutil.copytree(fewer_tokens.PROJECT, repo)
    if solved:
        for mod, extra in SOLUTION.items():
            with (repo / "textkit" / f"{mod}.py").open("a", encoding="utf-8") as f:
                f.write(extra)
    out = {}
    for s in load_scenarios(repo):
        r = subprocess.run(["bash", "-c", s.check], cwd=repo, capture_output=True, text=True)
        out[s.id] = r.returncode == 0
    return out


def test_every_task_names_its_file_and_has_a_real_check(tmp_path: Path):
    tasks = load_scenarios(fewer_tokens.PROJECT)
    assert len(tasks) == 10
    assert not validity.broken_checks(tasks)
    # The skill's first rule rests on it: each task says which file to change.
    assert all("textkit/" in s.instruction for s in tasks)
    assert set(_passes(tmp_path / "bare", False).values()) == {False}
    assert all(_passes(tmp_path / "ref", True).values())


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)


def test_the_endpoint_serves_the_example_with_the_apps_own_labels(tmp_path: Path):
    c = TestClient(create_app(tmp_path, home=tmp_path / "home"), base_url=BASE)
    b = c.get("/api/tutorial/tokens").json()
    text = b["text"]
    assert [s["id"] for s in text["steps"]] == STEPS
    assert all(s["yours"] for s in text["steps"])
    assert text["home"]["start"] == "Start the Repo Tutorial"
    # The goal template, the badges and the guard's pairs come from their own skills.
    goal = next(t for t in skills.value("repo-goals", "templates") if t["id"] == "fewer-tokens")
    describe = text["steps"][0]
    assert describe["goal"] == goal["text"] and goal["label"] in describe["template"]
    states = skills.value("measurability", "states")
    badges = {p["badge"] for p in text["steps"][2]["places"]}
    assert {states["runnable"]["label"], states["same"]["label"]} <= badges
    assert str(rig_score.metric_guard_pairs()) in text["home"]["lead"]
    assert [o["to"] for o in text["finish"]["options"]] == ["repo", "first", "home"]
    ex = b["example"]
    assert ex["name"] == "textkit" and ex["skill"]["name"] == "lean-context"
    assert [f["path"] for f in ex["files"]] == list(fewer_tokens.SHOWN)
    assert len(ex["tasks"]) == 10
    # The first track is unchanged beside it.
    assert c.get("/api/tutorial").json()["example"]["name"] == "pricetags"


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_it_never_reads_or_writes_the_workspace_repos_runs_or_store(tmp_path: Path, monkeypatch):
    repo = tmp_path / "mine"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("print('mine')\n")
    store = Store.for_project(repo)
    store.ensure_project(str(repo))
    ws = Workspace(tmp_path / "workspace.json")
    ws.add(repo)
    app = create_app(workspace=ws, home=tmp_path / "home", user_skills_dir=tmp_path / "skills")
    c = TestClient(app, base_url=BASE)
    repos_before = c.get("/api/repos").json()
    before = _tree(tmp_path)

    def touched(*_a, **_k):
        raise AssertionError("the tutorial opened the person's store or workspace")

    for name in ("for_project", "__init__"):
        monkeypatch.setattr(Store, name, touched)
    for name in ("repos", "get", "add"):
        monkeypatch.setattr(Workspace, name, touched)
    r = c.get("/api/tutorial/tokens")
    assert r.status_code == 200, r.text
    monkeypatch.undo()
    assert _tree(tmp_path) == before
    assert c.get("/api/repos").json() == repos_before
    assert Store.for_project(repo).list_experiments(store.ensure_project(str(repo))) == []


def test_with_no_run_recorded_it_says_so(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(fewer_tokens, "RECORDED", tmp_path / "none.json")
    v = fewer_tokens.view()
    assert v["run"] is None
    assert "No run has been recorded" in v["text"]["not_recorded"]


REC = fewer_tokens.recorded()
needs_run = pytest.mark.skipif(REC is None, reason="no recorded run yet")


@needs_run
def test_the_recorded_run_adds_up_and_was_scored_on_tokens():
    run = fewer_tokens.run_view(REC)
    assert not run["stale"], "the example changed after the run: record it again"
    assert [t["id"] for t in run["tasks"]] == [s.id for s in load_scenarios(fewer_tokens.PROJECT)]
    n = run["n"]
    assert n == len(run["tasks"]) * REC["repeats"]
    # Enough pairs for the guard, as the tutorial tells people to plan.
    assert n >= rig_score.metric_guard_pairs()
    assert run["with"] == sum(t["with"]["passed"] for t in run["tasks"])
    assert run["without"] == sum(t["without"]["passed"] for t in run["tasks"])
    ld = run["ledger"]
    assert ld["total"] == 2 * n and ld["with"] == ld["without"] == n
    # Scored on tokens, by the app, from tokens every trial reported.
    assert REC["metric"] == "tokens"
    m = run["metric"]
    assert m["id"] == "tokens" and m["n"] == n
    assert all(x > 0 for t in run["tasks"] for a in ("with", "without") for x in t[a]["tokens"])
    rig = run["rig"]
    assert [p["id"] for p in rig["parts"]] == ["lift", "cost", "followed", "holds_up", "reliable"]
    assert isinstance(rig["score"], int) and 0 <= rig["score"] <= 100
    assert REC["model"]["file"].endswith(".gguf")


@needs_run
def test_every_word_is_filled_and_the_brief_follows_the_verdict():
    v = fewer_tokens.view()
    left = [s for s in _strings(v["text"]) if "{" in s.replace("{step}", "")]
    assert left == []
    ship = v["text"]["steps"][-1]
    helps = v["run"]["rig"]["verdict"]["id"] == "helps"
    assert ship["brief"][0].startswith("Add the skill" if helps else "Leave the skill")
