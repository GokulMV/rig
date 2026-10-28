"""Every bench check fails on the untouched bench and passes on a correct solution."""

import re
import subprocess
import sys
from pathlib import Path

import pytest
from bench_solutions.solutions import SOLUTIONS

from proving_ground.bench import (
    bench,
    benches,
    for_tier,
    materialize,
    run_check_locally,
    tier_of,
)
from proving_ground.files import load_scenarios

# Each task in its own tier; a bench with a hard tier also proves its standard tasks in "all",
# where hard/'s files sit next to them.
CASES = [(b.id, s["id"], "standard") for b in benches() for s in b.scenarios] + [
    (b.id, s["id"], "hard") for b in benches() for s in b.hard
]
ALL = [(b.id, s["id"], "all") for b in benches() if b.hard for s in b.scenarios]
# Checks that count items: they print `RIG_ITEMS <right>/<total>` (partial credit), every hard
# task among them. The rest print nothing.
ITEM_BENCHES = {"finance", "compliance", "rag-qa", "support", "qa", "feature"}
ITEM_CASES = {(b, s) for b, s, t in CASES if b in ITEM_BENCHES or t == "hard"} | {
    ("data", "clean"),
    ("data", "monthly"),
}
ITEMS = re.compile(r"^RIG_ITEMS (\d+)/(\d+)$", re.M)


def test_every_scenario_has_a_reference_solution():
    assert {(b, s) for b, s, _ in CASES} == set(SOLUTIONS)
    assert {b.discipline for b in benches()} >= {"development", "data", "qa"}


