"""Workflows and rules in the discipline's words, code skills kept off non-code steps, confident
placement, BUILD.md notes vs tasks, Lab exports with the design, the glossary, library search,
and step-2 ranking by intent."""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from proving_ground import buildspec, catalog_arch, lab, skill_match, skills
from proving_ground.api.app import create_app
from proving_ground.architecture import Architecture
from proving_ground.catalog import classify, goal_terms, rank, search, word_match
from proving_ground.generate.examples import scenario_example
from proving_ground.placement import Block, place

BASE = "http://127.0.0.1:7357"
SUPPORT = (
    "Answer customer support tickets from our refund policy; refunds over $200 need a manager."
)
CODE_WORDS = re.compile(r"\b(the change|diff|tests?|test suite|files?|code|commit|PR)\b", re.I)

SEMGREP = {
    "path": "github:trailofbits/skills/plugins/static-analysis/skills/semgrep",
    "name": "semgrep",
    "description": "Runs a Semgrep security scan over a codebase: detects languages, selects "
    "rulesets, presents the plan for explicit approval, then runs every approved ruleset.",
}
REFUND = {
    "path": "/lib/refund-policy",
    "name": "refund-policy",
    "description": "The support desk's refund limits and when to escalate to a manager for approval.",
}


# ---------- Patterns and harness rules in the discipline's words ----------


def test_human_in_the_loop_for_support_reads_as_support_work_with_the_use_cases_limit():
    got = catalog_arch.lab_workflow("human-in-the-loop", SUPPORT, [])
    wf = got["workflow"]
    assert got["discipline"] == "support"
    text = " ".join(f"{s.name}: {s.does}" for s in wf.steps)
    assert "Plan the change" not in text
    assert "$200" in text and "manager" in text and "APPROVALS.md" not in text
    assert not CODE_WORDS.search(text), text
    assert wf.facts == {"limit": "$200"}


def test_every_pattern_in_every_non_code_discipline_says_no_code_words():
    for did in skills.value("workflow-patterns", "phrasing")["disciplines"]:
        for pid in lab.W["patterns"]:
            wf = lab.from_pattern(pid, lab.W["baseline_model"], [], discipline=did)
            for st in wf.steps:
                said = f"{st.name}: {st.does}"
                assert "{" not in said, (did, pid, said)  # every placeholder filled
                assert not re.search(
                    r"\b(diff|test suite|tests|commit|the change)\b", said, re.I
                ), (
                    did,
                    pid,
                    said,
                )
            assert not re.search(r"\b(coder|tester|green)\b", wf.name, re.I), (did, pid, wf.name)


def test_code_disciplines_keep_the_patterns_as_written():
    for did in ("development", "qa", "pattern"):
        wf = lab.from_pattern("approval-gate", lab.W["baseline_model"], [], discipline=did)
        assert wf.steps[0].does.startswith("Plan the change and list every action")


def test_harness_rules_follow_the_discipline():
    assert lab.harness_text("guardrails", "development") == (
        "Touch only files the task needs; no new dependencies; never weaken a test."
    )
    sup = lab.harness_text("guardrails", "support", lab.facts_from(SUPPORT))
    assert "Quote the policy line you rely on" in sup
    assert "Never promise a refund the policy doesn't allow".lower() in sup.lower()
    assert "Hand anything over $200 to a person".lower() in sup.lower()
    assert "the policy's limit" in lab.harness_text("guardrails", "support")
    res = lab.harness_text("guardrails", "research")
    assert (
        "Cite every claim" in res and "Say when the sources don't answer it".lower() in res.lower()
    )
    for did in skills.value("workflow-patterns", "phrasing")["disciplines"]:
        for h in lab.W["harness"]:
            t = lab.harness_text(h, did)
            assert "never weaken a test" not in t and "{" not in t, (did, h)


def test_the_compiled_rules_and_the_page_use_the_disciplines_words(tmp_path: Path):
    wf = catalog_arch.lab_workflow("human-in-the-loop", SUPPORT, [])["workflow"]
    wf.harness = ["guardrails"]
    md = (lab.compile_workflow(wf, tmp_path / "w") / "SKILL.md").read_text()
    assert "Quote the policy line" in md and "never weaken a test" not in md
    assert wf.dump()["harness_text"]["guardrails"].startswith("Quote the policy line")
    again = lab.load_workflow(json.loads(json.dumps(wf.dump())))
    assert again.facts == {"limit": "$200"}


def test_an_amount_in_the_use_case_is_found():
    assert lab.facts_from("refunds over $1,200. Thanks") == {"limit": "$1,200"}
    assert lab.facts_from("spend above £5k") == {"limit": "£5k"}
    assert lab.facts_from("no amount here") == {}


