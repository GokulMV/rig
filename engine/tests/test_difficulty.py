"""Bench difficulty: too easy from recorded trials, the baseline check, and the hard tier."""

import json
import shutil
from pathlib import Path

import pytest
from test_api_workspace import ORIGIN
from test_bench import _lab_client, _starter, _wait

from proving_ground import bench as bench_mod
from proving_ground import difficulty, skills
from proving_ground.models import ScenarioKind, Treatment, TreatmentKind
from proving_ground.scheduler import plan_trials
from proving_ground.store import Store
from proving_ground.trial import TrialOutcome

D = skills.load("bench-difficulty").values
HARD_BENCHES = ("finance", "compliance", "rag-qa", "bugfix")


def _record(root: Path, version: str, model: str, rows: list[tuple[str, str, str, int | None]]):
    """An experiment on a bench store with these (scenario, arm, outcome, reused_from) trials."""
    store = Store.for_project(root)
    pid = store.ensure_project(str(root))
    t = Treatment(kind=TreatmentKind.SKILL, name="w", path=str(root), content_hash="x" * 64)
    eid = store.create_experiment(pid, t, model, 1, 5.0, 0)
    d = root / ".proving-ground" / "runs" / str(eid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({"bench_version": version, "agent": "claude-code"}))
    for i, (sid, arm, out, src) in enumerate(rows):
        store.record_trial(
            eid, TrialOutcome(sid, ScenarioKind.TYPICAL, arm, i, out, cost_usd=0.1, reused_from=src)
        )
    return store, pid


def test_too_easy_needs_enough_clean_passes_on_every_task(tmp_path: Path):
    tasks = ["a", "b", "c"]
    sonnet, haiku = "claude-sonnet-5-5", "claude-haiku-5-5"
    store, pid = _record(
        tmp_path,
        "v1",
        sonnet,
        [("a", "without", "pass", None), ("b", "without", "pass", None)]
        + [("c", "without", "pass", None), ("a", "without", "pass", None)]
        + [("a", "with", "fail", None)]  # the "with" arm says nothing about the bench
        + [("b", "without", "errored", None)],  # not clean: not counted
    )
    got = difficulty.baseline(store, tmp_path, pid, "v1", tasks)[sonnet]
    assert (got["passed"], got["total"], got["tasks_seen"]) == (4, 4, 3)
    assert not got["too_easy"], "4 trials are fewer than min_trials"
    _record(tmp_path, "v1", sonnet, [("b", "without", "pass", None)])
    # A reused trial is a copy: counted once, where it ran.
    _record(tmp_path, "v1", sonnet, [("c", "without", "pass", 1)])
    # Another version (the bench changed) and another model are kept apart.
    _record(tmp_path, "v0", sonnet, [("c", "without", "fail", None)])
    _record(tmp_path, "v1", haiku, [(s, "without", "pass", None) for s in "abab"])
    got = difficulty.baseline(store, tmp_path, pid, "v1", tasks)
    assert got[sonnet]["total"] == D["min_trials"] == 5 and got[sonnet]["too_easy"]
    assert got[sonnet]["text"] == "Too easy for Sonnet 5.5: the agent alone passed 5 of 5"
    # Haiku: four passes on two of the three tasks is neither enough nor every task.
    assert not got[haiku]["too_easy"] and got[haiku]["tasks_seen"] == 2
    assert got[haiku]["text"] == "The agent alone (Haiku 5.5) passed 4 of 4"
    # One failure anywhere and it can show a lift.
    _record(tmp_path, "v1", sonnet, [("a", "without", "fail", None)])
    got = difficulty.baseline(store, tmp_path, pid, "v1", tasks)[sonnet]
    assert not got["too_easy"] and (got["passed"], got["total"]) == (5, 6)