def _solve(work: Path, bid: str, sid: str) -> subprocess.CompletedProcess:
    fix = SOLUTIONS[(bid, sid)]
    if callable(fix):
        fix(work / "app")
    else:
        for rel, text in fix.items():
            (work / "app" / rel).write_text(text)
    # Re-run against the solved app without copying the project over it again.
    return subprocess.run(
        [sys.executable, str(work / "tests" / "checks" / sid / "check.py")],
        cwd=work / "app",
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(("bid", "sid", "tier"), CASES + ALL)
def test_check_fails_untouched_and_passes_when_solved(
    tmp_path: Path, bid: str, sid: str, tier: str
):
    b = for_tier(bench(bid), tier)
    project = materialize(b, tmp_path / "project")
    before = run_check_locally(project, sid, tmp_path / "before")
    assert before.returncode != 0, f"{bid}/{sid} passes on the untouched bench"

    work = tmp_path / "after"
    run_check_locally(project, sid, work)  # lays out app/ and tests/checks
    r = _solve(work, bid, sid)
    assert r.returncode == 0, f"{bid}/{sid} fails on a correct solution:\n{r.stderr[-1500:]}"
    from proving_ground.runner.harbor import items_in

    sc = next(s for s in b.scenarios if s["id"] == sid)
    got, untouched = items_in(r.stdout + r.stderr), items_in(before.stdout + before.stderr)
    if (bid, sid) in ITEM_CASES:
        # A correct answer scores every item; the untouched bench scores fewer.
        assert got is not None and got[0] == got[1], f"{bid}/{sid}: {got} on a correct solution"
        assert untouched is not None and untouched[0] < untouched[1] == got[1], (
            f"{bid}/{sid}: {untouched} on the untouched bench"
        )
    else:
        assert got is None and untouched is None, f"{bid}/{sid} counts items but isn't listed"
    if tier_of(sc) == "hard":
        # Exactly one line on a hard task (bench-difficulty).
        assert len(ITEMS.findall(r.stdout)) == 1, f"{bid}/{sid}: {r.stdout[-500:]}"
    # A judged scenario hands its document to the judge.
    if sc.get("judge"):
        assert (work / "verifier" / "artifact.md").read_text().strip(), (
            f"{bid}/{sid} didn't hand over a document"
        )


def test_materialised_bench_is_a_runnable_project(tmp_path: Path):
    p = materialize(bench("bugfix"), tmp_path / "b")
    items = load_scenarios(p)
    assert {s.id for s in items} == {
        "rounding",
        "bulk-threshold",
        "coupon-case",
        "negative-qty",
        "delete-the-test",
    }
    assert all(
        s.check_status == "approved" and s.check.startswith("python3 /tests/checks/") for s in items
    )


def test_lab_runs_a_workflow_on_a_bench_and_reports_it(tmp_path: Path, monkeypatch):
    """The whole path with the sandbox faked: compile the workflow, refresh the bench, run
    with and without, record trials, and list the result."""
    import time
    from types import SimpleNamespace

    from fastapi.testclient import TestClient
    from test_api_workspace import BASE, ORIGIN
    from test_catalog import FakeGitHub

    import proving_ground.runner.harbor as harbor
    from proving_ground.agents import Credentials
    from proving_ground.api.app import create_app
    from proving_ground.workspace import Workspace

    seen = []

    def fake(req):
        seen.append(req)
        reward = 0.0 if req.agent == "nop" else (1.0 if req.skills else 0.0)
        return SimpleNamespace(
            exception_info=None,
            verifier_result=SimpleNamespace(rewards={"reward": reward}),
            agent_result=SimpleNamespace(n_input_tokens=1000, n_output_tokens=100, cost_usd=0.01),
            started_at=None,
            finished_at=None,
            trial_name="fake",
        )

    monkeypatch.setattr(harbor, "harbor_executor", fake)
    c = TestClient(
        create_app(
            workspace=Workspace(tmp_path / "ws.json"),
            credentials=Credentials(env={"ANTHROPIC_API_KEY": "k"}, home=tmp_path / "h"),
            github=FakeGitHub(),
            home=tmp_path / "home",
            user_skills_dir=tmp_path / "none",
            web_dist=tmp_path / "nodist",
            host_login=lambda: None,
        ),
        base_url=BASE,
    )
    assert {b["id"] for b in c.get("/api/lab/benches").json()} >= {
        "bugfix",
        "qa",
        "product",
        "support",
        "security",
    }
    wf = next(
        w
        for d in c.get("/api/lab").json()["disciplines"]
        if d["id"] == "development"
        for w in d["workflows"]
        if w["name"] == "Fix a bug"
    )
    r = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "bugfix", "size": "pilot", "budget": 5},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["trials"] == 10 and run["model"] == "claude-sonnet-5-5"
    for _ in range(200):
        rows = c.get("/api/lab/results").json()
        if rows and rows[0]["status"] not in ("running", "pending"):
            break
        time.sleep(0.05)
    row = rows[0]
    assert row["bench"] == "bugfix" and row["workflow"] == "Fix a bug" and row["verdict"] == "helps"
    assert (
        row["diff"] == 1.0
        and row["pass_with"] == 1.0
        and row["pass_without"] == 0.0
        and row["spent_usd"] > 0
    )
    # The with-arm got the compiled workflow; its protocol hands steps to subagents on their models.
    skill = Path(next(s for q in seen for s in q.skills))
    text = (skill / "SKILL.md").read_text()
    assert "Agent tool" in text and "model `opus`" in text and "model `haiku`" in text
    # A second run starts from the untouched bench again but keeps the first result.
    r2 = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "bugfix", "size": "pilot", "budget": 5},
        headers=ORIGIN,
    )
    assert r2.status_code == 200
    for _ in range(200):
        if len(c.get("/api/lab/results").json()) == 2:
            break
        time.sleep(0.05)
    assert len(c.get("/api/lab/results").json()) == 2
    # A budget that can't pay for one trial is refused before anything is created or checked.
    poor = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "bugfix", "size": "pilot", "budget": 0.001},
        headers=ORIGIN,
    )
    assert poor.status_code == 422 and "can't pay for one trial" in poor.json()["detail"]
    assert "$0.00 budget" not in poor.json()["detail"] and "measured on" in poor.json()["detail"]
    assert len(c.get("/api/lab/results").json()) == 2
    ev = c.get(f"/api/lab/runs/bugfix/{run['id']}/events")
    assert ev.status_code == 200 and "finished" in ev.text
    # Taking the sizing's offer: a full run grows to the pairs it names, as priced, and starts so.
    # (The fake's trials cost $0.01: $0.50 pays for 20 pairs, the sizing's $1.00 for all 31.)
    ask = {"pairs": 5, "bench": "bugfix", "workflow": wf, "size": "full", "tasks": 5, "budget": 0.5}
    low = c.post("/api/runs/estimate", json=ask, headers=ORIGIN).json()
    usd = low["sizing"]["usd"]
    assert low["pairs"] == 20 and low["sizing"]["pairs"] == 31 and usd > 0.5
    assert low["full"]["state"] == "detects" and low["sizing"]["enough_planned"]
    sized = c.post("/api/runs/estimate", json=ask | {"budget": usd}, headers=ORIGIN).json()
    assert sized["pairs"] == 35 and sized["pairs_in_budget"] >= 31  # 7 whole repeats of 5 tasks
    assert sized["full"]["state"] == "conclusive" and sized["sizing"]["enough_budget"]
    r3 = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "bugfix", "size": "full", "budget": usd},
        headers=ORIGIN,
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["trials"] == 2 * sized["pairs"] == 70
    for _ in range(600):
        if len(c.get("/api/lab/results").json()) == 3 and all(
            x["status"] not in ("running", "pending") for x in c.get("/api/lab/results").json()
        ):
            break
        time.sleep(0.05)


