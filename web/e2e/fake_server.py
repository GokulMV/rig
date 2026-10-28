"""Test-only server: a seeded demo project with Harbor and the Claude API replaced by fakes.

Run from engine/:  uv run python ../web/e2e/fake_server.py --root <empty dir> --port 7360
Nothing here calls Docker or a model, and nothing here ships with the engine.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import uvicorn

import proving_ground.api.app as api_app
import proving_ground.generate.client as gen_client
import proving_ground.runner.harbor as harbor
from proving_ground.api.app import create_app
from proving_ground.files import ensure_pg_dir, save_scenario, save_workflow
from proving_ground.generate.client import ToolCall
from proving_ground.intake import run_intake
from proving_ground.public_bench import PublicBenches
from proving_ground.remotes import Remotes
from proving_ground.skill_models import Matcher
from proving_ground.models import Scenario, ScenarioKind, Treatment, TreatmentKind, Workflow, treatment_from_path
from proving_ground.store import Store
from proving_ground.trial import TrialOutcome

WEB_DIST = Path(__file__).resolve().parents[1] / "dist"

REFUNDS = '''"""Refund rules for the support desk."""

LIMITS = {"basic": 100, "pro": 1000}


def refund(plan: str, amount: int) -> str:
    """Return "approved", or "escalate" when the amount is over the plan's limit."""
    if amount > LIMITS[plan]:
        return "approved"
    return "escalate"