def test_plan_trials_runs_only_the_arms_asked_for():
    from proving_ground.models import Scenario

    s = [Scenario(id=x, kind="typical", title=x, instruction=x, check="true") for x in "ab"]
    assert {a for _, _, a in plan_trials(s, 2, ("without",))} == {"without"}
    assert len(plan_trials(s, 2, ("without",))) == 4 and len(plan_trials(s, 2)) == 8


def test_baseline_check_runs_only_without_and_a_later_run_reuses_it(tmp_path: Path, monkeypatch):
    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)  # everything passes
    price = c.post("/api/lab/probe/price", json={"bench": "qa"}, headers=ORIGIN).json()
    # Priced like any run (trial-budget): nothing measured, the prior, once per task.
    assert price["trials"] == 2 and price["model"] == "claude-sonnet-5-5" and not price["free"]
    assert price["total_usd"] == pytest.approx(2 * price["per_trial"])
    assert price["budget"] >= price["total_usd"] and "$" in price["offer"]
    assert calls == [], "pricing ran something"
    r = c.post("/api/lab/probe", json={"bench": "qa"}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    probe = r.json()
    assert probe["probe"] and probe["trials"] == 2 and probe["budget"] == price["budget"]
    rows = _wait(c, 1)
    agent_calls = [q for q in calls if q.agent != "nop"]
    assert len(agent_calls) == 2 and not any(q.skills for q in agent_calls), "only the agent alone"
    row = rows[0]
    assert row["probe"] and row["workflow"] == D["probe"]["label"] and row["tier"] == "standard"
    assert row["status"] == "done" and row["rig"] is None and row["verdict"] is None
    assert row["probe_result"]["text"] == "The agent alone passed 2 of 2"
    # Its run page says nothing about a change: no Rig score, no verdict, no "Can't tell yet".
    page = c.get(f"/api/lab/results/qa/{row['id']}").json()
    assert page["rig"] is None and page["verdict"] is None
    # Its result feeds "too easy" (here 2 passes: fewer than min_trials, so only measured).
    qa = next(b for b in c.get("/api/lab/benches").json() if b["id"] == "qa")
    base = qa["baseline"]["standard"]["claude-sonnet-5-5"]
    assert (base["passed"], base["total"], base["too_easy"]) == (2, 2, False)
    # A real run afterwards pays for no baseline: both "without" trials come from the check.
    wf = _starter(c, "Fix a bug")
    before = len(calls)
    r = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "qa", "budget": 5, "auto": False},
        headers=ORIGIN,
    ).json()
    rows = _wait(c, 2)
    new = [q for q in calls[before:] if q.agent != "nop"]
    assert new and all(q.skills for q in new), "the run paid for its baseline again"
    run = next(x for x in rows if x["id"] == r["id"])
    assert run["reused"] == 2 and run["saved_usd"] > 0 and not run["probe"]
    ev = c.get(f"/api/lab/runs/qa/{r['id']}/events").text
    assert '"type": "reused"' in ev and f'"from": [{probe["id"]}]' in ev


def test_baseline_check_is_shown_running_and_can_be_stopped(tmp_path: Path, monkeypatch):
    import threading

    gate = threading.Event()

    def slow(req):
        gate.wait(5)
        return 1.0

    c, calls = _lab_client(tmp_path, monkeypatch, slow)
    probe = c.post("/api/lab/probe", json={"bench": "qa"}, headers=ORIGIN).json()
    for _ in range(200):
        going = c.get("/api/runs/active").json()["running"]
        if going:
            break
    assert going["probe"] and going["treatment"] == D["probe"]["label"]
    assert going["bench"] == "qa" and going["id"] == probe["id"]
    # One run at a time: a measure can't start next to it.
    busy = c.post(
        "/api/lab/run",
        json={"workflow": _starter(c, "Fix a bug"), "bench": "qa", "budget": 5},
        headers=ORIGIN,
    )
    assert busy.status_code == 409
    assert c.post(f"/api/lab/runs/qa/{probe['id']}/stop", headers=ORIGIN).status_code == 200
    gate.set()
    rows = _wait(c, 1)
    assert rows[0]["status"] == "stopped" and rows[0]["probe"]