# ---------- Code skills stay off non-code steps ----------


def test_a_security_scanner_never_lands_on_a_support_step():
    step = {
        "name": "Approval gate",
        "does": "Write each risky action with its reason to APPROVALS.md as a request; approve only the safe ones.",
    }
    lib = [SEMGREP, REFUND]
    assert skill_match.code_only(SEMGREP["name"], SEMGREP["description"])
    assert not skill_match.code_only(REFUND["name"], REFUND["description"])
    on_support = lab.step_skills({**step, "discipline": "support"}, lib, 2, models=None)
    assert "semgrep" not in [s["name"] for s in on_support]
    on_dev = lab.match_skills(step["name"], lib, 2, step["does"], (), "development")
    assert "semgrep" in [s["name"] for s in on_dev]  # the gate is only for non-code work
    assert skill_match.allowed(step["name"], lib, step["does"], discipline="support") == [
        False,
        True,
    ]


def test_the_gate_is_a_skill_value():
    gate = skills.value("match-skills", "discipline_gate")
    assert "support" not in gate["code_disciplines"] and "development" in gate["code_disciplines"]
    assert {"semgrep", "linter", "test runner"} <= set(gate["code_only"])


# ---------- Placement: confident links and real sentences ----------

BLOCKS = [
    Block("arch:sig", "external", "Signal sources", "external"),
    Block("arch:git", "external", "Git hosts", "GitHub and GitLab"),
    Block("setup:CLAUDE.md", "setup", "CLAUDE.md", "agent setup"),
    Block("setup:Hooks", "setup", "Hooks", "agent setup"),
]


def test_a_shared_word_links_with_a_plain_sentence():
    got = place(BLOCKS, "git-helper", "Helps with git branches", [], "skill")
    assert got["targets"] == [
        {"id": "arch:git", "why": "Applies to Git hosts: because the skill mentions git."}
    ]


def test_a_kind_alone_is_not_enough_to_link():
    got = place(BLOCKS, "xlsx", "Work with spreadsheets", [], "skill")
    assert got["targets"] == []
    assert got["reason"] == "No part of this repo matches; added to the agent setup."
    assert got["beside"] == "setup:CLAUDE.md"
    assert "belongs at a" not in json.dumps(got)


def test_a_kind_with_one_place_goes_there():
    got = place(BLOCKS, "guard", "Block risky commands", [], "hook")
    assert got["targets"][0]["id"] == "setup:Hooks"
    assert got["reason"] == "Applies to Hooks: because a hook runs with the agent setup."


# ---------- BUILD.md ----------


def _arch():
    return Architecture.model_validate(
        {
            "title": "dth",
            "components": [{"id": "cli", "label": "dth CLI", "type": "backend"}],
        }
    )


NOTE = {
    "id": "n1",
    "title": "Show where dth CLI gets its input",
    "kind": "check",
    "state": "accepted",
    "effort": "S",
    "targets": ["cli"],
    "what": "Add the line into dth CLI from what drives it.",
    "impact": {"clarity": "Every part shows its input."},
    "delta": {},
}
TASK = {
    "id": "t1",
    "title": "Add a CLAUDE.md",
    "kind": "add",
    "state": "accepted",
    "effort": "S",
    "targets": ["cli"],
    "what": "Write CLAUDE.md with the build and test commands.",
    "impact": {"agent": "The agent knows the commands."},
    "delta": {},
}


def test_diagram_only_suggestions_are_notes_not_tasks():
    assert buildspec.diagram_only(NOTE) and not buildspec.diagram_only(TASK)
    s = buildspec.spec_for_repo(_arch(), None, {}, suggestions=[NOTE, TASK], with_suggestions=True)
    assert [t["id"] for t in s["changes"]] == ["t1"]
    md = buildspec.render_markdown(s)
    changes = md.split("## Changes", 1)[1].split("\n## ", 1)[0]
    notes = md.split("## Notes on the architecture diagram", 1)[1].split("\n## ", 1)[0]
    assert "Add a CLAUDE.md" in changes and "dth CLI gets its input" not in changes
    assert "Show where dth CLI gets its input" in notes
    assert "1 task from accepted suggestions" in md


