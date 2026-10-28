from pathlib import Path

from typer.testing import CliRunner

from proving_ground.cli import app
from proving_ground.files import load_scenarios, save_scenario
from proving_ground.models import Scenario, ScenarioKind, Treatment, TreatmentKind
from proving_ground.store import Store
from proving_ground.trial import TrialOutcome

runner = CliRunner()


def test_init_creates_layout(tmp_path: Path):
    r = runner.invoke(app, ["init", str(tmp_path)])
    assert r.exit_code == 0, r.output
    pg = tmp_path / ".proving-ground"
    assert (pg / "scenarios").is_dir() and (pg / "workflows").is_dir()
    assert (pg / ".gitignore").read_text() == "pg.db\nruns/\nuploads/\n"
    assert "Initialized" in r.output


def test_intake_prints_findings(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies=["fastapi"]\n')
    (tmp_path / "main.py").write_text("x")
    notes = tmp_path / "notes.md"
    notes.write_text("design")
    r = runner.invoke(app, ["intake", str(tmp_path), "-f", str(notes)])
    assert r.exit_code == 0, r.output
    assert "Stack: FastAPI" in r.output
    assert "Sources: repo, md" in r.output


def test_scenarios_list_and_approve(tmp_path: Path):
    save_scenario(tmp_path, Scenario(id="a", instruction="x", check="pytest -q"))
    save_scenario(tmp_path, Scenario(id="b", instruction="x"))
    r = runner.invoke(app, ["scenarios", "list", "--root", str(tmp_path)])
    assert r.exit_code == 0
    assert "a  typical  unreviewed" in r.output
    r = runner.invoke(app, ["scenarios", "approve", "a", "--root", str(tmp_path)])
    assert r.exit_code == 0
    assert {s.id: s.check_status for s in load_scenarios(tmp_path)}["a"] == "approved"
    r = runner.invoke(app, ["scenarios", "approve", "b", "--root", str(tmp_path)])
    assert r.exit_code == 1
    assert "has no check" in r.output
    r = runner.invoke(app, ["scenarios", "approve", "zzz", "--root", str(tmp_path)])
    assert r.exit_code == 1
    assert "No scenario" in r.output


def test_scenarios_list_reports_bad_file(tmp_path: Path):
    d = tmp_path / ".proving-ground" / "scenarios"
    d.mkdir(parents=True)
    (d / "x.yaml").write_text("id: y\ninstruction: z\n")
    r = runner.invoke(app, ["scenarios", "list", "--root", str(tmp_path)])
    assert r.exit_code == 1
    assert "must match the file name" in r.output


def test_report(tmp_path: Path):
    store = Store.for_project(tmp_path)
    pid = store.ensure_project(str(tmp_path))
    eid = store.create_experiment(
        pid,
        Treatment(kind=TreatmentKind.SKILL, name="s", path="/s", content_hash="c" * 64),
        "m",
        1,
        1.0,
        0,
    )
    store.record_trial(eid, TrialOutcome("a", ScenarioKind.TYPICAL, "with", 0, "pass"))
    store.record_trial(eid, TrialOutcome("a", ScenarioKind.TYPICAL, "without", 0, "fail"))
    r = runner.invoke(app, ["report", str(eid), "--root", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "Experiment 1: s (skill" in r.output
    assert "Verdict: INCONCLUSIVE" in r.output
    r = runner.invoke(app, ["report", "99", "--root", str(tmp_path)])
    assert r.exit_code == 1
    assert "experiment 99 not found" in r.output
