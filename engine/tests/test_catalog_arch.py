"""The architecture catalog: valid entries, a deterministic ranking, and the canvas model."""

import pytest
from fastapi.testclient import TestClient
from test_api_workspace import BASE, ORIGIN
from test_api_workspace import env as env  # noqa: F401

from proving_ground import catalog_arch, skills
from proving_ground.agents import Credentials
from proving_ground.api.app import create_app
from proving_ground.architecture import Kind
from proving_ground.generate.client import ToolCall
from proving_ground.workspace import Workspace

LEVELS = {"low", "medium", "high"}
KINDS = set(Kind.__args__)


def test_catalog_loads_with_both_families_and_many_entries():
    es = catalog_arch.entries()
    assert len(es) >= 20
    assert {e["family"] for e in es} == {"rag", "agent"}
    assert len({e["id"] for e in es}) == len(es)
    for want in ("naive-rag", "multimodal-rag", "hyde-rag", "corrective-rag", "graph-rag",
                 "hybrid-rag", "adaptive-rag", "agentic-rag", "self-rag", "reranked-rag",
                 "react", "plan-and-execute", "reflexion", "lats", "router",
                 "orchestrator-workers", "evaluator-optimizer", "supervisor", "hierarchical",
                 "swarm-handoffs", "blackboard", "human-in-the-loop"):  # fmt: skip
        assert catalog_arch.entry(want), want


@pytest.mark.parametrize("e", catalog_arch.entries(), ids=lambda e: e["id"])
def test_every_entry_is_valid(e):
    for k in ("name", "summary", "when_to_use", "when_not_to_use"):
        assert e[k].strip()
    ids = [c["id"] for c in e["components"]]
    assert len(ids) == len(set(ids)) >= 3
    assert all(c["type"] in KINDS and c["label"] and c["role"] for c in e["components"])
    assert e["connections"]
    for a, b, label in e["connections"]:
        assert a in ids and b in ids and label
    assert e["parameters"]
    for p in e["parameters"]:
        assert p["name"] and "default" in p and p["what"]
        assert ("range" in p) != ("options" in p)
        if "range" in p:
            lo, hi = p["range"]
            assert lo < hi and lo <= p["default"] <= hi
        else:
            assert p["default"] in p["options"]
    assert set(e["tradeoffs"]) == {"latency", "cost", "accuracy", "complexity"}
    assert set(e["tradeoffs"].values()) <= LEVELS
    assert e["signals"]
    assert e["sources"]
    for s in e["sources"]:
        assert s["title"] and s["url"].startswith("https://")


def test_as_architecture_is_laid_out_for_the_canvas():
    for e in catalog_arch.entries():
        a = catalog_arch.as_architecture(e)
        assert len(a.components) == len(e["components"])
        assert all(c.pos is not None for c in a.components)
        assert len(a.connections) == len(e["connections"])
    assert catalog_arch.as_architecture(catalog_arch.entry("react")).title == "ReAct loop"


def test_rag_use_case_ranks_a_rag_entry_in_the_top_three_with_reasons():
    ranked = catalog_arch.recommend("answer questions over 500 PDFs with tables and citations")
    top = ranked[:3]
    assert any(catalog_arch.entry(r["id"])["family"] == "rag" for r in top)
    assert top[0]["id"] == "multimodal-rag"
    assert all(r["reasons"] for r in ranked)
    assert ranked == sorted(ranked, key=lambda r: (-r["score"], r["id"]))


def test_agent_use_case_ranks_an_agent_entry_first():
    ranked = catalog_arch.recommend("triage support tickets with tools and approvals")
    assert catalog_arch.entry(ranked[0]["id"])["family"] == "agent"
    assert {"router", "human-in-the-loop"} <= {r["id"] for r in ranked[:3]}


def test_ranking_is_deterministic_and_preferences_matter():
    text = "an faq bot over our docs"
    assert catalog_arch.recommend(text) == catalog_arch.recommend(text)
    plain = {r["id"]: r["score"] for r in catalog_arch.recommend(text)}
    fast = {r["id"]: r["score"] for r in catalog_arch.recommend(text + ", must be fast")}
    assert fast["naive-rag"] > plain["naive-rag"]
    assert catalog_arch.recommend("") == []


