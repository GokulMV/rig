"""Test benches: built-in task suites a workflow is measured on, when there is no repo.

A bench is a small project with scenarios whose checks are scripts: each fails on the untouched
project and passes when the task is done right. Materialised as an ordinary project folder, so
the usual run machinery (snapshot, sandbox, with/without, statistics) measures workflows on it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from proving_ground import skills
from proving_ground.files import PG_DIR, ensure_pg_dir, save_scenario, save_workflow
from proving_ground.models import Scenario, Workflow

HERE = Path(__file__).parent / "benches"
HARD = "hard"  # a bench's hard tier: hard/tasks.yaml, hard/project/ (added files), hard/checks/
D = skills.load("bench-difficulty").values


@dataclass(frozen=True)
class Bench:
    id: str
    name: str
    discipline: str
    summary: str
    scenarios: list[dict]
    workflow: dict
    path: Path
    disciplines: list[str]  # the workflows it measures: its own discipline, and any others it fits
    judged: bool = False  # some scenarios are documents graded by a judge
    tasks: Path | None = None  # an imported suite: ready Harbor task folders, run as they are
    generated: dict | None = None  # made for a workflow by a model: {by, workflow}
    public: dict | None = None  # a public benchmark's sample: {key, total, source, tasks}
    # The hard tier's tasks (hard/tasks.yaml), each marked `tier: hard`; their files in hard/.
    hard: list[dict] = field(default_factory=list)
    tier: str = "standard"  # which tier's tasks `scenarios` holds (for_tier)


# Where imported suites are recorded (set by the app: <home>/imported-benches.json), and where
# benches generated for a workflow live (<home>/generated-benches).
IMPORTS: Path | None = None
GENERATED: Path | None = None


def harbor_tasks(folder: Path) -> list[Path]:
    """The Harbor task folders in `folder` (itself, or its subfolders): each needs task.toml,
    instruction.md, an environment/ folder and tests/test.sh."""

    def ok(d: Path) -> bool:
        return all(
            (d / f).exists()
            for f in ("task.toml", "instruction.md", "environment", "tests/test.sh")
        )

    if ok(folder):
        return [folder]
    return [d for d in sorted(folder.iterdir()) if d.is_dir() and ok(d)] if folder.is_dir() else []


def import_suite(
    folder: Path, name: str, disciplines: list[str], public: dict | None = None
) -> Bench:
    """Record a folder of Harbor tasks (an eval suite) as a bench. Nothing is copied or run.
    `public`: where a public benchmark's sample came from (public_bench.py downloads it)."""
    import json

    folder = folder.expanduser().resolve()
    tasks = harbor_tasks(folder)
    if not tasks:
        raise ValueError(
            f"No Harbor tasks in {folder}: each needs task.toml, instruction.md, environment/ "
            "and tests/test.sh."
        )
    bid = "imp-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    if any(b.id == bid for b in _builtin()):
        raise ValueError(f"{name!r} clashes with a built-in bench.")
    assert IMPORTS is not None, "imports need a home"
    data = json.loads(IMPORTS.read_text()) if IMPORTS.is_file() else []
    data = [d for d in data if d["id"] != bid] + [
        {
            "id": bid,
            "name": name,
            "path": str(folder),
            "disciplines": disciplines or ["development"],
            **({"public": public} if public else {}),
        }
    ]
    IMPORTS.parent.mkdir(parents=True, exist_ok=True)
    IMPORTS.write_text(json.dumps(data, indent=2))
    return bench(bid)


