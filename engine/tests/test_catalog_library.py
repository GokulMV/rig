"""The Library's catalog: which kind a repository is, search, and Recommended for this project.

Fixtures are real items from the GitHub catalog cache (tests/fixtures/catalog_real_sample.json),
as fetched: their `category` is the first search that found them, before best-match classification.
"""

import json
import re
from pathlib import Path

import pytest

from proving_ground import skills
from proving_ground.catalog import (
    classify,
    page,
    project_terms,
    rank,
    reclassified,
    search,
    word_match,
)

REAL = json.loads((Path(__file__).parent / "fixtures" / "catalog_real_sample.json").read_text())
BY = {i["id"]: i for i in REAL["items"]}


@pytest.mark.parametrize(
    "repo, was, now",
    [
        # Hooks listed a harness, a design tool and desktop apps.
        ("gaia-react/gaia", "hook", "harness"),  # "A serious harness for Claude Code"
        ("mikesheehan54/Claude-Code-Design-AI", "hook", None),  # a UI/UX design generator
        ("Abhi24384/Anthropic-Mythos-Desktop-Studio", "hook", None),  # a desktop client
        ("aofp/yume", "hook", None),  # "Native desktop UI for Claude Code"
        # Harness listed a website skill.
        (
            "nateherkai/scroll-craft",
            "harness",
            "skill",
        ),  # "An agent skill for building ... websites"
        # Agents listed desktop apps and stand-alone coding agents.
        ("NanmiCoder/cc-haha", "agent", None),  # a desktop workbench
        ("KunAgent/Kun", "agent", None),  # "Local-first AI agent workspace"
        ("YaoApp/yao", "agent", None),
        ("QwenLM/qwen-code", "agent", None),  # a coding agent, not one you add
        ("career-ops-hq/career-ops", "skill", None),  # a job-search agent
        # Best match, not the first search that found it.
        ("kenryu42/cc-safety-net", "harness", "hook"),  # blocks destructive commands
        ("thedotmack/claude-mem", "skill", "harness"),  # memory across sessions
        ("shinpr/claude-code-workflows", "agent", "workflow"),
        ("Pseudogiant-xr/Pseudolife-MCP", "harness", "mcp"),
        # Right already, and kept.
        ("karanb192/claude-code-hooks", "hook", "hook"),
        ("liberzon/claude-hooks", "hook", "hook"),  # a PreToolUse hook
        ("VoltAgent/awesome-claude-code-subagents", "agent", "agent"),
        ("rockscy/shipcrew", "agent", "agent"),
        ("github/github-mcp-server", "mcp", "mcp"),
        ("ChromeDevTools/chrome-devtools-mcp", "mcp", "mcp"),  # "mcp" in the name only
        ("anthropics/skills", "skill", "skill"),
        ("mattpocock/evalite", "eval", "eval"),
        ("harbor-framework/harbor", "eval", "eval"),
        ("renzrollon/interlock", "workflow", "workflow"),  # "Spec-driven development"
    ],
)
def test_a_repository_goes_to_the_kind_it_matches_best(repo, was, now):
    item = BY[repo]
    assert item["category"] == was  # as the old first-search-wins rule filed it
    assert classify(item) == now


def test_a_tie_goes_to_the_first_kind_listed():
    item = {"name": "x", "description": "Hooks and skills for Claude Code", "topics": []}
    assert classify(item) == "skill"  # skill comes before hook in the list


def test_hooks_need_the_agentic_sense():
    assert (
        classify({"name": "use-hooks", "description": "React hooks for forms", "topics": []})
        is None
    )
    assert (
        classify({"name": "x", "description": "Git hooks for Claude Code", "topics": []}) == "hook"
    )


