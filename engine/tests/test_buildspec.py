import json

from fastapi.testclient import TestClient

from proving_ground import buildspec, catalog_arch, lab, skills
from proving_ground.api.app import create_app
from proving_ground.architecture import Architecture

BASE = "http://127.0.0.1:7357"


def arch(*comps, conns=()):
    return Architecture.model_validate(
        {
            "title": "Support bot",
            "components": [
                {"id": i, "label": label, "type": t, "role": r} for i, label, t, r in comps
            ],
            "connections": [{"from": a, "to": b, "label": w} for a, b, w in conns],
        }
    )


def paths(spec):
    return [e["path"] for e in spec["layout"]]


def test_layout_without_retrieval_or_memory():
    s = buildspec.spec_from_architecture(
        arch(("p", "Planner", "backend", "breaks goals into steps"), ("a", "API", "frontend", None))
    )
    ps = paths(s)
    assert not any("retrieval/" in p or "memory/" in p for p in ps)
    assert "retrieval" not in s
    assert any(p.endswith("agents/planner.py") for p in ps)
    assert not any(p.endswith("agents/reviewer.py") for p in ps)


def test_layout_with_retrieval_memory_and_roles():
    s = buildspec.spec_from_architecture(
        arch(
            ("p", "Planner", "backend", None),
            ("e", "Executor", "backend", None),
            ("r", "Reviewer", "backend", None),
            ("v", "Vector index", "database", "retrieval store"),
            ("m", "Session memory", "database", None),
            ("t", "Payments API", "external", "refund and charge cards"),
            conns=[("p", "e", "plan")],
        )
    )
    ps = paths(s)
    for f in ("planner", "executor", "reviewer"):
        assert any(p.endswith(f"agents/{f}.py") for p in ps)
    assert any("retrieval/search.py" in p for p in ps)
    assert any("memory/store.py" in p for p in ps)
    assert any("guardrails/approvals.py" in p for p in ps)
    assert s["retrieval"]["enabled"] and s["memory"]["enabled"]
    tool = next(t for t in s["tools"] if t["component"] == "t")
    assert tool["permission"] == "write" and tool["approval"]
    assert s["flows"][0] == {"from": "p", "to": "e", "what": "plan"}


def test_workflow_spec_has_steps_loops_models_budgets():
    wf = next(w for w in lab.business([]) if w.loops)
    s = buildspec.spec_from_workflow(wf)
    w = s["workflow"]
    assert len(w["steps"]) == len(wf.steps) and w["edges"] and w["loops"]
    assert all(st["model"] for st in w["steps"])
    assert set(s["models"]) == {st.id for st in wf.steps}
    b = s["budgets"]
    assert all(b[k] > 0 for k in ("tokens", "cost_usd", "steps", "time_s"))
    assert len(s["components"]) == len(wf.steps)


def test_markdown_has_every_section_and_is_deterministic():
    s = buildspec.spec_from_architecture(arch(("a", "Agent", "backend", None)))
    md = buildspec.render_markdown(s)
    for name in skills.value("build-spec", "sections"):
        assert f"## {name}" in md
    # A new project in the suggested language (Python: the use case names none).
    assert "support-bot/src/agent_app/agents/executor.py" in md
    assert "agentic-ai-project" not in md
    assert "Language: Python (suggested: the default" in md
    assert md == buildspec.render_markdown(
        buildspec.spec_from_architecture(arch(("a", "Agent", "backend", None)))
    )


def test_api_endpoints(tmp_path):
    root = tmp_path / "shop"
    root.mkdir()
    (root / "app.py").write_text("print('hi')\n")
    (root / "pyproject.toml").write_text("[project]\nname='shop'\ndependencies=['fastapi']\n")
    c = TestClient(
        create_app(root, home=tmp_path / "home"), base_url=BASE, headers={"origin": BASE}
    )
    for src in ("repo", "suggested"):
        r = c.post("/api/buildspec", json={"source": src})
        assert r.status_code == 200, r.text
        # A repo's brief is the changes to make in it: no new-project layout.
        assert r.json()["markdown"].startswith("# BUILD: shop")
        assert r.json()["json"]["kind"] == "change" and "layout" not in r.json()["json"]
    r = c.post("/api/buildspec/save", json={"source": "repo"})
    d = root / ".proving-ground" / "build"
    assert (d / "BUILD.md").is_file()
    assert json.loads((d / "rig.json").read_text())["kind"] == "change"
    assert r.json()["markdown"] == str(d / "BUILD.md")
    wf = lab.business([])[0].dump()
    r = c.post("/api/buildspec", json={"source": "workflow", "workflow": wf})
    assert r.json()["json"]["workflow"]["steps"]
    r = c.post("/api/buildspec/save", json={"source": "workflow", "workflow": wf})
    assert (tmp_path / "home" / "library" / "builds" / wf["id"] / "BUILD.md").is_file()
    assert c.post("/api/buildspec", json={"source": "workflow", "workflow": {}}).status_code == 422


