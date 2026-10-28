"""Write an accepted plan into .proving-ground/, all or nothing."""

from __future__ import annotations

from pathlib import Path

import yaml

from proving_ground.files import PG_DIR, save_scenario, save_workflow
from proving_ground.generate.schema import GeneratedPlan
from proving_ground.models import Scenario


class PlanConflictError(ValueError):
    pass


def write_plan(root: Path, plan: GeneratedPlan, scenarios: list[Scenario]) -> list[Path]:
    """Write the workflow, scenarios, check files, fixtures and suggestions. Return written paths."""
    pg = root / PG_DIR
    wid = plan.workflow.id
    targets = [pg / "workflows" / f"{wid}.yaml", pg / "suggestions" / f"{wid}.yaml"]
    for g in plan.scenarios:
        targets += [pg / "scenarios" / f"{g.id}.yaml", pg / "checks" / g.id, pg / "fixtures" / g.id]
    taken = [t for t in targets if t.exists()]
    if taken:
        listed = ", ".join(str(t.relative_to(root)) for t in taken)
        raise PlanConflictError(f"These already exist, so nothing was written: {listed}")

    written = [save_workflow(root, plan.workflow)]
    for g, s in zip(plan.scenarios, scenarios, strict=True):
        written.append(save_scenario(root, s))
        for group, files in (("checks", g.checks), ("fixtures", g.fixtures)):
            for f in files:
                path = pg / group / g.id / f.path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f.content, encoding="utf-8")
                if group == "checks":
                    path.chmod(0o755)
                written.append(path)
    sugg = pg / "suggestions" / f"{wid}.yaml"
    sugg.parent.mkdir(parents=True, exist_ok=True)
    data = [t.model_dump(mode="json", exclude_none=True) for t in plan.treatments]
    sugg.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    written.append(sugg)
    return written
