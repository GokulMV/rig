from pathlib import Path
from types import SimpleNamespace

import pytest

from proving_ground.files import save_scenario
from proving_ground.models import Scenario, ScenarioKind
from proving_ground.service import ServiceError, execute, prepare_experiment
from proving_ground.stats import Verdict


def fake_result(reward):
    return SimpleNamespace(
        exception_info=None,
        verifier_result=SimpleNamespace(rewards={"reward": reward}),
        agent_result=SimpleNamespace(n_input_tokens=10, n_output_tokens=5, cost_usd=0.5),
        started_at=None,
        finished_at=None,
        trial_name="t",
    )


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "proving_ground.runner.harbor.harbor_executor",
        lambda req: fake_result(0.0 if req.agent == "nop" else (1.0 if req.skills else 0.0)),
    )
    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.py").write_text("x")
    for sid, kind in (("a", "typical"), ("b", "edge")):
        save_scenario(
            root,
            Scenario(
                id=sid, kind=kind, instruction="Fix it.", check="true", check_status="approved"
            ),
        )
    sk = tmp_path / "skills" / "tdd"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: tdd\n---\nWrite the test first.\n")
    return root, sk


def test_prepare_then_execute(setup):
    root, sk = setup
    p = prepare_experiment(root, sk, budget=100, n=4)
    assert (p.eid, p.repeats, [s.id for s in p.scenarios]) == (1, 2, ["a", "b"])
    assert (root / ".proving-ground" / "runs" / "1" / "tasks" / "a" / "task.toml").is_file()
    events = []
    summary = execute(p, events.append)
    assert summary.verdict is Verdict.HELPS
    assert events[-1]["type"] == "done"
    assert sum(e["type"] == "trial" for e in events) == 8


def test_filters_and_resume_checks(setup):
    root, sk = setup
    p = prepare_experiment(root, sk, budget=100, n=2, kinds=[ScenarioKind.EDGE])
    assert [s.id for s in p.scenarios] == ["b"]
    with pytest.raises(ServiceError, match="No tasks match"):
        prepare_experiment(root, sk, budget=1, scenario_ids=["zzz"])
    (sk / "SKILL.md").write_text("changed")
    with pytest.raises(ServiceError, match="tdd changed since experiment 1"):
        prepare_experiment(root, sk, budget=1, resume=1)
    with pytest.raises(ServiceError, match="9"):
        prepare_experiment(root, sk, budget=1, resume=9)
    with pytest.raises(ServiceError, match="SKILL.md"):
        prepare_experiment(root, root, budget=1)