def test_a_cached_catalog_is_reclassified_and_pinned_repositories_keep_their_kind():
    data = {"fetched_at": 1.0, "items": REAL["items"]}
    got = {i["id"]: i for i in reclassified(data)["items"]}
    assert got["gaia-react/gaia"]["category"] == "harness"
    assert "aofp/yume" not in got
    # wshobson/agents is pinned as an agent; its text alone reads as a harness.
    assert classify(BY["wshobson/agents"]) == "harness"
    assert got["wshobson/agents"]["category"] == "agent" and got["wshobson/agents"]["pinned"]


# ---------- Search ----------


def ids(items):
    return [i["id"] for i in items]


def test_search_finds_a_theme_by_its_name():
    """'code review' found nothing while a Code review theme was on screen."""
    items = reclassified({"fetched_at": 2.0, "items": REAL["items"]})["items"]
    got = search(items, "code review")
    assert got, "the Code review theme's items"
    assert got[0]["id"] == "alibaba/open-code-review"  # both words in its name
    # Every hit is about review (the theme's words), not merely "Claude Code".
    rx = re.compile(r"\b(review\w*|pr|pull requests?|diffs?)\b")
    assert all(
        rx.search(f"{i['name']} {i['description']} {' '.join(i['topics'])}".lower()) for i in got
    )


def test_search_puts_a_name_match_before_a_description_match():
    """'rag' listed apple-design ("drag") and pick-ui-library above rag-engineer."""
    items = [
        {
            "id": "a/apple-design",
            "name": "apple-design",
            "description": "Drag, swipe and sheet interactions",
            "topics": [],
        },
        {
            "id": "a/pick-ui-library",
            "name": "pick-ui-library",
            "description": "Pick a UI library; uses RAG notes",
            "topics": [],
        },
        {
            "id": "a/rag-engineer",
            "name": "rag-engineer",
            "description": "Retrieval-Augmented Generation systems",
            "topics": [],
        },
        {
            "id": "a/ragflow",
            "name": "ragflow",
            "description": "An open-source engine",
            "topics": [],
        },
    ]
    got = ids(search(items, "rag"))
    assert got[:2] == ["a/rag-engineer", "a/ragflow"]  # name word, then name prefix
    assert "a/apple-design" not in got  # "drag" is not "rag"
    assert got[2] == "a/pick-ui-library"  # the description match comes last


def test_search_testing_finds_the_testing_theme():
    items = reclassified({"fetched_at": 3.0, "items": REAL["items"]})["items"]
    got = search(items, "testing")
    assert got
    rx = re.compile(
        r"\b(tests?|testing|tested|tdd|qa|lint\w*|quality|coverage)\b"
    )  # tested: same stem
    assert all(
        rx.search(f"{i['name']} {i['description']} {' '.join(i['topics'])}".lower()) for i in got
    )


def test_search_mcp_postgres_needs_postgres_not_just_mcp():
    items = [
        {
            "id": "a/github-mcp",
            "name": "github-mcp-server",
            "description": "GitHub's MCP server",
            "topics": ["mcp"],
        },
        {
            "id": "a/pg",
            "name": "postgres-mcp",
            "description": "MCP server for PostgreSQL",
            "topics": [],
        },
        {
            "id": "a/pg2",
            "name": "db-tools",
            "description": "Query Postgres from your agent over MCP",
            "topics": [],
        },
    ] + [
        {"id": f"a/m{n}", "name": f"tool-{n}-mcp", "description": "An MCP server", "topics": []}
        for n in range(8)
    ]
    # "mcp" is in every item, so only "postgres" is required.
    assert ids(search(items, "mcp postgres")) == ["a/pg", "a/pg2"]


def test_search_tolerates_a_typo_and_matches_word_starts():
    assert word_match("reveiw", "review") > 0  # two letters swapped
    assert word_match("revew", "reviews") > 0  # one missing, then a prefix
    assert word_match("test", "testing") > 0  # prefix
    assert word_match("test", "best") == 0  # four letters: no typo allowed
    assert word_match("rag", "drag") == 0


def test_an_exact_name_comes_first():
    items = [
        {"id": "a/x", "name": "tdd-guide", "description": "tdd tdd", "topics": ["tdd"]},
        {"id": "a/tdd", "name": "tdd", "description": "", "topics": []},
    ]
    assert ids(search(items, "tdd"))[0] == "a/tdd"


