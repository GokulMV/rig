"""Ship to any agent: a build spec (rig.json) and a brief (BUILD.md).

Two kinds. A repo gets a change brief: what to add or change in it, in its own languages and with
its own test commands, with every accepted suggestion as a task. With nothing yet (a Lab workflow
or a Garage design) there is a new project with a suggested layout in a suggested language.
Rules and defaults live in the build-spec skill. No model calls; deterministic.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from proving_ground import skills
from proving_ground.architecture import Architecture
from proving_ground.intake.repo import SKIP_DIRS
from proving_ground.lab import Workflow, goal_rules, is_code, levels

NAME = "build-spec"
V = skills.load(NAME).values
GOAL = skills.load("goal-rules").values


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "agent"


def _has(text: str, words: list[str]) -> bool:
    t = text.lower()
    return any(w in t for w in words)


def _roles(text: str) -> list[str]:
    return [r for r, words in V["roles"].items() if _has(text, words)]


def _text(c) -> str:
    return " ".join(x for x in (c.label, c.role, c.sublabel) if x)


def _tool_entry(name: str, comp: str, kind: str, text: str) -> dict:
    write = kind in ("database", "messagebus") or _has(text, V["write_words"])
    return {
        "name": _slug(name),
        "component": comp,
        "permission": "write" if write else "read",
        "approval": _has(text, V["sensitive_words"]),
        "description": text,
    }


def _word(text: str, w: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", text) is not None


def language_for(use_case: str = "", discipline: str | None = None) -> dict:
    """A new project's language: the first the use case names, else the default. A suggestion.
    `code` is False when the work isn't software (a support or finance agent, by its Lab
    discipline) and the goal names no language: then no code is needed to start."""
    t = (use_case or "").lower()
    for name, lang in V["languages"].items():
        hit = next((w for w in lang["words"] if _word(t, w)), None)
        if hit:
            return {
                "name": name,
                "suggested": True,
                "why": f"the use case says {hit!r}",
                "code": True,
            }
    return {
        "name": V["default_language"],
        "suggested": True,
        "why": "the default; the use case names no language",
        "code": discipline is None or is_code(discipline),
    }


def goal_block(goal: str | None) -> dict:
    """The goal as the brief states it: the whole text and its rule lines (goal-rules)."""
    text = _one(goal) if goal and goal.strip() else None
    return {"goal": text, "rules": goal_rules(goal) if text else []}


def _layout(
    agents: list[tuple[str, str]],
    retrieval: bool,
    memory: bool,
    approvals: bool,
    lang: str = "",
    name: str = "agent",
) -> list[dict]:
    """The reference file tree in the project's language, adapted: [{path, note}] in tree order."""
    L = V["languages"].get(lang) or V["languages"][V["default_language"]]
    x, src = L["ext"], L["src"]
    f: list[tuple[str, str]] = [
        (".github/workflows/ci.yml", "CI: tests, evals, build checks"),
        (f"{src}/agents/", "one file per agent role"),
    ]
    f += [(f"{src}/agents/{n}.{x}", note) for n, note in agents]
    f += [
        (f"{src}/orchestration/graph.{x}", "routes, loops and stop conditions"),
        (f"{src}/orchestration/state.{x}", "typed state and checkpoint schema"),
        (f"{src}/orchestration/retries.{x}", "timeouts, backoff, safe retries"),
        (f"{src}/llm/client.{x}", "provider adapters, structured output"),
        (
            f"{src}/prompts/system.md",
            "versioned instructions: role, constraints, output contract",
        ),
        (f"{src}/tools/registry.{x}", "tool schemas, permissions, dispatch"),
    ]
    if retrieval:
        f += [
            (f"{src}/retrieval/ingest.{x}", "parse, chunk, embed, index"),
            (f"{src}/retrieval/search.{x}", "hybrid retrieval, reranking, citations"),
        ]
    if memory:
        f += [
            (f"{src}/memory/session.{x}", "conversation context, working state"),
            (f"{src}/memory/store.{x}", "scoped storage, retention, recall"),
        ]
    f.append((f"{src}/guardrails/validation.{x}", "validate inputs, outputs, tool args"))
    if approvals:
        f.append((f"{src}/guardrails/approvals.{x}", "pause and resume sensitive actions"))
    f += [
        (f"{src}/observability/tracing.{x}", "traces, metrics, redacted logs"),
        (f"{src}/api/main.{x}", "request endpoints, health checks"),
        ("configs/default.yaml", "models, retrieval, tool settings"),
        ("configs/budgets.yaml", "token, cost, time, step limits"),
        ("evals/datasets/", "versioned cases and expected outcomes"),
        (f"evals/run.{x}", "score task success, safety, cost"),
        ("tests/unit/", "unit tests"),
        ("tests/integration/", "integration tests"),
        ("infra/", "deployment files"),
        ("scripts/", "helper scripts"),
        ("Dockerfile", "container image"),
        (".env.example", "variable names only"),
        (".gitignore", ""),
        (L["manifest"], "package and dependencies"),
        ("README.md", "what it is and how to run it"),
    ]
    top = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "agent"
    return [{"path": f"{top}/{p}", "note": n} for p, n in f]


def _evals(extras: dict, kind: str) -> dict:
    # Only scenarios a run can use are a way to check it: one marked runnable False (approved
    # with prose for a check, or not approved) is counted, never listed.
    listed = [
        s for s in extras.get("scenarios", []) if not isinstance(s, dict) or s.get("runnable", True)
    ]
    return {
        "scenarios": listed,
        "scenarios_left_out": int(extras.get("scenarios_left_out", 0))
        + len(extras.get("scenarios", [])) - len(listed),
        "latest": extras.get("results", []),
        "rerun": V["rerun"][kind],
        "api": V["rerun_api"][kind],
        "done_when": [
            "every task above passes its check",
            "no run exceeds the budgets",
            "no sensitive action runs without approval",
        ],
    }


