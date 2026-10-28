import json

import pytest

from proving_ground.generate.schema import (
    DEFAULT_MIX,
    InvalidPlanError,
    parse_mix,
    parse_plan,
    plan_json_schema,
)
from proving_ground.models import ScenarioKind

MIX = parse_mix("typical=1,failure=1,imaginary=1")


def problems(data, existing=frozenset()):
    with pytest.raises(InvalidPlanError) as e:
        parse_plan(data, MIX, set(existing))
    return "\n".join(e.value.problems)


def test_parse_mix():
    assert parse_mix("typical=2, edge=0,failure=1") == {
        ScenarioKind.TYPICAL: 2,
        ScenarioKind.FAILURE: 1,
    }
    assert sum(parse_mix(DEFAULT_MIX).values()) == 13
    for bad in ("typical", "nope=1", "typical=-1", "typical=21", "typical=0"):
        with pytest.raises(ValueError):
            parse_mix(bad)


def test_schema_is_self_contained():
    schema = plan_json_schema()
    assert "$ref" not in json.dumps(schema)
    assert set(schema["properties"]) == {"workflow", "scenarios", "treatments"}


def test_valid_plan_becomes_unreviewed_generated_scenarios(plan_data):
    plan, scenarios = parse_plan(plan_data, MIX, set())
    assert [s.id for s in scenarios] == ["refund-basic", "config-missing", "future-scale"]
    assert {s.check_status for s in scenarios} == {"unreviewed"}
    assert {s.origin for s in scenarios} == {"generated"}
    assert plan.treatments[0].name == "tdd"


def test_wrong_counts_and_duplicate_and_existing_ids(plan_data):
    plan_data["scenarios"][1] = dict(plan_data["scenarios"][0])
    text = problems(plan_data, existing={"future-scale"})
    assert "expected 1 failure tasks, got 0" in text
    assert "expected 1 typical tasks, got 2" in text
    assert "duplicate task id 'refund-basic'" in text
    assert "task id 'future-scale' already exists" in text


def test_unsupported_faults_and_unknown_generator(plan_data):
    plan_data["scenarios"][1]["faults"] = [
        {"http": {"host": "api.example.com", "status": 503}},
        {"file": {"path": "a.txt", "unreadable": True}},
        {"file": {"path": "../etc/passwd", "remove": True}},
    ]
    plan_data["scenarios"].append(
        {
            "id": "lots",
            "title": "Lots",
            "kind": "overload",
            "instruction": "Go.",
            "check": "false",
            "load": {"inputs": {"generate": "emails", "count": 5}},
        }
    )
    with pytest.raises(InvalidPlanError) as e:
        parse_plan(plan_data, MIX | {ScenarioKind.OVERLOAD: 1}, set())
    text = "\n".join(e.value.problems)
    assert "http faults are not supported yet" in text
    assert "cannot use 'unreadable'" in text
    assert "fault path '../etc/passwd' must be relative" in text
    assert "unknown load generator 'emails'" in text


def test_paths_steps_and_fixtures(plan_data):
    plan_data["scenarios"][0]["checks"][0]["path"] = "/etc/cron.d/x"
    plan_data["scenarios"][0]["step"] = "deploy"
    plan_data["scenarios"][2]["fixtures"] = []
    plan_data["treatments"][0]["step"] = "ship"
    text = problems(plan_data)
    assert "checks path '/etc/cron.d/x' must be relative" in text
    assert "step 'deploy' is not a workflow step" in text
    assert "imaginary tasks need at least one fixture file" in text
    assert "treatment tdd: step 'ship' is not a workflow step" in text


def test_kind_rules_from_scenario_model_are_reported(plan_data):
    plan_data["scenarios"][0]["faults"] = [{"command": {"match": "npm install"}}]
    assert "faults are only allowed on kind: failure" in problems(plan_data)


def test_shape_errors_are_reported_with_location(plan_data):
    del plan_data["scenarios"][0]["check"]
    plan_data["scenarios"][1]["surprise"] = 1
    text = problems(plan_data)
    assert "scenarios.0.check: Field required" in text
    assert "scenarios.1.surprise: Extra inputs are not permitted" in text
