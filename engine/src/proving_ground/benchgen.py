"""Make a bench for a workflow that has none: a model writes a small project and tasks; each
task's check is proven in Docker (fails untouched, passes on the reference solution) before it
is kept. Rules and values: the generate-bench skill.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml

from proving_ground import skills
from proving_ground.generate.client import GenerationError, ModelClient
from proving_ground.generate.prompt import Prompt

G = skills.load("generate-bench").values
FILE = {
    "type": "object",
    "required": ["path", "content"],
    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
}
TOOL = {
    "name": "emit_bench",
    "description": "Return the project and the tasks, each with its check and reference solution.",
    "input_schema": {
        "type": "object",
        "required": ["name", "summary", "files", "tasks"],
        "properties": {
            "name": {"type": "string"},
            "summary": {"type": "string"},
            "files": {"type": "array", "items": FILE},
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "id",
                        "title",
                        "kind",
                        "step",
                        "instruction",
                        "check",
                        "solution",
                        "wrong_solution",
                    ],
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "kind": {"type": "string", "enum": ["typical", "edge", "adversarial"]},
                        "step": {"type": "string"},
                        "instruction": {"type": "string"},
                        "check": {"type": "string", "description": "a Python 3.12 script"},
                        "solution": {"type": "array", "items": FILE},
                        "wrong_solution": {
                            "type": "array",
                            "items": FILE,
                            "description": "a plausible but wrong answer the check must reject",
                        },
                    },
                },
            },
        },
    },
}
SLUG = re.compile(r"[^a-z0-9]+")
PREAMBLE = 'import sys\n\nsys.path.insert(0, "/app")\n'


@dataclass
class Made:
    bench_id: str | None
    kept: list[str] = field(default_factory=list)
    dropped: dict[str, str] = field(default_factory=dict)  # task id -> why
    model: str = ""


def _slug(s: str, n: int = 40) -> str:
    return SLUG.sub("-", s.lower()).strip("-")[:n] or "x"


def _step(raw) -> str:
    """The step's name alone: writers tend to add its kind, "Capture the invoice (do): ..."."""
    return re.split(r"[(:]", str(raw or ""))[0].strip()[:40]


def _safe(rel: str) -> PurePosixPath:
    p = PurePosixPath(rel.lstrip("/").removeprefix("app/"))
    if not p.parts or ".." in p.parts or p.parts[0] in (".proving-ground", ".git"):
        raise ValueError(f"unsafe path {rel!r}")
    return p


def ask(model: ModelClient, wf: dict) -> dict:
    steps = "\n".join(
        f"- {s['name']} ({s['kind']}): {s.get('does', '')}" for s in wf.get("steps", [])
    )
    text = (
        f"<workflow>\nName: {wf.get('name')}\nDiscipline: {wf.get('discipline')}\nSteps:\n{steps}\n"
        f"</workflow>\nWrite {G['tasks']} tasks, at most {G['max_files']} project files, each file "
        f"under {G['max_file_chars']} characters."
    )
    call = model.call(
        Prompt(skills.section("generate-bench", "Writer prompt"), [{"type": "text", "text": text}]),
        TOOL,
        G["model"],
        G["max_tokens"],
    )
    if not isinstance(call.input, dict) or not call.input.get("tasks"):
        raise GenerationError("The model didn't return a bench.")
    return call.input


def _write(root: Path, files: list[dict]) -> None:
    for f in files[: G["max_files"] * 3]:
        p = root / _safe(str(f.get("path", "")))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(f.get("content", ""))[: G["max_file_chars"] * 2])


def _docker_check(app: Path, checks: Path, sid: str, run) -> tuple[bool, str]:
    """Run one check in a throwaway container: no network, the project at /app."""
    verifier = app.parent / "verifier"
    verifier.mkdir(exist_ok=True)
    cmd = [
        "docker", "run", "--rm", "--network", "none",
        "-v", f"{app}:/app", "-v", f"{checks}:/tests/checks:ro", "-v", f"{verifier}:/logs/verifier",
        "-w", "/app", G["image"], "python3", f"/tests/checks/{sid}/check.py",
    ]  # fmt: skip
    try:
        r = run(cmd, capture_output=True, text=True, timeout=G["proof_timeout_s"])
    except subprocess.TimeoutExpired:
        return False, "the check timed out"
    return r.returncode == 0, (r.stderr or r.stdout)[-300:]