def test_repo_facts_add_a_little_but_never_list_a_design_alone():
    meta = {"stack": ["FastAPI"], "languages": {"Python": 3}, "files": 900, "docs_words": 50000}
    # The repo's files alone don't make a recommendation.
    assert catalog_arch.recommend("help people find things", meta) == []
    with_repo = catalog_arch.recommend("answer questions from the docs", meta)
    plain = {r["id"]: r["score"] for r in catalog_arch.recommend("answer questions from the docs")}
    assert any("repo" in why for r in with_repo for why in r["reasons"])
    assert all(r["score"] >= plain[r["id"]] for r in with_repo if r["id"] in plain)


def test_the_skill_is_registered():
    assert "architecture-catalog" in skills.NAMES
    assert skills.load("architecture-catalog").body.startswith("# ")


def test_explain_uses_one_model_call_for_the_top_picks():
    calls = []

    class Fake:
        def call(self, prompt, tool, model, max_tokens):
            calls.append(model)
            return ToolCall(
                {
                    "explanations": [
                        {"id": "router", "text": "Sorts tickets."},
                        {"id": "zzz", "text": "x"},
                    ]
                },
                "tool_use",
                1,
                1,
            )

    ranked = catalog_arch.recommend("triage support tickets with tools and approvals")
    out = catalog_arch.explain(Fake(), "triage tickets", ranked)
    assert out == {"router": "Sorts tickets."}
    assert calls == [skills.value("architecture-catalog", "explain_model")]


# ---------- API ----------


def test_api_catalog_and_entry(env):  # noqa: F811
    c, *_ = env
    body = c.get("/api/garage/catalog").json()
    assert [f["id"] for f in body["families"]] == ["rag", "agent"]
    assert body["count"] == sum(len(f["entries"]) for f in body["families"]) >= 20
    one = c.get("/api/garage/catalog/graph-rag").json()
    assert one["name"] == "GraphRAG" and one["sources"]
    assert all(x["pos"] for x in one["architecture"]["components"])
    assert c.get("/api/garage/catalog/nope").status_code == 404


def test_api_recommend_with_and_without_a_repo(env):  # noqa: F811
    c, a, *_ = env
    r = c.post(
        "/api/garage/recommend",
        json={"use_case": "answer questions over 500 PDFs with tables and citations"},
        headers=ORIGIN,
    )
    assert r.status_code == 200
    picks = r.json()["picks"]
    assert picks[0]["id"] == "multimodal-rag" and picks[0]["reasons"] and picks[0]["entry"]["name"]
    assert picks[0]["explanation"] is None
    assert (
        c.post(
            "/api/garage/recommend", json={"use_case": "x", "repo": "nope"}, headers=ORIGIN
        ).status_code
        == 404
    )
    rid = c.post("/api/repos", json={"path": str(a)}, headers=ORIGIN).json()["id"]
    r = c.post(
        "/api/garage/recommend",
        json={"use_case": "a fastapi service for tickets", "repo": rid},
        headers=ORIGIN,
    )
    assert r.status_code == 200 and r.json()["picks"]
    assert c.post("/api/garage/recommend", json={"use_case": ""}, headers=ORIGIN).status_code == 422


def test_api_recommend_explain_uses_the_fake_model(tmp_path):
    class Explainer:
        def call(self, prompt, tool, model, max_tokens):
            return ToolCall(
                {"explanations": [{"id": "router", "text": "Sorts each ticket first."}]},
                "tool_use",
                1,
                1,
            )

    def app(host):
        return TestClient(
            create_app(
                workspace=Workspace(tmp_path / "h" / "workspace.json"),
                credentials=Credentials(env={}, home=tmp_path / "u"),
                home=tmp_path / "h",
                user_skills_dir=tmp_path / "none",
                web_dist=tmp_path / "nodist",
                host_login=lambda: host,
                cli_model=Explainer,
            ),
            base_url=BASE,
        )

    body = {"use_case": "triage support tickets with approvals", "explain": True}
    out = (
        app({"email": "me@example.com"})
        .post("/api/garage/recommend", json=body, headers=ORIGIN)
        .json()
    )
    by_id = {p["id"]: p["explanation"] for p in out["picks"]}
    assert by_id["router"] == "Sorts each ticket first."
    assert sum(v is not None for v in by_id.values()) == 1
    # Not signed in and no key: the ranking comes back, with a note, and no model is called.
    out = app(None).post("/api/garage/recommend", json=body, headers=ORIGIN).json()
    assert out["picks"] and out["note"] and all(p["explanation"] is None for p in out["picks"])