def _lab_client(tmp_path, monkeypatch, reward, env=None, log=None):
    """`log(req)`: what the trial's check printed (its verifier/check.log), if anything."""
    import itertools
    from types import SimpleNamespace

    from fastapi.testclient import TestClient
    from test_api_workspace import BASE
    from test_catalog import FakeGitHub

    import proving_ground.runner.harbor as harbor
    from proving_ground.agents import Credentials
    from proving_ground.api.app import create_app
    from proving_ground.workspace import Workspace

    calls = []
    names = itertools.count()

    def fake(req):
        calls.append(req)
        r = 0.0 if req.agent == "nop" else reward(req)
        name = "fake"
        text = log(req) if log is not None and req.agent != "nop" else None
        if text is not None:
            name = f"fake-{next(names)}"
            (req.trials_dir / name / "verifier").mkdir(parents=True, exist_ok=True)
            (req.trials_dir / name / "verifier" / "check.log").write_text(text)
        return SimpleNamespace(
            exception_info=None,
            verifier_result=SimpleNamespace(rewards={"reward": r}),
            agent_result=SimpleNamespace(n_input_tokens=1000, n_output_tokens=100, cost_usd=0.02),
            started_at=None,
            finished_at=None,
            trial_name=name,
        )

    monkeypatch.setattr(harbor, "harbor_executor", fake)
    c = TestClient(
        create_app(
            workspace=Workspace(tmp_path / "ws.json"),
            credentials=Credentials(env=env or {"ANTHROPIC_API_KEY": "k"}, home=tmp_path / "h"),
            github=FakeGitHub(),
            home=tmp_path / "home",
            user_skills_dir=tmp_path / "none",
            web_dist=tmp_path / "nodist",
            host_login=lambda: None,
        ),
        base_url=BASE,
    )
    return c, calls


def _wait(c, n):
    import time

    for _ in range(400):
        rows = c.get("/api/lab/results").json()
        if len(rows) >= n and all(r["status"] not in ("running", "pending") for r in rows):
            return rows
        time.sleep(0.05)
    raise AssertionError("runs did not finish")


def _starter(c, name):
    return next(
        w
        for d in c.get("/api/lab").json()["disciplines"]
        for w in d["workflows"]
        if w["name"] == name
    )


def test_shared_baseline_reuses_without_trials(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    a = _starter(c, "Fix a bug")
    b = _starter(c, "Refactor safely")
    assert (
        c.post(
            "/api/lab/run",
            json={"workflow": a, "bench": "qa", "budget": 5, "auto": False},
            headers=ORIGIN,
        ).status_code
        == 200
    )
    _wait(c, 1)
    before = len([q for q in calls if q.agent != "nop" and not q.skills])
    r = c.post(
        "/api/lab/run",
        json={"workflow": b, "bench": "qa", "budget": 5, "auto": False},
        headers=ORIGIN,
    ).json()
    rows = _wait(c, 2)
    after = len([q for q in calls if q.agent != "nop" and not q.skills])
    assert after == before, "the second workflow paid for its baseline again"
    second = next(x for x in rows if x["id"] == r["id"])
    assert (
        second["reused"] == 2
        and second["saved_usd"] > 0
        and second["verdict"] in ("helps", "inconclusive")
    )
    ev = c.get(f"/api/lab/runs/qa/{r['id']}/events").text
    assert '"type": "reused"' in ev


def test_auto_extend_adds_pairs_until_decided_or_limits(tmp_path: Path, monkeypatch):
    import itertools

    from test_api_workspace import ORIGIN

    flip = itertools.cycle([1.0, 0.0])  # without: alternates; with: always passes
    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else next(flip))
    a = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "qa", "budget": 50, "auto": True},
        headers=ORIGIN,
    ).json()
    rows = _wait(c, 1)
    ev = c.get(f"/api/lab/runs/qa/{r['id']}/events").text
    assert '"type": "extended"' in ev and '"type": "settled"' in ev
    assert rows[0]["n_pairs"] > 2  # more than the pilot's 2 pairs


def test_auto_extend_says_decided_when_the_last_look_decides_it(tmp_path: Path, monkeypatch):
    import json

    from test_api_workspace import ORIGIN

    from proving_ground import skills

    # One look allowed. With always passes, without never does: the pilot's 2 pairs aren't
    # decided at 99%, the 4 after the look are, and the reason says so, not the cap.
    monkeypatch.setitem(skills.value("judge-experiment", "auto_extend"), "max_looks", 1)
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    a = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "qa", "budget": 50, "auto": True},
        headers=ORIGIN,
    ).json()
    _wait(c, 1)
    text = c.get(f"/api/lab/runs/qa/{r['id']}/events").text
    ev = [json.loads(x[6:]) for x in text.splitlines() if x.startswith("data: ")]
    assert [e["pairs"] for e in ev if e["type"] == "extended"] == [2]
    settled = [e for e in ev if e["type"] == "settled"]
    assert settled == [
        {
            "type": "settled",
            "reason": "decided at the stricter interval (helps)",
            "pairs": 4,
            "looks": 1,
        }
    ]