def test_parts_removed_on_the_canvas_are_left_out_of_the_brief(tmp_path):
    root = tmp_path / "shop"
    root.mkdir()
    (root / "app.py").write_text("print('hi')\n")
    (root / "pyproject.toml").write_text("[project]\nname='shop'\ndependencies=['fastapi']\n")
    (root / "docker-compose.yml").write_text(
        "services:\n  api:\n    build: .\n    depends_on: [db]\n  db:\n    image: postgres:16\n"
    )
    c = TestClient(
        create_app(root, home=tmp_path / "home"), base_url=BASE, headers={"origin": BASE}
    )
    full = c.post("/api/buildspec", json={"source": "repo"}).json()["json"]
    ids = [x["id"] for x in full["parts"]]
    assert ids, full
    gone = ids[0]
    r = c.post("/api/buildspec", json={"source": "repo", "removed": [gone]}).json()
    cut = r["json"]
    assert gone not in [x["id"] for x in cut["parts"]]
    assert len(cut["parts"]) == len(ids) - 1
    # And the brief says to take it out.
    assert [x["id"] for x in cut["removed"]] == [gone]
    removed = r["markdown"].split("## Removed", 1)[1].split("\n## ", 1)[0]
    assert f"(`{gone}`)" in removed


def _shop(tmp_path):
    root = tmp_path / "shop"
    root.mkdir()
    (root / "app.py").write_text("print('hi')\n")
    (root / "pyproject.toml").write_text("[project]\nname='shop'\ndependencies=['fastapi']\n")
    c = TestClient(
        create_app(root, home=tmp_path / "home"), base_url=BASE, headers={"origin": BASE}
    )
    return root, c


def _added(root):
    return {
        "skills": [
            {"name": "tdd", "path": str(root / ".claude" / "skills" / "tdd")},
            {
                "name": "careful-review",
                "path": "/elsewhere/library/installed/acme__review",
                "repo": "acme/review",
                "folder": "skills/careful-review",
            },
            {"name": "notes", "path": "/opt/skills/notes"},
        ],
        "repos": [
            {
                "repo": "loops/ralph",
                "name": "ralph",
                "category": "harness",
                "parts": [
                    {
                        "kind": "command",
                        "name": "ship",
                        "path": ".claude/commands/ship.md",
                        "url": "https://github.com/loops/ralph/blob/main/.claude/commands/ship.md",
                        "description": "Ship one change",
                    },
                    {
                        "kind": "agent",
                        "name": "planner",
                        "path": ".claude/agents/planner.md",
                        "url": "https://evil.example/planner.md",
                    },
                ],
            }
        ],
        "planned": [{"name": "write-tests", "ref": "default/write-tests"}],
        "links": [
            {"from": "tdd", "to": "Step 2: fix", "relation": "applies to"},
            {"from": "ship", "to": "planner", "relation": "uses"},
        ],
        "notes": [{"on": "ship", "text": "Run it\nbefore every merge"}],
    }


