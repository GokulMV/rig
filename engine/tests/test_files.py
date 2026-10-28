from pathlib import Path

import pytest

from proving_ground.files import (
    FileFormatError,
    load_scenarios,
    load_workflows,
    save_scenario,
    save_workflow,
)
from proving_ground.models import Scenario, Workflow


def write(root: Path, rel: str, text: str) -> Path:
    p = root / ".proving-ground" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_missing_dir_returns_empty(tmp_path: Path):
    assert load_scenarios(tmp_path) == []
    assert load_workflows(tmp_path) == []


def test_load_spec_example(tmp_path: Path):
    write(
        tmp_path,
        "scenarios/refund-over-limit.yaml",
        "id: refund-over-limit\n"
        "kind: edge\n"
        "instruction: |\n"
        "  A customer on the $99 plan asks for a $1,200 refund. Handle ticket #T-118.\n"
        "setup: scripts/seed_ticket.sh T-118 --plan=basic --amount=1200\n"
        "check: pytest -q tests/pg/test_refund_escalated.py\n"
        "timeout: 600\n",
    )
    [s] = load_scenarios(tmp_path)
    assert s.kind.value == "edge"
    assert s.check == "pytest -q tests/pg/test_refund_escalated.py"


def test_id_must_match_filename(tmp_path: Path):
    write(tmp_path, "scenarios/a.yaml", "id: b\ninstruction: x\n")
    with pytest.raises(FileFormatError, match="must match the file name"):
        load_scenarios(tmp_path)


def test_invalid_yaml_and_non_mapping(tmp_path: Path):
    p = write(tmp_path, "scenarios/a.yaml", "id: [unclosed\n")
    with pytest.raises(FileFormatError, match="invalid YAML") as e:
        load_scenarios(tmp_path)
    assert e.value.path == p
    p.write_text("- just\n- a list\n")
    with pytest.raises(FileFormatError, match="expected a mapping"):
        load_scenarios(tmp_path)


def test_validation_error_names_the_file(tmp_path: Path):
    write(tmp_path, "scenarios/a.yaml", "id: a\nkind: failure\ninstruction: x\n")
    with pytest.raises(FileFormatError, match=r"(?s)a\.yaml.*needs at least one fault"):
        load_scenarios(tmp_path)


def test_scenario_round_trip(tmp_path: Path):
    s = Scenario.model_validate(
        {
            "id": "stripe-down",
            "kind": "failure",
            "instruction": "Charge the customer.",
            "check": "pytest -q",
            "faults": [{"http": {"host": "api.stripe.com", "status": 503}}],
            "check_status": "approved",
        }
    )
    path = save_scenario(tmp_path, s)
    assert path == tmp_path / ".proving-ground" / "scenarios" / "stripe-down.yaml"
    assert load_scenarios(tmp_path) == [s]


def test_scenarios_sorted_by_filename(tmp_path: Path):
    for sid in ["b", "a", "c"]:
        save_scenario(tmp_path, Scenario(id=sid, instruction="x"))
    assert [s.id for s in load_scenarios(tmp_path)] == ["a", "b", "c"]


def test_workflow_round_trip(tmp_path: Path):
    w = Workflow.model_validate(
        {"id": "triage", "name": "Ticket triage", "steps": [{"name": "Read", "type": "research"}]}
    )
    save_workflow(tmp_path, w)
    assert load_workflows(tmp_path) == [w]
