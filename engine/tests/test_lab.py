from pathlib import Path

from proving_ground.lab import (
    compile_workflow,
    from_pattern,
    load_workflow,
    random_workflow,
    starters,
)

LIB = [
    {"path": "/lib/tdd", "name": "tdd", "description": "Write a failing test first, then the fix"},
    {
        "path": "/lib/prd-writer",
        "name": "prd-writer",
        "description": "Write PRD requirements and success metrics",
    },
    {
        "path": "/lib/review",
        "name": "careful-review",
        "description": "Review the diff before finishing",
    },
]


def test_starters_cover_disciplines_with_models_and_skills():
    ds = {d["id"]: d for d in starters(LIB)}
    assert {
        "development",
        "qa",
        "product",
        "design",
        "data",
        "devops",
        "security",
        "docs",
        "support",
        "research",
        "marketing",
        "leadership",
    } <= set(ds)
    bug = next(w for w in ds["development"]["workflows"] if w["name"] == "Fix a bug")
    kinds = {s["name"]: (s["kind"], s["model"]) for s in bug["steps"]}
    assert kinds["Write a failing test"] == ("do", "claude-sonnet-5-5")
    assert kinds["Run the tests"] == ("check", "claude-haiku-5-5")
    assert kinds["Review the diff"] == ("think", "claude-opus-5-5")
    # Library skills are attached where their words fit the step, with the reason.
    tf = next(s for s in bug["steps"] if s["id"] == "test-first")
    assert tf["skills"] == [
        {"path": "/lib/tdd", "name": "tdd", "why": "matched: failing test; name 1/1"}
    ]
    prd = next(w for w in ds["product"]["workflows"] if w["name"] == "Write a PRD")
    assert any(s["skills"] and s["skills"][0]["name"] == "prd-writer" for s in prd["steps"])
    assert bug["loop"] == ["run-tests", "implement", 3] and bug["prior"] > 0 and bug["why"]


def test_random_workflows_are_sensible_and_new():
    shown: set[str] = set()
    for seed in range(40):
        wf = random_workflow(LIB, None, seed, shown)
        assert wf.id not in shown
        shown.add(wf.id)
        kinds = [s.kind for s in wf.steps]
        assert "do" in kinds
        if wf.loop:
            ids = [s.id for s in wf.steps]
            assert ids.index(wf.loop[0]) > ids.index(wf.loop[1])  # loops go back, never forward
    qa = random_workflow(LIB, "qa", 3)
    assert qa.discipline == "qa" and qa.origin == "random"


def test_patterns_become_workflows_with_pinned_models():
    esc = from_pattern("escalate", "claude-sonnet-5-5", LIB)
    assert [s.model for s in esc.steps] == ["claude-haiku-5-5", "claude-opus-5-5"]
    assert from_pattern("direct", "claude-sonnet-5-5", LIB).prior == 0


def test_compile_writes_a_runnable_skill_with_a_subagent_per_step(tmp_path: Path):
    bug = next(
        w
        for d in starters(LIB)
        if d["id"] == "development"
        for w in d["workflows"]
        if w["name"] == "Fix a bug"
    )
    wf = load_workflow(bug)
    out = compile_workflow(
        wf, tmp_path / "wf", {"/lib/tdd": "---\nname: tdd\n---\nAlways start from a red test."}
    )
    skill = (out / "SKILL.md").read_text()
    assert (
        skill.startswith("---\nname: workflow-") and "## Loop" in skill and "Run the tests" in skill
    )
    agents = sorted(p.name for p in (out / "agents").iterdir())
    assert agents == ["explore.md", "implement.md", "review.md", "run-tests.md", "test-first.md"]
    tf = (out / "agents" / "test-first.md").read_text()
    assert "model: sonnet" in tf and "Always start from a red test." in tf
    assert "model: opus" in (out / "agents" / "review.md").read_text()


def test_compiling_again_never_leaves_the_folder_missing_or_half_written(tmp_path: Path):
    # A suite compiles the same workflow for every bench while earlier runs still read it.
    bug = next(
        w
        for d in starters(LIB)
        if d["id"] == "development"
        for w in d["workflows"]
        if w["name"] == "Fix a bug"
    )
    wf = load_workflow(bug)
    out = compile_workflow(wf, tmp_path / "wf")
    (out / ".saved").write_text("")
    before = {f.name: f.stat().st_ino for f in out.iterdir()}
    # Unchanged: the folder is left as it was, not deleted and written again.
    assert compile_workflow(wf, tmp_path / "wf") == out
    assert {f.name: f.stat().st_ino for f in out.iterdir()} == before
    # Changed: the new folder is swapped in whole, still saved, with nothing left beside it.
    wf.name = "Fix a bug, carefully"
    compile_workflow(wf, tmp_path / "wf")
    assert '"name": "Fix a bug, carefully"' in (out / "workflow.json").read_text()
    assert (out / ".saved").is_file()
    assert [p.name for p in tmp_path.iterdir()] == ["wf"]