def test_what_was_placed_on_the_canvas_is_in_the_brief(tmp_path):
    root, c = _shop(tmp_path)
    r = c.post("/api/buildspec", json={"source": "repo", "added": _added(root)})
    assert r.status_code == 200, r.text
    md, spec = r.json()["markdown"], r.json()["json"]
    names = skills.value("build-spec", "added_sections")
    for key in ("skills", "repos", "planned", "links", "notes"):
        assert f"### {names[key]}" in md
    # Inside the repo: a relative path. From GitHub: its folder's URL. Else the local folder.
    assert "- **tdd**: in this repo at `./.claude/skills/tdd`" in md
    assert "https://github.com/acme/review/tree/HEAD/skills/careful-review" in md
    assert "- **notes**: a local folder: `/opt/skills/notes`" in md
    assert "### ralph (loops/ralph, harness)" in md
    assert (
        "- command **ship** `.claude/commands/ship.md` (https://github.com/loops/ralph/blob/main/.claude/commands/ship.md): Ship one change"
        in md
    )
    # A part URL that is not the repo's own on GitHub is dropped, never linked.
    assert "evil.example" not in md
    assert "- write-tests (`default/write-tests`)" in md
    assert "- tdd -> Step 2: fix: applies to" in md and "- ship -> planner: uses" in md
    # A note stays one line in the Markdown.
    assert "- ship: Run it before every merge" in md
    assert "Added on the canvas: 3 skills, 1 GitHub repo, 2 parts, 1 planned part, 2 links." in md
    assert spec["added"]["skills"][0]["name"] == "careful-review"  # sorted by name
    # In a repo's brief the canvas sections are under "Placed on the canvas", before Removed.
    assert (
        md.index("## Changes")
        < md.index("## Placed on the canvas")
        < md.index(f"### {names['skills']}")
        < md.index("## Removed")
    )
    # rig.json holds the same facts, and saving writes them.
    c.post("/api/buildspec/save", json={"source": "repo", "added": _added(root)})
    saved = json.loads((root / ".proving-ground" / "build" / "rig.json").read_text())
    assert saved["added"] == spec["added"]


def test_canvas_brief_is_deterministic_and_order_free(tmp_path):
    root, c = _shop(tmp_path)
    a = _added(root)
    # Everything listed in the other order; a repo's parts keep theirs (their flow order).
    b = {k: list(reversed(v)) for k, v in a.items()}
    one = c.post("/api/buildspec", json={"source": "repo", "added": a}).json()["markdown"]
    two = c.post("/api/buildspec", json={"source": "repo", "added": a}).json()["markdown"]
    flipped = c.post("/api/buildspec", json={"source": "repo", "added": b}).json()["markdown"]
    assert one == two == flipped
    # An empty canvas adds no sections and leaves the summary alone.
    plain = c.post("/api/buildspec", json={"source": "repo"}).json()["markdown"]
    empty = c.post("/api/buildspec", json={"source": "repo", "added": {}}).json()["markdown"]
    assert plain == empty
    for name in skills.value("build-spec", "added_sections").values():
        assert f"## {name}" not in empty


def test_canvas_fields_are_validated_and_bounded(tmp_path):
    root, c = _shop(tmp_path)
    lim = skills.value("build-spec", "added_limits")

    def post(added):
        return c.post("/api/buildspec", json={"source": "repo", "added": added}).status_code

    assert post({"skills": [{"name": 7}]}) == 422  # strings only
    assert post({"skills": [{"name": ""}]}) == 422
    assert post({"skills": [{"name": "x" * (lim["name"] + 1)}]}) == 422
    assert post({"skills": [{"name": "a", "path": "p" * (lim["path"] + 1)}]}) == 422
    assert post({"skills": [{"name": "a", "repo": "not a repo"}]}) == 422
    assert post({"skills": [{"name": "a", "extra": "x"}]}) == 422  # unknown fields refused
    assert post({"skills": [{"name": f"s{i}"} for i in range(lim["items"] + 1)]}) == 422
    assert post({"links": [{"from": "a", "to": "b"}] * (lim["links"] + 1)}) == 422
    assert post({"links": [{"from": "a", "to": "b", "relation": "owns"}]}) == 422
    assert post({"notes": [{"on": "a", "text": "t" * (lim["text"] + 1)}]}) == 422
    assert (
        post({"repos": [{"repo": "a/b", "name": "b", "parts": [{"kind": "x", "name": "y"}]}]})
        == 422
    )
    assert post({"skills": [{"name": "a"}]}) == 200