def test_baseline_check_refuses_a_budget_below_one_trial(tmp_path: Path, monkeypatch):
    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    r = c.post("/api/lab/probe", json={"bench": "qa", "budget": 0.01}, headers=ORIGIN)
    assert r.status_code == 422 and "baseline trial" in r.json()["detail"]
    assert c.get("/api/lab/results").json() == [] and calls == []


def test_too_easy_is_listed_with_the_warning(tmp_path: Path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    wf = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "bugfix", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    _wait(c, 1)
    bugfix = next(b for b in c.get("/api/lab/benches").json() if b["id"] == "bugfix")
    got = bugfix["baseline"]["standard"]["claude-sonnet-5-5"]
    assert (
        got["too_easy"] and got["text"] == "Too easy for Sonnet 5.5: the agent alone passed 5 of 5"
    )
    assert got["warn"] == f"{D['warn']} {D['warn_hard']}"
    assert "hard" not in bugfix["baseline"]  # nothing measured on the hard tier yet


@pytest.mark.parametrize("bid", HARD_BENCHES)
def test_hard_tier_is_its_own_version_and_standard_is_unchanged(bid: str):
    b = bench_mod.bench(bid)
    assert b.hard and all(s["tier"] == "hard" and s["id"].startswith("hard-") for s in b.hard)
    assert bench_mod.tiers(b) == ["standard", "hard", "all"]
    std, hard, both = (bench_mod.for_tier(b, t) for t in ("standard", "hard", "all"))
    assert std.scenarios == b.scenarios and hard.scenarios == b.hard
    assert [s["id"] for s in both.scenarios] == [s["id"] for s in b.scenarios + b.hard]
    from proving_ground.models import hash_tree

    # The standard tier hashes as the whole bench did before hard/ existed.
    without_hard = {
        p.relative_to(b.path).as_posix()
        for p in b.path.rglob("*")
        if p.is_file() and p.relative_to(b.path).parts[0] != "hard"
    }
    assert bench_mod.version(std) != bench_mod.version(hard) == hash_tree(b.path)[:16]
    assert without_hard and bench_mod.version(both) == bench_mod.version(hard)
    # hard/ only adds files: nothing in the standard project is replaced.
    added = {
        p.relative_to(b.path / "hard" / "project")
        for p in (b.path / "hard" / "project").rglob("*")
        if p.is_file()
    }
    assert added and not any((b.path / "project" / a).exists() for a in added)


def test_versions_change_only_for_the_tier_that_changed(tmp_path: Path):
    src = bench_mod.bench("finance").path
    where = tmp_path / "benches"
    shutil.copytree(src, where / "finance", ignore=shutil.ignore_patterns("__pycache__"))

    def versions():
        b = next(x for x in bench_mod._builtin(where) if x.id == "finance")
        return {t: bench_mod.version(bench_mod.for_tier(b, t)) for t in bench_mod.tiers(b)}

    first = versions()
    assert first["standard"] == bench_mod.version(bench_mod.bench("finance"))
    task = next((where / "finance" / "hard" / "checks").iterdir()) / "check.py"
    task.write_text(task.read_text() + "\n# edited\n")
    second = versions()
    assert second["standard"] == first["standard"] and second["hard"] != first["hard"]
    policy = where / "finance" / "project" / "POLICY.md"
    policy.write_text(policy.read_text() + "\nedited\n")
    third = versions()  # the hard tier runs in the standard project: it changes too
    assert third["standard"] != second["standard"] and third["hard"] != second["hard"]


def test_a_run_picks_its_tier(tmp_path: Path, monkeypatch):
    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    wf = _starter(c, "Fix a bug")
    benches = {b["id"]: b for b in c.get("/api/lab/benches").json()}
    fin = benches["finance"]
    assert [t["id"] for t in fin["tiers"]] == ["standard", "hard", "all"]
    assert fin["hard"] and all(s["tier"] == "hard" for s in fin["hard"])
    assert all(s["tier"] == "standard" for s in fin["scenarios"])
    assert [t["id"] for t in benches["qa"]["tiers"]] == ["standard"]  # no hard tasks
    bad = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "qa", "tier": "hard", "budget": 5},
        headers=ORIGIN,
    )
    assert bad.status_code == 422 and "no 'hard' tier" in bad.json()["detail"]
    r = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "finance", "tier": "hard", "budget": 20, "auto": False},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["tier"] == "hard" and set(got["scenarios"]) == {s["id"] for s in fin["hard"]}
    rows = _wait(c, 1)
    assert rows[0]["tier"] == "hard"
    hard = bench_mod.for_tier(bench_mod.bench("finance"), "hard")
    meta = json.loads(
        (
            tmp_path
            / "home"
            / "benches"
            / "finance"
            / ".proving-ground"
            / "runs"
            / str(got["id"])
            / "meta.json"
        ).read_text()
    )
    assert meta["tier"] == "hard" and meta["bench_version"] == bench_mod.version(hard)
    # The hard run's baseline doesn't count for the standard tier, nor the other way round.
    fin = next(b for b in c.get("/api/lab/benches").json() if b["id"] == "finance")
    # (The hard tier and all share a version, so it also counts toward all's hard tasks.)
    assert "standard" not in fin["baseline"] and "hard" in fin["baseline"]
    assert not fin["baseline"]["all"]["claude-sonnet-5-5"]["too_easy"]  # standard tasks unseen
    # A standard run (the default) runs the standard tasks, and reuses nothing from the hard run.
    r2 = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "finance", "budget": 20, "auto": False},
        headers=ORIGIN,
    ).json()
    rows = _wait(c, 2)
    assert (
        set(r2["scenarios"]) == {s["id"] for s in bench_mod.bench("finance").scenarios}
        and r2["tier"] == "standard"
    )
    assert next(x for x in rows if x["id"] == r2["id"])["reused"] == 0


