import base64
import json
import time
from pathlib import Path

import pytest

from proving_ground.catalog import (
    Catalog,
    install_skill,
    list_skills,
    rank,
    theme_of,
)


def repo(name, stars, pushed="2026-10-01T00:00:00Z", desc="", topics=()):
    return {
        "full_name": name,
        "name": name.split("/")[1],
        "owner": {"login": name.split("/")[0]},
        "html_url": f"https://github.com/{name}",
        "description": desc,
        "stargazers_count": stars,
        "pushed_at": pushed,
        "topics": list(topics),
        "archived": False,
    }


class FakeGitHub:
    def __init__(self):
        self.calls = []
        self.search_results = {
            "skill": [
                repo(
                    "anthropics/skills",
                    180000,
                    desc="Official agent skills",
                    topics=["agent-skills"],
                ),
                repo(
                    "acme/test-first",
                    900,
                    desc="TDD and testing skills",
                    topics=["agent-skills", "testing"],
                ),
                repo(
                    "tiny/fastapi-helper",
                    3,
                    pushed="2026-10-20T00:00:00Z",
                    desc="FastAPI endpoint skill",
                    topics=["agent-skills"],  # found by its topic: that says it's for agents
                ),
            ],
            "harness": [
                repo(
                    "loops/ralph",
                    5000,
                    desc="Autonomous agent loop harness",
                    topics=["agent-harness"],
                )
            ],
            "workflow": [repo("flows/spec-driven", 7000, desc="Spec-driven multi-agent workflow")],
            "agent": [
                repo("crew/reviewers", 1200, desc="Subagents for code review in Claude Code")
            ],
            "mcp": [
                repo("pg/mcp-postgres", 3000, desc="MCP server for Postgres"),
                repo("off/topic", 9000, desc="A todo app"),
            ],
            "hook": [repo("hooks/guard", 400, desc="Claude Code hooks that block risky commands")],
            "eval": [repo("bench/swe-mini", 800, desc="A small SWE-bench style eval suite")],
        }
        self.trees = {
            "acme/test-first": [
                "README.md",
                "skills/tdd/SKILL.md",
                "skills/tdd/ref.md",
                "skills/review/SKILL.md",
            ],
        }
        self.files = {
            "acme/test-first:skills/tdd/SKILL.md": "---\nname: tdd\ndescription: Test first\n---\nWrite the test.\n",
            "acme/test-first:skills/tdd/ref.md": "More detail.\n",
            "acme/test-first:skills/review/SKILL.md": "---\nname: review\ndescription: Review diffs\n---\nx\n",
        }

    def search(self, query, sort, per_page):
        self.calls.append(query)
        for cat, kws in (
            ("skill", "skills"),
            ("harness", "harness"),
            ("workflow", "workflow"),
            ("agent", "subagents"),
            ("mcp", "mcp-server"),
            ("hook", "hooks"),
            ("eval", "evaluation"),
        ):
            if kws in query or (cat == "skill" and "agent-skills" in query):
                return self.search_results[cat]
        return []

    def get(self, endpoint):
        if endpoint.startswith("repos/") and "/git/trees/" in endpoint:
            name = "/".join(endpoint.split("/")[1:3])
            return {
                "tree": [{"path": p, "type": "blob", "size": 100} for p in self.trees.get(name, [])]
            }
        if "/contents/" in endpoint:
            name = "/".join(endpoint.split("/")[1:3])
            path = endpoint.split("/contents/", 1)[1]
            text = self.files[f"{name}:{path}"]
            return {"content": base64.b64encode(text.encode()).decode(), "encoding": "base64"}
        if endpoint.startswith("repos/"):
            name = "/".join(endpoint.split("/")[1:3])
            return {"default_branch": "main", "full_name": name}
        raise KeyError(endpoint)


def test_builds_categories_and_caches(tmp_path: Path):
    gh = FakeGitHub()
    cat = Catalog(gh, cache=tmp_path / "catalog.json")
    items = cat.items()
    by = {i["id"]: i for i in items}
    assert by["anthropics/skills"]["category"] == "skill"
    assert by["loops/ralph"]["category"] == "harness"
    assert by["flows/spec-driven"]["category"] == "workflow"
    n = len(gh.calls)
    Catalog(gh, cache=tmp_path / "catalog.json").items()
    assert len(gh.calls) == n  # served from the cache
    data = json.loads((tmp_path / "catalog.json").read_text())
    data["fetched_at"] = time.time() - 2 * 86400
    (tmp_path / "catalog.json").write_text(json.dumps(data))
    Catalog(gh, cache=tmp_path / "catalog.json").items()
    assert len(gh.calls) > n  # stale after a day