def test_search_from_home_spans_every_kind_with_counts():
    items = reclassified({"fetched_at": 4.0, "items": REAL["items"]})["items"]
    got = page(items, "all", "recommended", "review", set())
    kinds = {i["category"] for i in got["items"]}
    assert len(kinds) >= 2
    assert sum(got["counts"].values()) == len(items)
    assert all(
        got["matches"][k] >= sum(1 for i in got["items"] if i["category"] == k) for k in kinds
    )
    per = skills.load("curate-catalog").values["search_per_kind"]
    assert all(sum(1 for i in got["items"] if i["category"] == k) <= per for k in kinds)


def test_the_web_app_uses_the_same_search_weights():
    """web/src/lib/librarySearch.ts mirrors the skill's search values."""
    ts = (Path(__file__).parents[2] / "web" / "src" / "lib" / "librarySearch.ts").read_text()
    m = re.search(r"export const SEARCH = (\{.*?\});", ts, re.S)
    assert m, "SEARCH constant in librarySearch.ts"
    mirrored = json.loads(re.sub(r"(\w+):", r'"\1":', m.group(1)).replace(",\n}", "\n}"))
    values = skills.load("curate-catalog").values["search"]
    assert {k: mirrored[k] for k in mirrored} == {k: values[k] for k in mirrored}
    assert set(mirrored) >= {"name", "description", "topics", "exact_name", "prefix", "fuzzy"}


# ---------- Recommended ----------


def test_recommended_puts_what_fits_the_project_before_famous_unrelated_items():
    """A job-search agent came first for a bug-fix goal; TrendRadar first among MCP servers."""
    famous = {"id": "s/trendradar", "name": "TrendRadar", "description": "AI trend monitor with MCP",
              "topics": ["mcp"], "stars": 120000, "pushed_at": "2026-10-20"}  # fmt: skip
    fits = {"id": "x/pg-mcp", "name": "pg-mcp", "description": "MCP server for FastAPI apps on Postgres",
            "topics": ["fastapi"], "stars": 40, "pushed_at": "2026-09-01"}  # fmt: skip
    one_lang = {"id": "y/py", "name": "py-mcp", "description": "A Python MCP server", "topics": [],
                "stars": 30000, "pushed_at": "2026-10-20"}  # fmt: skip
    terms = {"fastapi", "python"}
    got = ids(rank([famous, one_lang, fits], "recommended", terms))
    assert got[0] == "x/pg-mcp"  # relevance 2 (a framework) beats any number of stars
    # Without project terms, Recommended is the usual stars-and-freshness order.
    assert ids(rank([famous, one_lang, fits], "recommended"))[0] == "s/trendradar"


def test_a_zero_relevance_item_never_outranks_a_relevant_one_when_terms_exist():
    items = [
        {
            "id": f"f/{n}",
            "name": f"famous{n}",
            "description": "x",
            "topics": [],
            "stars": 10**6,
            "pushed_at": "2026-10-20",
        }
        for n in range(5)
    ] + [
        {
            "id": "r/1",
            "name": "r",
            "description": "for django sites",
            "topics": [],
            "stars": 1,
            "pushed_at": "2020-01-01",
        }
    ]
    ranked = rank(items, "recommended", {"django"})
    rel = [i["relevance"] for i in ranked]
    assert ranked[0]["id"] == "r/1"
    assert not any(
        rel[a] == 0 and rel[b] >= 2 for a in range(len(rel)) for b in range(a + 1, len(rel))
    )


def test_words_about_the_catalog_itself_are_not_project_terms():
    terms = project_terms(
        ["FastAPI"], {"Python": 5}, "An agent that fixes bugs with skills and hooks"
    )
    assert {"fastapi", "python", "fixes", "bugs"} <= terms
    assert not terms & {"agent", "skills", "hooks"}
