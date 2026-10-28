from pathlib import Path

import pytest
from pydantic import ValidationError

from proving_ground.models import (
    Scenario,
    ScenarioKind,
    TreatmentKind,
    Workflow,
    hash_tree,
    treatment_from_path,
)


def base(**kw):
    data = {"id": "refund-over-limit", "instruction": "Handle ticket T-118."}
    data.update(kw)
    return data


def test_minimal_scenario_defaults():
    s = Scenario.model_validate(base())
    assert s.kind is ScenarioKind.TYPICAL
    assert s.timeout == 600
    assert s.check_status == "unreviewed"
    assert s.origin == "user"
    assert s.runnable is False


def test_runnable_needs_check_and_approval():
    assert Scenario.model_validate(base(check="pytest -q")).runnable is False
    s = Scenario.model_validate(base(check="pytest -q", check_status="approved"))
    assert s.runnable is True
    assert Scenario.model_validate(base(check_status="approved")).runnable is False


def test_id_must_be_slug():
    with pytest.raises(ValidationError):
        Scenario.model_validate(base(id="Bad ID"))


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        Scenario.model_validate(base(chek="typo"))


def test_failure_kind_requires_faults_and_faults_require_failure_kind():
    with pytest.raises(ValidationError, match="needs at least one fault"):
        Scenario.model_validate(base(kind="failure"))
    with pytest.raises(ValidationError, match="only allowed on kind: failure"):
        Scenario.model_validate(base(faults=[{"command": {"match": "npm install"}}]))
    s = Scenario.model_validate(
        base(
            kind="failure",
            faults=[
                {"http": {"host": "api.stripe.com", "status": 503, "after": 1}},
                {"file": {"path": "config/prod.yaml", "remove": True}},
                {"command": {"match": "npm install", "exit": 1}},
            ],
        )
    )
    assert len(s.faults) == 3


def test_fault_needs_exactly_one_type():
    with pytest.raises(ValidationError, match="exactly one"):
        Scenario.model_validate(
            base(
                kind="failure",
                faults=[{"http": {"host": "a", "status": 500}, "command": {"match": "x"}}],
            )
        )


def test_file_fault_needs_exactly_one_action():
    with pytest.raises(ValidationError, match="exactly one of"):
        Scenario.model_validate(
            base(kind="failure", faults=[{"file": {"path": "a", "remove": True, "truncate": True}}])
        )


def test_overload_rules_and_effective_timeout():
    with pytest.raises(ValidationError, match="needs a load block"):
        Scenario.model_validate(base(kind="overload"))
    with pytest.raises(ValidationError, match="only allowed on kind: overload"):
        Scenario.model_validate(base(load={"timeout": 300}))
    s = Scenario.model_validate(
        base(
            kind="overload",
            load={
                "inputs": {"generate": "tickets", "count": 500},
                "context_fill": 120000,
                "timeout": 300,
            },
        )
    )
    assert s.effective_timeout == 300
    assert Scenario.model_validate(base(timeout=900)).effective_timeout == 900


def test_empty_load_block_rejected():
    with pytest.raises(ValidationError, match="at least one of"):
        Scenario.model_validate(base(kind="overload", load={}))


def test_workflow_needs_steps_with_known_types():
    w = Workflow.model_validate(
        {"id": "bug-fix", "name": "Bug-fix agent", "steps": [{"name": "Reproduce", "type": "test"}]}
    )
    assert w.steps[0].type.value == "test"
    with pytest.raises(ValidationError):
        Workflow.model_validate({"id": "x", "name": "X", "steps": []})
    with pytest.raises(ValidationError):
        Workflow.model_validate(
            {"id": "x", "name": "X", "steps": [{"name": "a", "type": "deploy"}]}
        )


def test_hash_tree_is_stable_and_content_sensitive(tmp_path: Path):
    skill = tmp_path / "my-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: my-skill\n---\nDo X.\n")
    (skill / "ref").mkdir()
    (skill / "ref" / "a.md").write_text("A")
    h1 = hash_tree(skill)
    assert h1 == hash_tree(skill)
    (skill / "ref" / "a.md").write_text("B")
    assert hash_tree(skill) != h1


def test_treatment_from_path(tmp_path: Path):
    skill = tmp_path / "tdd"
    skill.mkdir()
    (skill / "SKILL.md").write_text("x")
    t = treatment_from_path(skill)
    assert t.kind is TreatmentKind.SKILL
    assert t.name == "tdd"
    assert len(t.content_hash) == 64
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no SKILL.md"):
        treatment_from_path(empty)
    with pytest.raises(FileNotFoundError):
        treatment_from_path(tmp_path / "missing")