def test_canvas_paths_are_text_only(tmp_path):
    root, c = _shop(tmp_path)
    # A path that climbs out of the repo is not called "in this repo"; a folder with .. is dropped
    # from the GitHub URL. Nothing is read from either.
    added = {
        "skills": [
            {"name": "sneaky", "path": str(root / ".." / ".." / "etc")},
            {"name": "gh", "repo": "acme/x", "folder": "../../secrets"},
        ]
    }
    md = c.post("/api/buildspec", json={"source": "repo", "added": added}).json()["markdown"]
    assert "in this repo at" not in md
    assert "- **gh**: from GitHub: `https://github.com/acme/x`" in md
    assert "secrets" not in md


def test_with_canvas_is_pure():
    s = buildspec.spec_from_architecture(arch(("a", "Agent", "backend", None)))
    before = json.dumps(s, sort_keys=True)
    out = buildspec.with_canvas(s, {"planned": [{"name": "x"}]})
    assert json.dumps(s, sort_keys=True) == before and out["added"]["planned"] == [
        {"name": "x", "ref": ""}
    ]


# ---------- A repo's change brief, a chosen design, the words it uses ----------


def _go_repo(tmp_path):
    root = tmp_path / "docthere"
    (root / "internal" / "render").mkdir(parents=True)
    (root / "cmd" / "docthere").mkdir(parents=True)
    (root / "go.mod").write_text("module example.com/docthere\n\ngo 1.22\n")
    (root / "cmd" / "docthere" / "main.go").write_text("package main\n\nfunc main() {}\n")
    for i in range(6):
        (root / "internal" / "render" / f"r{i}.go").write_text("package render\n")
    (root / "internal" / "render" / "r_test.go").write_text("package render\n")
    (root / "Makefile").write_text("build:\n\tgo build ./...\n\ntest:\n\tgo test ./...\n")
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_text(
        json.dumps({"hooks": {"PostToolUse": [], "Stop": []}})
    )
    c = TestClient(
        create_app(root, home=tmp_path / "home"), base_url=BASE, headers={"origin": BASE}
    )
    c.put("/api/usecase", json={"text": "Write docs for any repo from its code."})
    return root, c


def _brief(c, **body):
    r = c.post("/api/buildspec", json=body)
    assert r.status_code == 200, r.text
    return r.json()["markdown"], r.json()["json"]


def test_a_go_repo_gets_a_change_brief_in_go_with_its_own_tests(tmp_path):
    root, c = _go_repo(tmp_path)
    for src in ("repo", "suggested"):
        md, spec = _brief(c, source=src)
        assert spec["kind"] == "change" and spec["repo"]["languages"] == ["Go"]
        assert md.startswith("# BUILD: docthere\n")
        assert "Changes to make in docthere (Go)" in md
        # Never a new project, never a language the repo doesn't use.
        for wrong in (
            "Python",
            "agentic-ai-project",
            "src/agent_app",
            "Project layout",
            "pyproject",
        ):
            assert wrong not in md, wrong
        assert "layout" not in spec
        # Its own goal, setup and test commands.
        assert "## Goal\n\nWrite docs for any repo from its code." in md
        assert "- CLAUDE.md: not there" in md and "- hooks: PostToolUse, Stop" in md
        check = md.split("## How to check it", 1)[1]
        assert "`go test ./...` (from go.mod)" in check and "`make test` (from Makefile)" in check
        assert [x["run"] for x in spec["checks"]] == ["go test ./...", "make test"]
        # Every section of a change brief, in order.
        T = skills.value("build-spec", "change_sections")
        keys = ["goal", "current", "changes", "added", "removed", "check", "evidence"]
        at = [md.index(f"\n## {T[k]}\n") for k in keys]
        assert at == sorted(at)