def _imported() -> list[Bench]:
    import json

    if IMPORTS is None or not IMPORTS.is_file():
        return []
    out = []
    for d in json.loads(IMPORTS.read_text()):
        folder = Path(d["path"])
        tasks = harbor_tasks(folder)
        if not tasks:
            continue  # moved or deleted: not offered
        pub = d.get("public")
        n = f"{len(tasks)} task{'s' if len(tasks) != 1 else ''}"
        summary = (
            f"A public benchmark from the Harbor registry: {n} sampled from its "
            f"{pub['total']}, run as they are, graded by their own tests."
            if pub
            else f"Imported from {folder}: {len(tasks)} Harbor task{'s' if len(tasks) != 1 else ''}, "
            "run as they are, graded by their own tests."
        )
        out.append(
            Bench(
                d["id"],
                d["name"],
                d["disciplines"][0],
                summary,
                [
                    {
                        "id": re.sub(r"[^a-z0-9-]+", "-", t.name.lower()).strip("-") or "task",
                        "kind": "typical",
                        "title": t.name,
                        "instruction": (t / "instruction.md").read_text(errors="replace")[:4000],
                        "folder": str(t),
                    }
                    for t in tasks
                ],
                {"id": d["id"], "name": d["name"], "steps": []},
                folder,
                d["disciplines"],
                False,
                folder,
                public=pub,
            )
        )
    return out


def benches() -> list[Bench]:
    return _builtin() + _builtin(GENERATED) + _imported()


def _builtin(where: Path | None = HERE) -> list[Bench]:
    out = []
    if where is None or not where.is_dir():
        return out
    for d in sorted(where.iterdir()):
        meta = d / "bench.yaml"
        if meta.is_file():
            m = yaml.safe_load(meta.read_text())
            hard_file = d / HARD / "tasks.yaml"
            hard = (
                [s | {"tier": "hard"} for s in yaml.safe_load(hard_file.read_text())["scenarios"]]
                if hard_file.is_file()
                else []
            )
            out.append(
                Bench(
                    m["id"],
                    m["name"],
                    m["discipline"],
                    m["summary"],
                    m["scenarios"],
                    m["workflow"],
                    d,
                    m.get("disciplines") or [m["discipline"]],
                    any(s.get("judge") for s in m["scenarios"]),
                    generated=m.get("generated"),
                    hard=hard,
                )
            )
    return out


def bench(bid: str) -> Bench:
    for b in benches():
        if b.id == bid:
            return b
    raise KeyError(f"No bench {bid!r}.")


def tiers(b: Bench) -> list[str]:
    """The tiers a run on this bench can choose (bench-difficulty: tiers): the standard tasks
    alone, and with a hard tier, those, the hard ones, or both."""
    return list(D["tiers"]) if b.hard else [D["default_tier"]]


def for_tier(b: Bench, tier: str) -> Bench:
    """The bench with `scenarios` holding one tier's tasks: standard (as it always was), hard,
    or all (standard first). Raises ValueError for a tier the bench doesn't have."""
    if tier not in tiers(b):
        raise ValueError(f"{b.name} has no {tier!r} tier: choose {' or '.join(tiers(b))}.")
    base = [s for s in b.scenarios if s.get("tier", "standard") == "standard"]
    tasks = {"standard": base, "hard": b.hard, "all": base + b.hard}[tier]
    return replace(b, scenarios=tasks, tier=tier)


def tier_of(sc: dict) -> str:
    return sc.get("tier", "standard")


def version(b: Bench) -> str:
    """Changes whenever the files, tasks or checks of the tier it runs change: baselines are only
    shared within one version. The standard tier leaves hard/ out, so adding or changing hard
    tasks keeps it (and every result on it) as it was; the hard tier, and all, hash everything,
    since their tasks run in the standard project with hard/'s files added."""
    import hashlib

    h = hashlib.sha256()  # hash_tree's recipe, so a version is unchanged where no cache sits
    files = sorted(
        (p.relative_to(b.path).as_posix(), p)
        for p in b.path.rglob("*")
        if p.is_file()
        # A check run locally leaves Python's caches; they mustn't make a new version.
        and "__pycache__" not in p.relative_to(b.path).parts
        and p.suffix != ".pyc"
        and (b.tier != "standard" or p.relative_to(b.path).parts[0] != HARD)
    )
    for rel, f in files:
        h.update(rel.encode())
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:16]