def test_hard_tier_is_priced_from_hard_runs_only(tmp_path: Path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    wf = _starter(c, "Fix a bug")
    # A standard run's trials ($0.02 each) say what a standard trial costs, not a hard one.
    c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "finance", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    _wait(c, 1)
    std = c.post("/api/lab/probe/price", json={"bench": "finance"}, headers=ORIGIN).json()
    hard = c.post(
        "/api/lab/probe/price", json={"bench": "finance", "tier": "hard"}, headers=ORIGIN
    ).json()
    assert std["source"].startswith("measured on") and std["per_trial"] == pytest.approx(0.025)
    assert hard["source"] == "a first guess: nothing measured yet"
    assert hard["trials"] == len(bench_mod.bench("finance").hard)
    est = c.post(
        "/api/runs/estimate",
        json={"pairs": 2, "bench": "finance", "workflow": wf, "tier": "hard"},
        headers=ORIGIN,
    ).json()
    assert est["source"]["without"] == "a first guess: nothing measured yet"


def test_python_caches_left_by_a_local_check_dont_change_a_bench_version(tmp_path):
    import shutil

    from proving_ground.bench import bench, for_tier, version

    src = bench("finance")
    copy = tmp_path / "finance"
    shutil.copytree(src.path, copy)
    b = type(src)(**{**src.__dict__, "path": copy}) if hasattr(src, "__dict__") else src
    before = {t: version(for_tier(b, t)) for t in ("standard", "hard")}
    cache = copy / "hard" / "checks" / "__pycache__"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "rules.cpython-312.pyc").write_bytes(b"\0junk")
    assert {t: version(for_tier(b, t)) for t in ("standard", "hard")} == before
    (copy / "hard" / "checks" / "note.txt").write_text("a real change")  # the copy is what's hashed
    assert version(for_tier(b, "hard")) != before["hard"]
    assert version(for_tier(b, "standard")) == before["standard"]
