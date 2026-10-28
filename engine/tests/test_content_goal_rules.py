"""The goal's policy reaches the agent (Goal & rules in the workflow, the compiled skill and
BUILD.md), non-code Nothing-yet briefs, step-2 reasons that quote only the matched words,
missing agent setup as a planned part, library search that folds weak matches, and copy left
over from code work."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from proving_ground import buildspec, catalog_arch, lab, skills
from proving_ground.api.app import create_app
from proving_ground.catalog import search
from proving_ground.generate.examples import scenario_example

BASE = "http://127.0.0.1:7357"
ORIGIN = {"Origin": BASE}
POLICY = (
    "Answer customer support tickets from our refund policy: refund within 30 days → full "
    "refund; 30–60 days → store credit; nothing after 60; anything over $200 needs a manager."
)
REAL = json.loads((Path(__file__).parent / "fixtures" / "catalog_real_sample.json").read_text())
REAL = REAL["items"] if isinstance(REAL, dict) else REAL


# ---------- The policy reaches the agent ----------


def test_the_refund_policys_rules_are_found_in_the_goals_own_words():
    assert lab.goal_rules(POLICY) == [
        "refund within 30 days → full refund",
        "30–60 days → store credit",
        "nothing after 60",
        "anything over $200 needs a manager",
    ]


def test_rules_are_lines_with_a_number_or_a_rule_word_and_nothing_else():
    goal = (
        "A support agent for our shop.\n- Always quote the policy line\n- be friendly\n"
        "Refunds must be approved by a manager. Never promise a date."
    )
    assert lab.goal_rules(goal) == [
        "Always quote the policy line",
        "Refunds must be approved by a manager",
        "Never promise a date",
    ]
    assert lab.goal_rules("Help me answer tickets") == []
    assert lab.goal_rules(None) == [] and lab.goal_rules("") == []
    assert lab.goal_rules("Prices like $1.50 stay whole; at 10:30 we close") == [
        "Prices like $1.50 stay whole",
        "at 10:30 we close",
    ]
    assert len(lab.goal_rules("; ".join(f"rule {n}" for n in range(40)))) == skills.value(
        "goal-rules", "max_rules"
    )


def test_a_design_built_from_the_goal_carries_it_as_goal_and_rules():
    wf = catalog_arch.lab_workflow("human-in-the-loop", POLICY, [])["workflow"]
    assert wf.brief == POLICY
    dump = wf.dump()
    assert dump["brief"] == POLICY and "30–60 days → store credit" in dump["rules"]
    # It survives the page's round trip (the Lab sends the workflow back as JSON).
    again = lab.load_workflow(json.loads(json.dumps(dump)))
    assert again.brief == POLICY
    # A RAG design too; a pattern with no use case has none.
    rag = catalog_arch.lab_workflow("naive-rag", POLICY, [])["workflow"]
    assert rag.brief == POLICY
    assert lab.from_pattern("approval-gate", lab.W["baseline_model"], []).brief is None


def test_the_compiled_skill_gives_the_first_step_every_rule(tmp_path: Path):
    wf = catalog_arch.lab_workflow("human-in-the-loop", POLICY, [])["workflow"]
    dest = lab.compile_workflow(wf, tmp_path / "w")
    md = (dest / "SKILL.md").read_text()
    assert "## Goal & rules" in md and POLICY in md
    first = next(ln for ln in md.splitlines() if ln.strip().startswith("Brief:"))
    for rule in ("30 days → full refund", "30–60 days → store credit", "nothing after 60", "$200"):
        assert rule in first, rule
    assert "Follow these rules:" in first
    later = [ln for ln in md.splitlines() if ln.strip().startswith("Brief:")][1:]
    assert later and all("Keep to the Goal & rules." in ln for ln in later)
    # The subagent file Claude Code reads has them too.
    agent = (dest / "agents" / "propose.md").read_text()
    assert "Follow these rules:" in agent and "- 30–60 days → store credit" in agent
    # No goal: nothing about rules.
    plain = lab.from_pattern("approval-gate", lab.W["baseline_model"], [])
    text = (lab.compile_workflow(plain, tmp_path / "p") / "SKILL.md").read_text()
    assert "Goal & rules" not in text and "Follow these rules" not in text


def test_build_md_for_a_workflow_states_the_goal_and_its_rules():
    wf = catalog_arch.lab_workflow("human-in-the-loop", POLICY, [])["workflow"]
    md = buildspec.render_markdown(buildspec.spec_from_workflow(wf))
    goal = md.split("## Goal\n", 1)[1].split("\n## ", 1)[0]
    assert POLICY in goal
    assert "Rules to follow:" in goal
    for rule in (
        "- refund within 30 days → full refund",
        "- 30–60 days → store credit",
        "- nothing after 60",
        "- anything over $200 needs a manager",
    ):
        assert rule in goal, rule
    # A goal passed in (step 1's) wins over the workflow's own brief.
    other = buildspec.spec_from_workflow(wf, goal="Refunds only within 14 days.")
    assert other["goal"] == "Refunds only within 14 days." and other["rules"] == [
        "Refunds only within 14 days"
    ]


def test_build_md_for_a_repo_states_the_goal_and_its_rules(tmp_path: Path):
    from proving_ground.architecture import Architecture

    spec = buildspec.spec_for_repo(Architecture(title="desk"), tmp_path, {}, use_case=POLICY)
    md = buildspec.render_markdown(spec)
    assert "## Goal\n\n" + POLICY in md
    assert "Rules to follow:\n- refund within 30 days → full refund" in md
    assert "- 30–60 days → store credit" in md


def test_the_api_takes_the_goal_and_falls_back_to_the_workflows_brief(tmp_path: Path):
    c = TestClient(create_app(tmp_path, home=tmp_path / "home"), base_url=BASE, headers=ORIGIN)
    got = c.post("/api/garage/workflow", json={"entry": "human-in-the-loop", "use_case": POLICY})
    wf = got.json()["workflow"]
    assert wf["brief"] == POLICY and "nothing after 60" in wf["rules"]
    md = c.post("/api/buildspec", json={"source": "workflow", "workflow": wf}).json()["markdown"]
    assert "30 days" in md and "store credit" in md and "Rules to follow:" in md
    md2 = c.post(
        "/api/buildspec",
        json={"source": "workflow", "workflow": {**wf, "brief": None}, "goal": POLICY},
    ).json()["markdown"]
    assert "- 30–60 days → store credit" in md2
    design = c.post(
        "/api/buildspec",
        json={"source": "design", "design": {"id": "human-in-the-loop"}, "goal": POLICY},
    ).json()["markdown"]
    assert "store credit" in design and "## Goal" in design
    # The Lab's price call keeps an edited brief and says its rules again.
    priced = c.post("/api/lab/price", json={**wf, "brief": "Never refund after 90 days."}).json()
    assert priced["rules"] == ["Never refund after 90 days"]


# ---------- Nothing yet, for work that isn't software ----------


def test_a_support_workflow_needs_no_code_to_start_and_the_layout_is_optional():
    wf = catalog_arch.lab_workflow("human-in-the-loop", POLICY, [])["workflow"]
    spec = buildspec.spec_from_workflow(wf)
    assert spec["language"]["code"] is False
    md = buildspec.render_markdown(spec)
    assert "No code required to start: build it in your agent platform" in md
    assert "(Python suggested)" in md
    assert "Language: Python (suggested" not in md
    assert "## Project layout (optional)" in md and "Optional: only if a coding agent" in md


def test_a_code_workflow_or_a_named_language_keeps_the_layout():
    dev = lab.from_pattern("approval-gate", lab.W["baseline_model"], [], discipline="development")
    md = buildspec.render_markdown(buildspec.spec_from_workflow(dev))
    assert "Language: Python (suggested" in md and "## Project layout\n" in md
    named = buildspec.spec_from_workflow(
        catalog_arch.lab_workflow("human-in-the-loop", POLICY + " Written in TypeScript.", [])[
            "workflow"
        ]
    )
    assert named["language"]["name"] == "TypeScript" and named["language"]["code"] is True


def test_a_design_for_a_support_goal_is_no_code_and_with_no_goal_keeps_the_layout(tmp_path: Path):
    c = TestClient(create_app(tmp_path, home=tmp_path / "home"), base_url=BASE, headers=ORIGIN)
    body = {"source": "design", "design": {"id": "human-in-the-loop"}}
    sup = c.post("/api/buildspec", json={**body, "goal": POLICY}).json()["markdown"]
    assert "No code required to start" in sup
    none = c.post("/api/buildspec", json=body).json()["markdown"]
    assert "No code required" not in none and "## Project layout\n" in none


# ---------- Step-2 reasons quote only the matched words ----------


def test_step_two_reasons_quote_the_matched_phrase_not_the_sentence():
    top = catalog_arch.recommend(
        "A support agent that answers questions from our help center docs; answers must be "
        "cited, and refunds over $200 need a manager."
    )
    by = {r["id"]: r["reasons"] for r in top}
    assert "Because you said 'refunds over $200 need a manager'" in by["human-in-the-loop"][0]
    rag = by["reranked-rag"]
    assert any("'from our help center docs'" in w for w in rag)
    assert any("'answers must be cited'" in w for w in rag)
    # Never the whole long sentence, and different designs show different phrases.
    for r in top:
        for w in r["reasons"]:
            assert "A support agent that answers questions" not in w
    assert by["human-in-the-loop"] != rag


def test_overlapping_quotes_of_one_design_are_one_reason():
    hitl = next(r for r in catalog_arch.recommend(POLICY) if r["id"] == "human-in-the-loop")
    said = [w for w in hitl["reasons"] if w.startswith("Because you said")]
    assert (
        "Because you said 'anything over $200 needs a manager' (a person must approve some actions)."
        in said
    )
    assert len(said) == len(set(said)) <= 2


# ---------- Missing agent setup becomes a planned part in BUILD.md ----------


def test_a_planned_setup_part_is_listed_with_what_to_put_in_it(tmp_path: Path):
    from proving_ground.architecture import Architecture

    spec = buildspec.spec_for_repo(Architecture(title="desk"), tmp_path, {}, use_case="x")
    plan = "Add CLAUDE.md at the repo root: how to build, test and run it (test: pytest -q)."
    spec = buildspec.with_canvas(
        spec,
        {"planned": [{"name": "CLAUDE.md", "ref": "setup/CLAUDE.md", "do": plan}]},
        tmp_path,
    )
    md = buildspec.render_markdown(spec)
    assert "### Planned, not written yet" in md
    assert f"- CLAUDE.md (`setup/CLAUDE.md`): {plan}" in md
    assert "1 planned part" in md


# ---------- Copy: approvals without a file, a use case placeholder in the repo's work ----------


def test_the_support_approval_step_holds_requests_without_a_file():
    wf = catalog_arch.lab_workflow("human-in-the-loop", POLICY, [])["workflow"]
    gate = next(s for s in wf.steps if s.id == "gate")
    assert "APPROVALS.md" not in gate.does and "as a request for a manager" in gate.does
    for did in skills.value("workflow-patterns", "phrasing")["disciplines"]:
        w = lab.from_pattern("approval-gate", lab.W["baseline_model"], [], discipline=did)
        assert all("APPROVALS.md" not in s.does for s in w.steps), did


def test_the_use_case_placeholder_follows_the_repo():
    assert "pytest" in scenario_example({"languages": {"Python": 9}}, "")["use_case"]
    assert "go test" in scenario_example({"languages": {"Go": 9}}, "")["use_case"]
    assert "refund" not in scenario_example({}, "")["use_case"].lower()


def test_the_suggested_tab_counts_tasks_like_the_brief():
    p = {"state": "accepted", "kind": "check", "impact": {"clarity": "x"}}
    assert buildspec.diagram_only(p)  # a note, not a task: the tab's "tasks" leaves it out


# ---------- The glossary ----------


def test_the_glossary_has_the_new_terms_and_the_unit_of_pts():
    terms = skills.value("glossary", "terms")
    for k in ("pairs", "arms", "baseline", "change", "pilot-vs-full", "held-out", "sandbox"):
        assert k in terms and terms[k]["short"], k
    assert terms["pts"]["term"] == "pts (pass-rate points)"
    assert "isolated test copy" in terms["sandbox"]["short"]
    assert "both" in terms["arms"]["short"].lower()


# ---------- Library search: distinctive words first, weak matches folded ----------


def _names(q: str) -> tuple[list[str], list[str]]:
    got = search(REAL, q)
    return [i["name"] for i in got if not i.get("weak")], [i["name"] for i in got if i.get("weak")]


def test_postgres_shows_the_postgres_tool_and_folds_the_ones_with_only_a_topic():
    strong, weak = _names("postgres")
    assert strong[0] == "pg-aiguide"
    assert "Pseudolife-MCP" in weak and "Pseudolife-MCP" not in strong


def test_postgres_in_passing_in_a_description_is_weak():
    # A real catalog item: a video downloader whose description mentions a PostgreSQL archive.
    douyin = {
        "id": "Evil0ctal/Douyin_TikTok_Download_API",
        "name": "Douyin_TikTok_Download_API",
        "description": "Self-hosted TikTok, Douyin & Bilibili scraper and no-watermark video "
        "downloader — async REST API, MCP server for AI agents, CLI and web console, plus "
        "offline speech-to-text for downloaded videos. Self-healing identity pool, PostgreSQL "
        "archive, one docker compose up.",
        "topics": ["crawler", "douyin", "mcp-server", "scraper", "tiktok"],
        "category": "mcp",
    }
    got = search([*REAL, douyin], "postgres")
    assert got[0]["name"] == "pg-aiguide"
    assert next(i for i in got if i["name"] == douyin["name"]).get("weak") is True


def test_code_review_leads_with_code_review_tools_and_folds_scattered_words():
    strong, weak = _names("code review")
    assert strong[0] == "open-code-review"
    # Strong ones say "code review" (name, description or a code-review topic).
    for n in strong:
        item = next(i for i in REAL if i["name"] == n)
        text = f"{item['name']} {item['description']} {' '.join(item['topics'])}".lower()
        assert "code review" in text.replace("-", " "), n
    assert weak, "something only says the words apart"


def test_a_theme_alone_is_a_weak_match():
    # "review" names the Code review theme; an item matched only through the theme is weak.
    strong, weak = _names("review")
    for n in strong:
        item = next(i for i in REAL if i["name"] == n)
        assert "review" in f"{item['name']} {item['description']}".lower(), n


def test_the_library_page_counts_weak_matches_per_kind():
    from proving_ground.catalog import page

    got = page(REAL, "all", "recommended", "postgres", set())
    assert sum(got["weak"].values()) >= 1
    assert got["items"][0]["name"] == "pg-aiguide"
