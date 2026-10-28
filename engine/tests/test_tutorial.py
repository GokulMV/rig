"""The tutorial's example space (tutorial skill): a tiny repo whose checks really tell a house-style
label from a guess, a recorded run that adds up, and an endpoint that reads only the example,
never the person's workspace, repos, runs or store."""

import shutil
import subprocess
from pathlib import Path

import pytest
from bench_solutions.tutorial_pricetags import GUESS, SOLUTION
from fastapi.testclient import TestClient

from proving_ground import skills, tutorial, validity
from proving_ground.api.app import create_app
from proving_ground.files import load_scenarios
from proving_ground.rig_score import R as RIG
from proving_ground.store import Store
from proving_ground.workspace import Workspace

BASE = "http://127.0.0.1:7357"
T = skills.load("tutorial").values


def _passes(tmp_path: Path, extra: str) -> dict[str, bool]:
    """Each task's check, run on a copy of the example repo with `extra` appended to tags.py."""
    repo = tmp_path / "pricetags"
    shutil.copytree(tutorial.PROJECT, repo)
    with (repo / "pricetags" / "tags.py").open("a", encoding="utf-8") as f:
        f.write(extra)
    out = {}
    for s in load_scenarios(repo):
        r = subprocess.run(["bash", "-c", s.check], cwd=repo, capture_output=True, text=True)
        out[s.id] = r.returncode == 0
    return out


def test_every_task_has_a_real_check_that_the_bare_repo_fails(tmp_path: Path):
    tasks = load_scenarios(tutorial.PROJECT)
    assert len(tasks) == 10
    assert not validity.broken_checks(tasks)
    assert set(_passes(tmp_path, "").values()) == {False}


def test_the_house_style_passes_every_check_and_a_guess_only_the_ones_the_code_shows(tmp_path: Path):
    assert all(_passes(tmp_path / "ref", SOLUTION).values())
    guessed = _passes(tmp_path / "guess", GUESS)
    # Only what the code alone shows the way to: a total is price() of a sum; a label read back.
    assert {k for k, ok in guessed.items() if ok} == {"total", "parse-price"}


def test_the_endpoint_serves_the_example_and_the_skills_words(tmp_path: Path):
    c = TestClient(create_app(tmp_path, home=tmp_path / "home"), base_url=BASE)
    b = c.get("/api/tutorial").json()
    assert [s["id"] for s in b["text"]["steps"]] == ["describe", "design", "build", "measure", "ship"]
    assert b["text"]["home"]["start"] == T["home"]["start"] == "Start the Tutorial"
    assert b["text"]["home"]["replay"] == "Replay the Tutorial"
    assert [o["label"] for o in b["text"]["finish"]["options"]] == [
        "Rig Your Own Repo",
        "Rig a Workflow",
        "Back to Home",
    ]
    assert [o["to"] for o in b["text"]["finish"]["options"]] == ["repo", "lab", "home"]
    ex = b["example"]
    assert ex["name"] == "pricetags"
    assert [f["path"] for f in ex["files"]] == list(tutorial.SHOWN)
    assert ex["skill"]["name"] == "price-tags-style"
    assert "-€3,00" in ex["skill"]["body"]
    assert len(ex["tasks"]) == 10 and all(t["check"] for t in ex["tasks"])


def _tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


def test_the_tutorial_never_reads_or_writes_the_workspace_repos_runs_or_store(
    tmp_path: Path, monkeypatch
):
    """Isolation: with a real repo attached and a run in its store, reading the tutorial leaves
    every file under the home, the workspace and the repo byte for byte as it was, and opening
    any store or workspace while it serves fails the test."""
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

    monkeypatch.setattr(Store, "for_project", touched)
    monkeypatch.setattr(Store, "__init__", touched)
    monkeypatch.setattr(Workspace, "repos", touched)
    monkeypatch.setattr(Workspace, "get", touched)
    monkeypatch.setattr(Workspace, "add", touched)
    r = c.get("/api/tutorial")
    assert r.status_code == 200, r.text
    monkeypatch.undo()

    assert _tree(tmp_path) == before
    assert c.get("/api/repos").json() == repos_before
    # Nothing of the example leaked into the person's space: no repo, no run.
    assert all(Path(x["root"]).resolve() != tutorial.PROJECT.resolve() for x in repos_before)
    assert Store.for_project(repo).list_experiments(store.ensure_project(str(repo))) == []


REC = tutorial.recorded()
needs_run = pytest.mark.skipif(REC is None, reason="no recorded run yet")


@needs_run
def test_the_recorded_run_adds_up_and_was_made_on_this_example():
    run = tutorial.run_view(REC)
    assert not run["stale"], "the example changed after the run: record it again"
    assert [t["id"] for t in run["tasks"]] == [s.id for s in load_scenarios(tutorial.PROJECT)]
    n = run["n"]
    assert n == len(run["tasks"]) * REC["repeats"]
    assert run["with"] == sum(t["with"]["passed"] for t in run["tasks"])
    assert run["without"] == sum(t["without"]["passed"] for t in run["tasks"])
    ld = run["ledger"]
    assert ld["total"] == 2 * n and ld["with"] == ld["without"] == n
    assert all(t[a]["trials"] == REC["repeats"] for t in run["tasks"] for a in ("with", "without"))
    # A free local model: the Cost part says so, and the score is the app's, with its five parts.
    rig = run["rig"]
    cost = next(p for p in rig["parts"] if p["id"] == "cost")
    assert cost["detail"] == RIG["text"]["cost"]["free"]
    assert [p["id"] for p in rig["parts"]] == ["lift", "cost", "followed", "holds_up", "reliable"]
    assert isinstance(rig["score"], int) and 0 <= rig["score"] <= 100
    assert REC["model"]["file"].endswith(".gguf")


@needs_run
def test_every_word_is_filled_once_a_run_is_recorded(tmp_path: Path):
    b = TestClient(create_app(tmp_path, home=tmp_path / "home"), base_url=BASE).get(
        "/api/tutorial"
    )
    text = b.json()["text"]

    def strings(v):
        if isinstance(v, str):
            yield v
        elif isinstance(v, list):
            for x in v:
                yield from strings(x)
        elif isinstance(v, dict):
            for x in v.values():
                yield from strings(x)

    # "{step}" alone is the page's to fill: which step it is on.
    left = [s for s in strings(text) if "{" in s.replace("{step}", "")]
    assert left == []
    assert "{step}" in text["eyebrow"]


def test_the_recorded_runs_are_served_in_todays_words_with_their_numbers_as_recorded():
    from proving_ground import rig_score
    from proving_ground.tutorial import fewer_tokens

    for view, rec in ((tutorial.view(), tutorial.recorded()), (fewer_tokens.view(), fewer_tokens.recorded())):
        served, kept = view["run"]["rig"], rec["rig"]
        assert [p["name"] for p in served["parts"]] == [rig_score.P[p["id"]]["name"] for p in kept["parts"]]
        assert served["verdict"]["word"] == rig_score.VD["words"][kept["verdict"]["id"]]
        assert served["label"].startswith(rig_score._band(kept["band"])["label"].split("{")[0])
        assert served["score"] == kept["score"]
        assert [p["score"] for p in served["parts"]] == [p["score"] for p in kept["parts"]]
    m = fewer_tokens.view()["run"]["rig"]["metric"]
    assert m["name"] == rig_score.M["names"]["tokens"] and m["headline"].startswith(m["name"] + ":")
