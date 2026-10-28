from pathlib import Path

from test_architecture import TOOL, write

from proving_ground.architecture import infer_architecture
from proving_ground.generate.client import ToolCall
from proving_ground.recommend import draft, needs_for, rough, save_draft, with_model


class FakeModel:
    def __init__(self, out):
        self.out, self.calls = out, []

    def call(self, prompt, tool, model, max_tokens):
        self.calls.append((prompt, tool["name"], model))
        return ToolCall(self.out, "tool_use", 1, 1)


ITEMS = [
    {
        "id": "a/resume",
        "name": "reactive-resume",
        "description": "A resume builder in JavaScript",
        "topics": ["javascript"],
        "stars": 45000,
    },
    {
        "id": "b/claude-retry",
        "name": "claude-retry",
        "description": "Retry and timeout patterns for Anthropic Claude API calls",
        "topics": [],
        "stars": 120,
    },
    {
        "id": "c/refund",
        "name": "refund-tests",
        "description": "Write tests for refund rules before changing them",
        "topics": [],
        "stars": 30,
    },
]


def needs(tmp_path):
    write(tmp_path, TOOL)
    return needs_for(
        infer_architecture(tmp_path),
        [("fix", "code", "Change the refund rules"), ("deploy", "test", "")],
        ["Refund over the limit escalates"],
        ["Move model calls off the request path"],
        ["old-tdd"],
        "Fix refund bugs without breaking limits",
    )


def test_needs_come_from_the_project_not_the_language(tmp_path: Path):
    n = needs(tmp_path)
    texts = [x.text for x in n]
    assert "calls Claude API" in texts and any(t.startswith("step 'fix'") for t in texts)
    assert "a better version of old-tdd, which didn't help when measured here" in texts
    assert not any("python" in x.terms or "javascript" in x.terms for x in n)


def test_rough_picks_serve_a_need_and_skip_popular_misfits(tmp_path: Path):
    out = rough(
        needs(tmp_path), ITEMS, [{"path": "/s/old-tdd", "name": "old-tdd", "description": ""}]
    )
    ids = [p["id"] for p in out["picks"]]
    assert "a/resume" not in ids  # 45k stars, serves nothing here
    assert "b/claude-retry" in ids and "c/refund" in ids
    assert all(p["need"] and p["why"] for p in out["picks"])
    # A step nothing serves gets a skill to create; a skill that didn't help gets a rewrite.
    assert any(c["name"] == "deploy-here" for c in out["create"])
    assert out["improve"][0]["path"] == "/s/old-tdd" and out["basis"] == "rough"


def test_model_picks_are_checked_against_the_candidates(tmp_path: Path):
    m = FakeModel(
        {
            "picks": [
                {
                    "id": "b/claude-retry",
                    "need": "calls Claude API",
                    "why": "the API calls Claude inline",
                },
                {"id": "ghost/x", "need": "x", "why": "invented"},
            ],
            "create": [
                {
                    "name": "refund-limits-here",
                    "need": "step 'fix'",
                    "what": "the plan limits",
                    "why": "none exists",
                },
                {"name": "Bad Name!", "need": "", "what": "", "why": ""},
            ],
            "improve": [
                {"path": "/s/old-tdd", "need": "x", "how": "use pytest -q", "why": "didn't help"},
                {"path": "/elsewhere", "need": "", "how": "", "why": ""},
            ],
        }
    )
    out = with_model(
        m, needs(tmp_path), ITEMS, [{"path": "/s/old-tdd", "name": "old-tdd"}], "Skills"
    )
    assert [p["id"] for p in out["picks"]] == ["b/claude-retry"]
    assert [c["name"] for c in out["create"]] == ["refund-limits-here"]
    assert [c["path"] for c in out["improve"]] == ["/s/old-tdd"]
    assert m.calls[0][2] == "claude-haiku-5-5"  # picking uses the cheapest tier


def test_draft_and_save_a_new_version(tmp_path: Path):
    assert "Template" in draft(None, "deploy-here", "step 'deploy'", "how to deploy")
    m = FakeModel({"skill_md": "---\nname: deploy-here\ndescription: x\n---\n# Deploy\n"})
    text = draft(m, "deploy-here", "n", "w", "repo summary", base="old text")
    assert text.startswith("---") and "old text" in m.calls[0][0].content[0]["text"]
    a = save_draft(tmp_path, "deploy-here", text)
    b = save_draft(tmp_path, "deploy-here", text, improves=str(a))
    assert a.name == "deploy-here" and b.name == "deploy-here-v2" and (b / "SKILL.md").is_file()


def test_recommend_api_without_a_model(tmp_path: Path):
    from fastapi.testclient import TestClient
    from test_api_workspace import BASE, ORIGIN
    from test_catalog import FakeGitHub

    from proving_ground.agents import Credentials
    from proving_ground.api.app import create_app

    write(tmp_path / "tool", TOOL)
    c = TestClient(
        create_app(
            root=tmp_path / "tool",
            credentials=Credentials(env={}, home=tmp_path / "h"),
            github=FakeGitHub(),
            home=tmp_path / "home",
            user_skills_dir=tmp_path / "none",
            web_dist=tmp_path / "nodist",
            host_login=lambda: None,
        ),
        base_url=BASE,
    )
    c.get("/api/catalog")  # starts the catalog build
    import time

    for _ in range(50):
        if not c.get("/api/catalog").json().get("loading"):
            break
        time.sleep(0.05)
    r = c.get("/api/recommend", params={"category": "skill"}).json()
    assert r["basis"] == "rough" and r["creatable"] is True
    assert any(n["text"] == "calls Claude API" for n in r["needs"])
    d = c.post(
        "/api/draft", json={"name": "api-here", "need": "x", "what": "y"}, headers=ORIGIN
    ).json()
    assert "Template" in d["text"]
    saved = c.post(
        "/api/draft/save", json={"name": "api-here", "text": d["text"]}, headers=ORIGIN
    ).json()
    assert saved["name"] == "api-here"
    t = c.get("/api/treatments").json()
    assert [x["name"] for x in t["created"]] == ["api-here"] and t["created"][0][
        "source"
    ] == "created here"


GO_NAMING = {
    "id": "infiniflow/ragflow:go-naming",
    "name": "go-naming",
    "description": "Go naming conventions. Use this skill when working with Go code.",
}


def test_a_skill_for_a_language_the_repo_has_none_of_is_not_a_fit():
    from proving_ground.recommend import fitting, item_languages, language_note

    assert item_languages("go-naming", GO_NAMING["description"]) == ["Go"]
    # One capitalised "Go" at the start of a sentence is not a Go skill.
    assert item_languages("tidy", "Go through each file and tidy it.") == []
    py_ts = {"Python": 400, "TypeScript": 99}
    assert language_note("go-naming", GO_NAMING["description"], py_ts) == (
        "For Go; this repo has none."
    )
    assert language_note("go-naming", GO_NAMING["description"], {"Go": 3}) is None
    # A JavaScript skill fits a TypeScript repo; one for several languages fits any of them.
    assert language_note("node-tips", "JavaScript and Node.js tips", {"TypeScript": 9}) is None
    assert language_note("polyglot", "Rules for Go and Python and Python", py_ts) is None
    other = {"id": "a/tdd", "name": "tdd", "description": "Write a failing test first."}
    assert fitting([GO_NAMING, other], py_ts) == [other]
    assert fitting([GO_NAMING, other], {}) == [GO_NAMING, other]  # nothing known: nothing ruled out