def test_lab_api_needs_no_repo(tmp_path: Path):
    from fastapi.testclient import TestClient
    from test_api_workspace import BASE, ORIGIN
    from test_catalog import FakeGitHub

    from proving_ground.agents import Credentials
    from proving_ground.api.app import create_app
    from proving_ground.workspace import Workspace

    skills_dir = tmp_path / "skills" / "tdd"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: tdd\ndescription: Write a failing test first\n---\nRed, green.\n"
    )
    c = TestClient(
        create_app(
            workspace=Workspace(tmp_path / "ws.json"),
            credentials=Credentials(env={}, home=tmp_path / "h"),
            github=FakeGitHub(),
            home=tmp_path / "home",
            user_skills_dir=tmp_path / "skills",
            web_dist=tmp_path / "nodist",
            host_login=lambda: None,
        ),
        base_url=BASE,
    )
    assert c.get("/api/repos").json() == []  # no repo attached
    lab = c.get("/api/lab").json()
    assert (
        len(lab["disciplines"]) == 12
        and len(lab["business"]) == 15
        and len(lab["patterns"]) == 25
        and lab["skills"][0]["name"] == "tdd"
    )
    # The page gets the reason a skill was attached, to show next to it.
    bug = next(w for d in lab["disciplines"] for w in d["workflows"] if w["name"] == "Fix a bug")
    tf = next(s for s in bug["steps"] if s["id"] == "test-first")
    assert [(s["name"], s["why"]) for s in tf["skills"]] == [
        ("tdd", "matched: failing test; name 1/1")
    ]
    wf = c.post(
        "/api/lab/random", json={"discipline": "development", "seed": 1}, headers=ORIGIN
    ).json()
    assert wf["discipline"] == "development" and wf["steps"]
    wf["steps"][0]["model"] = "claude-haiku-5-5"
    priced = c.post("/api/lab/price", json=wf, headers=ORIGIN).json()
    assert priced["cost"] <= wf["cost"]
    saved = c.post("/api/lab/save", json=priced, headers=ORIGIN).json()
    assert Path(saved["path"], "SKILL.md").is_file()
    assert c.get("/api/lab").json()["saved"][0]["id"] == wf["id"]


def test_a_graph_with_parallel_steps_joins_and_loops_compiles_by_stage(tmp_path: Path):
    from proving_ground.lab import levels

    wf = load_workflow(
        {
            "id": "g1",
            "name": "Release review",
            "discipline": "development",
            "origin": "custom",
            "steps": [
                {
                    "id": "plan",
                    "name": "Plan",
                    "does": "Plan it.",
                    "kind": "think",
                    "model": "claude-opus-5-5",
                },
                {
                    "id": "code",
                    "name": "Implement",
                    "does": "Code it.",
                    "kind": "do",
                    "model": "claude-sonnet-5-5",
                },
                {
                    "id": "docs",
                    "name": "Document",
                    "does": "Write docs.",
                    "kind": "do",
                    "model": "claude-haiku-5-5",
                },
                {
                    "id": "test",
                    "name": "Run the tests",
                    "does": "Test it.",
                    "kind": "check",
                    "model": "claude-haiku-5-5",
                },
                {
                    "id": "review",
                    "name": "Review",
                    "does": "Review it.",
                    "kind": "judge",
                    "model": "claude-sonnet-5-5",
                },
            ],
            "edges": [
                ["plan", "code"],
                ["plan", "docs"],
                ["code", "test"],
                ["test", "review"],
                ["docs", "review"],
            ],
            "loops": [["test", "code", 3], ["review", "plan", 1]],
        }
    )
    assert levels(wf) == [["plan"], ["code", "docs"], ["test"], ["review"]]
    assert any("parallel" in w for w in wf.why) and sum("Loops back" in w for w in wf.why) == 2
    text = (compile_workflow(wf, tmp_path / "g") / "SKILL.md").read_text()
    assert "run these 2 steps in parallel" in text
    assert (
        "(Waits for: Run the tests, Document" in text
        or "(Waits for: Document, Run the tests" in text
    )
    assert text.count("go back to") == 2


def test_cycles_must_be_drawn_as_loops():
    import pytest

    with pytest.raises(ValueError, match="circle"):
        load_workflow(
            {
                "id": "c",
                "name": "c",
                "discipline": "development",
                "origin": "custom",
                "steps": [
                    {
                        "id": "a",
                        "name": "A",
                        "does": "x",
                        "kind": "do",
                        "model": "claude-sonnet-5-5",
                    },
                    {
                        "id": "b",
                        "name": "B",
                        "does": "x",
                        "kind": "do",
                        "model": "claude-sonnet-5-5",
                    },
                ],
                "edges": [["a", "b"], ["b", "a"]],
            }
        )


