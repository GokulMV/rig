"""The shape the generator must return, and the checks that accept or reject it."""

from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from proving_ground.models import (
    SLUG,
    Fault,
    LoadSpec,
    NetworkSpec,
    Scenario,
    ScenarioKind,
    TreatmentKind,
    Workflow,
)
from proving_ground.sandbox.loadgen import GENERATORS

DEFAULT_MIX = "typical=4,edge=2,adversarial=2,failure=2,overload=1,imaginary=2"
MAX_FILE_BYTES = 200_000
MAX_FILES_PER_SCENARIO = 20


class InvalidPlanError(ValueError):
    """The generator's output was rejected. Nothing was written."""

    def __init__(self, problems: list[str]):
        super().__init__("generated plan rejected:\n" + "\n".join(f"- {p}" for p in problems))
        self.problems = problems


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GeneratedFile(_Strict):
    path: str = Field(min_length=1, description="Relative path, for example check.sh")
    content: str


class GeneratedScenario(_Strict):
    id: str = Field(pattern=SLUG)
    title: str = Field(min_length=1)
    kind: ScenarioKind
    instruction: str = Field(min_length=1)
    setup: str | None = None
    check: str = Field(min_length=1)
    timeout: int = Field(default=600, ge=10, le=7_200)
    step: str | None = None
    faults: list[Fault] = Field(default_factory=list)
    load: LoadSpec | None = None
    network: NetworkSpec = Field(default_factory=NetworkSpec)
    checks: list[GeneratedFile] = Field(default_factory=list)
    fixtures: list[GeneratedFile] = Field(default_factory=list)

    def to_scenario(self) -> Scenario:
        data = self.model_dump(exclude={"checks", "fixtures"})
        return Scenario.model_validate(data | {"check_status": "unreviewed", "origin": "generated"})


class SuggestedTreatment(_Strict):
    name: str = Field(min_length=1)
    kind: TreatmentKind
    why: str = Field(min_length=1)
    step: str | None = None


class GeneratedPlan(_Strict):
    workflow: Workflow
    scenarios: list[GeneratedScenario] = Field(min_length=1)
    treatments: list[SuggestedTreatment] = Field(default_factory=list)


def parse_mix(text: str) -> dict[ScenarioKind, int]:
    """Parse `typical=4,edge=2` into counts. Kinds with 0 are dropped."""
    mix: dict[ScenarioKind, int] = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        name, _, num = part.partition("=")
        try:
            kind, count = ScenarioKind(name.strip()), int(num)
        except ValueError:
            raise ValueError(f"bad mix entry {part!r}; use kind=count") from None
        if not 0 <= count <= 20:
            raise ValueError(f"bad mix entry {part!r}; counts go from 0 to 20")
        if count:
            mix[kind] = count
    if not mix:
        raise ValueError("the mix asks for no scenarios")
    return mix


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            return _inline_refs(defs[node["$ref"].rsplit("/", 1)[-1]], defs)
        return {k: _inline_refs(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def plan_json_schema() -> dict[str, Any]:
    """JSON schema for GeneratedPlan with every $ref inlined."""
    raw = GeneratedPlan.model_json_schema()
    return _inline_refs(raw, raw.get("$defs", {}))


def _bad_path(path: str) -> bool:
    p = PurePosixPath(path)
    return p.is_absolute() or ".." in p.parts or path.startswith("~")


def parse_plan(
    data: Any, mix: dict[ScenarioKind, int], existing_ids: set[str]
) -> tuple[GeneratedPlan, list[Scenario]]:
    """Validate raw generator output as a whole. Raise InvalidPlanError on any problem."""
    try:
        plan = GeneratedPlan.model_validate(data)
    except ValidationError as e:
        raise InvalidPlanError(
            [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
        ) from e
    problems: list[str] = []
    got = Counter(s.kind for s in plan.scenarios)
    for kind in ScenarioKind:
        if got[kind] != mix.get(kind, 0):
            problems.append(f"expected {mix.get(kind, 0)} {kind.value} tasks, got {got[kind]}")
    ids = Counter(s.id for s in plan.scenarios)
    problems += [f"duplicate task id {i!r}" for i, c in ids.items() if c > 1]
    problems += [f"task id {i!r} already exists" for i in ids if i in existing_ids]
    steps = {st.name for st in plan.workflow.steps}
    scenarios: list[Scenario] = []
    for g in plan.scenarios:
        where = f"task {g.id}"
        if g.step is not None and g.step not in steps:
            problems.append(f"{where}: step {g.step!r} is not a workflow step")
        for f in g.faults:
            if f.http is not None:
                problems.append(f"{where}: http faults are not supported yet")
            if f.file is not None and f.file.unreadable:
                problems.append(f"{where}: file faults cannot use 'unreadable'")
            if f.file is not None and _bad_path(f.file.path):
                problems.append(f"{where}: fault path {f.file.path!r} must be relative")
        if g.load is not None and g.load.inputs is not None:
            if g.load.inputs.generate not in GENERATORS:
                problems.append(
                    f"{where}: unknown load generator {g.load.inputs.generate!r}; "
                    f"use one of {', '.join(sorted(GENERATORS))}"
                )
        if g.kind is ScenarioKind.IMAGINARY and not g.fixtures:
            problems.append(f"{where}: imaginary tasks need at least one fixture file")
        files = g.checks + g.fixtures
        if len(files) > MAX_FILES_PER_SCENARIO:
            problems.append(f"{where}: more than {MAX_FILES_PER_SCENARIO} files")
        for group, items in (("checks", g.checks), ("fixtures", g.fixtures)):
            seen = Counter(f.path for f in items)
            problems += [f"{where}: duplicate {group} path {p!r}" for p, c in seen.items() if c > 1]
            for f in items:
                if _bad_path(f.path):
                    problems.append(f"{where}: {group} path {f.path!r} must be relative")
                if len(f.content.encode()) > MAX_FILE_BYTES:
                    problems.append(f"{where}: {group} file {f.path!r} is over 200 KB")
        try:
            scenarios.append(g.to_scenario())
        except ValidationError as e:
            problems += [f"{where}: {err['msg']}" for err in e.errors()]
    for t in plan.treatments:
        if t.step is not None and t.step not in steps:
            problems.append(f"treatment {t.name}: step {t.step!r} is not a workflow step")
    if problems:
        raise InvalidPlanError(problems)
    return plan, scenarios