def test_adherence_reads_the_session_logs(tmp_path: Path):
    import json as _json

    from proving_ground.adherence import check, summarize

    wf = {
        "id": "w1",
        "steps": [
            {"id": "plan", "name": "Plan the change", "model": "claude-opus-5-5"},
            {"id": "implement", "name": "Implement", "model": "claude-sonnet-5-5"},
            {"id": "run-tests", "name": "Run the tests", "model": "claude-haiku-5-5"},
        ],
        "loop": ["run-tests", "implement", 2],
    }

    def trial(name, calls):
        d = tmp_path / name / "agent" / "sessions" / "projects" / "-app"
        d.mkdir(parents=True)
        lines = [_json.dumps({"type": "user", "message": {"content": "do it"}})]
        for desc, model in calls:
            block = {
                "type": "tool_use",
                "name": "Agent",
                "input": {
                    "description": desc,
                    "prompt": "brief",
                    "subagent_type": "general-purpose",
                },
            }
            if model:
                block["input"]["model"] = model
            lines.append(
                _json.dumps(
                    {
                        "type": "assistant",
                        "message": {"content": [{"type": "text", "text": "ok"}, block]},
                    }
                )
            )
        (d / "0b5c3a1e-0000-4000-8000-000000000000.jsonl").write_text("\n".join(lines))
        return tmp_path / name

    good = check(
        wf,
        trial(
            "good", [("Plan the change", "opus"), ("Implement", None), ("Run the tests", "haiku")]
        ),
        "claude-sonnet-5-5",
    )
    assert good.followed and good.models_ok == 3 and good.opened is False
    # Opening the workflow skill is seen too: a "with" trial that never opened it is reported.
    log = next((tmp_path / "good").rglob("*.jsonl"))
    opened = {"type": "tool_use", "name": "Skill", "input": {"skill": f"workflow-{wf['id']}"}}
    log.write_text(
        _json.dumps({"type": "assistant", "message": {"content": [opened]}})
        + "\n"
        + log.read_text()
    )
    good = check(wf, tmp_path / "good", "claude-sonnet-5-5")
    assert good.opened is True and good.followed
    skipped = check(wf, trial("skipped", [("Implement", "sonnet")]), "claude-sonnet-5-5")
    assert not skipped.followed and skipped.missing == ["Plan the change", "Run the tests"]
    wrong = check(
        wf,
        trial(
            "wrong",
            [("Plan the change", "sonnet"), ("Implement", "sonnet"), ("Run the tests", "haiku")],
        ),
        "claude-sonnet-5-5",
    )
    assert wrong.wrong_model == ["Plan the change: sonnet instead of opus"]
    looped = check(
        wf,
        trial(
            "looped",
            [("Plan the change", "opus")]
            + [("Implement", "sonnet"), ("Run the tests", "haiku")] * 5,
        ),
        "claude-sonnet-5-5",
    )
    assert not looped.loop_ok
    none = check(wf, tmp_path / "nologs", "claude-sonnet-5-5")
    assert not none.found
    s = summarize([good, skipped, wrong, looped, none])
    assert s == {
        "trials": 5,
        "read": 4,
        "steps": 3,
        "followed": 1,
        "steps_run": round((1 + 1 / 3 + 1 + 1) / 4, 2),
        "models_ok": round((1 + 1 / 3 + 2 / 3 + 1) / 4, 2),
        "loop_broken": 1,
        "not_applied": 0,  # every trial with logs ran at least one step
        "not_opened": 3,
        "missing": ["Plan the change", "Run the tests"],
        # In how many of the 4 trials read each step was skipped: the union above is not a count.
        "skipped": [
            {"step": "Plan the change", "trials": 1},
            {"step": "Run the tests", "trials": 1},
        ],
        "wrong_model": ["Plan the change: sonnet instead of opus"],
    }


def test_results_report_adherence(tmp_path: Path, monkeypatch):
    """The board says how many trials followed the workflow, from logs the agent left behind."""
    import json as _json
    import uuid

    from test_api_workspace import ORIGIN

    seq = iter(range(10_000))

    def reward(req):
        return 1.0 if req.skills else 0.0

    c, calls = _lab_client(tmp_path, monkeypatch, reward)
    import proving_ground.runner.harbor as harbor

    inner = harbor.harbor_executor

    def with_logs(req):
        r = inner(req)
        r.trial_name = f"t{next(seq)}"
        if req.skills:
            wf = _json.loads((Path(req.skills[0]) / "workflow.json").read_text())
            d = req.trials_dir / r.trial_name / "agent" / "sessions" / "projects" / "-app"
            d.mkdir(parents=True, exist_ok=True)
            lines = [
                _json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Agent",
                                    "input": {
                                        "description": st["name"],
                                        "model": st["model"].split("-")[1],
                                    },
                                }
                            ]
                        },
                    }
                )
                for st in wf["steps"]
            ]
            (d / f"{uuid.uuid4()}.jsonl").write_text("\n".join(lines))
        return r

    monkeypatch.setattr(harbor, "harbor_executor", with_logs)
    a = _starter(c, "Fix a bug")
    assert (
        c.post(
            "/api/lab/run",
            json={"workflow": a, "bench": "qa", "budget": 5, "auto": False},
            headers=ORIGIN,
        ).status_code
        == 200
    )
    row = _wait(c, 1)[0]
    assert row["adherence"]["read"] == 2 and row["adherence"]["followed"] == 2


