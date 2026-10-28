"""Skills preloaded from GitHub (starter-skills): indexed, cached, used with no local skills,
and downloaded only when a workflow that uses one is saved."""

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
from test_api_workspace import BASE, ORIGIN
from test_catalog import FakeGitHub

from proving_ground import lab
from proving_ground.catalog import starter
from proving_ground.catalog.starter import StarterLibrary, _spread


def skill_md(name: str, desc: str, body: str = "Do it well.") -> str:
    return f"---\nname: {name}\ndescription: {desc}\n---\n{body}\n"


class StarterGitHub(FakeGitHub):
    def __init__(self):
        super().__init__()
        self.gets = 0
        self.down = False
        self.trees |= {
            "anthropics/skills": [
                "README.md",
                "skills/pdf/SKILL.md",
                "skills/pdf/forms.md",
                "skills/canvas-design/SKILL.md",
                "skills/canvas-design/fonts/Inter.ttf",  # not text: left out
                "template/SKILL.md",  # a scaffold: left out
            ],
            "obra/superpowers": [
                "skills/test-driven-development/SKILL.md",
                "skills/writing-plans/SKILL.md",
                "skills/requesting-code-review/SKILL.md",
            ],
        }
        self.files |= {
            "anthropics/skills:skills/pdf/SKILL.md": skill_md("pdf", "Read and fill PDF forms"),
            "anthropics/skills:skills/pdf/forms.md": "Forms detail.\n",
            "obra/superpowers:skills/test-driven-development/SKILL.md": skill_md(
                "test-driven-development",
                "Write the failing test first, then the code; tests before implementation",
                "Red, then green, then refactor.",
            ),
            "obra/superpowers:skills/writing-plans/SKILL.md": skill_md(
                "writing-plans", "Plan the work as small steps with an architecture sketch"
            ),
            "obra/superpowers:skills/requesting-code-review/SKILL.md": skill_md(
                "requesting-code-review", "Ask for a code-review of the diff for correctness"
            ),
        }

    def get(self, endpoint):
        self.gets += 1
        if self.down:
            raise RuntimeError("offline")
        return super().get(endpoint)


def test_index_is_built_and_cached(tmp_path: Path):
    gh = StarterGitHub()
    lib = StarterLibrary(lambda: gh, tmp_path / "starter.json")
    data = lib.load()
    by = {s["name"]: s for s in data["skills"]}
    assert set(by) == {"pdf", "test-driven-development", "writing-plans", "requesting-code-review"}
    tdd = by["test-driven-development"]
    assert tdd["source"] == "github" and tdd["repo"] == "obra/superpowers"
    assert tdd["folder"] == "skills/test-driven-development"
    assert tdd["path"] == "github:obra/superpowers/skills/test-driven-development"
    assert (
        tdd["url"] == "https://github.com/obra/superpowers/tree/HEAD/skills/test-driven-development"
    )
    assert data["failed"] == [] and lib.snapshot()["state"] == "ready"
    n = gh.gets
    StarterLibrary(lambda: gh, tmp_path / "starter.json").load()
    assert gh.gets == n  # from the cache
    cached = json.loads((tmp_path / "starter.json").read_text())
    cached["fetched_at"] = time.time() - starter.TTL_S - 1
    (tmp_path / "starter.json").write_text(json.dumps(cached))
    StarterLibrary(lambda: gh, tmp_path / "starter.json").load()
    assert gh.gets > n  # stale after the TTL


def test_a_long_repo_is_sampled_evenly():
    items = [f"s{i:03}" for i in range(100)]
    got = _spread(items, 4)
    assert got == ["s000", "s025", "s050", "s075"]
    assert _spread(items[:3], 4) == items[:3]


def test_offline_keeps_the_last_index_or_says_so(tmp_path: Path):
    gh = StarterGitHub()
    lib = StarterLibrary(lambda: gh, tmp_path / "starter.json")
    first = lib.load()
    gh.down = True
    again = lib.load(refresh=True)
    assert again["failed"] == starter.REPOS
    assert {s["name"] for s in again["skills"]} == {s["name"] for s in first["skills"]}
    snap = lib.snapshot()
    assert snap["state"] == "partial" and "showing the last list" in snap["note"]

    fresh = StarterLibrary(lambda: gh, tmp_path / "none.json").load()
    assert fresh["skills"] == [] and "offline" in fresh["error"]
    snap = StarterLibrary(lambda: gh, tmp_path / "none.json").snapshot()
    assert snap["state"] == "offline" and "Couldn't reach GitHub" in snap["note"]


def test_random_workflow_with_no_local_skills_uses_github_skills(tmp_path: Path):
    lib = StarterLibrary(StarterGitHub, tmp_path / "starter.json").load()["skills"]
    used = [
        s
        for seed in range(12)
        for st in lab.random_workflow(lib, "development", seed).steps
        for s in st.skills
    ]
    assert used and all(s["source"] == "github" and s["repo"] for s in used)
    assert any(s["name"] == "test-driven-development" for s in used)


