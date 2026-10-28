"""Load and save the YAML files a project keeps under .proving-ground/."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from proving_ground.models import Scenario, Workflow

PG_DIR = ".proving-ground"
GITIGNORE = "pg.db\nruns/\nuploads/\n"


def ensure_pg_dir(root: Path) -> Path:
    """Create .proving-ground/ with a .gitignore for local state, keeping an existing one."""
    pg = root / PG_DIR
    pg.mkdir(parents=True, exist_ok=True)
    ignore = pg / ".gitignore"
    if not ignore.exists():
        ignore.write_text(GITIGNORE)
    return pg


class FileFormatError(ValueError):
    def __init__(self, path: Path, message: str):
        super().__init__(f"{path}: {message}")
        self.path = path


def _load[M: BaseModel](path: Path, model: type[M]) -> M:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise FileFormatError(path, f"invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise FileFormatError(path, "expected a mapping at the top level")
    try:
        obj = model.model_validate(data)
    except ValidationError as e:
        raise FileFormatError(path, str(e)) from e
    if getattr(obj, "id", path.stem) != path.stem:
        raise FileFormatError(path, f"id '{obj.id}' must match the file name '{path.stem}'")
    return obj


def _load_dir[M: BaseModel](root: Path, sub: str, model: type[M]) -> list[M]:
    d = root / PG_DIR / sub
    if not d.is_dir():
        return []
    return [_load(p, model) for p in sorted(d.glob("*.yaml"))]


def _save(root: Path, sub: str, obj: BaseModel) -> Path:
    d = root / PG_DIR / sub
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{obj.id}.yaml"
    data = obj.model_dump(mode="json", exclude_defaults=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def load_scenario(path: Path) -> Scenario:
    return _load(path, Scenario)


def load_scenarios(root: Path) -> list[Scenario]:
    return _load_dir(root, "scenarios", Scenario)


def save_scenario(root: Path, s: Scenario) -> Path:
    return _save(root, "scenarios", s)


def load_workflows(root: Path) -> list[Workflow]:
    return _load_dir(root, "workflows", Workflow)


def save_workflow(root: Path, w: Workflow) -> Path:
    return _save(root, "workflows", w)