def test_coding_tasks_get_coding_architectures_and_one_word_is_a_weak_fit():
    from proving_ground.catalog_arch import recommend

    fix = recommend("fix bugs in a python web app", {})
    assert fix and fix[0]["id"] == "evaluator-optimizer" and not fix[0]["weak"]
    feature = [r["id"] for r in recommend("add a feature across a large codebase", {})[:3]]
    assert "orchestrator-workers" in feature
    # "refund" alone points at approvals, but only as a hint, ranked below the real fit.
    refund = recommend("Fix refund bugs without breaking the plan limits.", {})
    assert refund[0]["id"] == "evaluator-optimizer"
    hitl = next(r for r in refund if r["id"] == "human-in-the-loop")
    assert hitl["weak"]


@pytest.mark.parametrize("e", catalog_arch.entries(), ids=lambda e: e["id"])
def test_every_design_opens_a_lab_workflow_of_its_own_kind(e):
    got = catalog_arch.lab_workflow(e["id"], "", [])
    wf = got["workflow"]
    kind, _, ref = e["lab_workflow"].partition(":")
    assert kind == ("rag" if e["family"] == "rag" else "pattern")
    assert wf.origin == kind and wf.steps
    if kind == "rag":
        assert wf.discipline == "research"
    else:
        assert wf.name == skills.load("workflow-patterns").values["patterns"][ref]["name"]
    # A stand-in (the Lab can't run all of it) always says so.
    if e["id"] == "multimodal-rag":
        assert "Naive RAG" in got["note"]


def test_the_hand_off_matches_the_design_not_a_generic_starter():
    pick = lambda i: catalog_arch.lab_workflow(i, "", [])["workflow"]  # noqa: E731
    assert pick("human-in-the-loop").name == "Human-in-the-loop approvals"
    assert any(s.name == "Approval gate" for s in pick("human-in-the-loop").steps)
    assert pick("agentic-rag").name.startswith("Agentic RAG")
    assert pick("evaluator-optimizer").loops == [["evaluator", "generator", 3]]
    lats = pick("lats")
    assert max(len(stage) for stage in __import__("proving_ground.lab").lab.levels(lats)) == 3
    assert {s.kind for s in lats.steps} == {"think", "do", "judge"}


def test_a_pattern_takes_the_use_cases_discipline_and_says_why():
    got = catalog_arch.lab_workflow("router", "route support tickets to the right queue", [])
    assert got["discipline"] == "support" and got["matched"]
    assert got["workflow"].discipline == "support"
    # Nothing to go on: the family's default (development for agents, research for RAG).
    assert catalog_arch.discipline_for("", "agent") == ("development", [])
    assert catalog_arch.discipline_for("", "rag") == ("research", [])
    # RAG keeps its bench's discipline whatever the use case says.
    assert catalog_arch.lab_workflow("naive-rag", "fix flaky tests", [])["discipline"] == "research"
    with pytest.raises(KeyError):
        catalog_arch.lab_workflow("nope", "", [])