def test_judged_bench_grades_documents_after_the_rules(tmp_path: Path, monkeypatch):
    """Rule checks pass in the sandbox; the judge here decides; grades are kept with the trial."""
    import json as _json

    from test_api_workspace import ORIGIN

    import proving_ground.api.app as api_app
    from proving_ground.generate.client import ToolCall

    class FakeJudge:
        def __init__(self, *_a, **_k):
            pass

        def call(self, prompt, tool, model, max_tokens):
            assert tool["name"] == "emit_grades" and model == "claude-opus-5-5"
            text = prompt.content[0]["text"]
            n = text.count("\n", text.index("<rubric>"), text.index("</rubric>")) - 1
            good = "kind and clear" in text
            return ToolCall(
                {"scores": [{"criterion": "c", "score": 5 if good else 2, "evidence": "e"}] * n},
                "tool_use",
                1,
                1,
            )

    monkeypatch.setattr(api_app, "AnthropicClient", FakeJudge)
    seq = iter(range(10_000))
    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    import proving_ground.runner.harbor as harbor

    inner = harbor.harbor_executor

    def with_artifact(req):
        r = inner(req)
        r.trial_name = f"t{next(seq)}"
        v = req.trials_dir / r.trial_name / "verifier"
        v.mkdir(parents=True, exist_ok=True)
        (v / "artifact.md").write_text("A kind and clear reply." if req.skills else "Denied.")
        return r

    monkeypatch.setattr(harbor, "harbor_executor", with_artifact)
    a = _starter(c, "Handle a ticket")
    r = c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "support", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    row = _wait(c, 1)[0]
    assert (
        row["pass_with"] == 1.0
        and row["pass_without"] == 0.0
        and row["verdict"] in ("helps", "inconclusive")
    )
    grades = list((tmp_path / "home" / "benches" / "support").rglob("grade.json"))
    assert grades and _json.loads(grades[0].read_text())["scores"]


def test_calibration_needs_good_to_beat_bad(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    import proving_ground.api.app as api_app
    from proving_ground.generate.client import ToolCall

    class FakeJudge:
        def __init__(self, *_a, **_k):
            pass

        def call(self, prompt, tool, model, max_tokens):
            text = prompt.content[0]["text"]
            doc = text[text.index("<document>") : text.index("</document>")]
            n = text.count("\n", text.index("<rubric>"), text.index("</rubric>")) - 1
            score = (
                2
                if ("TBD" in doc or "None expected" in doc or "chatbot that answers" in doc)
                else 5
            )
            return ToolCall(
                {"scores": [{"criterion": "c", "score": score, "evidence": "e"}] * n},
                "tool_use",
                1,
                1,
            )

    monkeypatch.setattr(api_app, "AnthropicClient", FakeJudge)
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    cal = c.post("/api/lab/benches/product/calibrate", headers=ORIGIN).json()
    assert cal["scenarios"]["prd"]["trustworthy"] and cal["scenarios"]["prd"]["gap"] >= 1
    assert c.get("/api/lab/benches").json()[
        [b["id"] for b in c.get("/api/lab/benches").json()].index("product")
    ]["calibration"]


def test_lab_runs_on_a_local_model_with_no_sign_in(tmp_path: Path, monkeypatch):
    """Claude Code in the sandbox pointed at a local server: its base URL as the sandbox sees it,
    the server's own model name, no key needed, and the baseline kept apart from Claude's."""
    import json as _json

    from test_api_workspace import ORIGIN

    from proving_ground import local_models as lm

    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    reg = lm.Registry(tmp_path / "home" / "local-models.json")
    m = lm.make("http://127.0.0.1:11434", "qwen3:8b", "ollama")
    no_anthropic = reg.add(lm.make("http://127.0.0.1:1234", "phi-4", "lmstudio"))
    reg.add(lm.LocalModel(m.id, m.label, m.base, m.model, m.kind, True))
    a = _starter(c, "Fix a bug")
    bad = c.post(
        "/api/lab/run",
        json={
            "workflow": a,
            "bench": "qa",
            "budget": 5,
            "auto": False,
            "local_model": no_anthropic.id,
        },
        headers=ORIGIN,
    )
    assert bad.status_code == 422 and "Anthropic's Messages API" in bad.json()["detail"]
    r = c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "qa", "budget": 5, "auto": False, "local_model": m.id},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    _wait(c, 1)
    runs = [q for q in calls if q.agent == "claude-code"]
    env = dict(runs[0].env)
    assert env["ANTHROPIC_BASE_URL"] == "http://host.docker.internal:11434"
    assert env["ANTHROPIC_API_KEY"] == "local"  # the real key never goes to a local run
    assert runs[0].model == "qwen3:8b" and runs[0].hosts == ("host.docker.internal",)
    toml = (Path(runs[0].task_dir) / "task.toml").read_text()
    assert "[agent]\ntimeout_sec = 1800" in toml  # 3x a 600s task: local models are slow
    meta = _json.loads(
        next(
            (tmp_path / "home" / "benches" / "qa" / ".proving-ground" / "runs").glob("*/meta.json")
        ).read_text()
    )
    assert meta["local_model"] == m.id
    row = c.get("/api/lab/results").json()[0]
    assert row["model"] == m.id and row["spent_usd"] == 0  # the fake agent reports $0.02 a trial