def spec_from_architecture(
    arch: Architecture,
    extras: dict | None = None,
    use_case: str = "",
    kind: str = "design",
    goal: str | None = None,
    discipline: str | None = None,
) -> dict:
    """A new project's spec built from an architecture (a Garage design, with nothing yet).
    `goal` is what step 1 says (else the use case); `discipline` the Lab discipline it is for."""
    x = extras or {}
    lang = language_for(goal or use_case, discipline)
    comps, agents, tools = [], [], []
    seen_agent: set[str] = set()
    retrieval = memory = False
    for c in arch.components:
        text = _text(c)
        roles = _roles(text)
        retrieval |= "retrieval" in roles or _has(text, ["vector", "graph db", "graph database"])
        memory |= "memory" in roles
        resp = [r for r in (c.role, c.sublabel, c.why) if r]
        resp += [f"found in {e}" for e in c.evidence[:3]]
        comps.append(
            {
                "id": c.id,
                "label": c.label,
                "type": c.type,
                "role": c.role or c.type,
                "responsibilities": resp or [f"Implements {c.label}."],
                # What Rig found about a part is a fact about it, not something to tune.
                "parameters": {},
            }
        )
        for r in roles:
            if r in ("planner", "executor", "orchestrator", "reviewer") and r not in seen_agent:
                seen_agent.add(r)
                agents.append((r, f"{c.label}: {c.role or r}"))
        if "tool" in roles or c.type in V["tool_types"]:
            tools.append(_tool_entry(c.label, c.id, c.type, text))
    if not agents:
        agents.append(("executor", "select actions, interpret results"))
    approvals = any(t["approval"] for t in tools) or any(
        "approval" in _roles(_text(c)) for c in arch.components
    )
    flows = [
        {"from": ln.from_, "to": ln.to, "what": ln.label or ""}
        for ln in arch.connections
        if ln.variant != "removed"
    ]
    flows += [
        {"from": s.from_, "to": s.to, "what": f"{f.name}: {s.what}".strip(": ")}
        for f in arch.flows
        for s in f.steps
    ]
    b = V["budgets"]
    spec: dict[str, Any] = {
        "kind": "new",
        "name": arch.title,
        **goal_block(goal or use_case),
        "summary": f"{arch.title}: {len(comps)} components, {len(flows)} flows.",
        "components": comps,
        "flows": flows,
        "models": x.get("models") or {a: V["default_model"] for a, _ in agents},
        "budgets": x.get("budgets")
        or {
            "tokens": b["tokens"],
            "cost_usd": b["cost_usd"],
            "steps": b["steps_per_run"],
            "time_s": b["time_s"],
            "default": True,
        },
        "guardrails": x.get("guardrails")
        or [
            "Validate inputs, outputs and tool arguments (guardrails/validation"
            f".{V['languages'][lang['name']]['ext']}).",
            "Only call tools in the registry, within their permission.",
            "Stop at the step, token, cost or time budget and report what is left.",
        ]
        + (["Pause sensitive actions for approval before they run."] if approvals else []),
        "tools": x.get("tools") or tools,
        "memory": {"enabled": memory, "scope": "per session, with retention" if memory else None},
        "evals": _evals(x, kind),
        "language": lang,
        "layout": _layout(agents, retrieval, memory, approvals, lang["name"], arch.title),
        "loop": V["agent_loop"],
    }
    if retrieval:
        spec["retrieval"] = {
            "enabled": True,
            "pipeline": "ingest (parse, chunk, embed, index) then search (hybrid, rerank, cite)",
            "components": [
                c["label"] for c in comps if "retrieval" in _roles(c["label"] + " " + c["role"])
            ],
        }
    return spec


def spec_from_workflow(
    wf: Workflow, extras: dict | None = None, use_case: str = "", goal: str | None = None
) -> dict:
    """A new project's spec built from a Lab workflow (nothing yet: no repo). The goal is the
    one passed, else the workflow's own brief (its Goal & rules), else the use case."""
    x = extras or {}
    goal = goal or wf.brief or use_case
    lang = language_for(goal, wf.discipline)
    names = {s.id: s.name for s in wf.steps}
    edges = wf.edges or [[a.id, b.id] for a, b in zip(wf.steps, wf.steps[1:], strict=False)]
    comps = [
        {
            "id": s.id,
            "label": s.name,
            "type": "agent",
            "role": s.kind,
            "responsibilities": [s.does] + [f"Skill: {k['name']}" for k in s.skills],
            "parameters": {"model": s.model},
        }
        for s in wf.steps
    ]
    flows = [
        {"from": a, "to": b, "what": f"{names.get(a, a)} hands to {names.get(b, b)}"}
        for a, b in edges
    ]
    flows += [
        {"from": a, "to": b, "what": f"loop back to fix, at most {mx} time{'' if mx == 1 else 's'}"}
        for a, b, mx in wf.loops
    ]
    from proving_ground.lab import W

    b = V["budgets"]
    rounds = 1 + sum(mx for *_, mx in wf.loops)
    units = sum(W["models"][s.model]["cost"] for s in wf.steps)
    n = len(wf.steps) * rounds
    from proving_ground.lab import harness_text

    harness = [
        f"{W['harness'][h]['name']}: {harness_text(h, wf.discipline, wf.facts)}" for h in wf.harness
    ]
    # A step that searches sources or keeps notes puts retrieval or memory in (RAG: retrieval).
    retrieving = [
        st
        for st in wf.steps
        if wf.origin == "rag" or _says(f"{st.name} {st.does}", V["retrieval_words"])
    ]
    memory = any(_says(f"{st.name} {st.does}", V["memory_words"]) for st in wf.steps)
    tools = (
        [_tool_entry("run_checks", "check", "backend", "run checks and report pass or fail")]
        if any(s.kind in ("check", "judge") for s in wf.steps)
        else []
    )
    spec: dict[str, Any] = {
        "kind": "new",
        "name": wf.name,
        **goal_block(goal),
        "summary": f"{wf.name}: {len(wf.steps)} steps, {len(wf.loops)} loops ({wf.discipline}).",
        "components": comps,
        "flows": flows,
        "workflow": {
            "id": wf.id,
            "discipline": wf.discipline,
            "steps": [
                {
                    "id": s.id,
                    "name": s.name,
                    "kind": s.kind,
                    "does": s.does,
                    "model": s.model,
                    "skills": [k["name"] for k in s.skills],
                }
                for s in wf.steps
            ],
            "edges": edges,
            "loops": [list(lp) for lp in wf.loops],
            "parallel_levels": [list(lv) for lv in levels(wf)],
            "harness": harness,
        },
        "models": x.get("models") or {s.id: s.model for s in wf.steps},
        "budgets": x.get("budgets")
        or {
            "tokens": b["tokens_per_step"] * n,
            "cost_usd": round(b["usd_per_cost_unit_step"] * units * rounds, 2),
            "steps": n,
            "time_s": b["seconds_per_step"] * n,
            "default": True,
        },
        "guardrails": x.get("guardrails")
        or (harness or ["Stop at the budgets and report what is left."]),
        "tools": x.get("tools") or tools,
        "memory": {
            "enabled": memory,
            "scope": "per session, with retention" if memory else None,
        },
        "evals": _evals(x, "workflow"),
        "language": lang,
        "layout": _layout(
            [(_slug(s.id), f"{s.name} ({s.kind}): {s.does}") for s in wf.steps],
            bool(retrieving),
            memory,
            any(t["approval"] for t in tools),
            lang["name"],
            wf.name,
        ),
        "loop": V["agent_loop"],
    }
    if retrieving:
        spec["retrieval"] = {
            "enabled": True,
            "pipeline": "ingest (parse, chunk, embed, index) then search (hybrid, rerank, cite)",
            "components": [s.name for s in retrieving],
        }
    return spec