def test_accepted_suggestions_are_tasks_dismissed_left_out_open_listed(tmp_path):
    root, c = _go_repo(tmp_path)
    props = c.get("/api/suggestions").json()["proposals"]
    claude = next(x for x in props if x["title"] == "Add a CLAUDE.md with the commands")
    c.put(f"/api/suggestions/{claude['id']}", json={"state": "accepted"})
    others = [x for x in props if x["id"] != claude["id"]]
    dismissed = others[0] if others else None
    if dismissed:
        c.put(f"/api/suggestions/{dismissed['id']}", json={"state": "dismissed"})
    md, spec = _brief(c, source="suggested")
    changes = md.split("## Changes", 1)[1].split("\n## ", 1)[0]
    assert "### 1. Add a CLAUDE.md with the commands" in changes
    assert "- why: There is no CLAUDE.md or AGENTS.md" in changes
    assert "- do: Add one at the root with the build, test and run commands" in changes
    assert "- files: `CLAUDE.md` (new)" in changes
    assert "- effort: S (small)" in changes
    task = spec["changes"][0]
    assert task["id"] == claude["id"] and task["files"] == [{"path": "CLAUDE.md", "new": True}]
    if dismissed:
        assert dismissed["title"] not in md
    still_open = [x for x in others[1:]]
    if still_open:
        undecided = md.split("## Not decided yet", 1)[1].split("\n## ", 1)[0]
        for x in still_open:
            assert x["title"] in undecided
    # As it is: no task; the brief says one accepted suggestion is left out.
    md2, spec2 = _brief(c, source="repo")
    assert spec2["changes"] == [] and spec2["left_out"] == 1
    assert "1 accepted suggestion is left out" in md2
    assert "Not decided yet" not in md2


def test_tasks_are_in_a_fixed_order_and_the_brief_is_deterministic(tmp_path):
    root, c = _go_repo(tmp_path)
    for x in c.get("/api/suggestions").json()["proposals"]:
        c.put(f"/api/suggestions/{x['id']}", json={"state": "accepted"})
    one, spec = _brief(c, source="suggested")
    two, _ = _brief(c, source="suggested")
    assert one == two
    order = skills.value("build-spec", "effort_order")
    keys = [(order.index(t["effort"]), t["title"].lower(), t["id"]) for t in spec["changes"]]
    assert keys == sorted(keys) and len(keys) >= 1


def test_the_chosen_design_and_its_parameters_are_in_the_brief(tmp_path):
    root, c = _go_repo(tmp_path)
    design = {"id": "naive-rag", "parameters": {"top_k": 8, "chunk_size": "512", "nope": "x"}}
    md, spec = _brief(c, source="suggested", design=design)
    assert "## Design to move toward: Naive RAG" in md
    assert "| `top_k` | 8 (changed) | 5 |" in md
    assert "| `chunk_size` | 512 | 512 |" in md
    assert "| `embedding_model` | general-text | general-text |" in md
    assert "nope" not in md
    assert "- Retriever -> Model: question + chunks" in md
    d = spec["design"]
    assert [p["name"] for p in d["parameters"] if p["changed"]] == ["top_k"]
    # The form's text and the catalog's values compare as one: "false" is False, 0.60 is 0.6.
    pure = buildspec.with_design(
        {},
        catalog_arch.entry("corrective-rag"),
        {"web_fallback": "false", "relevance_threshold": "0.60"},
    )["design"]["parameters"]
    by = {p["name"]: p for p in pure}
    assert by["web_fallback"]["value"] == "false" and by["web_fallback"]["changed"]
    assert by["web_fallback"]["default"] == "true" and "note" not in by["web_fallback"]
    assert by["relevance_threshold"]["value"] == "0.6" and not by["relevance_threshold"]["changed"]
    # Out of range is said, not hidden.
    md, _ = _brief(c, source="repo", design={"id": "naive-rag", "parameters": {"top_k": 99}})
    assert "outside 1 to 30" in md
    # A Lab workflow with a design: built as a new project, the design stated.
    wf = lab.business([])[0].dump()
    md, spec = _brief(c, source="workflow", workflow=wf, design=design)
    assert f"## {skills.value('build-spec', 'design_section')}: Naive RAG" in md
    assert "| `top_k` | 8 (changed) | 5 |" in md and spec["kind"] == "new"
    # Only a design, nothing yet: a new project from its parts.
    md, spec = _brief(c, source="design", design=design)
    assert spec["kind"] == "new" and any("retrieval/" in e["path"] for e in spec["layout"])
    assert "## Design: Naive RAG" in md
    bad = c.post("/api/buildspec", json={"source": "design", "design": {"id": "no-such"}})
    assert bad.status_code == 422
    assert c.post("/api/buildspec", json={"source": "design"}).status_code == 422
    long = {"id": "naive-rag", "parameters": {"top_k": "x" * 201}}
    assert c.post("/api/buildspec", json={"source": "repo", "design": long}).status_code == 422