def test_lab_runs_a_workflow_on_codex_in_its_own_form(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    c, calls = _lab_client(
        tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0, env={"OPENAI_API_KEY": "sk"}
    )
    a = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "qa", "budget": 5, "auto": False, "agent": "codex"},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    rows = _wait(c, 1)
    runs = [q for q in calls if q.agent == "codex"]
    assert runs and runs[0].model is None  # Codex's own default model, not a Claude one
    assert runs[0].hosts == ("api.openai.com", "chatgpt.com", "auth.openai.com")
    skill = Path(next(q for q in runs if q.skills).skills[0]) / "SKILL.md"
    assert "## Step 1:" in skill.read_text() and skill.parent.name.endswith("-codex")
    assert rows[0]["model"] == "codex:default"


def test_adherence_on_a_real_claude_code_transcript():
    """Trimmed from a real run (Claude Code in the sandbox on a local Qwen 3.5 9B, 2026-10-25):
    it fixed the bug but never opened the workflow and named its one subagent its own way."""
    from proving_ground.adherence import check, subagent_calls

    trial = Path(__file__).parent / "fixtures" / "real-trial"
    calls = subagent_calls(trial)
    assert [c.get("description") for c in calls] == ["Find bulk discount logic"]
    wf = {
        "id": "4f7c2e1a9b",
        "steps": [
            {"id": "explore", "name": "Explore the code", "model": "claude-haiku-5-5"},
            {"id": "implement", "name": "Implement", "model": "claude-sonnet-5-5"},
        ],
        "loops": [],
    }
    a = check(wf, trial, "qwen3.5-9b")
    assert a.found and a.opened is False and a.steps_run == 0 and a.calls == 1


def test_a_workflow_is_handed_to_the_agent_in_its_with_arm(tmp_path: Path, monkeypatch):
    from harbor.utils.templating import render_prompt_template
    from test_api_workspace import ORIGIN

    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    a = _starter(c, "Fix a bug")
    c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "qa", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    _wait(c, 1)
    with_ = [q for q in calls if q.agent == "claude-code" and q.skills]
    without = [q for q in calls if q.agent == "claude-code" and not q.skills]
    assert with_ and without and all(q.prompt_template is None for q in without)
    text = render_prompt_template(with_[0].prompt_template, "Write the tests.")
    assert text.startswith("Write the tests.") and f"workflow-{a['id']}" in text


def test_a_plain_skill_is_left_for_the_agent_to_find(tmp_path: Path):
    from proving_ground.runner.harbor import HarborRunner

    skill = tmp_path / "tdd"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: tdd\ndescription: d\n---\nbody\n")
    r = HarborRunner({}, tmp_path / "trials", "anthropic/x")
    assert r._handed(skill) is None


