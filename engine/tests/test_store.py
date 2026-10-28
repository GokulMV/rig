from pathlib import Path

import pytest

from proving_ground.models import ScenarioKind, Treatment, TreatmentKind
from proving_ground.store import DuplicateTrialError, Store
from proving_ground.trial import TrialOutcome

TREAT = Treatment(kind=TreatmentKind.SKILL, name="tdd", path="/x/tdd", content_hash="a" * 64)


@pytest.fixture
def store() -> Store:
    return Store("sqlite://")


def test_for_project_creates_db_file(tmp_path: Path):
    Store.for_project(tmp_path)
    assert (tmp_path / ".proving-ground" / "pg.db").is_file()


def test_ensure_project_is_idempotent(store: Store):
    assert store.ensure_project("/repo") == store.ensure_project("/repo")
    assert store.ensure_project("/other") != store.ensure_project("/repo")


def test_sources_replace_same_kind_and_name(store: Store):
    pid = store.ensure_project("/repo")
    store.add_source(pid, "repo", "repo/", "v1", {"files": 1})
    store.add_source(pid, "repo", "repo/", "v2", {"files": 2})
    store.add_source(pid, "pdf", "spec.pdf", "text")
    rows = store.list_sources(pid)
    assert [(r.kind, r.name, r.text) for r in rows] == [
        ("repo", "repo/", "v2"),
        ("pdf", "spec.pdf", "text"),
    ]
    assert rows[0].meta == {"files": 2}


def test_experiment_lifecycle(store: Store):
    pid = store.ensure_project("/repo")
    eid = store.create_experiment(
        pid, TREAT, model="claude-sonnet-5-5", repeats=4, budget_usd=5.0, seed=7
    )
    e = store.get_experiment(eid)
    assert (e.status, e.treatment_name, e.treatment_hash, e.repeats, e.seed) == (
        "pending",
        "tdd",
        "a" * 64,
        4,
        7,
    )
    store.set_status(eid, "running")
    assert store.get_experiment(eid).status == "running"
    with pytest.raises(ValueError, match="unknown status"):
        store.set_status(eid, "exploded")


def test_trials_round_trip_and_keys(store: Store):
    pid = store.ensure_project("/repo")
    eid = store.create_experiment(pid, TREAT, "m", 1, 1.0, 0)
    t1 = TrialOutcome("a", ScenarioKind.EDGE, "with", 0, "pass", 10, 5, 0.02, 3.5, 0, "runs/1.json")
    t2 = TrialOutcome("a", ScenarioKind.EDGE, "without", 0, "fail", cost_usd=0.03)
    store.record_trial(eid, t1)
    store.record_trial(eid, t2)
    assert store.trials(eid) == [t1, t2]
    assert store.done_keys(eid) == {("a", "with", 0), ("a", "without", 0)}
    assert store.spent(eid) == pytest.approx(0.05)
    with pytest.raises(DuplicateTrialError):
        store.record_trial(eid, t1)


def test_upgrading_an_old_database_twice_at_once_is_safe(tmp_path):
    """Two requests opening the same old database both try to add the new column."""
    import threading

    from sqlalchemy import create_engine, text

    from proving_ground.store import Store

    db = tmp_path / "pg.db"
    url = f"sqlite:///{db}"
    Store(url)  # current schema
    e = create_engine(url)
    with e.begin() as c:  # make it look like a database from before reused_from existed
        c.execute(text("ALTER TABLE trials DROP COLUMN reused_from"))
    errors = []

    def open_it():
        try:
            Store(url)
        except Exception as ex:  # noqa: BLE001
            errors.append(ex)

    ts = [threading.Thread(target=open_it) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert errors == []
