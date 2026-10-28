"""Add on a repo canvas: a link only for a reason a person can check (place-in-architecture)."""

from proving_ground.placement import Block, place

# Rig's own canvas: a Python engine and a React web app, no CLAUDE.md yet, none of its internal
# config skills.
RIG = [
    Block("arch:web", "frontend", "web", "React · Vite"),
    Block("arch:cli", "frontend", "pg CLI", "command line"),
    Block("arch:api", "backend", "api", "FastAPI · HTTP API over the engine"),
    Block("arch:architecture", "backend", "architecture", "A repo's architecture as components"),
    Block(
        "arch:catalog", "backend", "catalog", "A catalog from GitHub: skills, agents, MCP servers"
    ),
    Block("arch:skills", "backend", "skills", "The rules behind every step, one file per step"),
    Block("arch:sqlite", "database", "SQLite", "local file"),
    Block("setup:CLAUDE.md", "setup", "CLAUDE.md", "agent setup missing: add it", present=False),
    Block("setup:Hooks", "setup", "Hooks", "agent setup none", present=False),
    Block("setup:Test command", "setup", "Test command", "agent setup uv run pytest"),
]
PY_TS = {"Python": 423, "TypeScript": 99}
GO_NAMING = (
    "Go naming conventions and best practices. Use this skill when working with Go code and need "
    "to name packages, files, directories, structs, interfaces, functions, variables, or "
    "constants. Provides comprehensive naming guidelines following Go community standards."
)


def test_go_naming_on_a_python_repo_goes_with_the_agent_setup_and_says_why():
    got = place(RIG, "go-naming", GO_NAMING, languages=PY_TS)
    assert [t["id"] for t in got["targets"]] == ["setup:CLAUDE.md"]
    assert got["reason"] == (
        "Applies to the whole repo: because it is about conventions & style, so it goes with "
        "CLAUDE.md. For Go; this repo has none."
    )
    # The card shows the reason, and the language note on its own.
    assert got["targets"][0]["why"].endswith("so it goes with CLAUDE.md.")
    assert got["note"] == "For Go; this repo has none."


def test_go_naming_on_a_go_repo_has_no_language_note():
    got = place(RIG, "go-naming", GO_NAMING, languages={"Go": 40})
    assert got["targets"][0]["id"] == "setup:CLAUDE.md"
    assert "this repo has none" not in got["reason"] and got["note"] is None


def test_a_testing_skill_goes_where_the_tests_run():
    got = place(RIG, "pytest-patterns", "Fixtures, parametrize and coverage for pytest suites.")
    assert [t["id"] for t in got["targets"]] == ["setup:Test command"]
    assert got["reason"] == (
        "Applies to Test command: because the skill is about testing & quality and Test command "
        "uses pytest."
    )


def test_a_testing_skill_goes_to_the_test_step_of_the_workflow():
    blocks = [b for b in RIG if b.id != "setup:Test command"] + [
        Block("step:plan", "step", "plan", "Read the issue", "research", 0),
        Block("step:verify", "step", "verify", "Run the tests", "test", 1),
    ]
    got = place(blocks, "tdd", "Write a failing test first, then the fix.")
    assert [t["id"] for t in got["targets"]] == ["step:verify"]
    assert got["reason"] == (
        "Applies to verify: because the skill is about testing & quality and verify uses tests."
    )


def test_a_frontend_skill_goes_to_the_web_frontend_not_the_cli():
    got = place(
        RIG,
        "frontend-design",
        "Guidance for distinctive, intentional visual design when building new UI.",
    )
    assert [t["id"] for t in got["targets"]] == ["arch:web"]
    assert got["reason"] == (
        "Applies to web: because the skill is about frontend & design and web uses react and vite."
    )


def test_nothing_fits_no_link_to_a_random_block():
    got = place(RIG, "xlsx", "Create, edit and analyze spreadsheets with formulas and charts.")
    assert got["targets"] == []
    assert got["reason"] == "No part of this repo matches; added to the agent setup."
    assert got["beside"] == "setup:CLAUDE.md"


def test_words_of_a_blocks_description_alone_do_not_link():
    # "skills, agents" and "MCP servers" are in the catalog block's description, not its name.
    got = place(RIG, "mcp-lister", "Lists the agents and MCP servers in a folder.")
    assert "arch:catalog" not in [t["id"] for t in got["targets"]]


def test_the_repos_own_claude_md_wins_over_a_placeholder():
    blocks = [b for b in RIG if b.id != "setup:CLAUDE.md"] + [
        Block("setup:AGENTS.md", "setup", "AGENTS.md", "agent setup at the root")
    ]
    got = place(blocks, "docs-style", "House style for docs and the README.")
    assert got["targets"][0]["id"] == "setup:AGENTS.md"
    assert got["reason"].startswith("Applies to the whole repo: because it is about")