def test_api_design_to_workflow(env):  # noqa: F811
    c, *_ = env
    r = c.post(
        "/api/garage/workflow",
        json={"entry": "human-in-the-loop", "use_case": "triage support tickets"},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workflow"]["name"] == "Human-in-the-loop approvals"
    assert body["discipline"] == "support" and body["discipline_label"] == "Support"
    assert body["workflow"]["discipline"] == "support" and body["matched"]
    # The workflow comes back runnable: pricing it again changes nothing that matters.
    again = c.post("/api/lab/price", json=body["workflow"], headers=ORIGIN).json()
    assert [s["id"] for s in again["steps"]] == [s["id"] for s in body["workflow"]["steps"]]
    assert c.post("/api/garage/workflow", json={"entry": "nope"}, headers=ORIGIN).status_code == 404


def test_too_little_to_rank_shows_the_close_designs_and_what_to_add():
    text = "support agent workflow"
    scored = catalog_arch.scored(text)
    assert catalog_arch.ranked(scored) == []
    got = catalog_arch.empty_state(text, scored)
    assert got["matched"] == "Only 'support' and 'workflow' matched, too little to rank on."
    assert got["title"] == "No fits yet" and got["heading"] == "Close, not a fit yet"
    near = {n["id"]: n["matched"] for n in got["near"]}
    assert near["router"] == ["support"] and near["swarm-handoffs"] == ["support"]
    assert near["plan-and-execute"] == ["workflow"]
    intents = skills.value("architecture-catalog", "intents")
    assert intents["routing"]["ask"] in got["asks"] and intents["handoffs"]["ask"] in got["asks"]
    assert got["words"].startswith("Words like tickets, customer")
    assert got["browse"] == "Or browse them all below."
    # Every word it suggests would rank one of them for real.
    more = got["words"].removeprefix("Words like ").removesuffix(" count too.")
    for w in more.replace(" or ", ", ").split(", "):
        assert catalog_arch.recommend(f"{text} {w}"), w


def test_no_word_matched_says_so_and_points_at_the_catalog():
    got = catalog_arch.empty_state("help with things", catalog_arch.scored("help with things"))
    assert got["matched"] == "None of its words point at a design."
    assert got["near"] == [] and got["asks"] == [] and got["words"] is None
    assert "browse below" in got["browse"]


@pytest.mark.parametrize("iid", list(skills.value("architecture-catalog", "intents")))
def test_every_intent_says_what_to_add(iid):
    assert skills.value("architecture-catalog", "intents")[iid]["ask"].strip()


def test_api_empty_state_and_explain_with_no_picks_asks_nothing(tmp_path):
    calls = []

    class Explainer:
        def call(self, prompt, tool, model, max_tokens):
            calls.append(model)
            return ToolCall({"explanations": []}, "tool_use", 1, 1)

    c = TestClient(
        create_app(
            workspace=Workspace(tmp_path / "h" / "workspace.json"),
            credentials=Credentials(env={}, home=tmp_path / "u"),
            home=tmp_path / "h",
            user_skills_dir=tmp_path / "none",
            web_dist=tmp_path / "nodist",
            host_login=lambda: {"email": "me@example.com"},
            cli_model=Explainer,
        ),
        base_url=BASE,
    )
    body = {"use_case": "support agent workflow", "explain": True}
    out = c.post("/api/garage/recommend", json=body, headers=ORIGIN).json()
    assert out["picks"] == [] and calls == []
    assert out["note"] == skills.value("architecture-catalog", "explain_nothing")
    assert out["empty"]["matched"].startswith("Only 'support'")
    assert {n["id"] for n in out["empty"]["near"]} >= {"router", "swarm-handoffs"}
    # With picks there is no empty state, and no note unless the model was asked.
    out = c.post(
        "/api/garage/recommend", json={"use_case": "triage support tickets"}, headers=ORIGIN
    ).json()
    assert out["picks"] and out["empty"] is None and out["note"] is None


def test_a_phrase_matches_its_first_word_in_any_form_too():
    for said in ("hands off to a person", "handed off", "handing off", "hand-off", "hand off"):
        assert "handoffs" in [i["id"] for i in catalog_arch.intents(said)], said
    # "hands-off", the adjective, is not a handoff: an inflected first word needs a space.
    assert catalog_arch.intents("a hands-off approach") == []
    top = catalog_arch.recommend(
        "customer support agent that answers tickets and hands off to a person"
    )[0]
    assert top["id"] == "swarm-handoffs" and top["fit"] == "strong"
    assert top["reasons"][0].startswith("Because you said 'hands off to a person'")