def test_parameters_are_only_what_can_be_tuned():
    s = buildspec.spec_from_architecture(
        Architecture.model_validate(
            {
                "title": "T",
                "components": [
                    {
                        "id": "a",
                        "label": "API",
                        "type": "external",
                        "source": "a.py",
                        "check": "found",
                    }
                ],
            }
        )
    )
    assert s["components"][0]["parameters"] == {}
    md = buildspec.render_markdown(s)
    params = md.split("## Parameters", 1)[1].split("\n## ", 1)[0]
    for junk in ("| check |", "| kind |", "| source |", "external |"):
        assert junk not in params
    wf = next(w for w in lab.business([]) if w.loops)
    md = buildspec.render_markdown(buildspec.spec_from_workflow(wf))
    params = md.split("## Parameters", 1)[1].split("\n## ", 1)[0]
    assert "| kind |" not in params and "| model |" in params and "| max loops |" in params


def test_the_brief_uses_the_apps_words_and_keeps_api_calls_in_rig_json(tmp_path):
    root, c = _go_repo(tmp_path)
    wf = lab.business([])[0].dump()
    for body in (
        {"source": "repo"},
        {"source": "suggested"},
        {"source": "workflow", "workflow": wf},
        {"source": "design", "design": {"id": "react"}},
    ):
        md, spec = _brief(c, **body)
        for stale in (
            "Prove",
            "Rig a Workflow",
            "Rig a Repo",
            "Agent tab",
            "POST /api",
            "GET /api",
            "press Run",
        ):
            assert stale not in md, (body["source"], stale)
        assert "step 4, Measure" in md
        assert spec["evals"]["api"].startswith("POST /api/")
    md, _ = _brief(c, source="repo")
    assert "agent pill at the top right" in md


def test_a_new_projects_language_follows_the_use_case():
    wf = lab.business([])[0]
    s = buildspec.spec_from_workflow(wf, use_case="A support bot in TypeScript on Next.js")
    assert s["language"]["name"] == "TypeScript" and s["language"]["suggested"]
    ps = paths(s)
    assert any(p.endswith(".ts") for p in ps) and any(p.endswith("/package.json") for p in ps)
    assert not any(p.endswith(".py") or "pyproject" in p for p in ps)
    md = buildspec.render_markdown(s)
    assert "Language: TypeScript (suggested: the use case says 'typescript')" in md
    # "ReAct" is an agent pattern, not React; "go" alone is not Go.
    assert buildspec.language_for("a ReAct agent that can go to the web")["name"] == "Python"


