import json
from pathlib import Path

from test_architecture import TOOL, write

from proving_ground.architecture import infer_architecture, parse_data
from proving_ground.architecture.advise import advise, apply
from proving_ground.placement import Block, place


def spec(components, connections=()):
    return parse_data(
        {
            "diagram_type": "architecture",
            "components": components,
            "connections": list(connections),
        },
        source="mapped",
    )


def titles(ps):
    return [p.title for p in ps]


def test_rules_find_hot_paths_shared_flows_cycles_inputs_and_planned_links(tmp_path: Path):
    a = spec(
        [
            {"id": "user", "type": "external", "label": "User"},
            {"id": "ui", "type": "frontend", "label": "Web UI"},
            {"id": "cli", "type": "frontend", "label": "CLI"},
            {"id": "api", "type": "backend", "label": "API", "sublabel": "FastAPI"},
            {"id": "jobs", "type": "backend", "label": "Jobs"},
            {"id": "billing", "type": "backend", "label": "Billing"},
            {"id": "ledger", "type": "backend", "label": "Ledger"},
            {"id": "driver", "type": "frontend", "label": "Driver"},
            {"id": "claude", "type": "external", "label": "Anthropic API"},
        ],
        [
            {"from": "user", "to": "ui"},
            {"from": "user", "to": "cli"},
            *[{"from": w, "to": t} for w in ("ui", "cli") for t in ("api", "jobs", "billing")],
            {"from": "api", "to": "claude"},
            {"from": "billing", "to": "ledger"},
            {"from": "ledger", "to": "billing"},
            {"from": "driver", "to": "api", "variant": "planned", "label": "screen state"},
        ],
    )
    ps = advise(tmp_path, a, [("fix", "code")], {}, [])
    t = titles(ps)
    assert "Move model calls off the request path" in t
    assert "Let Web UI and CLI share one flow" in t
    assert "Break the loop between Billing and Ledger" in t
    assert "Show where Driver gets its input" in t
    assert "Build the link from Driver to API" in t
    assert "Add a CLAUDE.md with the commands" in t
    assert "Add a verify step to the workflow" in t
    hot = next(p for p in ps if p.title.startswith("Move model calls"))
    assert hot.impact["speed"] and hot.delta["disconnect"] == [["api", "claude"]]
    # Accepting it redraws the architecture with the queue and the worker.
    b = apply(a, [hot.dump()])
    lines = {(x.from_, x.to) for x in b.connections}
    assert (
        ("api", "claude") not in lines
        and ("api", "api-jobs") in lines
        and ("api-model-worker", "claude") in lines
    )
    assert all(c.pos for c in b.components)


def test_big_blocks_are_split_along_their_folders(tmp_path: Path):
    for part, n in (("alpha", 2600), ("beta", 1800)):
        f = tmp_path / "svc" / part / "x.py"
        f.parent.mkdir(parents=True)
        f.write_text("x = 1\n" * n)
    a = spec([{"id": "svc", "type": "backend", "label": "Service", "evidence": ["svc/"]}])
    split = next(
        p
        for p in advise(tmp_path, a, None, None, ["CLAUDE.md"])
        if p.kind == "split" and "folders" in p.title
    )
    assert "alpha/ (2,600)" in split.why and [x["label"] for x in split.delta["add"]] == [
        "alpha",
        "beta",
    ]


def test_this_repo_shape_gets_grounded_proposals(tmp_path: Path):
    write(tmp_path, TOOL)
    ps = advise(tmp_path, infer_architecture(tmp_path), None, None, [])
    # The FastAPI app calls the Claude API directly.
    assert any(p.title == "Move model calls off the request path" for p in ps)
    # Every proposal says why, what, and what it improves.
    assert all(p.why and p.what and p.impact for p in ps)