def _says(text: str, words: list[str]) -> bool:
    t = text.lower()
    return any(re.search(rf"(?<![a-z]){re.escape(w)}", t) for w in words)


def _one(text: str) -> str:
    """One line of plain text: canvas strings go into Markdown, never break its structure."""
    return " ".join(str(text).split())


def _code(text: str) -> str:
    return _one(text).replace("`", "'")


def _where(path: str, root: Path | None) -> str:
    """A path relative to the repo when it is inside it; else the path, home shortened to ~.
    Worked out from the text alone: nothing is read from it."""
    if not path:
        return ""
    p = os.path.normpath(path)
    if root is not None and os.path.isabs(p):
        r = os.path.normpath(str(root))
        if p.startswith(r.rstrip(os.sep) + os.sep):
            return "./" + os.path.relpath(p, r).replace(os.sep, "/")
    home = os.path.normpath(str(Path.home()))
    if p.startswith(home.rstrip(os.sep) + os.sep):
        return "~/" + os.path.relpath(p, home).replace(os.sep, "/")
    return p


_SAFE_FOLDER = re.compile(r"^[A-Za-z0-9_./-]*$")


def _github_tree(repo: str, folder: str) -> str:
    f = folder.strip("/")
    if f and (not _SAFE_FOLDER.match(f) or ".." in f.split("/")):
        f = ""
    return f"https://github.com/{repo}" + (f"/tree/HEAD/{f}" if f else "")


def with_canvas(spec: dict, added: dict, root: Path | None = None) -> dict:
    """The spec with what was placed on the canvas: skills (and where to get each), GitHub repos
    and their parts, planned skills, the links drawn and the notes. Sorted, so the same canvas
    always gives the same brief."""
    skills_ = {}
    for k in added.get("skills", []):
        local = _where(k.get("path", ""), root)
        inside = local.startswith("./")
        gh = _github_tree(k["repo"], k.get("folder", "")) if k.get("repo") else ""
        entry = {
            "name": _one(k["name"]),
            "get": local if inside or not gh else gh,
            "from": "repo" if inside else "github" if gh else "local",
        }
        if gh:
            entry["github"] = gh
        if local and not inside:
            entry["local"] = local
        skills_.setdefault((entry["name"].lower(), entry["get"]), entry)
    repos = {}
    for r in added.get("repos", []):
        cur = repos.setdefault(
            r["repo"],
            {
                "repo": r["repo"],
                "name": _one(r["name"]),
                "url": f"https://github.com/{r['repo']}",
                "category": _one(r.get("category", "")),
                "parts": [],
            },
        )
        if r.get("category") and not cur["category"]:
            cur["category"] = _one(r["category"])
        seen = {x["path"] for x in cur["parts"]}
        for part in r.get("parts", []):
            if part["path"] in seen:
                continue
            seen.add(part["path"])
            url = part.get("url", "")
            ok = url.startswith(f"https://github.com/{r['repo']}/") and not any(
                c.isspace() for c in url
            )
            cur["parts"].append(
                {
                    "kind": _one(part["kind"]),
                    "name": _one(part["name"]),
                    "path": _one(part["path"]),
                    "url": url if ok else "",
                    "description": _one(part.get("description", "")),
                }
            )
    planned = sorted(
        {
            _one(x["name"]): (x.get("ref", ""), x.get("do", "")) for x in added.get("planned", [])
        }.items()
    )
    links = sorted(
        {
            (_one(x["from"]), _one(x["to"]), x.get("relation", "connects to"))
            for x in added.get("links", [])
        }
    )
    notes = sorted(
        {(_one(x["on"]), " ".join(str(x["text"]).split())) for x in added.get("notes", [])}
    )
    out = {
        "skills": [skills_[k] for k in sorted(skills_)],
        "repos": [repos[k] for k in sorted(repos, key=str.lower)],
        "planned": [
            {"name": n, "ref": _one(r)} | ({"do": _one(d)} if d else {}) for n, (r, d) in planned
        ],
        "links": [{"from": a, "to": b, "relation": rel} for a, b, rel in links],
        "notes": [{"on": a, "text": t} for a, t in notes],
    }
    n_parts = sum(len(r["parts"]) for r in out["repos"])
    bits = [
        (len(out["skills"]), "skill"),
        (len(out["repos"]), "GitHub repo"),
        (n_parts, "part"),
        (len(out["planned"]), "planned part"),
        (len(out["links"]), "link"),
    ]
    said = [f"{n} {w}{'' if n == 1 else 's'}" for n, w in bits if n]
    spec = {**spec, "added": out}
    if said:
        spec["summary"] = f"{spec['summary']} Added on the canvas: {', '.join(said)}."
    return spec


# ---------- A repo: the changes to make in it ----------