def test_old_list_workflows_become_chains():
    bug = next(
        w
        for d in starters(LIB)
        if d["id"] == "development"
        for w in d["workflows"]
        if w["name"] == "Fix a bug"
    )
    assert bug["edges"][0] == ["explore", "test-first"] and bug["loops"] == [
        ["run-tests", "implement", 3]
    ]


def test_business_workflows_are_real_graphs_with_sources(tmp_path: Path):
    from proving_ground.lab import business, levels, templates

    wfs = business(LIB)
    assert len(wfs) >= 15
    assert {"finance", "compliance"} <= {w.discipline for w in wfs}
    for w in wfs:
        assert w.origin == "business" and len(w.steps) >= 7
        assert w.why[0].startswith("Modelled on: ")
        stages = levels(w)
        assert max(len(s) for s in stages) >= 2, f"{w.name} has no parallel stage"
        assert w.loops, f"{w.name} has no loop"
        ins: dict[str, int] = {}
        for _, b in w.edges:
            ins[b] = ins.get(b, 0) + 1
        assert max(ins.values()) >= 2, f"{w.name} has no join"
    kyc = next(w for w in wfs if w.name == "KYC onboarding")
    # Sanctions, PEP and adverse media screen in parallel, then the risk rating waits for all three.
    assert {"sanctions", "pep", "media"} in [set(s) for s in levels(kyc)]
    text = compile_workflow(kyc, tmp_path / "kyc").joinpath("SKILL.md").read_text()
    assert "in parallel" in text.lower() and "Rate the risk" in text
    # The disciplines they add are there to build and randomise with.
    assert {"finance", "compliance"} <= {t["id"] for t in templates()}
    assert random_workflow(LIB, "finance", 3).discipline == "finance"


def test_each_agent_gets_its_own_form_of_the_workflow(tmp_path: Path):
    from proving_ground.lab import business, workflow_name

    wf = next(w for w in business(LIB) if w.name == "KYC onboarding")
    cc = compile_workflow(wf, tmp_path / "cc").joinpath("SKILL.md").read_text()
    assert "Agent tool" in cc and "model `opus`" in cc and (tmp_path / "cc" / "agents").is_dir()
    oc = compile_workflow(wf, tmp_path / "oc", agent="opencode").joinpath("SKILL.md").read_text()
    assert "task tool" in oc and "model `" not in oc and not (tmp_path / "oc" / "agents").exists()
    cx = compile_workflow(wf, tmp_path / "cx", agent="codex").joinpath("SKILL.md").read_text()
    assert "## Step 3: Sanctions screening" in cx and "subagent" not in cx.lower()
    assert 'echo "PG""_STEP:sanctions"' in cx and "PG_STEP:" not in cx  # only running it prints one
    assert "in any order" in cx  # the parallel screening, done one after another
    assert f"name: {workflow_name(wf, 'codex')}" in cx and workflow_name(wf).endswith(wf.id)
    import pytest

    with pytest.raises(ValueError, match="No way to write"):
        compile_workflow(wf, tmp_path / "x", agent="aider")


def test_phase_adherence_for_agents_without_subagents(tmp_path: Path):
    from proving_ground import adherence
    from proving_ground.lab import business

    wf = next(w for w in business(LIB) if w.name == "Invoice three-way match").dump()
    trial = tmp_path / "t"
    (trial / "agent").mkdir(parents=True)
    names = [s["name"] for s in wf["steps"]]
    # A Codex log: JSON lines with the headings inside escaped strings; one step skipped.
    lines = [
        __import__("json").dumps({"type": "message", "text": f"## Step {i}: {n}\nworking..."})
        for i, n in enumerate(names, 1)
        if n != "Route exceptions"
    ]
    (trial / "agent" / "codex.txt").write_text("\n".join(lines))
    a = adherence.check(wf, trial, "gpt-5", "codex")
    assert a.found and a.steps_run == len(names) - 1 and a.missing == ["Route exceptions"]
    assert a.models_ok == a.steps_run  # one model for the whole session: nothing to get wrong

    # With step markers, a heading the agent wrote into a document does not count as a step.
    marked = tmp_path / "m"
    (marked / "agent").mkdir(parents=True)
    ids = {s["name"]: s["id"] for s in wf["steps"]}
    skipped = {"Route exceptions", "Resolve"}
    lines = [
        __import__("json").dumps({"type": "output", "text": f"PG_STEP:{ids[n]}"})
        for n in names
        if n not in skipped
    ]
    # The agent wrote a document quoting an old workflow's heading: it must not count as Resolve.
    lines.append(__import__("json").dumps({"type": "file", "text": "## Step 9: Resolve\nnotes"}))
    (marked / "agent" / "codex.jsonl").write_text("\n".join(lines))
    m = adherence.check(wf, marked, "gpt-5", "codex")
    assert m.found and m.steps_run == len(names) - 2 and sorted(m.missing) == sorted(skipped)
    # A marker with an unknown id is ignored.
    (marked / "agent" / "codex.jsonl").write_text(
        (marked / "agent" / "codex.jsonl").read_text() + '\n{"cmd": "echo PG_STEP:nope"}'
    )
    assert adherence.check(wf, marked, "gpt-5", "codex").steps_run == len(names) - 2