def test_a_lab_export_keeps_the_designs_parameters_and_retrieval():
    wf = catalog_arch.lab_workflow("agentic-rag", "answer from our policy docs", [])["workflow"]
    spec = buildspec.spec_from_workflow(wf, {}, "answer from our policy docs")
    spec = buildspec.with_design(spec, catalog_arch.entry("agentic-rag"), {"max_iterations": "4"})
    md = buildspec.render_markdown(spec)
    params = md.split("## Parameters", 1)[1].split("\n## ", 1)[0]
    assert "`max_iterations` | 4 (changed) | 6" in params
    assert "Retrieval: not part of this design" not in md
    assert "Retrieval: ingest" in md
    assert any("/retrieval/search." in p for p in (e["path"] for e in spec["layout"]))
    assert "Vector index" in spec["retrieval"]["components"]


def test_a_rag_workflow_alone_has_retrieval_and_a_plain_one_doesnt():
    rag = lab.rag([])[0]
    assert buildspec.spec_from_workflow(rag).get("retrieval", {}).get("enabled")
    plain = lab.from_pattern("direct", lab.W["baseline_model"], [])
    assert "retrieval" not in buildspec.spec_from_workflow(plain)


def test_a_goal_naming_another_stack_is_warned_about():
    meta = {"languages": {"Python": 40, "TypeScript": 30}}
    w = buildspec.stack_warnings("Review Java pull requests; we use JUnit", meta)
    assert w == ["Your goal mentions Java/JUnit; this repo is Python/TypeScript."]
    assert buildspec.stack_warnings("Fix bugs in the Python service", meta) == []
    s = buildspec.spec_for_repo(_arch(), None, meta, use_case="Review Java code with JUnit")
    assert "Your goal mentions Java/JUnit" in buildspec.render_markdown(s)


def test_the_agent_setup_lane_lists_whats_there_and_whats_missing(tmp_path: Path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"Stop": []}}))
    (tmp_path / "go.mod").write_text("module x\n")
    lane = {x["label"]: x for x in buildspec.setup_lane(tmp_path, {})}
    assert lane["CLAUDE.md"]["present"] is False and "missing" in lane["CLAUDE.md"]["detail"]
    assert lane["Hooks"]["present"] and lane["Hooks"]["detail"] == "Stop"
    assert lane["MCP servers"]["present"] is False
    assert lane["Test command"]["run"] == "go test ./..."
    (tmp_path / "CLAUDE.md").write_text("# x\n")
    lane = {x["label"]: x for x in buildspec.setup_lane(tmp_path, {})}
    assert lane["CLAUDE.md"]["present"] is True


# ---------- Glossary ----------


def test_the_glossary_has_every_term_the_pages_use():
    terms = skills.value("glossary", "terms")
    want = {"pts", "pair", "trial", "change", "baseline", "held-out", "lift", "interval",
            "pilot", "full", "bench", "task", "judged", "rig-score"}  # fmt: skip
    assert want <= set(terms)
    assert "percentage points" in terms["pts"]["short"].lower()
    assert "without" in terms["baseline"]["short"]
    for t in terms.values():
        assert t["term"] and 20 < len(t["short"]) < 260
    web = Path(__file__).parents[2] / "web" / "src"
    used = set()
    for f in web.rglob("*.tsx"):
        used |= set(re.findall(r'<Term k="([a-z-]+)"', f.read_text()))
    assert used and used <= set(terms), used - set(terms)


def test_the_glossary_endpoint(tmp_path: Path):
    c = TestClient(create_app(tmp_path, home=tmp_path / "home"), base_url=BASE)
    body = c.get("/api/glossary").json()
    assert body["terms"]["pts"]["term"] == "pts (pass-rate points)"  # the unit, said
    # The app says "task"; the older word still finds the same entry.
    assert body["terms"]["task"]["term"] == "task"
    assert body["terms"]["scenario"] == body["terms"]["task"]
    assert "aliases" not in body["terms"]["task"]
    # The page says "change"; the engine's word for it finds the same entry.
    assert body["terms"]["change"]["term"] == "change"
    assert body["terms"]["treatment"] == body["terms"]["change"]


# ---------- Scenario examples follow the repo ----------


def test_scenario_examples_follow_the_repo_and_the_work():
    go = scenario_example({"languages": {"Go": 30}}, "Bug fixing in my repo")
    assert go["title"] == "Fix the failing date parsing in pkg/dates"
    assert go["check"] == "go test ./pkg/dates/... -run TestParse"
    sup = scenario_example({"languages": {"Python": 3}}, "Handle support tickets and refunds")
    assert "$1,200" in sup["instruction"]
    py = scenario_example({"languages": {"Python": 3}}, "")
    assert py["check"].startswith("pytest")


# ---------- Library search and Recommended ----------