def test_repo_test_commands_come_from_its_own_files(tmp_path):
    root = tmp_path / "mono"
    (root / "web").mkdir(parents=True)
    (root / "engine").mkdir()
    (root / "node_modules" / "x").mkdir(parents=True)
    (root / "CLAUDE.md").write_text(
        "Run `pytest -q` before you finish. Tests live in `tests/` and `test_refund.py`.\n"
        "```bash\n$ npm run lint\nnpx vitest run\n```\n"
    )
    (root / "package.json").write_text(
        json.dumps({"scripts": {"test": 'echo "Error: no test specified"'}})
    )
    (root / "web" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest"}}))
    (root / "web" / "pnpm-lock.yaml").write_text("")
    (root / "engine" / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    (root / "engine" / "uv.lock").write_text("")
    (root / "node_modules" / "x" / "package.json").write_text(
        json.dumps({"scripts": {"test": "x"}})
    )
    got = buildspec.repo_tests(root)
    assert [x["run"] for x in got] == [
        "pytest -q",
        "npx vitest run",
        "cd engine && uv run pytest",
        "cd web && pnpm test",
    ]
    assert got[0]["from"] == "CLAUDE.md" and got[2]["from"] == "engine/pyproject.toml"
    assert buildspec.repo_tests(None) == []


def test_a_tasks_files_come_from_its_parts_evidence_and_text():
    a = Architecture.model_validate(
        {
            "title": "x",
            "components": [{"id": "api", "label": "API", "source": "internal/api/server.go"}],
        }
    )
    sugg = [
        {"id": "b", "title": "Split API", "state": "accepted", "effort": "M", "targets": ["api"]},
        {
            "id": "a",
            "title": "Add a task for verify",
            "state": "accepted",
            "effort": "S",
            "targets": ["step:verify"],
            "evidence": ["./.claude/settings.json:3", "no tests at all"],
        },
        {"id": "c", "title": "Gone", "state": "dismissed", "effort": "S"},
    ]
    s = buildspec.spec_for_repo(a, None, {}, suggestions=sugg, with_suggestions=True)
    assert [t["id"] for t in s["changes"]] == ["a", "b"]  # S before M
    assert [f["path"] for f in s["changes"][0]["files"]] == [
        ".proving-ground/scenarios/",
        ".claude/settings.json",
    ]
    assert s["changes"][1]["files"] == [{"path": "internal/api/server.go", "new": False}]
    assert s["changes"][1]["parts"] == ["API"]
    assert "Gone" not in buildspec.render_markdown(s)


def test_a_repo_brief_uses_the_goal_the_browser_sends_else_the_saved_one(tmp_path):
    # The goal in use may be an unsaved draft: the brief says that one, and nothing is saved.
    _, c = _go_repo(tmp_path)
    md, spec = _brief(c, source="repo", use_case="Answer questions about the docs in Go.")
    assert spec["goal"] == "Answer questions about the docs in Go."
    assert "Answer questions about the docs in Go." in md
    assert c.get("/api/project").json()["use_case"] == "Write docs for any repo from its code."
    # Not sent: the repo's saved goal. Sent empty (a draft cleared): no goal.
    assert _brief(c, source="repo")[1]["goal"] == "Write docs for any repo from its code."
    md, spec = _brief(c, source="repo", use_case="")
    assert spec["goal"] is None and "No use case written yet" in md


def test_goal_check_names_a_stack_the_repo_has_no_files_in(tmp_path):
    _, c = _go_repo(tmp_path)
    r = c.post("/api/goal/check", json={"use_case": "Write JUnit tests for the Java services."})
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == ["Your goal mentions Java/JUnit; this repo is Go."]
    ok = c.post("/api/goal/check", json={"use_case": "Write docs for any repo from its code."})
    assert ok.json()["warnings"] == []


def test_build_md_lists_only_runnable_scenarios_and_falls_back_to_the_repos_tests(tmp_path):
    """build-spec: an approved scenario whose check is prose is no way to check it."""
    from proving_ground.files import save_scenario
    from proving_ground.models import Scenario

    root, c = _go_repo(tmp_path)
    save_scenario(
        root,
        Scenario(id="token-cost", title="Token cost", instruction="Keep it cheap.",
                 check="token cost", check_status="approved"),
    )
    md, spec = _brief(c, source="repo")
    check = md.split("## How to check it", 1)[1].split("\n## ", 1)[0]
    assert "token-cost" not in md and spec["evals"]["scenarios"] == []
    assert spec["evals"]["scenarios_left_out"] == 1
    assert "No valid Rig tasks yet: use the repo's own tests: `go test ./...`." in check
    assert "the Rig tasks pass at least as often as before" not in check
    # Once one runs as a command, it is listed and the fallback goes.
    save_scenario(
        root,
        Scenario(id="renders", title="Renders", instruction="Render it.",
                 check="go test ./internal/render/...", check_status="approved"),
    )
    md, spec = _brief(c, source="repo")
    check = md.split("## How to check it", 1)[1].split("\n## ", 1)[0]
    assert "- `renders`: Renders" in check and "token-cost" not in check
    assert "No valid Rig tasks yet" not in check
    assert [s["id"] for s in spec["evals"]["scenarios"]] == ["renders"]


def test_a_run_that_isnt_evidence_never_reads_helps():
    L: list[str] = []
    ev = {
        "latest": [
            {"name": "audit", "diff": 100.0, "pairs": 1, "verdict": "helps",
             "rig": {"band": "not_evidence", "score": None}},
            {"name": "refund-policy", "diff": 33.3, "pairs": 3, "verdict": "inconclusive",
             "rig": {"band": "not_proven", "score": 0, "label": "Not proven", "reason": "x"}},
        ]
    }  # fmt: skip
    buildspec._measured(L, ev)
    rows = L[0].splitlines()
    assert rows[2] == "| audit | – | 1 | not evidence | not evidence |"
    assert rows[3].startswith("| refund-policy | 33.3 | 3 | inconclusive |")