def task_dirs(b: Bench) -> dict[str, Path] | None:
    """An imported suite's own task folders, by scenario id; None for a built-in bench."""
    return {s["id"]: Path(s["folder"]) for s in b.scenarios} if b.tasks is not None else None


def check_command(sid: str) -> str:
    return f"python3 /tests/checks/{sid}/check.py"


def materialize(b: Bench, dest: Path) -> Path:
    """Write the bench as a project: its files, its workflow, its scenarios (approved) and checks.
    Done again from scratch each time, so a run always starts from the untouched bench."""
    if dest.exists():
        shutil.rmtree(dest)
    if b.tasks is not None:  # an imported suite: a project that only holds its scenarios
        dest.mkdir(parents=True)
        (dest / "README.md").write_text(f"# {b.name}\n\n{b.summary}\n")
        ensure_pg_dir(dest)
        for s in b.scenarios:
            save_scenario(
                dest,
                Scenario(
                    id=s["id"],
                    kind=s["kind"],
                    title=s["title"],
                    instruction=s["instruction"],
                    check="bash tests/test.sh",  # the task's own verifier
                    origin="bench",
                    check_status="approved",
                ),
            )
        return dest
    shutil.copytree(b.path / "project", dest)
    if b.tier != "standard" and (b.path / HARD / "project").is_dir():
        shutil.copytree(b.path / HARD / "project", dest, dirs_exist_ok=True)
    ensure_pg_dir(dest)
    if (b.path / "Dockerfile.base").is_file():  # a bench that needs more than Python (Node, say)
        shutil.copy(b.path / "Dockerfile.base", dest / PG_DIR / "Dockerfile.base")
    save_workflow(dest, Workflow(**b.workflow))
    for s in b.scenarios:
        checks = dest / PG_DIR / "checks" / s["id"]
        src = b.path / ("checks" if tier_of(s) == "standard" else f"{HARD}/checks")
        shutil.copytree(src / s["id"], checks)
        save_scenario(
            dest,
            Scenario(
                id=s["id"],
                kind=s["kind"],
                title=s["title"],
                instruction=s["instruction"],
                check=check_command(s["id"]),
                step=s.get("step"),
                origin="bench",
                check_status="approved",  # benches ship with checks that were proven both ways
                judge=s.get("judge"),
            ),
        )
    return dest


def run_check_locally(project: Path, sid: str, work: Path) -> subprocess.CompletedProcess:
    """Run one scenario's check outside the sandbox, with /app and /tests/checks mapped to local
    folders. For proving a bench, not for measuring: no agent, no isolation."""
    app = work / "app"
    checks = work / "tests" / "checks"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(project, app, ignore=shutil.ignore_patterns(PG_DIR))
    shutil.copytree(project / PG_DIR / "checks", checks)
    verifier = work / "verifier"
    for f in checks.rglob("*.py"):
        text = (
            f.read_text()
            .replace("/tests/checks", str(checks))
            .replace("/logs/verifier", str(verifier))
        )
        # Only paths that start at the sandbox's /app (inside a string), never "/app" inside them.
        f.write_text(re.sub(r"(?<=[\"'])/app(?=[/\"'])", str(app), text))
    script = checks / sid / "check.py"
    return subprocess.run(
        [sys.executable, str(script)], cwd=app, capture_output=True, text=True, timeout=120
    )


def refresh(b: Bench, dest: Path) -> Path:
    """The bench at `dest`, untouched again, keeping its run records (.proving-ground/pg.db, runs/)."""
    if not (dest / PG_DIR).is_dir():
        return materialize(b, dest)
    keep = dest.parent / f".{dest.name}.keep"
    if keep.exists():
        shutil.rmtree(keep)
    keep.mkdir(parents=True)
    for name in ("pg.db", "runs"):
        if (dest / PG_DIR / name).exists():
            shutil.move(str(dest / PG_DIR / name), keep / name)
    materialize(b, dest)
    for item in keep.iterdir():
        shutil.move(str(item), dest / PG_DIR / item.name)
    shutil.rmtree(keep)
    return dest