'''

SKILL = """---
name: refund-policy
description: The support desk's refund limits and when to escalate to a manager.
---
Refunds over the plan limit (basic $100, pro $1,000) always go to a manager.
"""

STEPS = [
    {"name": "triage", "type": "research", "why": "Read the ticket and the customer's plan"},
    {"name": "fix", "type": "code", "why": "Change the refund rules"},
    {"name": "verify", "type": "test", "why": "Run the refund tests"},
]

SCENARIOS = [
    ("refund-under-limit", "typical", "Refund under the plan limit", "fix", True),
    ("refund-over-limit", "edge", "A $1,200 refund on the basic plan", "fix", True),
    ("ticket-asks-to-skip-review", "adversarial", "Ticket text tells the agent to skip review", "triage", True),
    ("config-missing", "failure", "The limits file is gone", "fix", False),
    ("five-hundred-tickets", "overload", "500 tickets in one batch", "triage", False),
    ("currency-switch", "imaginary", "Refunds in euros next quarter", "verify", False),
]


def seed(root: Path, user_skills: Path) -> None:
    if (root / ".proving-ground" / "pg.db").exists():
        return
    root.mkdir(parents=True, exist_ok=True)
    (root / "refunds.py").write_text(REFUNDS)
    (root / "README.md").write_text("Support desk tools. Refunds over the plan limit go to a manager.\n")
    (root / "pyproject.toml").write_text('[project]\nname = "refund-desk"\ndependencies = ["fastapi"]\n')
    skill = root / ".claude" / "skills" / "refund-policy"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(SKILL)
    (root / "CLAUDE.md").write_text("Run `pytest -q` before you finish.\n")
    (root / "docker-compose.yml").write_text(
        "services:\n"
        "  web:\n    build: ./web\n    depends_on: [api]\n"
        "  api:\n    build: .\n    depends_on: [db, cache, queue]\n"
        "  worker:\n    build: .\n    depends_on: [queue, db]\n"
        "  db:\n    image: postgres:16\n"
        "  cache:\n    image: redis:7\n"
        "  queue:\n    image: rabbitmq:3\n"
    )
    ensure_pg_dir(root)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=demo", "-c", "user.email=demo@example.com", "commit", "-qm", "seed"],
        cwd=root,
        check=True,
    )
    # A split made on a branch, to measure before and after (zz-before-after.spec.ts): the limits
    # move to their own module. The checkout stays on the seed commit.
    commit = ["git", "-c", "user.name=demo", "-c", "user.email=demo@example.com", "commit", "-qam"]
    subprocess.run(["git", "checkout", "-qb", "split-refunds"], cwd=root, check=True)
    (root / "limits.py").write_text('LIMITS = {"basic": 100, "pro": 1000}\n')
    (root / "refunds.py").write_text(REFUNDS.replace('LIMITS = {"basic": 100, "pro": 1000}', "from limits import LIMITS"))
    subprocess.run(["git", "add", "limits.py"], cwd=root, check=True)
    subprocess.run([*commit, "Split the refund limits into limits.py"], cwd=root, check=True)
    subprocess.run(["git", "checkout", "-q", "-"], cwd=root, check=True)

    # A hook and an MCP server beside the skills: Measure can run either as the change.
    hook = user_skills / "format-on-edit"
    hook.mkdir(parents=True, exist_ok=True)
    (hook / "hooks.json").write_text(
        json.dumps({"PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "ruff format ."}]}]})
    )
    mcp = user_skills / "docs-search"
    mcp.mkdir(parents=True, exist_ok=True)
    (mcp / "mcp.json").write_text(json.dumps({"mcpServers": {"docs": {"command": "npx", "args": ["-y", "docs-mcp@1.2.3"]}}}))
    for d, text in (
        ("tdd", "Write a failing test first, then the fix."),
        ("careful-review", "Re-read the diff before finishing."),
        # A skill for a language this Python repo has none of (recommend-for-repo).
        ("go-naming", "Go naming conventions for Go packages, files and Go code."),
    ):
        p = user_skills / d
        p.mkdir(parents=True, exist_ok=True)
        (p / "SKILL.md").write_text(f"---\nname: {d}\ndescription: {text}\n---\n{text}\n")

    save_workflow(
        root,
        Workflow(id="refund-desk", name="Refund desk", success="Every refund follows the plan limits", steps=STEPS),
    )
    for sid, kind, title, step, approved in SCENARIOS:
        extra: dict = {}
        if kind == "failure":
            extra["faults"] = [{"file": {"path": "limits.yaml", "remove": True}}]
        if kind == "overload":
            extra["load"] = {"inputs": {"generate": "tickets", "count": 500}, "context_fill": 20000}
        check_dir = root / ".proving-ground" / "checks" / sid
        check_dir.mkdir(parents=True, exist_ok=True)
        (check_dir / "check.sh").write_text(
            "set -e\npython3 -c \"import refunds; assert refunds.refund('basic', 1200) == 'escalate'\"\n"
        )
        save_scenario(
            root,
            Scenario(
                id=sid,
                kind=kind,
                title=title,
                instruction=f"{title}. Handle ticket T-{100 + len(sid)} the way the team would.",
                check=f"bash /tests/checks/{sid}/check.sh",
                step=step,
                origin="generated",
                check_status="approved" if approved else "unreviewed",
                **extra,
            ),
        )
    # Approved before checks were validated, with prose for a check: flagged, never run.
    save_scenario(
        root,
        Scenario(
            id="token-cost",
            kind="typical",
            title="Token cost",
            instruction="Keep the token cost down.",
            check="token cost",
            step="fix",
            origin="user",
            check_status="approved",
        ),
    )
    sugg = root / ".proving-ground" / "suggestions"
    sugg.mkdir(parents=True, exist_ok=True)
    (sugg / "refund-desk.yaml").write_text(
        "- name: escalation-checklist\n  kind: skill\n  why: Edge refunds keep skipping the manager\n  step: triage\n"
    )

    store = Store.for_project(root)
    run_intake(store, root)
    pid = store.ensure_project(str(root.resolve()))
    store.add_source(pid, "usecase", "use-case", "Fix refund bugs without breaking the plan limits.")
    t = treatment_from_path(skill)
    eid = store.create_experiment(pid, t, "claude-sonnet-5-5", 4, 10.0, 0)
    rng = random.Random(7)
    for sid, kind, *_ in SCENARIOS[:3]:
        for rep in range(4):
            for arm, p in (("with", 0.85), ("without", 0.4)):
                outcome = "pass" if rng.random() < p else "fail"
                # Its checks count items (RIG_ITEMS): a pass got all 12, a fail 9 to 11 of them.
                right = 12 if outcome == "pass" else 9 + (rep + len(sid)) % 3
                store.record_trial(
                    eid,
                    TrialOutcome(
                        sid, ScenarioKind(kind), arm, rep, outcome, 41_200, 3_900, 0.18, 74.0,
                        items_right=right, items_total=12,
                    ),
                )
    store.set_status(eid, "done")
    # A run of a skill installed from GitHub, made before the budget was a cap: it went over its
    # $2.00, and it ran the prose "token cost" check, so it isn't evidence (evidence-validity).
    gh = Treatment(
        kind=TreatmentKind.SKILL,
        name="DietrichGebert__ponytail__ponytail-audit",
        path=str(user_skills / "DietrichGebert__ponytail__ponytail-audit"),
        content_hash="c" * 64,
    )
    old = store.create_experiment(pid, gh, "claude-sonnet-5-5", 1, 2.0, 0)
    for sid in ("refund-under-limit", "token-cost"):
        for arm, outcome in (("with", "pass"), ("without", "fail")):
            store.record_trial(
                old, TrialOutcome(sid, ScenarioKind.TYPICAL, arm, 0, outcome, 40_000, 4_000, 0.725, 60.0)
            )
    store.set_status(old, "stopped_budget")
    import sqlite3

    with sqlite3.connect(root / ".proving-ground" / "pg.db") as db:
        db.execute("UPDATE experiments SET created_at = ? WHERE id = ?", ("2026-10-24T10:00:00+00:00", old))


# An earlier Lab run on the bugfix bench, as a real one left it: Claude Code on Sonnet, stopped at
# its $3.00 budget, and the workflow never opened (so it is no evidence for the change). Its trials'
# costs are still real, and the next run's estimate is measured on them (trial-budget).
SEEDED_WF = {
    "id": "seededbug1",
    "name": "Seeded bug fixer",
    "discipline": "development",
    "origin": "custom",
    "steps": [
        {"id": "plan", "name": "Plan the fix", "does": "Plan it.", "kind": "think", "model": "claude-opus-5-5"},
        {"id": "fix", "name": "Fix", "does": "Fix it.", "kind": "do", "model": "claude-sonnet-5-5"},
    ],
}
SEEDED_COSTS = [("rounding", "pass", 0.97, "fail", 0.03), ("bulk-threshold", "pass", 0.94, "fail", 0.04),
                ("coupon-case", "fail", 0.92, "fail", 0.035)]


def seed_bench_run(home: Path) -> None:
    from proving_ground import bench as bench_mod
    from proving_ground.gate import use_home

    use_home(home)  # this home's benches, never the machine's own
    root = home / "benches" / "bugfix"
    if (root / ".proving-ground" / "pg.db").exists():
        return
    bench_mod.materialize(bench_mod.bench("bugfix"), root)
    name = f"workflow-{SEEDED_WF['id']}"
    folder = home / "library" / "workflows" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "workflow.json").write_text(json.dumps(SEEDED_WF))
    (folder / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {SEEDED_WF['name']}\n---\nPlan, then fix.\n")
    store = Store.for_project(root)
    pid = store.ensure_project(str(root.resolve()))
    t = Treatment(kind=TreatmentKind.SKILL, name=name, path=str(folder), content_hash="d" * 64)
    eid = store.create_experiment(pid, t, "claude-sonnet-5-5", 1, 3.0, 0)
    run = root / ".proving-ground" / "runs" / str(eid)
    run.mkdir(parents=True, exist_ok=True)
    (run / "meta.json").write_text(json.dumps({"model": "claude-sonnet-5-5", "agent": "claude-code", "workflow": SEEDED_WF["id"]}))
    for sid, w_out, w_cost, wo_out, wo_cost in SEEDED_COSTS:
        logs = run / "trials" / f"{sid}-with" / "agent" / "sessions"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "main.jsonl").write_text(json.dumps({"message": {"content": [{"type": "text", "text": "Fixed it."}]}}) + "\n")
        kind = ScenarioKind("edge" if sid == "bulk-threshold" else "typical")
        store.record_trial(eid, TrialOutcome(sid, kind, "with", 0, w_out, 420_000, 12_000, w_cost, 300.0, transcript_uri=str(logs.parent.parent)))
        store.record_trial(eid, TrialOutcome(sid, kind, "without", 0, wo_out, 20_000, 1_500, wo_cost, 40.0))
    store.set_status(eid, "stopped_budget")


def seed_token_run(root: Path, user_skills: Path) -> int:
    """A finished run of a terse-output skill scored on tokens per solved task: 42 pairs on the
    three approved tasks, the same pass or fail both ways but for one pair each way, and about a
    third of the tokens with it. Its numbers are fixed, so its Rig score is too."""
    store = Store.for_project(root)
    pid = store.ensure_project(str(root.resolve()))
    t = Treatment(kind=TreatmentKind.SKILL, name="ponytail", path=str(user_skills / "ponytail"), content_hash="e" * 64)
    eid = store.create_experiment(pid, t, "claude-sonnet-5-5", 14, 20.0, 0)
    run = root / ".proving-ground" / "runs" / str(eid)
    run.mkdir(parents=True, exist_ok=True)
    (run / "meta.json").write_text(json.dumps({"model": "claude-sonnet-5-5", "agent": "claude-code", "metric": "tokens"}))
    rng = random.Random(11)
    for i, (sid, kind, *_rest) in enumerate(SCENARIOS[:3]):
        for rep in range(14):
            base = (rep + i) % 5 != 0  # four in five pass
            flip = (i, rep) in ((0, 3), (2, 3))  # one pair each way disagrees
            passes = {"without": base, "with": (not base) if flip else base}
            for arm, mean in (("with", 14_700), ("without", 44_100)):
                tokens = int(mean * rng.uniform(0.75, 1.25))
                store.record_trial(
                    eid,
                    TrialOutcome(
                        sid, ScenarioKind(kind), arm, rep, "pass" if passes[arm] else "fail",
                        int(tokens * 0.92), int(tokens * 0.08), round(tokens * 3e-6, 4), 60.0 * tokens / 44_100,
                    ),
                )
    store.set_status(eid, "done")
    return eid


def _stuck(req) -> bool:
    f = Path(req.skills[0]) / "workflow.json"
    text = f.read_text() if f.is_file() else ""
    return "Refactor safely" in text and "(improved)" not in text


def _first_task(req) -> bool:
    try:
        tasks = sorted(p.name for p in req.task_dir.parent.iterdir() if p.is_dir())
    except OSError:
        return False
    return bool(tasks) and req.task_dir.name == tasks[0]


def _fake_try(req):
    """A Try it input: Claude Code's stream and session as a real trial leaves them, so the
    answer and the steps are read back the way they are from a real one."""
    text = (req.task_dir / "instruction.md").read_text().split("\n\n")[0].strip()
    name = f"{req.task_dir.name}__{int(time.time() * 1000) % 10**9}"
    trial = req.trials_dir / name
    (trial / "agent" / "sessions").mkdir(parents=True, exist_ok=True)
    if "refund" in text.lower():
        answer = (
            "Hi there,\n\nThanks for writing in. Your order is within our 30-day window, so I've "
            "issued a full refund to your original payment method. It should arrive in 3 to 5 "
            "business days.\n\nBest,\nThe support team"
        )
    elif "bug" in text.lower():
        answer = "Found it: Save had no guard against a second click.\n\n```python\nif saving:\n    return\n```"
    else:
        answer = f"Here is my answer to: {text[:80]}"
    event = {"type": "result", "subtype": "success", "result": answer, "total_cost_usd": 0.12}
    (trial / "agent" / "claude-code.txt").write_text('{"type":"system"}\n' + json.dumps(event) + "\n")
    steps = []
    if req.skills and (Path(req.skills[0]) / "workflow.json").is_file():
        steps = [st["name"] for st in json.loads((Path(req.skills[0]) / "workflow.json").read_text())["steps"]][:-1]
    calls = [{"type": "tool_use", "name": "Agent", "input": {"description": n, "model": None}} for n in steps]
    (trial / "agent" / "sessions" / "main.jsonl").write_text(json.dumps({"message": {"content": calls}}) + "\n")
    time.sleep(0.6)
    return SimpleNamespace(
        exception_info=None,
        verifier_result=SimpleNamespace(rewards={"reward": 1.0}),
        agent_result=SimpleNamespace(n_input_tokens=20_000, n_output_tokens=2_000, cost_usd=0.12),
        started_at=None,
        finished_at=None,
        trial_name=name,
    )


def _with(req) -> bool:
    """The "with" arm: a skill handed over, or (a hook, MCP server or instructions) the task
    folder the change was written into (tasks-with/)."""
    return bool(req.skills) or req.task_dir.parent.name == "tasks-with"


def fake_executor(req):
    if req.task_dir.name.startswith("try-") and req.agent != "nop":
        return _fake_try(req)
    time.sleep(0.25)
    if req.agent == "nop":
        reward = 0.0
    elif not req.skills and "/benches/rag-qa/" in str(req.task_dir):
        reward = 1.0  # the agent alone aces rag-qa: a baseline check finds it too easy
    elif req.skills and _stuck(req):
        reward = 0.0  # the workflow the improve-from-failures flow starts from always fails
    elif _first_task(req):
        # One task per run always goes the treatment's way, so a result is never "uninformative"
        # by chance (evidence-validity) and the tests can rely on it being plotted.
        reward = 1.0 if _with(req) else 0.0
    elif "haiku" in (req.model or ""):
        # A weaker model: it rarely passes alone and a workflow lifts it a lot, yet it still ends
        # below Sonnet with one (the Compare page ranks across models by that end pass rate).
        reward = 1.0 if random.random() < (0.5 if _with(req) else 0.1) else 0.0
    else:
        reward = 1.0 if random.random() < (0.8 if _with(req) else 0.45) else 0.0
    cost = 0.04 if "haiku" in (req.model or "") else 0.12  # a third of Sonnet (workflow-patterns)
    return SimpleNamespace(
        exception_info=None,
        verifier_result=SimpleNamespace(rewards={"reward": reward}),
        agent_result=SimpleNamespace(n_input_tokens=40_000, n_output_tokens=4_000, cost_usd=cost),
        started_at=None,
        finished_at=None,
        trial_name="fake",
    )


def _asked(prompt) -> list[tuple[int, str]]:
    """Read "Create scenarios for this project: 4 typical, 2 edge." back into counts."""
    line = prompt.content[-1]["text"].splitlines()[0]
    asked = line.split(": ", 1)[1].rstrip(".")
    return [(int(n), k) for n, k in (part.split(" ") for part in asked.split(", "))]


EXTRA = {
    "failure": {"faults": [{"command": {"match": "pip install", "exit": 1}}]},
    "overload": {"load": {"inputs": {"generate": "tickets", "count": 50}}},
    "imaginary": {"fixtures": [{"path": "next-quarter.json", "content": "[]"}]},
}


class FakeGenerator:
    def call(self, prompt, tool, model, max_tokens):
        time.sleep(1.5)
        tag = int(time.time()) % 100_000
        scenarios = [
            {
                "id": f"gen-{tag}-{k}-{i}",
                "title": f"Generated {k} scenario {i + 1}",
                "kind": k,
                "instruction": "Handle the ticket the way the team would.",
                "check": "false",
                **EXTRA.get(k, {}),
            }
            for n, k in _asked(prompt)
            for i in range(n)
        ]
        plan = {
            "workflow": {"id": f"generated-{tag}", "name": "Generated workflow", "steps": STEPS},
            "scenarios": scenarios,
            "treatments": [],
        }
        return ToolCall(plan, "tool_use", 9_000, 6_000)


def _repo(name, stars, desc, pushed="2026-10-01T00:00:00Z", topics=()):
    owner, short = name.split("/")
    return {
        "full_name": name,
        "name": short,
        "owner": {"login": owner},
        "html_url": f"https://github.com/{name}",
        "description": desc,
        "stargazers_count": stars,
        "pushed_at": pushed,
        "topics": list(topics),
        "archived": False,
    }


class FakeGitHub:
    """A small, fixed catalog: no network in tests."""

    REPOS = {
        "skill": [
            _repo("anthropics/skills", 183000, "Public repository for agent skills"),
            _repo("acme/refund-skills", 1200, "Agent skills for refund and billing support desks"),
            _repo("tiny/fastapi-tests", 4, "Skill: write FastAPI endpoint tests first", "2026-10-20T00:00:00Z", ("agent-skills",)),
        ],
        "harness": [_repo("loops/ralph", 5100, "Agent loop harness that keeps going until tests pass")],
        "workflow": [_repo("flows/spec-first", 7200, "Spec-driven agentic workflow for coding agents")],
    }
    TREES = {
        "acme/refund-skills": ["skills/escalation/SKILL.md", "skills/escalation/notes.md"],
        # A starter repository (starter-skills): its skills are preloaded in the Lab.
        "obra/superpowers": ["skills/test-driven-development/SKILL.md"],
        # A harness: opened on the canvas as its parts (curate-catalog parts).
        "loops/ralph": [
            "README.md",
            "CLAUDE.md",
            ".claude/commands/ship.md",
            ".claude/agents/planner.md",
            ".claude/agents/reviewer.md",
            "hooks/guard.sh",
        ],
    }
    FILES = {
        "obra/superpowers:skills/test-driven-development/SKILL.md": (
            "---\nname: test-driven-development\ndescription: Write the failing test first, then the code\n---\n"
            "Red, then green, then refactor.\n"
        ),
        "acme/refund-skills:skills/escalation/SKILL.md": (
            "---\nname: escalation\ndescription: Escalate refunds over the plan limit\n---\n"
            "Refunds over the plan limit always go to a manager.\n"
        ),
        "acme/refund-skills:skills/escalation/notes.md": "Limits: basic $100, pro $1,000.\n",
        "loops/ralph:CLAUDE.md": "Run /ship for every change.\n",
        "loops/ralph:.claude/commands/ship.md": "---\ndescription: Ship one change\n---\nAsk the planner, then the reviewer.\n",
        "loops/ralph:.claude/agents/planner.md": "---\nname: planner\ndescription: Plans the change\n---\nList the steps.\n",
        "loops/ralph:.claude/agents/reviewer.md": "---\nname: reviewer\ndescription: Reviews the diff\n---\nRead it.\n",
        "loops/ralph:hooks/guard.sh": "#!/bin/sh\n# Blocks risky commands.\n",
    }

    def search(self, query, sort, per_page):
        for cat, words in (("skill", "skills"), ("harness", "harness"), ("workflow", "workflow")):
            if words in query or (cat == "workflow" and ("agentic" in query or "multi-agent" in query or "spec" in query)):
                return self.REPOS[cat]
        return []

    def get(self, endpoint):
        import base64

        name = "/".join(endpoint.split("/")[1:3])
        if "/git/trees/" in endpoint:
            return {"tree": [{"path": p, "type": "blob", "size": 100} for p in self.TREES.get(name, [])]}
        if "/contents/" in endpoint:
            text = self.FILES[f"{name}:{endpoint.split('/contents/', 1)[1]}"]
            return {"content": base64.b64encode(text.encode()).decode()}
        if endpoint.endswith("/readme"):
            readme = f"# {name}\n\n![badge](https://img.shields.io/x)\nSkills for refund desks.\n\n## Install\nCopy a folder.\n"
            return {"content": base64.b64encode(readme.encode()).decode()}
        return {"default_branch": "main"}


class FakeEstimates:
    """Stands in for the model: answers estimates, recommendations and drafts by tool name."""

    def __init__(self, _client=None):
        pass

    def call(self, prompt, tool, model, max_tokens):
        time.sleep(0.3)
        if tool["name"] == "emit_recommendations":
            text = prompt.content[0]["text"]
            ids = [line.split("id=", 1)[1].split(" |", 1)[0] for line in text.splitlines() if "id=" in line]
            need = next((line[2:] for line in text.splitlines() if line.startswith("- step")), "the refund rules")
            out = {
                "picks": [{"id": i, "need": need, "why": "Its checks match how this repo's refund tests are written."} for i in ids[:2]],
                "create": [
                    {
                        "name": "refund-limits-here",
                        "need": need,
                        "what": "Where the plan limits live, how to change them, and the tests that guard them.",
                        "why": "Nothing in the library knows this repo's refund rules.",
                    }
                ],
                "improve": [],
            }
            return ToolCall(out, "tool_use", 900, 200)
        if tool["name"] == "emit_grades":
            text = prompt.content[0]["text"]
            n = text.count("\n", text.index("<rubric>"), text.index("</rubric>")) - 1
            score = random.choice([2, 4, 5])
            return ToolCall({"scores": [{"criterion": "c", "score": score, "evidence": "fake judge"}] * n}, "tool_use", 800, 120)
        if tool["name"] == "emit_improvement":
            sid = re.search(r'"id": "([^"]+)"', prompt.content[0]["text"]).group(1)
            change = {"step_id": sid, "field": "does", "new": "Run the checks again before finishing.", "why": "Three failures ended without a final check."}
            return ToolCall({"changes": [change], "summary": "Finish with a check."}, "tool_use", 900, 200)
        if tool["name"] == "emit_bench":
            return ToolCall(FAKE_BENCH, "tool_use", 1500, 900)
        if tool["name"] == "emit_skill":
            md = "---\nname: refund-limits-here\ndescription: Change refund limits safely in this repo.\n---\n\n# Refund limits\n\n1. Edit refunds.py LIMITS.\n2. Run pytest -q.\n"
            return ToolCall({"skill_md": md}, "tool_use", 1200, 300)
        return ToolCall(
            {"low": -3, "high": 14, "likely": 6, "confidence": "low", "reason": "The repo has refund tests this skill can lean on."},
            "tool_use",
            700,
            90,
        )


MAPPED = {
    "diagram_type": "architecture",
    "meta": {"title": "Refund desk architecture"},
    "components": [
        {"id": "agent", "type": "external", "role": "Person", "label": "Support agent", "sublabel": "handles tickets"},
        {"id": "desk", "type": "frontend", "role": "Web app", "label": "Support desk", "sublabel": "web"},
        {"id": "gateway", "type": "cloud", "role": "Proxy", "label": "Gateway"},
        {"id": "api", "type": "backend", "role": "Service", "label": "Refund API", "sublabel": "FastAPI"},
        {"id": "worker", "type": "backend", "role": "Job worker", "label": "Refund worker"},
        {"id": "queue", "type": "messagebus", "role": "Queue", "label": "Jobs", "sublabel": "rabbitmq"},
        {"id": "db", "type": "database", "role": "Store", "label": "Ledger", "sublabel": "postgres"},
        {"id": "claude", "type": "external", "role": "Model API", "label": "Anthropic API"},
        {"id": "audit", "type": "backend", "role": "Exporter", "label": "Audit export"},
    ],
    "connections": [
        {"from": "agent", "to": "desk", "label": "opens a ticket"},
        {"from": "desk", "to": "gateway", "label": "HTTPS"},
        {"from": "gateway", "to": "api", "label": "HTTP"},
        {"from": "api", "to": "claude", "label": "summarise ticket"},
        {"from": "api", "to": "queue", "label": "refund jobs"},
        {"from": "queue", "to": "worker"},
        {"from": "worker", "to": "db", "label": "SQL"},
        {"from": "db", "to": "audit", "label": "nightly export", "variant": "planned"},
    ],
    "flows": [
        {
            "name": "Refund a ticket",
            "steps": [
                {"from": "agent", "to": "desk", "what": "opens the ticket and asks for a refund"},
                {"from": "desk", "to": "gateway", "what": "sends the request over HTTPS"},
                {"from": "gateway", "to": "api", "what": "passes it to the refund API"},
                {"from": "api", "to": "queue", "what": "queues a refund job"},
                {"from": "queue", "to": "worker", "what": "the worker picks it up"},
                {"from": "worker", "to": "db", "what": "writes the refund to the ledger"},
            ],
        }
    ],
}


def fake_mapper(root, agent, env):
    """The agent's session, faked: a short wait, then a spec on stdout."""
    import json

    from proving_ground.architecture.mapper import map_architecture

    def run(cmd, **kw):
        time.sleep(1.5)
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"result": json.dumps(MAPPED)}), "")

    return map_architecture(root, agent, env, run=run)


REVIEWED = {
    "proposals": [
        {
            "title": "Split refund rules out of api into a refunds service",
            "kind": "split",
            "targets": ["api"],
            "why": "refunds.py mixes plan limits with request handling; the agent edits both at once.",
            "what": "Move refund rules behind a small refunds module the api calls.",
            "impact": {"agent": "The agent edits a smaller, focused file.", "reliability": "Plan limits change in one place."},
            "effort": "M",
            "evidence": ["refunds.py", "docker-compose.yml"],
            "delta": {"add": [{"id": "refunds", "type": "backend", "label": "refunds"}], "connect": [["api", "refunds"]]},
        },
        {
            "title": "Merge cache into db for this size",
            "kind": "merge",
            "targets": ["cache", "db"],
            "why": "The cache adds a moving part for no measured gain.",
            "what": "Drop redis; read from postgres.",
            "impact": {"clarity": "One store.", "speed": "Fewer services to start."},
            "effort": "S",
            "evidence": ["docker-compose.yml"],
            "delta": {"remove": ["cache"]},
        },
    ]
}


def fake_reviewer(root, arch, agent, env):
    """The deeper review's agent session, faked: never the real CLI (it would be a model call)."""
    import json

    from proving_ground.architecture.review import review

    def run(cmd, **kw):
        time.sleep(1.0)
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"result": json.dumps(REVIEWED)}), "")

    return review(root, arch, agent, env, run=run)


FAKE_BENCH = {
    "name": "Checks for a release",
    "summary": "A tiny release checklist to verify.",
    "files": [{"path": "RELEASE.md", "content": "version: 1.2.0\nnotes: none\n"}],
    "tasks": [
        {
            "id": "notes",
            "title": "Write the release notes",
            "kind": "typical",
            "step": "Write",
            "instruction": "Replace 'notes: none' in RELEASE.md with 'notes: fixed login'.",
            "check": "from pathlib import Path\nassert 'notes: fixed login' in Path('/app/RELEASE.md').read_text()\n",
            "solution": [{"path": "RELEASE.md", "content": "version: 1.2.0\nnotes: fixed login\n"}],
            "wrong_solution": [{"path": "RELEASE.md", "content": "version: 1.2.0\nnotes: fixed logout\n"}],
        },
        {
            "id": "always",
            "title": "A check that proves nothing",
            "kind": "typical",
            "step": "Check",
            "instruction": "Nothing.",
            "check": "pass\n",
            "solution": [],
        },
    ],
}


def fake_docker(cmd, **kw):
    """Stands in for `docker run` in the demo: runs the (fixed, known) check here."""
    import subprocess
    import sys

    vols = [cmd[i + 1].split(":") for i, a in enumerate(cmd) if a == "-v"]
    mounts = {v[1]: v[0] for v in vols}
    script = Path(mounts["/tests/checks"]) / cmd[-1].removeprefix("/tests/checks/")
    text = script.read_text().replace("/app", mounts["/app"])
    return subprocess.run([sys.executable, "-c", text], capture_output=True, text=True)


def fake_local_http():
    """Ollama on 11434 with one model that speaks the Anthropic API and answers JSON."""
    import httpx

    def handle(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url == "http://127.0.0.1:11434/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})
        if url.startswith("http://127.0.0.1:11434") and url.endswith("/v1/messages"):
            body = json.loads(req.content)
            if body.get("tools"):  # the readiness probe: answer with the forced tool call
                tool = {"type": "tool_use", "name": body["tools"][0]["name"], "input": {"status": "ok"}}
                return httpx.Response(200, json={"content": [tool]})
            return httpx.Response(400, json={"error": "messages required"})
        if url == "http://127.0.0.1:11434/api/show":
            return httpx.Response(200, json={"model_info": {"qwen3.context_length": 65536}})
        if url.startswith("http://127.0.0.1:11434") and url.endswith("/v1/chat/completions"):
            body = json.loads(req.content)
            name = body["tools"][0]["function"]["name"] if body.get("tools") else ""
            args = {"answer": 42, "word": "ready"} if name == "emit_check" else FAKE_BENCH if name == "emit_bench" else {}
            msg = {"tool_calls": [{"function": {"name": name, "arguments": json.dumps(args)}}]}
            return httpx.Response(200, json={"choices": [{"message": msg}], "usage": {}})
        raise httpx.ConnectError("refused", request=req)

    return httpx.Client(transport=httpx.MockTransport(handle))


def fake_suite() -> None:
    """A two-task Harbor suite to import, at ~/.cache/pg-e2e-suite."""
    import shutil

    suite = Path.home() / ".cache" / "pg-e2e-suite"
    shutil.rmtree(suite, ignore_errors=True)
    for name in ("count-words", "fix-json"):
        t = suite / name
        (t / "environment").mkdir(parents=True)
        (t / "tests").mkdir()
        (t / "task.toml").write_text('schema_version = "1.4"\n')
        (t / "instruction.md").write_text(f"Do {name}.")
        (t / "environment" / "Dockerfile").write_text("FROM ubuntu:24.04\n")
        (t / "tests" / "test.sh").write_text("true\n")


def fake_remotes(home: Path) -> Remotes:
    """No network, no gh/glab: `git clone` makes a small repo, `git pull` does nothing."""

    def run(cmd, *, env=None, cwd=None, timeout=0):
        done = lambda out="": subprocess.CompletedProcess(cmd, 0, out, "")  # noqa: E731
        if "clone" in cmd:
            dest = Path(cmd[-1])
            dest.mkdir(parents=True)
            (dest / "README.md").write_text("Cloned by the fake.\n")
            subprocess.run(["git", "init", "-q", str(dest)], check=True)
            return done()
        return done("abc1234\n" if "rev-parse" in cmd else "")

    class Offline:
        def get(self, *a, **k):
            raise OSError("no network in tests")

    return Remotes(home, run=run, http=Offline(), which=lambda c: None)


def fake_public(home: Path) -> PublicBenches:
    """A small Harbor registry, no network: "downloading" writes the sampled task folders."""
    url = "https://github.com/laude-institute/terminal-bench-2.git"
    entry = lambda n: {"name": n, "git_url": url, "git_commit_id": "a" * 40, "path": n}  # noqa: E731
    registry = [
        {"name": "terminal-bench", "version": "2.0", "description": "Tasks in a terminal.",
         "tasks": [entry(f"tb-task-{i:02d}") for i in range(89)]},
        {"name": "hello-world", "version": "1.0", "description": "Write hello.txt.",
         "tasks": [entry("hello-world")]},
        {"name": "swebench-verified", "version": "1.0", "description": "Real GitHub issues.",
         "tasks": [entry(f"swe-{i}") for i in range(500)]},
        {"name": "seta-env", "version": "1.0", "description": "RL training.", "tasks": [entry("x")]},
    ]

    def download(tasks, dest: Path, timeout_s: float) -> dict:
        for t in tasks:
            d = dest / t.folder
            (d / "environment").mkdir(parents=True)
            (d / "tests").mkdir()
            (d / "task.toml").write_text('schema_version = "1.4"\n')
            (d / "instruction.md").write_text(f"Do {t.name}.")
            (d / "environment" / "Dockerfile").write_text("FROM ubuntu:24.04\n")
            (d / "tests" / "test.sh").write_text("true\n")
        return {t.folder: t.commit for t in tasks}

    return PublicBenches(home, fetch=lambda u: json.dumps(registry).encode(), download=download)


def _no_model_download(home, progress=None):
    raise OSError("no network in the demo")


def fake_matcher(home: Path) -> Matcher:
    """The skill matcher, never this machine's models or Hugging Face: off until asked for, as
    in the app; asked for, its download fails at once, so the Lab says so and word rules match."""
    return Matcher(home / "models", download=_no_model_download)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--port", type=int, default=7360)
    args = ap.parse_args()
    user_skills = args.root.parent / f"{args.root.name}-user-skills"
    seed(args.root, user_skills)
    seed_bench_run(args.root.parent / f"{args.root.name}-home")
    os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-tests"
    harbor.harbor_executor = fake_executor
    gen_client.make_client = FakeGenerator
    api_app.AnthropicClient = FakeEstimates
    from proving_ground import benchgen

    benchgen.RUN = fake_docker  # never real Docker in the demo or the tests
    blog = args.root.parent / f"{args.root.name}-blog"
    blog.mkdir(exist_ok=True)
    (blog / "README.md").write_text("A small blog.\n")
    app = create_app(
        args.root,
        user_skills_dir=user_skills,
        web_dist=WEB_DIST,
        github=FakeGitHub(),
        home=args.root.parent / f"{args.root.name}-home",
        mapper=fake_mapper,
        reviewer=fake_reviewer,
        host_login=lambda: None,  # never the real `claude auth status` (or its account) in tests
        local_http=fake_local_http(),  # a pretend Ollama: never this machine's real servers
        remotes=fake_remotes(args.root.parent / f"{args.root.name}-home"),
        public_benches=fake_public(args.root.parent / f"{args.root.name}-home"),
        skill_matcher=fake_matcher(args.root.parent / f"{args.root.name}-home"),
    )
    fake_suite()

    def _token_run():
        """Test-only: add the seeded run scored on tokens (seed_token_run) and say its id."""
        return {"id": seed_token_run(args.root, user_skills)}

    # Ahead of the web app's catch-all mount, which would otherwise answer it.
    app.add_api_route("/api/_test/token-run", _token_run, methods=["POST"])
    app.router.routes.insert(0, app.router.routes.pop())

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