def app(tmp_path: Path, gh) -> TestClient:
    from proving_ground.agents import Credentials
    from proving_ground.api.app import create_app
    from proving_ground.workspace import Workspace

    (tmp_path / "skills").mkdir(exist_ok=True)  # no local skills at all
    return TestClient(
        create_app(
            workspace=Workspace(tmp_path / "ws.json"),
            credentials=Credentials(env={}, home=tmp_path / "h"),
            github=gh,
            home=tmp_path / "home",
            user_skills_dir=tmp_path / "skills",
            web_dist=tmp_path / "nodist",
            host_login=lambda: None,
        ),
        base_url=BASE,
    )


def ready_lab(c: TestClient) -> dict:
    for _ in range(100):  # the index is fetched in the background on the first visit
        got = c.get("/api/lab").json()
        if got["skills_status"]["state"] != "loading":
            return got
        time.sleep(0.05)
    raise AssertionError("the GitHub index never finished")


def test_lab_lists_github_skills_and_installs_them_on_save(tmp_path: Path):
    gh = StarterGitHub()
    c = app(tmp_path, gh)
    data = ready_lab(c)
    assert data["skills_status"] == {"state": "ready", "note": None, "github": 4, "local": 0}
    assert all(s["source"] == "github" for s in data["skills"])
    wf = c.post(
        "/api/lab/random", json={"discipline": "development", "seed": 3}, headers=ORIGIN
    ).json()
    tdd = next(s for s in data["skills"] if s["name"] == "test-driven-development")
    wf["steps"][0]["skills"] = [{k: tdd[k] for k in ("path", "name", "source", "repo", "url")}]
    library = tmp_path / "home" / "library"
    assert not (library / "obra__superpowers__test-driven-development").exists()  # not yet

    r = c.post("/api/lab/save", json=wf, headers=ORIGIN)
    assert r.status_code == 200, r.text
    got = library / "obra__superpowers__test-driven-development"
    assert (got / "SKILL.md").read_text().startswith("---\nname: test-driven-development")
    out = Path(r.json()["path"])
    assert "Red, then green, then refactor." in (out / "SKILL.md").read_text()
    saved = json.loads((out / "workflow.json").read_text())
    assert saved["steps"][0]["skills"][0]["path"] == str(got.resolve())  # the downloaded copy

    # Downloaded once: listed from the library now, still marked as from GitHub, not twice.
    again = c.get("/api/lab").json()["skills"]
    assert [s["name"] for s in again].count("test-driven-development") == 1
    mine = next(s for s in again if s["name"] == "test-driven-development")
    assert mine["source"] == "github" and mine["path"] == str(got.resolve())
    n = gh.gets
    assert c.post("/api/lab/save", json=wf, headers=ORIGIN).status_code == 200
    assert gh.gets == n  # not downloaded again


def test_a_local_skill_wins_over_github_on_a_name_clash(tmp_path: Path):
    gh = StarterGitHub()
    c = app(tmp_path, gh)
    mine = tmp_path / "skills" / "tdd"
    mine.mkdir()
    (mine / "SKILL.md").write_text(skill_md("test-driven-development", "my own"))
    data = ready_lab(c)
    tdd = [s for s in data["skills"] if s["name"] == "test-driven-development"]
    assert len(tdd) == 1 and tdd[0]["source"] == "local" and tdd[0]["description"] == "my own"
    assert data["skills_status"]["local"] == 1 and data["skills_status"]["github"] == 3


def test_download_failures_are_clear(tmp_path: Path):
    gh = StarterGitHub()
    c = app(tmp_path, gh)
    ready_lab(c)
    wf = c.post(
        "/api/lab/random", json={"discipline": "development", "seed": 3}, headers=ORIGIN
    ).json()
    wf["steps"][0]["skills"] = [{"path": "github:evil/repo/skills/x", "name": "x"}]
    r = c.post("/api/lab/save", json=wf, headers=ORIGIN)
    assert r.status_code == 422 and "isn't one of the GitHub repositories" in r.json()["detail"]
    wf["steps"][0]["skills"] = [{"path": "github:obra/superpowers/../../etc", "name": "x"}]
    assert c.post("/api/lab/save", json=wf, headers=ORIGIN).status_code == 422
    wf["steps"][0]["skills"] = [
        {"path": "github:obra/superpowers/skills/writing-plans", "name": "writing-plans"}
    ]
    gh.down = True
    r = c.post("/api/lab/save", json=wf, headers=ORIGIN)
    assert (
        r.status_code == 502 and "Could not download the skill writing-plans" in r.json()["detail"]
    )


def test_a_skill_inside_a_test_fixture_folder_is_not_offered(tmp_path: Path):
    gh = StarterGitHub()
    gh.trees["obra/superpowers"].append("plugins/x/tests/fixtures/review-pr/SKILL.md")
    gh.files["obra/superpowers:plugins/x/tests/fixtures/review-pr/SKILL.md"] = skill_md("review-pr", "Fixture")
    names = {s["name"] for s in StarterLibrary(lambda: gh, tmp_path / "s.json").load()["skills"]}
    assert "test-driven-development" in names and "review-pr" not in names