def test_place_puts_items_next_to_what_they_serve():
    blocks = [
        Block("arch:db", "database", "PostgreSQL", "Store · Hikari pool"),
        Block("arch:api", "backend", "Brain", "Planner service · Spring Boot"),
        Block("step:triage", "step", "triage", "", "research", 0),
        Block("step:verify", "step", "verify", "", "test", 2),
        Block("setup:CLAUDE.md", "setup", "CLAUDE.md", "agent setup"),
    ]
    mcp = place(blocks, "mcp-postgres", "MCP server for PostgreSQL databases", [], "mcp")
    assert mcp["targets"][0]["id"] == "arch:db" and "postgresql" in mcp["reason"]
    tdd = place(blocks, "tdd", "Write a failing test first", [], "skill", "Testing & quality")
    assert tdd["targets"][0]["id"] == "step:verify"
    hook = place(blocks, "guard", "Block risky commands", [], "hook")
    assert hook["targets"][0]["id"] == "setup:CLAUDE.md"
    flow = place(blocks, "spec-first", "Spec-driven workflow", [], "workflow")
    assert flow["targets"][0]["id"] == "step:triage"
    assert place([], "x", "", [], "skill")["targets"] == []


def test_suggestions_api_decide_and_propose(tmp_path: Path):
    from fastapi.testclient import TestClient
    from test_api_workspace import BASE, ORIGIN
    from test_catalog import FakeGitHub

    from proving_ground.agents import Credentials
    from proving_ground.api.app import create_app

    write(tmp_path / "tool", TOOL)
    app = create_app(
        root=tmp_path / "tool",
        credentials=Credentials(env={}, home=tmp_path / "h"),
        github=FakeGitHub(),
        home=tmp_path / "home",
        user_skills_dir=tmp_path / "none",
        web_dist=tmp_path / "nodist",
        host_login=lambda: None,
    )
    c = TestClient(app, base_url=BASE)
    ps = c.get("/api/suggestions").json()["proposals"]
    hot = next(p for p in ps if p["title"] == "Move model calls off the request path")
    assert hot["state"] == "open"
    assert (
        c.put(
            f"/api/suggestions/{hot['id']}", json={"state": "accepted"}, headers=ORIGIN
        ).status_code
        == 200
    )
    prop = c.get("/api/architecture/proposed").json()
    assert prop["accepted"] == [hot["id"]]
    assert prop["archify"]["diagram_type"] == "architecture"
    assert any(x["label"] == "Model worker" for x in prop["archify"]["components"])
    # Only accepted ones are drawn (open ones only when previewed); what they take away stays
    # on the canvas, marked.
    assert prop["shown"] == [hot["id"]]
    d = prop["diff"]
    assert "Model worker" in d["added"] and d["suggestions"] == 1 and d["drawn"] == 1
    # Each new part names the suggestion it came from; the brief's tasks are listed by name.
    worker = next(x for x in prop["architecture"]["components"] if x["label"] == "Model worker")
    assert prop["origins"][worker["id"]] == {"id": hot["id"], "title": hot["title"], "state": "accepted"}
    # Each with its measurability state, as on Build: it adds a part, so it changes the code.
    assert d["task_items"] == [
        {"id": hot["id"], "title": hot["title"], "measure": "before_after"}
    ] and d["note_items"] == []
    assert hot["measure"] == "before_after"
    # Previewing an open one draws only it.
    other = next(p for p in ps if p["state"] == "open" and p["id"] != hot["id"])
    seen = c.get("/api/architecture/proposed", params={"preview": other["id"]}).json()
    assert seen["shown"] == [other["id"]] and seen["accepted"] == []
    # Every suggestion says whether Measure can test it; moving model calls changes the code.
    assert hot["measure"] == "before_after"
    assert all(p["measure"] for p in ps)
    kept = {c["id"]: c for c in prop["architecture"]["components"]}
    assert all(kept[c]["source"] == "removed" for c in kept if kept[c].get("source") == "removed")
    placed = c.post(
        "/api/place",
        json={
            "name": "claude-api-retries",
            "description": "Retries for Claude API calls",
            "category": "skill",
        },
        headers=ORIGIN,
    ).json()
    assert placed["targets"][0]["id"] == "arch:claude-api"
    assert (
        c.post("/api/suggestions/review", json={"agent": "codex"}, headers=ORIGIN).status_code
        == 400
    )