def make(
    model: ModelClient, wf: dict, dest_root: Path, model_name: str, run=subprocess.run
) -> Made:
    """Ask, prove each task in Docker, and write a bench of the proven ones under dest_root."""
    spec = ask(model, wf)
    bid = "gen-" + _slug(f"{wf.get('name', 'workflow')}-{wf.get('id', '')}", 48)
    # Under the home folder: Colima and some VMs share only that with Docker.
    dest_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".work-", dir=dest_root))
    made = Made(None, model=model_name)
    try:
        project = work / "project"
        project.mkdir()
        try:
            _write(project, spec.get("files") or [])
        except ValueError as e:
            raise GenerationError(f"The project had {e}.") from e
        checks = work / "checks"
        tasks = []
        for t in spec["tasks"][: G["tasks"] + 2]:
            sid = _slug(str(t.get("id") or t.get("title") or "task"), 30)
            if sid in [x["id"] for x in tasks] or not str(t.get("check", "")).strip():
                made.dropped[sid] = "no check, or a duplicate id"
                continue
            (checks / sid).mkdir(parents=True)
            # Checks run as `python3 /tests/checks/<id>/check.py` (in the proof and in the
            # sandbox alike): put the project on the path, as the built-in checks do.
            (checks / sid / "check.py").write_text(PREAMBLE + str(t["check"]))
            before = work / "runs" / sid / "before" / "app"
            shutil.copytree(project, before)
            ok, why = _docker_check(before, checks, sid, run)
            if ok:
                made.dropped[sid] = "the check passes on the untouched project"
                shutil.rmtree(checks / sid)
                continue
            after = work / "runs" / sid / "after" / "app"
            shutil.copytree(project, after)
            try:
                _write(after, t.get("solution") or [])
            except ValueError as e:
                made.dropped[sid] = f"the solution had {e}"
                shutil.rmtree(checks / sid)
                continue
            ok, why = _docker_check(after, checks, sid, run)
            if not ok:
                made.dropped[sid] = (
                    f"the check fails on the reference solution: {why.strip()[-160:]}"
                )
                shutil.rmtree(checks / sid)
                continue
            # A check that only looks for the right shape accepts wrong answers: try one.
            wrong = work / "runs" / sid / "wrong" / "app"
            shutil.copytree(project, wrong)
            try:
                _write(wrong, t.get("wrong_solution") or [])
            except ValueError as e:
                made.dropped[sid] = f"the wrong answer had {e}"
                shutil.rmtree(checks / sid)
                continue
            if not t.get("wrong_solution"):
                made.dropped[sid] = "no wrong answer to test the check against"
                shutil.rmtree(checks / sid)
                continue
            ok, why = _docker_check(wrong, checks, sid, run)
            if ok:
                made.dropped[sid] = "the check accepts a wrong answer"
                shutil.rmtree(checks / sid)
                continue
            (work / "solutions" / sid).mkdir(parents=True)
            (work / "solutions" / sid / "solution.json").write_text(
                json.dumps(t["solution"], indent=1)
            )
            kind = (
                t.get("kind") if t.get("kind") in ("typical", "edge", "adversarial") else "typical"
            )
            tasks.append(
                {
                    "id": sid,
                    "kind": kind,
                    "title": str(t.get("title", sid))[:80]
                    + (f" (for {_step(t['step'])})" if _step(t.get("step")) else ""),
                    # The writer's step name goes in the title: the bench's own workflow is one step.
                    "instruction": str(t["instruction"])[:4000],
                }
            )
            made.kept.append(sid)
        if len(tasks) < G["min_kept"]:
            return made
        dest = dest_root / bid
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        shutil.copytree(project, dest / "project")
        shutil.copytree(checks, dest / "checks")
        shutil.copytree(work / "solutions", dest / "solutions")
        (dest / "bench.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": bid,
                    "disciplines": [wf.get("discipline") or "development"],
                    "name": str(spec.get("name") or f"Bench for {wf.get('name')}")[:70],
                    "discipline": wf.get("discipline") or "development",
                    "summary": f"{str(spec.get('summary', ''))[:400]} Generated by {model_name} for "
                    f"the workflow {wf.get('name')}; every check proven both ways in Docker.",
                    "generated": {"by": model_name, "workflow": wf.get("id")},
                    "workflow": {
                        "id": bid,
                        "name": str(wf.get("name", "workflow"))[:60],
                        "steps": [{"name": "work", "type": "code", "why": "Do the task"}],
                    },
                    "scenarios": [{k: v for k, v in t.items() if v is not None} for t in tasks],
                },
                sort_keys=False,
                allow_unicode=True,
            )
        )
        made.bench_id = bid
        return made
    finally:
        shutil.rmtree(work, ignore_errors=True)