def test_views_and_relevance(tmp_path: Path):
    items = Catalog(FakeGitHub(), cache=tmp_path / "c.json").items()
    skills = [i for i in items if i["category"] == "skill"]
    assert [i["id"] for i in rank(skills, "stars")][0] == "anthropics/skills"
    assert [i["id"] for i in rank(skills, "latest")][0] == "tiny/fastapi-helper"
    rel = rank(skills, "relevant", terms={"fastapi", "python"})
    assert rel[0]["id"] == "tiny/fastapi-helper"  # 3 stars, but it matches this project
    assert all(i["relevance"] > 0 for i in rel)
    assert rank(skills, "recommended")[0]["id"] == "anthropics/skills"


def test_themes():
    assert (
        theme_of({"name": "x", "description": "TDD and testing skills", "topics": []})
        == "Testing & quality"
    )
    assert theme_of({"name": "x", "description": "nothing special", "topics": []}) == "General"


def test_lists_skills_in_a_repo():
    skills = list_skills(FakeGitHub(), "acme/test-first")
    assert [(s["path"], s["name"], s["description"]) for s in skills] == [
        ("skills/review", "review", "Review diffs"),
        ("skills/tdd", "tdd", "Test first"),
    ]


def test_installs_one_skill_folder(tmp_path: Path):
    path = install_skill(FakeGitHub(), "acme/test-first", "skills/tdd", tmp_path / "library")
    assert path == tmp_path / "library" / "acme__test-first__tdd"
    assert (path / "SKILL.md").read_text().startswith("---\nname: tdd")
    assert (path / "ref.md").read_text() == "More detail.\n"
    assert json.loads((path / ".source.json").read_text())["repo"] == "acme/test-first"


@pytest.mark.parametrize("bad", ["../x", "/etc", "skills/missing"])
def test_refuses_bad_skill_paths(tmp_path: Path, bad):
    with pytest.raises(ValueError):
        install_skill(FakeGitHub(), "acme/test-first", bad, tmp_path / "library")


def test_theme_words_match_whole_words():
    assert (
        theme_of({"name": "x", "description": "docker deploy helpers", "topics": []})
        == "DevOps & cloud"
    )
    assert theme_of({"name": "x", "description": "spec-driven development", "topics": []}) == (
        "Planning & orchestration"
    )


def test_failed_searches_make_a_short_lived_partial_catalog(tmp_path: Path):
    gh = FakeGitHub()
    real = gh.search

    def flaky(query, sort, per_page):
        if "harness" in query:
            raise RuntimeError("rate limited")
        return real(query, sort, per_page)

    gh.search = flaky
    cat = Catalog(gh, cache=tmp_path / "c.json")
    data = cat.load()
    assert data["partial"] is True and data["failed"] > 0
    assert not any(i["category"] == "harness" for i in data["items"])
    saved = json.loads((tmp_path / "c.json").read_text())
    saved["fetched_at"] = time.time() - 15 * 60  # older than the partial TTL
    (tmp_path / "c.json").write_text(json.dumps(saved))
    gh.search = real
    assert any(i["category"] == "harness" for i in Catalog(gh, cache=tmp_path / "c.json").items())


def test_agents_mcp_hooks_and_evals_are_categories_too(tmp_path: Path):
    by = {i["id"]: i for i in Catalog(FakeGitHub(), cache=tmp_path / "c.json").items()}
    assert by["crew/reviewers"]["category"] == "agent"
    assert by["pg/mcp-postgres"]["category"] == "mcp"
    assert by["hooks/guard"]["category"] == "hook"
    assert by["bench/swe-mini"]["category"] == "eval"
    assert "off/topic" not in by  # tagged mcp-server but says nothing about MCP


def test_for_this_repo_matches_whole_words_and_weighs_frameworks():
    from proving_ground.catalog import project_terms, rank, relevance

    terms = project_terms(["Spring Boot", "GitHub Actions"], {"Java": 10, "JavaScript": 2}, None)
    assert "actions" not in terms and "github-actions" not in terms
    resume = {"name": "reactive-resume", "description": "A resume builder", "topics": ["javascript"],
              "stars": 45000, "pushed_at": "2026-10-24"}  # fmt: skip
    spring = {"name": "nerviz", "description": "Agent harness for Spring Boot", "topics": ["spring-boot"],
              "stars": 40, "pushed_at": "2026-10-20"}  # fmt: skip
    # "java" does not match inside "javascript"; one language alone isn't enough.
    assert relevance(resume, {"java"}) == 0
    assert relevance(resume, terms) == 1
    assert relevance(spring, terms) >= 2
    assert relevance({**spring, "topics": []}, terms) == 2  # "Spring Boot" in the description
    assert [i["name"] for i in rank([resume, spring], "relevant", terms)] == ["nerviz"]


