"""Turn engine records into JSON for the web app."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from proving_ground import priors, proven, skills, validity
from proving_ground.baseline import source_cost
from proving_ground.budget import status_text
from proving_ground.files import PG_DIR
from proving_ground.intake.repo import parse_skill
from proving_ground.models import Scenario, detect_kind, hash_tree
from proving_ground.sandbox.treatments import instruction_compare, instruction_file
from proving_ground.stats import ResultSummary, summarize
from proving_ground.store import ExperimentRow, Store


def summary_json(s: ResultSummary) -> dict[str, Any]:
    data = asdict(s)
    data["verdict"] = s.verdict.value
    # Partial credit only when every task in the pairs counted items: otherwise no key at all.
    data.pop("items")
    return data | items_json(s)


def items_json(s: ResultSummary) -> dict[str, Any]:
    """{"items": {...}} for a result row whose tasks count items (RIG_ITEMS), else {}."""
    return {"items": s.items.as_json()} if s.items is not None else {}


def _files(d: Path) -> list[Path]:
    return sorted(p for p in d.rglob("*") if p.is_file()) if d.is_dir() else []


def scenario_json(root: Path, s: Scenario, use_case: str | None = None) -> dict[str, Any]:
    """`use_case` is the repo's use case now: a scenario written for another one says so."""
    pg = root / PG_DIR
    return s.model_dump(mode="json") | {
        "runnable": s.runnable,
        # A check that isn't a command (evidence-validity): it can't be approved or run.
        "check_problem": validity.check_problem(s.check) if s.check else None,
        "goal_changed": s.written_for is not None
        and s.written_for != validity.use_case_tag(use_case),
        "file": f"{PG_DIR}/scenarios/{s.id}.yaml",
        "check_files": [
            {"path": p.relative_to(root).as_posix(), "content": p.read_text(errors="replace")}
            for p in _files(pg / "checks" / s.id)
        ],
        "fixtures": [p.relative_to(root).as_posix() for p in _files(pg / "fixtures" / s.id)],
    }


def experiment_json(store: Store, e: ExperimentRow) -> dict[str, Any]:
    return asdict(e) | {
        "spent_usd": round(store.spent(e.id), 6),
        "status_text": status_text(e.status),
    }


def evidence_json(store: Store, e: ExperimentRow) -> dict[str, Any]:
    s = summarize(store.trials(e.id))
    h = s.headline
    return {
        "experiment_id": e.id,
        "status": e.status,
        "status_text": status_text(e.status),
        "verdict": s.verdict.value,
        "diff": h.diff if h else None,
        "ci_low": h.ci_low if h else None,
        "ci_high": h.ci_high if h else None,
        "n_pairs": h.n_pairs if h else 0,
        "trials": {"total": s.total, "errored": s.errored, "broken": s.broken},
    } | items_json(s)


def costs_json(store: Store, trials: list) -> dict[str, Any]:
    """Spend and tasks solved on each arm, reused trials at what they cost when they ran."""
    return priors.cost_per_solved(trials, source_cost(store))


def _evidence(store: Store, experiments: list[ExperimentRow], path: Path) -> dict[str, Any] | None:
    matching = [e for e in experiments if e.treatment_name == path.name]
    if not matching:
        return None
    digest = hash_tree(path)
    for e in matching:  # newest first
        if e.treatment_hash == digest:
            return evidence_json(store, e)
    return None


def _skill_dirs(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if (p / "SKILL.md").is_file())


def compare_json(root: Path, path: Path, kind: str, v: dict) -> dict[str, Any]:
    """What a hook, MCP server or instructions run would compare, in words (treatment-kinds
    `compare_text`); for instructions also the case, the file it writes and its text, so
    Measure can show it and offer an edited copy."""
    texts = v["compare_text"]
    if kind != "instructions":
        return {"compare": kind, "compare_text": texts[kind]}
    f = instruction_file(path)
    case = instruction_compare(root, path)
    text = f.read_text(errors="replace")
    return {
        "compare": case,
        "compare_text": texts[case].format(name=f.name),
        "file": f.name,
        "text": text[: v["draft_max_chars"]],
    }


def treatments_json(
    root: Path,
    store: Store,
    experiments: list[ExperimentRow],
    repo_skills: list[dict],
    user_dir: Path,
    library_dir: Path | None = None,
) -> dict[str, Any]:
    def item(path: Path, name: str, description: str, source: str | None = None) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "path": str(path.resolve()),
            "evidence": _evidence(store, experiments, path),
            "source": source,
            "kind": "skill",
            "proven": proven.read(path),
        }

    def configs() -> list[dict[str, Any]]:
        """Hooks, MCP servers and instructions: in the repo's .claude/ folder, its root
        instruction files, the user's skill folder and the library (treatment-kinds skill)."""
        v = skills.load("treatment-kinds").values
        cands: list[tuple[Path, str]] = []

        def walk(base: Path, depth: int, source: str) -> None:
            if depth < 0 or not base.is_dir():
                return
            for d in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")):
                cands.append((d, source))
                walk(d, depth - 1, source)

        for r in v["repo_roots"]:
            walk(root / r, v["scan_depth"] - 1, "repo")
        cands += [(root / n, "repo") for n in v["repo_files"] if (root / n).is_file()]
        drafts = root / v["drafts_dir"]
        if drafts.is_dir():  # edited copies saved from Measure
            cands += [(d, "draft") for d in sorted(drafts.iterdir()) if d.is_dir()]
        for base, src in (
            (user_dir, "user"),
            *(((library_dir / "installed", "library"),) if library_dir else ()),
        ):
            if base.is_dir():
                cands += [(d, src) for d in sorted(base.iterdir()) if d.is_dir()]
        out, seen = [], set()
        for path, src in cands:
            try:
                kind = detect_kind(path)
            except (FileNotFoundError, ValueError):
                continue
            if kind.value == "skill" or path.resolve() in seen:
                continue
            seen.add(path.resolve())
            it = item(path, path.name, "", src) | {"kind": kind.value, "source": src}
            out.append(it | compare_json(root, path, kind.value, v))
        return out

    def folder(base: Path, with_source: bool = False) -> list[dict[str, Any]]:
        out = []
        for d in _skill_dirs(base):
            sk = parse_skill(f"{d.name}/SKILL.md", (d / "SKILL.md").read_text(errors="replace"))
            src = None
            extra: dict[str, Any] = {}
            if with_source and (d / ".source.json").is_file():
                meta = json.loads((d / ".source.json").read_text())
                src = meta.get("repo") or (
                    f"rewrite of {Path(meta['improves']).name}"
                    if meta.get("improves")
                    else "created here"
                )
                # Installed from GitHub: its folder there, so a brief can say where to get it.
                if meta.get("repo"):
                    extra["folder"] = meta.get("path") or ""
            out.append(item(d, sk.name, sk.description, src) | extra)
        return out

    repo = [item((root / s["path"]).parent, s["name"], s["description"]) for s in repo_skills]
    user = folder(user_dir)
    installed = folder(library_dir, with_source=True) if library_dir else []
    suggested = []
    sugg_dir = root / PG_DIR / "suggestions"
    for f in sorted(sugg_dir.glob("*.yaml")) if sugg_dir.is_dir() else []:
        for t in yaml.safe_load(f.read_text()) or []:
            suggested.append(t | {"workflow": f.stem})
    created = folder(library_dir / "created", with_source=True) if library_dir else []
    lab = folder(library_dir / "workflows") if library_dir else []
    return {
        "repo": repo,
        "user": user,
        "installed": installed,
        "created": created,
        "workflows": lab,
        "suggested": suggested,
        "configs": configs(),
    }