def test_review_keeps_only_grounded_proposals(tmp_path: Path):
    import subprocess

    from proving_ground.architecture.review import review

    (tmp_path / "server").mkdir()
    (tmp_path / "server" / "app.py").write_text("x = 1\n")
    a = spec(
        [
            {"id": "api", "type": "backend", "label": "API"},
            {"id": "db", "type": "database", "label": "DB"},
        ],
        [{"from": "api", "to": "db"}],
    )
    reply = {
        "proposals": [
            {"title": "Pool connections", "kind": "add", "targets": ["api", "db"], "why": "opens one per request",
             "what": "add a pool", "impact": {"speed": "fewer connects"}, "effort": "S", "evidence": ["server/app.py"]},
            {"title": "Invented", "kind": "add", "targets": ["ghost"], "why": "x", "what": "x",
             "impact": {"speed": "x"}, "evidence": ["server/app.py"]},
            {"title": "No evidence", "kind": "add", "targets": ["api"], "why": "x", "what": "x",
             "impact": {"speed": "x"}, "evidence": ["nope.py"]},
        ]
    }  # fmt: skip

    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"result": json.dumps(reply)}), "")

    got = review(tmp_path, a, "claude-code", run=run)
    assert [p.title for p in got] == ["Pool connections"] and got[0].source == "review"


def test_apply_can_keep_what_it_removes_marked():
    from proving_ground.architecture import Architecture
    from proving_ground.architecture.advise import apply

    a = Architecture.model_validate(
        {
            "title": "t",
            "components": [
                {"id": "a", "label": "A"},
                {"id": "b", "label": "B"},
                {"id": "c", "label": "C"},
            ],
            "connections": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
        }
    )
    p = {
        "delta": {
            "remove": ["c"],
            "disconnect": [["a", "b"]],
            "connect": [["a", "c"]],
            "add": [{"id": "d", "label": "D"}],
        }
    }
    gone = apply(a, [p])
    assert {c.id for c in gone.components} == {"a", "b", "d"} and gone.connections == []
    kept = apply(a, [p], keep_removed=True)
    src = {c.id: c.source for c in kept.components}
    assert src["c"] == "removed" and src["d"] == "proposed"
    variants = {(c.from_, c.to): c.variant for c in kept.connections}
    assert variants[("a", "b")] == "removed" and variants[("b", "c")] == "removed"
    assert ("a", "c") not in variants  # no new link to a removed part


def test_measurability_of_suggestions():
    from proving_ground import skills
    from proving_ground.measurability import of_proposal

    states = skills.value("measurability", "states")
    note = {"kind": "check", "impact": {"clarity": "x"}, "delta": {}}
    split = {"kind": "split", "impact": {"agent": "x"}, "delta": {"add": [{"id": "a"}]}}
    claude = {"kind": "add", "impact": {"agent": "x"}, "delta": {}, "adds": "instructions"}
    task = {"kind": "add", "impact": {"agent": "x"}, "delta": {}, "adds": "task"}
    verify = {"kind": "check", "impact": {"reliability": "x"}, "delta": {}}
    got = [of_proposal(p) for p in (note, split, claude, task, verify)]
    # A CLAUDE.md the repo doesn't have yet is the change: the "with" arm gets it, "without" none.
    assert got == ["note", "before_after", "runnable", "enables", "brief"]
    assert all(g in states for g in got)
    # The switch: a kind's state is read from the skill, so making instructions runnable is one value.
    assert skills.value("measurability", "treatments")["instructions"] == "runnable"
    assert set(skills.value("measurability", "treatments")) == {
        "skill", "loop", "config", "hook", "mcp", "instructions"
    }  # fmt: skip


def test_agent_readiness_says_what_it_adds(tmp_path: Path):
    from proving_ground.architecture.advise import advise

    write(tmp_path, TOOL)
    a = infer_architecture(tmp_path)
    ps = advise(tmp_path, a, [("triage", "research"), ("fix", "code")], {}, [])
    adds = {p.title: p.adds for p in ps if p.adds}
    assert adds.get("Add a CLAUDE.md with the commands") == "instructions"
    assert any(t.startswith("Add a task for") and v == "task" for t, v in adds.items())
    assert adds.get("Add a verify step to the workflow") == "step"