def test_printing_the_workflow_does_not_fake_its_markers(tmp_path: Path):
    """An agent that only prints SKILL.md (into its log) must not look like it ran every step."""
    from proving_ground import adherence
    from proving_ground.lab import business

    w = next(x for x in business(LIB) if x.name == "Invoice three-way match")
    skill = compile_workflow(w, tmp_path / "cx", agent="codex").joinpath("SKILL.md").read_text()
    trial = tmp_path / "t"
    (trial / "agent").mkdir(parents=True)
    (trial / "agent" / "codex.txt").write_text(skill)
    a = adherence.check(w.dump(), trial, "gpt-5", "codex")
    assert a.steps_run == 0


def test_the_same_workflow_always_gets_the_same_guess():
    """learned-priors: pricing a workflow again (a reload re-prices the saved draft) never moves
    its number. An unedited pattern keeps its pattern's prior; ties between models don't flip."""
    from proving_ground import gate, lab

    for pid in lab.W["patterns"]:
        wf = from_pattern(pid, "claude-sonnet-5-5", LIB)
        again = load_workflow(wf.dump())
        assert (again.prior, again.why, again.cost) == (wf.prior, wf.why, wf.cost), pid
        assert load_workflow(again.dump()).prior == wf.prior
    for d in starters(LIB):
        for w in d["workflows"]:
            assert load_workflow(w).prior == w["prior"], w["name"]
    # Edited (no longer origin "pattern"), it is priced from its shape like any workflow.
    hil = from_pattern("approval-gate", "claude-sonnet-5-5", LIB).dump()
    mine = load_workflow(hil | {"origin": "custom"})
    assert mine.why != [lab._pattern_helps("approval-gate", "pattern")]
    # A tie between two models goes to the earliest step's, whatever the set order.
    assert gate.session_model(["claude-opus-5-5", "claude-sonnet-5-5"]) == "claude-opus-5-5"
    assert gate.session_model(["claude-sonnet-5-5", "claude-opus-5-5"]) == "claude-sonnet-5-5"
    two = load_workflow(
        {
            "id": "t",
            "name": "T",
            "discipline": "development",
            "origin": "custom",
            "steps": [
                {"id": "a", "name": "A", "does": "a", "kind": "do", "model": "claude-haiku-5-5"},
                {"id": "b", "name": "B", "does": "b", "kind": "do", "model": "claude-opus-5-5"},
            ],
        }
    )
    assert "tier:fast" in lab.features(two)


def test_a_steps_model_moves_the_guess_more_on_thinking_than_on_checks():
    """learned-priors: model_weight_by_kind. Opus to Haiku on a planning step costs more points
    than the same swap on a check; the reason is in the workflow's why."""
    from proving_ground import lab

    bug = next(w for d in starters(LIB) for w in d["workflows"] if w["name"] == "Fix a bug")
    base = load_workflow(bug)

    def swap(kind: str, to: str) -> float:
        d = base.dump()
        st = next(s for s in d["steps"] if s["kind"] == kind)
        st["model"] = to
        return load_workflow(d | {"origin": "custom"}).prior

    think_down = swap("think", "claude-haiku-5-5")
    check_up = swap("check", "claude-opus-5-5")
    assert think_down < base.prior < check_up
    weights = lab.P["model_weight_by_kind"]
    total = sum(weights[s.kind] for s in base.steps)
    opus, haiku = (lab.W["models"][m]["prior"] for m in ("claude-opus-5-5", "claude-haiku-5-5"))
    # Exactly the weighted share of the model's prior change (to the rounding of each prior).
    assert abs((base.prior - think_down) - weights["think"] * (opus - haiku) / total) <= 0.1
    assert abs((check_up - base.prior) - weights["check"] * (opus - haiku) / total) <= 0.1
    assert (base.prior - think_down) > (check_up - base.prior)
    assert any(w.startswith("Models (") and "a guess" in w for w in base.why)
    # A pattern on Haiku guesses lower than on Opus, by the models' priors.
    lo = from_pattern("plan-act-verify", "claude-haiku-5-5", LIB).prior
    hi = from_pattern("plan-act-verify", "claude-opus-5-5", LIB).prior
    assert hi - lo == opus - haiku