def _read(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _test_word(cmd: str) -> bool:
    """A command that runs tests: a test word as a word; a lone file or folder name is not one."""
    t = cmd.lower().strip()
    if not t or (" " not in t and re.search(r"[./]", t) and not t.startswith("./")):
        return False
    return any(re.search(rf"(?<![a-z0-9_]){re.escape(w)}(?![a-z0-9_])", t) for w in V["test_words"])


def _written_commands(text: str) -> list[str]:
    """Test commands a team wrote in CLAUDE.md / AGENTS.md: in backticks or in a code block."""
    found = re.findall(r"(?<!`)`([^`\n]{2,160})`(?!`)", text)
    for block in re.findall(r"```[^\n]*\n(.*?)```", text, re.S):
        found += [ln.strip().lstrip("$ ").strip() for ln in block.splitlines()]
    return [
        c.strip() for c in found if c.strip() and _test_word(c) and not c.strip().endswith(".md")
    ]


def _marker_command(folder: Path, rule: dict) -> str | None:
    f = folder / rule["file"]
    if not f.is_file():
        return None
    run = rule["run"]
    if rule.get("script"):
        try:
            script = (json.loads(_read(f)).get("scripts") or {}).get(rule["script"], "")
        except (ValueError, AttributeError):
            return None
        if not script or "no test specified" in script:
            return None
        if (folder / "pnpm-lock.yaml").is_file():
            run = run.replace("npm", "pnpm", 1)
        elif (folder / "yarn.lock").is_file():
            run = run.replace("npm", "yarn", 1)
    if rule.get("has") and rule["has"] not in _read(f):
        return None
    if run == "pytest" and (folder / "uv.lock").is_file():
        run = "uv run pytest"
    return run


def repo_tests(root: Path | None) -> list[dict]:
    """How the repo is tested, from its own files: [{run, from}], what the team wrote first."""
    if root is None or not root.is_dir():
        return []
    out: list[dict] = []
    seen: set[str] = set()

    def add(run: str, src: str) -> None:
        if run not in seen:
            seen.add(run)
            out.append({"run": run, "from": src})

    for name in ("CLAUDE.md", "AGENTS.md"):
        for c in _written_commands(_read(root / name, 50_000)):
            add(c, name)
    folders = [root] + sorted(
        d
        for d in root.iterdir()
        if d.is_dir() and not d.name.startswith(".") and d.name not in SKIP_DIRS
    )
    for folder in folders:
        rel = "" if folder == root else folder.name
        for rule in V["test_commands"]:
            run = _marker_command(folder, rule)
            if run:
                add(f"cd {rel} && {run}" if rel else run, f"{rel}/{rule['file']}".lstrip("/"))
    return out[: V["max_test_commands"]]


def _json_keys(path: Path, key: str) -> list[str]:
    try:
        data = json.loads(_read(path))
    except ValueError:
        return []
    v = data.get(key) if isinstance(data, dict) else None
    return sorted(str(k) for k in v) if isinstance(v, dict) else []


def repo_setup(root: Path | None, meta: dict) -> dict:
    """The agent setup the repo has now: instructions, skills, hooks, MCP servers, the rest."""
    found = set(meta.get("agent_setup", []))
    at_root = {n: bool(root and (root / n).is_file()) for n in ("CLAUDE.md", "AGENTS.md")}
    hooks: list[str] = []
    mcp: list[str] = []
    if root is not None:
        for f in ("settings.json", "settings.local.json"):
            hooks += _json_keys(root / ".claude" / f, "hooks")
        mcp = _json_keys(root / ".mcp.json", "mcpServers")
    return {
        "instructions": [
            {"file": n, "present": n in found or at_root[n], "at_root": at_root[n]}
            for n in ("CLAUDE.md", "AGENTS.md")
        ],
        "skills": sorted(
            (
                {"name": _one(k["name"]), "path": k.get("path", "")}
                for k in meta.get("skill_details", [])
            ),
            key=lambda k: (k["name"].lower(), k["path"]),
        ),
        "hooks": sorted(set(hooks)),
        "mcp_servers": mcp or (["(listed in .mcp.json)"] if "MCP servers" in found else []),
        "other": sorted(found - {"CLAUDE.md", "AGENTS.md", "Skills", "MCP servers"}),
    }


def setup_lane(root: Path | None, meta: dict) -> list[dict]:
    """The coding agent's setup as the canvas draws it, first: [{id, label, present, detail}].
    Instructions (CLAUDE.md or AGENTS.md, or a placeholder to add one), skills, hooks, MCP
    servers, the repo's test command, then anything else found. Ids are the canvas's."""
    st = repo_setup(root, meta)
    out: list[dict] = []
    have = [i for i in st["instructions"] if i["present"]]
    for i in have:
        where = "at the root" if i["at_root"] else "in a subfolder"
        out.append(
            {"id": f"setup:{i['file']}", "label": i["file"], "present": True, "detail": where}
        )
    if not have:
        out.append(
            {
                "id": "setup:CLAUDE.md",
                "label": "CLAUDE.md",
                "present": False,
                "detail": "missing: add it, so the agent knows the repo's commands and rules",
            }
        )
    n = len(st["skills"])
    out.append(
        {
            "id": "setup:Skills",
            "label": "Skills",
            "present": bool(n),
            "detail": f"{n} in the repo" if n else "none in the repo",
        }
    )
    out.append(
        {
            "id": "setup:Hooks",
            "label": "Hooks",
            "present": bool(st["hooks"]),
            "detail": ", ".join(st["hooks"]) if st["hooks"] else "none in .claude/settings*.json",
        }
    )
    mcp = st["mcp_servers"]
    out.append(
        {
            "id": "setup:MCP servers",
            "label": "MCP servers",
            "present": bool(mcp),
            "detail": ", ".join(mcp) if mcp else "none in .mcp.json",
        }
    )
    tests = repo_tests(root)
    out.append(
        {
            "id": "setup:Test command",
            "label": "Test command",
            "present": bool(tests),
            "detail": f"{tests[0]['run']} (from {tests[0]['from']})" if tests else "none found",
            "run": tests[0]["run"] if tests else "",
        }
    )
    for o in st["other"]:
        out.append({"id": f"setup:{o}", "label": o, "present": True, "detail": "found in the repo"})
    return out


def _languages(meta: dict) -> list[str]:
    """The repo's main languages: the biggest, and any with at least a tenth of the code files."""
    langs = meta.get("languages") or {}
    total = sum(langs.values()) or 1
    ordered = sorted(langs.items(), key=lambda kv: (-kv[1], kv[0]))
    return [k for n, (k, v) in enumerate(ordered) if n == 0 or v / total >= 0.1][:3]


_PATHISH = re.compile(r"^(\.?[\w\-]+(?:[./][\w\-]+)+)(?::\d+(?:-\d+)?)?$")
_NAMED_FILE = re.compile(r"(?<![\w/.-])((?:\.?[\w-]+/)*\.?[\w-]+\.(?:md|json|ya?ml|toml|sh))\b")


def _files(p: dict, comps: dict[str, Any], root: Path | None) -> list[dict]:
    """The files a suggestion touches: its parts' code, the paths in its evidence, the files
    its title or what-to-do names. A file not in the repo yet is marked new."""
    paths: list[str] = []
    for t in p.get("targets", []):
        if str(t).startswith("step:"):  # a workflow step: its scenarios are Rig's files
            paths.append(".proving-ground/scenarios/")
        c = comps.get(t)
        if c is not None and c.source and c.source not in ("proposed", "removed"):
            paths.append(c.source)
    for e in p.get("evidence", []):
        e = str(e).strip()
        m = _PATHISH.match(e[2:] if e.startswith("./") else e)
        if m and not m.group(1).startswith("http"):
            paths.append(m.group(1))
    for text in (p.get("title", ""), p.get("what", "")):
        paths += _NAMED_FILE.findall(str(text))
    out, seen = [], set()
    for x in paths:
        x = x.strip()[2:] if x.startswith("./") else x.strip()
        if not x or x in seen or ".." in x.split("/"):
            continue
        seen.add(x)
        new = root is not None and not (root / x).exists()
        out.append({"path": x, "new": new})
    return out


def _task(p: dict, comps: dict[str, Any], root: Path | None) -> dict:
    d = p.get("delta") or {}
    label = {i: c.label for i, c in comps.items()}
    adds = [f"{a.get('label', a.get('id'))} ({a.get('type', 'backend')})" for a in d.get("add", [])]
    return {
        "id": p["id"],
        "title": _one(p["title"]),
        "kind": p.get("kind", ""),
        "why": _one(p.get("why", "")),
        "do": _one(p.get("what", "")),
        "parts": [label.get(t, t) for t in p.get("targets", []) if not str(t).startswith("step:")],
        "adds": adds,
        "takes_out": [label.get(r, r) for r in d.get("remove", [])],
        "files": _files(p, comps, root),
        "effort": p.get("effort", "M"),
        "improves": {k: _one(v) for k, v in sorted((p.get("impact") or {}).items())},
        "source": p.get("source", "rules"),
    }


def spec_for_repo(
    arch: Architecture,
    root: Path | None,
    meta: dict,
    *,
    use_case: str | None = None,
    suggestions: list[dict] | None = None,
    with_suggestions: bool = False,
    removed: list[dict] | None = None,
    extras: dict | None = None,
) -> dict:
    """A repo's change brief: what to add or change in it, never a new project."""
    x = extras or {}
    name = root.name if root is not None else arch.title
    comps = {c.id: c for c in arch.components}
    props = suggestions or []
    order = {e: n for n, e in enumerate(V["effort_order"])}

    def key(p: dict):
        return (order.get(p.get("effort"), len(order)), _one(p["title"]).lower(), p["id"])

    accepted = sorted((p for p in props if p.get("state") == "accepted"), key=key)
    still_open = sorted((p for p in props if p.get("state", "open") == "open"), key=key)
    langs = _languages(meta)
    notes = [p for p in accepted if diagram_only(p)]
    code = [p for p in accepted if not diagram_only(p)]
    tasks = [_task(p, comps, root) for p in code] if with_suggestions else []
    spec: dict[str, Any] = {
        "kind": "change",
        "name": name,
        "summary": (
            f"Changes to make in {name}"
            + (f" ({', '.join(langs)})" if langs else "")
            + f": {len(tasks)} task{'' if len(tasks) == 1 else 's'} from accepted suggestions."
            if with_suggestions
            else f"Changes to make in {name}" + (f" ({', '.join(langs)})" if langs else "") + "."
        ),
        **goal_block(use_case),
        "repo": {
            "name": name,
            "languages": langs,
            "language_files": dict(
                sorted((meta.get("languages") or {}).items(), key=lambda kv: (-kv[1], kv[0]))
            ),
            "stack": sorted(meta.get("stack", [])),
            "files": meta.get("files", 0),
        },
        "setup": repo_setup(root, meta),
        "parts": [
            {
                "id": c.id,
                "label": c.label,
                "type": c.type,
                "role": c.role or c.sublabel or "",
                "source": c.source or "",
            }
            for c in arch.components
            if c.source not in ("proposed", "removed")
        ],
        "changes": tasks,
        "undecided": (
            [
                {"id": p["id"], "title": _one(p["title"]), "why": _one(p.get("why", ""))}
                for p in still_open
            ]
            if with_suggestions
            else []
        ),
        "diagram_notes": (
            [
                {"id": p["id"], "title": _one(p["title"]), "do": _one(p.get("what", ""))}
                for p in notes
            ]
            if with_suggestions
            else []
        ),
        "warnings": stack_warnings(use_case or "", meta),
        "left_out": 0 if with_suggestions else len(accepted),
        "removed": sorted(
            ({"id": r["id"], "label": _one(r.get("label") or r["id"])} for r in removed or []),
            key=lambda r: (r["label"].lower(), r["id"]),
        ),
        "checks": repo_tests(root),
        "evals": _evals(x, "repo"),
    }
    return spec


def diagram_only(p: dict) -> bool:
    """A suggestion that only fixes the diagram (build-spec: diagram_only): nothing to code."""
    rule = V["diagram_only"]
    d = p.get("delta") or {}
    impacts = set((p.get("impact") or {}).keys())
    return (
        p.get("kind") in rule["kinds"]
        and not d.get("add")
        and not d.get("remove")
        and bool(impacts)
        and impacts <= set(rule["impacts"])
    )


def stack_warnings(use_case: str, meta: dict) -> list[str]:
    """A language or tool the use case names that the repo has no files in (stack_words)."""
    have = {str(k) for k in (meta.get("languages") or {})}
    said: list[str] = []
    for lang, words in V["stack_words"].items():
        if lang in have:
            continue
        said += [w for w in words if _mentions(use_case, w)]
    if not said:
        return []
    langs = "/".join(_languages(meta)) or "in other languages"
    return [f"Your goal mentions {'/'.join(dict.fromkeys(said))}; this repo is {langs}."]


def _mentions(text: str, word: str) -> bool:
    return re.search(rf"(?<![\w.#]){re.escape(word.lower())}(?![\w#+])", text.lower()) is not None


def _canon(v: Any) -> str:
    """A parameter value as text that compares the same way the form shows it: true and True,
    0.6 and 0.60 are one value."""
    if isinstance(v, bool):
        return "true" if v else "false"
    t = _one(str(v))
    if t.lower() in ("true", "false"):
        return t.lower()
    try:
        return f"{float(t):g}"
    except ValueError:
        return t


def with_design(spec: dict, entry: dict, values: dict | None = None) -> dict:
    """The spec with a chosen Garage design: its parts, links and parameters, each with the value
    chosen and the default. Only names the design has are taken; values stay text."""
    vals = {str(k): v for k, v in (values or {}).items()}
    label = {c["id"]: c["label"] for c in entry["components"]}
    params = []
    for p in entry.get("parameters", []):
        default = _canon(p["default"])
        raw = vals.get(p["name"])
        value = default if raw is None or _one(str(raw)) == "" else _canon(raw)
        note = ""
        if raw is not None and p.get("options"):
            if value not in [_canon(o) for o in p["options"]]:
                note = f"not one of {', '.join(_canon(o) for o in p['options'])}"
        elif raw is not None and p.get("range"):
            lo, hi = p["range"]
            try:
                if not lo <= float(value) <= hi:
                    note = f"outside {lo} to {hi}"
            except ValueError:
                note = "not a number"
        params.append(
            {
                "name": p["name"],
                "value": value,
                "default": default,
                "changed": value != default,
                "what": _one(p.get("what", "")),
                **({"note": note} if note else {}),
            }
        )
    design = {
        "id": entry["id"],
        "name": entry["name"],
        "family": entry.get("family", ""),
        "summary": _one(entry.get("summary", "")),
        "parts": [
            {"id": c["id"], "label": c["label"], "type": c["type"], "role": _one(c.get("role", ""))}
            for c in entry["components"]
        ],
        "connections": [
            {"from": label.get(a, a), "to": label.get(b, b), "what": _one(w)}
            for a, b, w in entry["connections"]
        ],
        "parameters": params,
    }
    out = {**spec, "design": design}
    if spec.get("kind") == "new":
        out = _design_parts_in(out, entry)
    return out


def _design_parts_in(spec: dict, entry: dict) -> dict:
    """A new project's brief with the design's retrieval and memory parts: the Memory and
    retrieval section and the layout follow the design as well as the workflow's steps."""
    texts = [(c["label"], f"{c['label']} {c.get('role', '')}") for c in entry["components"]]
    retr = [lbl for lbl, t in texts if "retrieval" in _roles(t) or _says(t, V["retrieval_words"])]
    mem = [lbl for lbl, t in texts if "memory" in _roles(t)]
    spec = dict(spec)
    L = V["languages"].get(spec["language"]["name"]) or V["languages"][V["default_language"]]
    top = spec["layout"][0]["path"].split("/", 1)[0] if spec["layout"] else "agent"
    paths = [e["path"] for e in spec["layout"]]
    add: list[dict] = []
    if retr:
        old = spec.get("retrieval") or {"components": []}
        spec["retrieval"] = {
            "enabled": True,
            "pipeline": "ingest (parse, chunk, embed, index) then search (hybrid, rerank, cite)",
            "components": list(dict.fromkeys([*old.get("components", []), *retr])),
        }
        add += [
            {
                "path": f"{top}/{L['src']}/retrieval/ingest.{L['ext']}",
                "note": "parse, chunk, embed, index",
            },
            {
                "path": f"{top}/{L['src']}/retrieval/search.{L['ext']}",
                "note": "hybrid retrieval, reranking, citations",
            },
        ]
    if mem:
        spec["memory"] = {"enabled": True, "scope": "per session, with retention"}
        add += [
            {
                "path": f"{top}/{L['src']}/memory/session.{L['ext']}",
                "note": "conversation context, working state",
            },
            {
                "path": f"{top}/{L['src']}/memory/store.{L['ext']}",
                "note": "scoped storage, retention, recall",
            },
        ]
    new = [a for a in add if a["path"] not in paths]
    if new:
        at = 1 + max(
            (
                n
                for n, p in enumerate(paths)
                if p.endswith(f"tools/registry.{L['ext']}") or "/retrieval/" in p or "/memory/" in p
            ),
            default=len(paths) - 1,
        )
        spec["layout"] = spec["layout"][:at] + new + spec["layout"][at:]
    return spec


def _table(rows: list[list[str]], head: list[str]) -> str:
    def esc(v):
        return str(v).replace("|", "\\|").replace("\n", " ")

    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _render_added(L: list[str], added: dict | None, level: int = 2) -> bool:
    """The canvas sections, each only when it has entries. True when any was written."""
    if not added:
        return False
    T = V["added_sections"]
    hh = "#" * level
    wrote = False

    def head(key: str) -> None:
        nonlocal wrote
        wrote = True
        L.extend(["", f"{hh} {T[key]}", ""])

    if added["skills"]:
        head("skills")
        L.append("Add each skill to the project's agent setup; get it from where it says.")
        where = {"repo": "in this repo at", "github": "from GitHub:", "local": "a local folder:"}
        for k in added["skills"]:
            L.append(f"- **{k['name']}**: {where[k['from']]} `{_code(k['get'])}`")
            if k["from"] == "repo" and k.get("github"):
                L.append(f"  - also on GitHub: {k['github']}")
    if added["repos"]:
        head("repos")
        for r in added["repos"]:
            kind = f", {r['category']}" if r["category"] else ""
            L.append(f"{hh}# {r['name']} ({r['repo']}{kind})")
            L.append(f"- repo: {r['url']}")
            if not r["parts"]:
                L.append("- no parts laid out yet: pick what to use from it")
            for part in r["parts"]:
                desc = f": {part['description']}" if part["description"] else ""
                url = f" ({part['url']})" if part["url"] else ""
                L.append(f"- {part['kind']} **{part['name']}** `{_code(part['path'])}`{url}{desc}")
    if added["planned"]:
        head("planned")
        L.append(
            "Planned on the canvas; not written yet. Write each before relying on it: a skill, "
            "or the file it names."
        )
        L += [
            f"- {x['name']}"
            + (f" (`{_code(x['ref'])}`)" if x["ref"] else "")
            + (f": {x['do']}" if x.get("do") else "")
            for x in added["planned"]
        ]
    if added["links"]:
        head("links")
        L += [f"- {x['from']} -> {x['to']}: {x['relation']}" for x in added["links"]]
    if added["notes"]:
        head("notes")
        L += [f"- {x['on']}: {x['text']}" for x in added["notes"]]
    return wrote


def _not_evidence(r: dict) -> bool:
    return (r.get("rig") or {}).get("band") == "not_evidence"


def _measured(L: list[str], ev: dict) -> None:
    if ev["latest"]:
        L.append(
            _table(
                [
                    [
                        r.get("name", ""),
                        # A run that isn't evidence has no change and no verdict to read: its
                        # number never sits beside "helps".
                        "–" if _not_evidence(r) else r.get("diff", ""),
                        r.get("pairs", ""),
                        "not evidence" if _not_evidence(r) else r.get("verdict", ""),
                        rig_text(r.get("rig")),
                    ]
                    for r in ev["latest"]
                ],
                ["measured", "change (points)", "pairs", "verdict", "Rig score"],
            )
        )
        L += [
            f"- {r.get('name', '')}: Rig {r['rig']['score']}/100. {r['rig']['reason']}."
            for r in ev["latest"]
            if (r.get("rig") or {}).get("score") is not None
        ]
    else:
        L.append(
            "Nothing measured yet. Measure it in Rig (step 4, Measure) and the results appear here."
        )


def _params_table(d: dict) -> str:
    return _table(
        [
            [
                f"`{p['name']}`",
                f"{p['value']}" + (" (changed)" if p["changed"] else ""),
                str(p["default"]),
                p["what"] + (f" Note: {p['note']}." if p.get("note") else ""),
            ]
            for p in d["parameters"]
        ],
        ["parameter", "value", "default", "what it sets"],
    )


def _design_lines(d: dict, params: bool = True) -> list[str]:
    L = [d["summary"], "", "Parts:"]
    L += [
        f"- **{p['label']}** (`{p['id']}`, {p['type']})" + (f": {p['role']}" if p["role"] else "")
        for p in d["parts"]
    ]
    L += ["", "Connections:"]
    L += [
        f"- {c['from']} -> {c['to']}" + (f": {c['what']}" if c["what"] else "")
        for c in d["connections"]
    ] or ["- none"]
    if d["parameters"] and params:
        L += ["", "Parameters (the value chosen in Rig, and the design's default):", ""]
        L.append(_params_table(d))
    elif d["parameters"]:
        L += ["", "Its parameters, with the values chosen in Rig, are under Parameters below."]
    return L


def _effort(e: str) -> str:
    w = V["effort_words"].get(e)
    return f"{e} ({w})" if w else e


def render_change(spec: dict) -> str:
    """A repo's brief: the changes to make in it, in its own language, checked its own way."""
    T = V["change_sections"]
    r = spec["repo"]
    L: list[str] = [f"# BUILD: {spec['name']}"]
    langs = ", ".join(r["languages"]) or "the languages already in it"

    def h(key: str, extra: str = "") -> None:
        L.extend(["", f"## {T[key]}{extra}", ""])

    L += [
        "",
        spec["summary"],
        "",
        f"This brief is for the existing repo **{spec['name']}** ({r['files']} files; "
        f"{langs}" + (f"; {', '.join(r['stack'])}" if r["stack"] else "") + "). "
        "Change it in place: keep its language, layout and conventions, add only what a task "
        "below asks for, and don't start a new project or move existing code.",
    ]
    h("goal")
    L.append(spec["goal"] or "No use case written yet. Add one in Rig (step 1, Describe).")
    _rules(L, spec)
    for w in spec.get("warnings", []):
        L += ["", f"Note: {w} Check the goal is about this repo before changing it."]
    h("current")
    st = spec["setup"]
    for i in st["instructions"]:
        where = (
            "" if not i["present"] else " (at the root)" if i["at_root"] else " (in a subfolder)"
        )
        L.append(f"- {i['file']}: {'yes' + where if i['present'] else 'not there'}")
    skills_ = st["skills"]
    L.append(
        f"- skills: {len(skills_)}: "
        + ", ".join(f"{k['name']} (`{_code(k['path'])}`)" for k in skills_[:12])
        + (f", and {len(skills_) - 12} more" if len(skills_) > 12 else "")
        if skills_
        else "- skills: none"
    )
    L.append(f"- hooks: {', '.join(st['hooks'])}" if st["hooks"] else "- hooks: none")
    L.append(
        f"- MCP servers: {', '.join(st['mcp_servers'])}"
        if st["mcp_servers"]
        else "- MCP servers: none"
    )
    if st["other"]:
        L.append(f"- also: {', '.join(st['other'])}")
    if spec["parts"]:
        L += ["", "Parts Rig read from the code:"]
        L += [
            f"- **{p['label']}** ({p['type']}"
            + (f", {_one(p['role'])}" if p["role"] else "")
            + ")"
            + (f" `{_code(p['source'])}`" if p["source"] else "")
            for p in spec["parts"][:30]
        ]
        if len(spec["parts"]) > 30:
            L.append(f"- and {len(spec['parts']) - 30} more in rig.json")
    h("changes")
    if spec["changes"]:
        for n, t in enumerate(spec["changes"], 1):
            L.append(f"### {n}. {t['title']}")
            L.append(f"- why: {t['why']}" if t["why"] else "- why: accepted in Rig")
            L.append(f"- do: {t['do']}" if t["do"] else "- do: as the title says")
            if t["parts"]:
                L.append(f"- parts: {', '.join(t['parts'])}")
            if t["adds"]:
                L.append(f"- adds: {', '.join(t['adds'])}")
            if t["takes_out"]:
                L.append(f"- takes out: {', '.join(t['takes_out'])}")
            if t["files"]:
                L.append(
                    "- files: "
                    + ", ".join(
                        f"`{_code(f['path'])}`" + (" (new)" if f["new"] else "") for f in t["files"]
                    )
                )
            else:
                L.append("- files: find them from the parts above")
            if t["improves"]:
                L.append("- improves: " + "; ".join(f"{k}: {v}" for k, v in t["improves"].items()))
            L.append(f"- effort: {_effort(t['effort'])}")
            L.append("")
        L.pop()
    elif spec["left_out"]:
        n = spec["left_out"]
        L.append(
            f"No suggestions in this brief: it is the repo as it is. {n} accepted suggestion"
            f'{" is" if n == 1 else "s are"} left out; choose "With the accepted suggestions" '
            "in Rig to make them tasks."
        )
    elif spec.get("diagram_notes"):
        L.append(
            "No code or config changes among the accepted suggestions: they are notes on the "
            "diagram (below). Make the canvas changes below, if any."
        )
    else:
        L.append(
            "No accepted suggestions. Accept some in Rig (step 3, Build: the Suggestions tab), "
            "or make the canvas changes below."
        )
    if spec.get("diagram_notes"):
        h("diagram")
        L.append(
            "Accepted in Rig, but they fix how the diagram reads, not the code: nothing to change "
            "in the repo for these. Redraw the diagram in Rig, or ignore them here."
        )
        L += [
            f"- {n['title']}" + (f": {n['do']}" if n["do"] else "") for n in spec["diagram_notes"]
        ]
    if spec["undecided"]:
        h("undecided")
        L.append("Open in Rig, neither accepted nor dismissed. Don't do these unless asked.")
        L += [f"- {u['title']}" + (f": {u['why']}" if u["why"] else "") for u in spec["undecided"]]
    if spec.get("design"):
        d = spec["design"]
        h("design", f": {d['name']}")
        L.append(
            "The design chosen in Rig (step 2, Design). Move the repo toward it where a change "
            "touches these parts; it is a direction, not a rewrite."
        )
        L.append("")
        L += _design_lines(d)
    h("added")
    if not _render_added(L, spec.get("added"), level=3):
        L.append("Nothing placed on the canvas.")
    h("removed")
    if spec["removed"]:
        L.append(
            "Taken off the canvas: remove these parts and the links to them, and keep the tests passing."
        )
        L += [f"- {x['label']} (`{x['id']}`)" for x in spec["removed"]]
    else:
        L.append("Nothing removed.")
    h("check")
    if spec["checks"]:
        L.append("The repo's own tests, before and after the change:")
        L += [f"- `{_code(c['run'])}` (from {c['from']})" for c in spec["checks"]]
    else:
        L.append(
            "No test command found in the repo's build files or CLAUDE.md; run its usual tests."
        )
    ev = spec["evals"]
    if ev["scenarios"]:
        L += ["", "Rig tasks (in .proving-ground/scenarios/):"]
        L += [
            f"- `{s.get('id', '')}`: {s.get('title', s)}" if isinstance(s, dict) else f"- {s}"
            for s in ev["scenarios"]
        ]
    else:
        own = f"`{_code(spec['checks'][0]['run'])}`" if spec["checks"] else "its usual tests"
        L += ["", f"No valid Rig tasks yet: use the repo's own tests: {own}."]
    L += ["", "Done when:", "- the repo's tests pass", "- every change above is made"]
    if ev["scenarios"]:
        L.append("- the Rig tasks pass at least as often as before")
    L += ["", f"Measure again: {ev['rerun']}"]
    h("evidence")
    _measured(L, ev)
    return "\n".join(L) + "\n"


def rig_text(rig: dict | None) -> str:
    """A Rig score in one table cell: "15/100 Doesn't Work — no lift shown (provisional, 2 pairs)"."""
    if rig and rig.get("band") == "not_evidence":  # invalid or uninformative: no score
        return "not evidence"
    if not rig or rig.get("score") is None:
        return "not measured"
    out = f"{rig['score']}/100 {rig['label']}"
    return out + (f" (provisional, {rig['pairs']} pairs)" if rig.get("provisional") else "")


def render_markdown(spec: dict) -> str:
    if spec.get("kind") == "change":
        return render_change(spec)
    return render_new(spec)


def _rules(L: list[str], spec: dict) -> None:
    """The goal's rule lines (goal-rules), under the goal."""
    if spec.get("rules"):
        L += ["", f"{GOAL['brief_rules']}:"]
        L += [f"- {r}" for r in spec["rules"]]


def render_new(spec: dict) -> str:
    """A new project's brief: nothing yet, so a suggested language and layout. For work that
    isn't software (a support agent), no code is needed to start and the layout is optional."""
    L: list[str] = [f"# BUILD: {spec['name']}"]
    S = iter(V["sections"])
    lang = spec["language"]
    code = lang.get("code", True)

    def h():
        name = next(S)
        if name == V["layout_section"] and not code:
            name += " (optional)"
        L.extend(["", f"## {name}", ""])

    ext = V["languages"].get(lang["name"], V["languages"][V["default_language"]])["ext"]
    h()
    L.append(spec["summary"])
    if code:
        L.append(
            f"Build this as a new project in the layout below. Language: {lang['name']} "
            f"(suggested: {lang['why']}); if you work in another, keep the same parts and swap the "
            "file names. Do exactly what is stated; where a value is marked default, it is a "
            "starting limit to adjust."
        )
    else:
        L.append(V["no_code"].format(language=lang["name"]))
    L.extend(["", f"## {V['goal_section']}", ""])
    L.append(spec.get("goal") or "No goal written yet. Add one in Rig (step 1, Describe).")
    _rules(L, spec)
    if spec.get("design"):
        d = spec["design"]
        L.extend(["", f"## {V['design_section']}: {d['name']}", ""])
        L.append("The design chosen in Rig (step 2, Design): build these parts, linked this way.")
        L.append("")
        L += _design_lines(d, params=False)
    h()
    for c in spec["components"]:
        L.append(f"### {c['label']} (`{c['id']}`, {c['type']}, {c['role']})")
        L += [f"- {r}" for r in c["responsibilities"]]
    h()
    L += [f"- `{f['from']}` -> `{f['to']}`: {f['what'] or 'calls'}" for f in spec["flows"]] or [
        "- none stated"
    ]
    if spec.get("workflow"):
        wf = spec["workflow"]
        L += [
            "",
            "Workflow steps: "
            + ", ".join(f"{s['name']} ({s['kind']}, {s['model']})" for s in wf["steps"]),
        ]
        L += [
            f"- loop {a} -> {b}, at most {m} time{'' if m == 1 else 's'}" for a, b, m in wf["loops"]
        ]
        L += [f"- harness rule: {r}" for r in wf["harness"]]
    _render_added(L, spec.get("added"))
    h()
    rows = [[c["id"], k, v] for c in spec["components"] for k, v in c["parameters"].items()]
    if spec.get("workflow"):
        rows += [[f"{a} -> {b}", "max loops", m] for a, b, m in spec["workflow"]["loops"]]
    if rows:
        L.append(_table(rows, ["part", "parameter", "value"]))
    if spec.get("design") and spec["design"]["parameters"]:
        d = spec["design"]
        L += (["", ""] if rows else []) + [
            f"{d['name']} (the value chosen in Rig, and the design's default):",
            "",
            _params_table(d),
        ]
    elif not rows:
        L.append("No tunable parameters beyond the budgets below.")
    h()
    if not code:
        L.append(V["layout_optional"].format(language=lang["name"]))
        L.append("")
    L.append("```text")
    L += [f"{e['path']}" + (f"  # {e['note']}" if e["note"] else "") for e in spec["layout"]]
    L.append("```")
    h()
    L.append(spec["loop"])
    h()
    L.append(_table([[k, v] for k, v in spec["models"].items()], ["role or step", "model"]))
    h()
    t = spec["tools"]
    L.append(
        _table(
            [
                [x["name"], x["permission"], "yes" if x["approval"] else "no", x["description"]]
                for x in t
            ],
            ["tool", "permission", "needs approval", "what it does"],
        )
        if t
        else f"No tools beyond the model. Add each tool to tools/registry.{ext} with its schema and permission."
    )
    h()
    b = spec["budgets"]
    L.append(
        f"- tokens: {b['tokens']}\n- cost: ${b['cost_usd']}\n- steps: {b['steps']}\n- time: {b['time_s']} s"
    )
    if b.get("default"):
        L.append("- These are default limits worked out from the structure, not measured.")
    L.append("- Put them in configs/budgets.yaml and stop the run when any is reached.")
    h()
    L += [f"- {g}" for g in spec["guardrails"]]
    h()
    if spec["memory"]["enabled"]:
        L.append(f"Memory: {spec['memory']['scope']}.")
    else:
        L.append("Memory: not part of this design; leave memory/ out.")
    if spec.get("retrieval"):
        L.append(f"Retrieval: {spec['retrieval']['pipeline']}.")
    else:
        L.append("Retrieval: not part of this design; leave retrieval/ out.")
    h()
    ev = spec["evals"]
    L += [
        f"- task `{s.get('id', '')}`: {s.get('title', s)}" if isinstance(s, dict) else f"- {s}"
        for s in ev["scenarios"]
    ]
    L.append("Done when:")
    L += [f"- {d}" for d in ev["done_when"]]
    L.append(f"Measure again: {ev['rerun']}")
    h()
    _measured(L, ev)
    return "\n".join(L) + "\n"