def test_per_repo_search_keeps_off_topic_repos_out(tmp_path: Path):
    gh = FakeGitHub()
    gh.search_results["skill"].append(repo("resume/builder", 45000, desc="A resume builder"))
    items = Catalog(gh, cache=tmp_path / "c.json").for_project({"fastapi"})
    assert "resume/builder" not in {i["id"] for i in items}


def test_a_cache_from_before_a_category_was_added_is_fetched_again(tmp_path: Path):
    """The real catalog once kept only three categories for a day after four more were added."""
    import json
    import time

    cache = tmp_path / "catalog.json"
    # Fresh, but written before the categories were recorded (or with fewer of them).
    cache.write_text(
        json.dumps({"fetched_at": time.time(), "items": [], "partial": False, "failed": 0})
    )
    gh = FakeGitHub()
    items = Catalog(gh, cache=cache).items()
    assert gh.calls and items
    calls = len(gh.calls)
    Catalog(gh, cache=cache).items()  # now it records its categories: served from the cache
    assert len(gh.calls) == calls


def test_pinned_repositories_are_listed_even_when_search_misses_them(tmp_path: Path):
    class WithPinned(FakeGitHub):
        def get(self, endpoint):
            if endpoint == "repos/SWE-bench/SWE-bench":
                return repo("SWE-bench/SWE-bench", 4000, desc="Can language models resolve issues?")
            if endpoint == "repos/disler/claude-code-hooks-mastery":
                return repo("disler/claude-code-hooks-mastery", 2000) | {"archived": True}
            if endpoint.startswith("repos/") and endpoint.count("/") == 2:
                raise RuntimeError("Not Found")
            return super().get(endpoint)

    data = Catalog(WithPinned(), tmp_path / "c.json").load()
    by_id = {i["id"]: i for i in data["items"]}
    # Pinned skips the must-mention filter, keeps its own category, and is marked.
    assert by_id["SWE-bench/SWE-bench"]["category"] == "eval"
    assert by_id["SWE-bench/SWE-bench"]["pinned"] is True
    assert "disler/claude-code-hooks-mastery" not in by_id  # archived
    # A pinned repository that is gone is skipped without making the catalog partial.
    assert data["partial"] is False


def test_a_harness_repository_opens_as_its_parts_with_the_links_its_text_shows():
    from proving_ground.catalog import repo_parts

    gh = FakeGitHub()
    gh.trees["loops/ralph"] = [
        "README.md",
        "CLAUDE.md",
        ".claude/commands/ship.md",
        ".claude/agents/planner.md",
        ".claude/agents/reviewer.md",
        "skills/tdd/SKILL.md",
        "hooks/guard.sh",
        ".mcp.json",
        "tests/agents/fake.md",
    ]
    gh.files.update(
        {
            "loops/ralph:CLAUDE.md": "Use /ship.",
            "loops/ralph:.claude/commands/ship.md": "---\ndescription: Ship a change\n---\nAsk the planner, then the reviewer.",
            "loops/ralph:.claude/agents/planner.md": "---\nname: planner\ndescription: Plans\n---\nUse the tdd skill.",
            "loops/ralph:.claude/agents/reviewer.md": "---\nname: reviewer\n---\nReads diffs.",
            "loops/ralph:skills/tdd/SKILL.md": "---\nname: tdd\n---\nTest first.",
            "loops/ralph:hooks/guard.sh": "#!/bin/sh\n",
            "loops/ralph:.mcp.json": "{}",
        }
    )
    got = repo_parts(gh, "loops/ralph")
    kinds = [p["kind"] for p in got["parts"]]
    # In flow order, tests left out.
    assert kinds == ["instructions", "command", "agent", "agent", "skill", "hook", "mcp"]
    by_name = {p["name"]: p["id"] for p in got["parts"]}
    assert got["parts"][1]["description"] == "Ship a change"
    assert got["parts"][1]["url"].startswith("https://github.com/loops/ralph/blob/main/")
    links = {(a["from"], a["to"]) for a in got["links"]}
    assert (by_name["ship"], by_name["planner"]) in links
    assert (by_name["ship"], by_name["reviewer"]) in links
    # "tdd" is under four letters: too short to count as a mention.
    assert all(t != by_name["tdd"] for _, t in links)
    assert got["more"] == 0
