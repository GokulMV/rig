"""Domain models for scenarios, workflows and treatments."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SLUG = r"^[a-z0-9][a-z0-9-]{0,63}$"


class ScenarioKind(StrEnum):
    TYPICAL = "typical"
    EDGE = "edge"
    ADVERSARIAL = "adversarial"
    FAILURE = "failure"
    OVERLOAD = "overload"
    IMAGINARY = "imaginary"


class StepType(StrEnum):
    RESEARCH = "research"
    PLAN = "plan"
    CODE = "code"
    TEST = "test"
    REVIEW = "review"
    WRITE = "write"
    DATA = "data"
    DESIGN = "design"


class TreatmentKind(StrEnum):
    SKILL = "skill"
    LOOP = "loop"
    CONFIG = "config"
    HOOK = "hook"
    MCP = "mcp"
    INSTRUCTIONS = "instructions"
    # A code change measured on two commits (beforeafter.py): no folder, the repo itself.
    BEFORE_AFTER = "before_after"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HttpFault(_Strict):
    host: str = Field(min_length=1)
    status: int = Field(ge=100, le=599)
    after: int = Field(default=0, ge=0)


class FileFault(_Strict):
    path: str = Field(min_length=1)
    remove: bool = False
    truncate: bool = False
    unreadable: bool = False
    corrupt: bool = False

    @model_validator(mode="after")
    def _one_action(self) -> FileFault:
        if sum([self.remove, self.truncate, self.unreadable, self.corrupt]) != 1:
            raise ValueError(
                "file fault needs exactly one of remove, truncate, unreadable, corrupt"
            )
        return self


class CommandFault(_Strict):
    match: str = Field(min_length=1)
    exit: int = Field(default=1, ge=1, le=255)
    stderr: str = ""


class Fault(_Strict):
    http: HttpFault | None = None
    file: FileFault | None = None
    command: CommandFault | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Fault:
        if sum(x is not None for x in (self.http, self.file, self.command)) != 1:
            raise ValueError("each fault must set exactly one of http, file, command")
        return self


class LoadInputs(_Strict):
    generate: str = Field(min_length=1)
    count: int = Field(ge=1, le=100_000)


class LoadSpec(_Strict):
    inputs: LoadInputs | None = None
    context_fill: int | None = Field(default=None, ge=1_000, le=900_000)
    timeout: int | None = Field(default=None, ge=10, le=7_200)

    @model_validator(mode="after")
    def _not_empty(self) -> LoadSpec:
        if self.inputs is None and self.context_fill is None and self.timeout is None:
            raise ValueError("load needs at least one of inputs, context_fill, timeout")
        return self


class NetworkSpec(_Strict):
    allow: list[str] = Field(default_factory=list)


class JudgeSpec(_Strict):
    """A document graded by a model after the rule checks pass (judge-documents skill)."""

    rubric: list[str] = Field(min_length=1)
    context: list[str] = Field(
        default_factory=list
    )  # repo paths the author had, shown to the judge


class Scenario(_Strict):
    id: str = Field(pattern=SLUG)
    title: str = ""
    kind: ScenarioKind = ScenarioKind.TYPICAL
    instruction: str = Field(min_length=1)
    setup: str | None = None
    check: str | None = None
    timeout: int = Field(default=600, ge=10, le=7_200)
    step: str | None = None
    faults: list[Fault] = Field(default_factory=list)
    load: LoadSpec | None = None
    network: NetworkSpec = Field(default_factory=NetworkSpec)
    check_status: Literal["unreviewed", "approved"] = "unreviewed"
    origin: Literal["generated", "user", "bench"] = "user"
    judge: JudgeSpec | None = None
    # The use case a generated scenario was written for (validity.use_case_tag; "" for none).
    written_for: str | None = None

    @model_validator(mode="after")
    def _kind_rules(self) -> Scenario:
        if self.faults and self.kind is not ScenarioKind.FAILURE:
            raise ValueError("faults are only allowed on kind: failure")
        if self.kind is ScenarioKind.FAILURE and not self.faults:
            raise ValueError("kind: failure needs at least one fault")
        if self.load is not None and self.kind is not ScenarioKind.OVERLOAD:
            raise ValueError("load is only allowed on kind: overload")
        if self.kind is ScenarioKind.OVERLOAD and self.load is None:
            raise ValueError("kind: overload needs a load block")
        return self

    @property
    def runnable(self) -> bool:
        return bool(self.check) and self.check_status == "approved"

    @property
    def effective_timeout(self) -> int:
        if self.load is not None and self.load.timeout is not None:
            return self.load.timeout
        return self.timeout


class Step(_Strict):
    name: str = Field(min_length=1)
    type: StepType
    why: str = ""


class Workflow(_Strict):
    id: str = Field(pattern=SLUG)
    name: str = Field(min_length=1)
    success: str = ""
    steps: list[Step] = Field(min_length=1)


class Treatment(_Strict):
    kind: TreatmentKind
    name: str = Field(min_length=1)
    path: str
    content_hash: str = Field(min_length=64, max_length=64)


def hash_tree(path: Path) -> str:
    """SHA-256 over relative paths and bytes of every file, in sorted order."""
    h = hashlib.sha256()
    if path.is_file():
        files = [(path.name, path)]
    else:
        files = sorted((p.relative_to(path).as_posix(), p) for p in path.rglob("*") if p.is_file())
    for rel, f in files:
        h.update(rel.encode())
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def detect_kind(path: Path) -> TreatmentKind:
    """The kind of a treatment file or folder, read from its file names (treatment-kinds skill).

    Raises FileNotFoundError for a missing path and ValueError when nothing, or more than one
    thing, identifies it."""
    from proving_ground import skills

    v = skills.load("treatment-kinds").values
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_file():
        if path.name in v["instruction_files"]:
            return TreatmentKind.INSTRUCTIONS
        raise ValueError(f"{path} is a file but not {' or '.join(v['instruction_files'])}")
    found = []
    if (path / v["skill_file"]).is_file():
        found.append(TreatmentKind.SKILL)
    if (path / v["hooks_file"]).is_file():
        found.append(TreatmentKind.HOOK)
    if (path / v["mcp_file"]).is_file():
        found.append(TreatmentKind.MCP)
    if any((path / n).is_file() for n in v["instruction_files"]):
        found.append(TreatmentKind.INSTRUCTIONS)
    if not found:
        raise ValueError(
            f"{path} has no SKILL.md, {v['hooks_file']}, {v['mcp_file']} or "
            f"{' / '.join(v['instruction_files'])}"
        )
    if len(found) > 1:
        raise ValueError(f"{path} matches more than one treatment kind: {[k.value for k in found]}")
    return found[0]


def treatment_from_path(path: Path, kind: TreatmentKind | None = None) -> Treatment:
    """A treatment from a path. With no `kind`, it is detected (see detect_kind)."""
    if not path.exists():
        raise FileNotFoundError(path)
    if kind is None:
        kind = detect_kind(path)
    elif kind is TreatmentKind.SKILL and not (path / "SKILL.md").is_file():
        raise ValueError(f"{path} has no SKILL.md")
    return Treatment(
        kind=kind, name=path.name, path=str(path.resolve()), content_hash=hash_tree(path)
    )