def test_search_matches_word_forms_and_compounds():
    tdd = {"name": "test-driven-development", "description": "any feature or bugfix", "topics": []}
    other = {
        "name": "horn",
        "description": "a bugle",
        "topics": [],
    }  # a name prefix would match by design
    assert search([tdd, other], "bug") == [tdd]
    assert word_match("bugs", "bug") > 0 and word_match("reviewing", "review") > 0
    assert word_match("bug", "bugle") == 0


def test_search_puts_all_words_and_the_phrase_before_any_word():
    anim = {
        "name": "review-animations",
        "description": "Reviews animation and motion code.",
        "topics": [],
    }
    web = {
        "name": "web-design-guidelines",
        "description": "Review UI code for guidelines.",
        "topics": [],
    }
    cr = {"name": "code-review", "description": "Review the diff.", "topics": []}
    rq = {
        "name": "requesting-code-review",
        "description": "Verify work meets requirements.",
        "topics": [],
    }
    got = search([anim, web, rq, cr], "code review")
    assert [i["name"] for i in got[:2]] == ["code-review", "requesting-code-review"]


def test_an_mcp_server_that_ships_skills_is_an_mcp_server():
    pg = {
        "name": "pg-aiguide",
        "description": "MCP server and Claude plugin for Postgres skills and documentation. "
        "Helps AI coding tools generate better PostgreSQL code.",
        "topics": ["mcp", "mcp-server", "claude-skills", "skills", "postgres"],
    }
    assert classify(pg) == "mcp"


def test_recommended_ranks_by_the_goals_words_first():
    famous = {"id": "a/scroll-craft", "name": "scroll-craft", "stars": 4000, "pushed_at": "2026-09-30",
              "description": "An agent skill for scroll-driven websites", "topics": ["frontend"]}  # fmt: skip
    fits = {"id": "b/debug", "name": "systematic-debugging", "stars": 10, "pushed_at": "2026-09-01",
            "description": "Find the root cause of a bug before fixing it", "topics": []}  # fmt: skip
    goal = goal_terms("Bug fixing in my repo")
    assert goal == {"bug", "fixing"}
    assert rank([famous, fits], "recommended", {"frontend"}, goal)[0]["id"] == "b/debug"


# ---------- Step-2 ranking by intent ----------


def _top(uc, meta=None, n=3):
    return catalog_arch.recommend(uc, meta)[:n]


def test_support_refunds_over_a_limit_get_human_in_the_loop_and_retrieval_as_strong_fits():
    top = _top(SUPPORT)
    ids = [r["id"] for r in top]
    assert ids[0] == "human-in-the-loop" and top[0]["fit"] == "strong"
    rag = [r for r in top if catalog_arch.entry(r["id"])["family"] == "rag"]
    assert rag and rag[0]["fit"] == "strong"
    assert any(
        "because you said 'refunds over $200 need a manager'" in w.lower()
        for w in top[0]["reasons"]
    )
    assert all(
        "score" not in w.lower() and "mentions 'code'" not in w for r in top for w in r["reasons"]
    )


def test_docs_qa_that_must_cite_ranks_the_rag_family():
    top = _top("A Q&A bot that answers from our product docs and must cite the page it used.")
    assert all(catalog_arch.entry(r["id"])["family"] == "rag" for r in top)
    assert top[0]["fit"] == "strong"


def test_java_code_review_ranks_the_loops_that_check_code():
    top = _top("Review Java pull requests for bugs and style; the team uses JUnit.", n=2)
    assert top[0]["id"] in ("evaluator-optimizer", "plan-and-execute")
    assert all(catalog_arch.entry(r["id"])["family"] == "agent" for r in top)


def test_sql_files_in_the_repo_dont_rank_retrieval_for_bug_fixing():
    meta = {"languages": {"SQL": 909, "Python": 300}, "files": 1500, "stack": ["FastAPI"]}
    top = _top("Bug fixing in my repo", meta, n=5)
    assert not any(catalog_arch.entry(r["id"])["family"] == "rag" for r in top)
    assert catalog_arch.recommend("help with things", meta) == []


def test_fit_labels_are_words_from_the_skill():
    labels = skills.value("architecture-catalog", "fit_labels")
    for r in catalog_arch.recommend(SUPPORT):
        assert r["fit_label"] == labels[r["fit"]]


def test_one_everyday_word_in_a_description_is_not_a_match():
    steps = [
        Block(
            "step:triage",
            "step",
            "triage",
            "Read the ticket and the customer's plan",
            "research",
            0,
        )
    ]
    got = place(steps, "careful-review", "Re-read the diff before finishing.", [], "skill")
    assert got["targets"] == [] and got["reason"].startswith("No part of this repo matches")