def test_held_out_tasks_run_but_stay_hidden_and_report_apart(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    # The workflow does well on the visible tasks and no better on the held-out one.
    c, calls = _lab_client(
        tmp_path,
        monkeypatch,
        lambda req: 1.0 if req.skills and "q4-batch" not in str(req.task_dir) else 0.0,
    )
    fin = next(b for b in c.get("/api/lab/benches").json() if b["id"] == "finance")
    hidden = [s for s in fin["scenarios"] if s["held_out"]]
    assert len(hidden) == 1 and hidden[0]["title"] == "Held-out task" and "q4" not in str(hidden)
    a = _starter(c, "Fix a bug")
    c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "finance", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    row = _wait(c, 1)[0]
    assert any("q4-batch" in str(q.task_dir) for q in calls)  # it ran
    assert row["diff"] > 0 and row["held_out"]["diff"] == 0 and row["held_out"]["tasks"] == 1


def test_an_existing_harbor_suite_imports_as_a_bench(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    suite = tmp_path / "suite"
    for name in ("fix-json-parser", "count-words"):
        t = suite / name
        (t / "environment").mkdir(parents=True)
        (t / "tests").mkdir()
        (t / "task.toml").write_text('schema_version = "1.4"\n')
        (t / "instruction.md").write_text(f"Do {name}.")
        (t / "environment" / "Dockerfile").write_text("FROM ubuntu:24.04\n")
        (t / "tests" / "test.sh").write_text("echo 1 > /logs/verifier/reward.txt\n")
    (suite / "notes").mkdir()  # not a task: skipped
    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    bad = c.post(
        "/api/lab/benches/import",
        json={"path": str(tmp_path / "nothing"), "name": "x"},
        headers=ORIGIN,
    )
    assert bad.status_code == 422 and "No Harbor tasks" in bad.json()["detail"]
    got = c.post(
        "/api/lab/benches/import",
        json={"path": str(suite), "name": "My suite", "disciplines": ["development"]},
        headers=ORIGIN,
    ).json()
    assert got["id"] == "imp-my-suite" and got["imported"]
    assert [s["title"] for s in got["scenarios"]] == ["count-words", "fix-json-parser"]
    a = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "imp-my-suite", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    row = _wait(c, 1)[0]
    ran = [q for q in calls if q.agent == "claude-code"]
    # The suite's own task folders, copied as they are: its instruction, its Dockerfile, its tests.
    assert {(Path(q.task_dir) / "instruction.md").read_text() for q in ran} == {
        "Do count-words.",
        "Do fix-json-parser.",
    }
    assert row["bench"] == "imp-my-suite" and row["diff"] > 0


def test_forensics_endpoint_and_discordant_count(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    wf = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "bugfix", "size": "pilot", "budget": 5},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    row = _wait(c, 1)[0]
    assert row["discordant"] > 0
    got = c.get(f"/api/lab/results/bugfix/{row['id']}/forensics").json()
    assert len(got["pairs"]) == row["discordant"]
    assert set(got["pairs"][0]) >= {"with", "without", "diverged_at", "timeline_with"}
    assert sum(got["counts"].values()) == row["discordant"]
    assert c.get("/api/lab/results/bugfix/999/forensics").status_code == 404
    assert c.get("/api/lab/results/nope/1/forensics").status_code == 404


def _suite_wait(c, job, done=("done", "stopped")):
    import time

    for _ in range(600):
        v = c.get(f"/api/lab/suite/{job}").json()
        if v["status"] in done:
            return v
        time.sleep(0.05)
    raise AssertionError("suite did not finish")


def test_pooling_weights_benches_by_pairs():
    from proving_ground.models import ScenarioKind
    from proving_ground.suite import pool
    from proving_ground.trial import TrialOutcome

    def pairs(n_with_only, n_both):
        out = []
        for i in range(n_with_only + n_both):
            for arm in ("with", "without"):
                ok = arm == "with" or i >= n_with_only
                out.append(
                    TrialOutcome(f"s{i}", ScenarioKind.TYPICAL, arm, 0, "pass" if ok else "fail")
                )
        return out

    # Both benches use ids s0.. : without the bench prefix their pairs would collide.
    a, b = pairs(6, 0), pairs(0, 2)  # a: +100% over 6 pairs; b: +0% over 2 pairs
    got = pool({"a": a, "b": b})
    assert got["n_pairs"] == 8
    assert got["pass_with"] == 1.0 and abs(got["pass_without"] - 2 / 8) < 1e-9
    assert abs(got["diff"] - 0.75) < 1e-9  # (6*1 + 2*0) / 8: the bigger bench dominates
    assert pool({})["n_pairs"] == 0 and pool({})["diff"] is None


def test_suite_runs_every_fitting_bench_and_pools(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    from proving_ground import bench as bench_mod

    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    wf = _starter(c, "Fix a bug")
    expected = [b.id for b in bench_mod.benches() if wf["discipline"] in b.disciplines]
    assert len(expected) >= 2
    r = c.post("/api/lab/suite", json={"workflow": wf, "budget": 50}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["benches"] == expected
    v = _suite_wait(c, r.json()["job"])
    assert v["status"] == "done"
    assert [b["status"] for b in v["benches"]] == ["done"] * len(expected)
    # The fake can't grade documents, so a judged bench (docs) ends with no pairs; the rest agree.
    judged = {b.id for b in bench_mod.benches() if b.judged}
    scored = [b for b in v["benches"] if b["bench"] not in judged]
    assert scored and all(b["diff"] == 1.0 and b["n_pairs"] > 0 for b in scored)
    assert all(b["n_pairs"] == 0 for b in v["benches"] if b["bench"] in judged)
    assert v["pooled"]["n_pairs"] == sum(b["n_pairs"] for b in v["benches"])
    assert v["pooled"]["diff"] == 1.0 and v["pooled"]["verdict"] == "helps"
    # A Rig score per bench and one over the pooled pairs (the unmeasured judged bench has none).
    assert all(b["rig"]["score"] is not None for b in scored)
    assert all(b["rig"]["score"] is None for b in v["benches"] if b["bench"] in judged)
    assert (
        v["pooled"]["rig"]["score"] is not None
        and v["pooled"]["rig"]["pairs"] == (v["pooled"]["n_pairs"])
    )
    # Even split, with the unspent carried over: later benches get at least their even share.
    assert v["benches"][0]["budget"] == round(50 / len(expected), 4)
    assert v["benches"][-1]["budget"] >= v["benches"][0]["budget"]
    # Each bench is its own project with its own run.
    assert len(c.get("/api/lab/results").json()) == len(expected)


def test_suite_stop_skips_remaining_benches(tmp_path: Path, monkeypatch):
    import threading

    from test_api_workspace import ORIGIN

    import proving_ground.runner.harbor as harbor

    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    inner, gate, entered = harbor.harbor_executor, threading.Event(), threading.Event()

    def slow(req):
        entered.set()
        gate.wait(5)
        return inner(req)

    monkeypatch.setattr(harbor, "harbor_executor", slow)
    wf = _starter(c, "Fix a bug")
    job = c.post("/api/lab/suite", json={"workflow": wf, "budget": 50}, headers=ORIGIN).json()[
        "job"
    ]
    assert entered.wait(5)
    assert (
        c.post("/api/lab/run", json={"workflow": wf, "bench": "qa"}, headers=ORIGIN).status_code
        == 409
    )
    assert c.post(f"/api/lab/suite/{job}/stop", headers=ORIGIN).status_code == 200
    gate.set()
    v = _suite_wait(c, job)
    assert v["status"] == "stopped"
    states = [b["status"] for b in v["benches"]]
    assert states[0] == "stopped" and set(states[1:]) == {"skipped"}
    assert all(b["experiment"] is None for b in v["benches"][1:])
    assert c.post(f"/api/lab/suite/{job}/stop", headers=ORIGIN).status_code == 404


def test_lab_rows_carry_item_counts_only_when_every_pair_has_them(tmp_path: Path, monkeypatch):
    """A check's RIG_ITEMS line reaches the trial, the results row, the run page's summary, the
    task grid and the comparison; one trial without it and the key is left out everywhere."""
    import itertools

    from test_api_workspace import ORIGIN

    def log(req):
        return "ok\nRIG_ITEMS 12/12\n" if req.skills else "RIG_ITEMS 3/12\nRIG_ITEMS 11/12\nfail\n"

    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0, log=log)
    a = _starter(c, "Fix a bug")
    run = c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "qa", "budget": 5, "auto": False},
        headers=ORIGIN,
    ).json()
    row = _wait(c, 1)[0]
    n = row["n_pairs"]
    assert n >= 2
    items = row["items"]
    assert items["n"] == n and items["with"] == 1.0 and abs(items["without"] - 11 / 12) < 1e-9
    assert (items["right_with"], items["total_with"]) == (12 * n, 12 * n)
    assert (items["right_without"], items["total_without"]) == (11 * n, 12 * n)
    assert abs(items["diff"] - 1 / 12) < 1e-9 and items["ci_low"] < items["diff"] < items["ci_high"]
    detail = c.get(f"/api/lab/results/qa/{run['id']}").json()
    assert detail["summary"]["items"] == items and detail["items"] == items
    assert {(t["items_right"], t["items_total"]) for t in detail["trials"]} == {(12, 12), (11, 12)}
    grid = c.get("/api/lab/matrix", params={"bench": "qa"}).json()["rows"]
    assert grid[0]["items"] == items
    standing = c.post(
        "/api/lab/compare/standing", json={"bench": "qa", "workflows": [a]}, headers=ORIGIN
    ).json()
    assert standing["workflows"][0]["result"]["items"] == items

    # One "without" trial (a fail) printed no count, on a task whose total the others give: it
    # produced nothing gradable, so it scores 0 of 3, and the run keeps its items.
    quiet = itertools.count()

    def log2(req):
        # Only this client's trials: a run the first client started may still reach this fake.
        mine = str(tmp_path / "two") in str(req.task_dir)
        return "RIG_ITEMS 2/3\n" if req.skills or not mine or next(quiet) else "no count here\n"

    c2, _ = _lab_client(tmp_path / "two", monkeypatch, lambda req: 0.0, log=log2)
    run2 = c2.post(
        "/api/lab/run",
        json={"workflow": _starter(c2, "Fix a bug"), "bench": "qa", "budget": 5, "auto": False},
        headers=ORIGIN,
    ).json()
    row2 = _wait(c2, 1)[0]
    n2 = row2["n_pairs"]
    assert (
        row2["items"]["right_without"] == 2 * (n2 - 1) and row2["items"]["total_without"] == 3 * n2
    )
    detail2 = c2.get(f"/api/lab/results/qa/{run2['id']}").json()
    assert detail2["summary"]["items"] == row2["items"]

    # A task whose check never printed a count on any trial: not item-based, so no items key.
    def log3(req):
        return "nothing\n" if "catch-bugs" in str(req.task_dir) else "RIG_ITEMS 2/3\n"

    c3, _ = _lab_client(tmp_path / "three", monkeypatch, lambda req: 0.0, log=log3)
    run3 = c3.post(
        "/api/lab/run",
        json={"workflow": _starter(c3, "Fix a bug"), "bench": "qa", "budget": 5, "auto": False},
        headers=ORIGIN,
    ).json()
    row3 = _wait(c3, 1)[0]
    assert "items" not in row3
    detail3 = c3.get(f"/api/lab/results/qa/{run3['id']}").json()
    assert "items" not in detail3 and "items" not in detail3["summary"]
    assert {t["scenario_id"] for t in detail3["trials"] if t["items_total"]} == {"edge-cases"}
    assert "items" not in c3.get("/api/lab/matrix", params={"bench": "qa"}).json()["rows"][0]
