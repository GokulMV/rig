"""Improve from failures: what the model sees, which edits survive, and the overfitting gate."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_bench import _lab_client, _starter, _wait

from proving_ground import improve, lab
from proving_ground.generate.client import GenerationError, ToolCall


class FakeModel:
    def __init__(self, changes, summary="Tighten the checks."):
        self.changes, self.summary, self.prompts = changes, summary, []

    def call(self, prompt, tool, model, max_tokens):
        assert tool["name"] == "emit_improvement"
        self.prompts.append(prompt.content[0]["text"])
        return ToolCall({"changes": self.changes, "summary": self.summary}, "tool_use", 1, 1)


def _wf():
    steps = [
        {"id": "plan", "name": "Plan", "does": "Plan the work.", "kind": "think"},
        {"id": "do", "name": "Do", "does": "Do the work.", "kind": "do"},
    ]
    for s in steps:
        s["model"] = "claude-sonnet-5-5"
    return lab.load_workflow(
        {"id": "w1", "name": "W", "discipline": "qa", "origin": "custom", "steps": steps}
    )


def _trial(tmp_path, name, scenario, outcome="fail", arm="with", log="", text=""):
    d = tmp_path / name
    if log:
        (d / "verifier").mkdir(parents=True)
        (d / "verifier" / "check.log").write_text(log)
    if text:
        s = d / "agent" / "sessions" / "projects" / "-app"
        s.mkdir(parents=True)
        line = {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
        (s / "a.jsonl").write_text(json.dumps(line))
    return SimpleNamespace(arm=arm, outcome=outcome, scenario_id=scenario, transcript_uri=str(d))


SCENARIOS = [
    {"id": "vis", "instruction": "Visible task."},
    {"id": "secret", "instruction": "Held-out task.", "held_out": True},
]


def test_evidence_never_includes_held_out_tasks(tmp_path: Path):
    trials = [
        _trial(tmp_path, "a", "vis", log="x" * 3000 + "TAIL", text="y" * 2000),
        _trial(tmp_path, "b", "secret", log="HELD-OUT-LOG", text="HELD-OUT-TEXT"),
        _trial(tmp_path, "c", "vis", outcome="pass"),  # passed: not a failure
        _trial(tmp_path, "d", "vis", arm="without"),  # baseline arm
    ]
    got = improve.evidence(trials, SCENARIOS)
    assert len(got) == 1 and got[0]["scenario"] == "vis"
    assert got[0]["check_log"].endswith("TAIL") and len(got[0]["check_log"]) == 1500
    assert len(got[0]["agent_last"]) == 800
    assert "Held-out" not in json.dumps(got) and "HELD-OUT" not in json.dumps(got)


def test_evidence_is_capped_in_count_and_size(tmp_path: Path):
    trials = [_trial(tmp_path, f"t{i}", "vis", log="z" * 1500, text="q" * 800) for i in range(20)]
    got = improve.evidence(trials, SCENARIOS)
    assert 1 < len(got) <= improve.V["max_trials"]
    assert sum(len(str(v)) for e in got for v in e.values()) <= improve.V["max_evidence_chars"]


def test_propose_keeps_only_valid_changes_and_returns_an_edited_workflow():
    model = FakeModel(
        [
            {"step_id": "ghost", "field": "does", "new": "x", "why": "unknown step"},
            {"step_id": "plan", "field": "kind", "new": "do", "why": "field not allowed"},
            {"step_id": "plan", "field": "does", "new": "  ", "why": "empty"},
            {"step_id": "do", "field": "does", "new": "Do it, then run the checks.", "why": "w1"},
            {"step_id": "", "field": "harness_add", "new": "nonsense", "why": "unknown rule"},
            {"step_id": "", "field": "harness_add", "new": "cite-evidence", "why": "w2"},
            {"step_id": "plan", "field": "name", "new": "Plan first", "why": "w3"},
            {"step_id": "plan", "field": "does", "new": "Over the cap", "why": "w4"},
        ]
    )
    wf = _wf()
    got = improve.propose(model, wf, [{"instruction": "i", "check_log": "c", "agent_last": "a"}])
    assert [(c["step_id"], c["field"]) for c in got["changes"]] == [
        ("do", "does"),
        ("", "harness_add"),
        ("plan", "name"),
    ]  # at most max_changes, in order
    assert got["changes"][0]["old"] == "Do the work."  # read from the workflow, not the model
    new = got["workflow"]
    assert new.steps[1].does == "Do it, then run the checks." and new.steps[0].name == "Plan first"
    assert new.harness == ["cite-evidence"] and new.id != wf.id and new.name.endswith("(improved)")
    assert wf.steps[1].does == "Do the work."  # the original is untouched


def test_propose_without_a_usable_change_or_evidence_raises():
    with pytest.raises(GenerationError):
        improve.propose(
            FakeModel([{"step_id": "ghost", "field": "does", "new": "x", "why": "y"}]),
            _wf(),
            [{"instruction": "i", "check_log": "c", "agent_last": "a"}],
        )
    with pytest.raises(GenerationError):
        improve.propose(FakeModel([]), _wf(), [])


def _row(vis, held):
    return {"visible": {"diff": vis}, "held_out": None if held is False else {"diff": held}}


@pytest.mark.parametrize(
    ("parent", "child", "verdict", "vis", "held"),
    [
        (_row(0.0, 0.5), _row(0.5, 0.5), "overfit", 50.0, 0.0),
        (_row(0.0, 0.5), _row(0.3, 0.2), "overfit", 30.0, -30.0),
        (_row(0.0, 0.0), _row(0.5, 0.25), "generalises", 50.0, 25.0),
        (_row(0.0, 0.0), _row(0.05, 0.0), "unclear", 5.0, 0.0),  # visible gain under 10 pts
        (_row(0.0, 0.0), _row(0.0, 0.5), "generalises", 0.0, 50.0),
        (_row(0.0, 0.0), _row(0.5, False), "unclear", 50.0, None),  # no held-out
        (
            {"visible": {"diff": 0.0}, "held_out": {"diff": None}},
            _row(0.5, 0.5),
            "unclear",
            50.0,
            None,
        ),
    ],
)
def test_overfit_verdicts(parent, child, verdict, vis, held):
    got = improve.overfit(parent, child)
    assert got == {"visible_gain_pts": vis, "held_out_gain_pts": held, "verdict": verdict}


def test_api_improve_then_measure_flags_overfitting(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    import proving_ground.api.app as api_app
    import proving_ground.runner.harbor as harbor

    seen = FakeModel([])

    class Model:
        def __init__(self, *_a, **_k):
            pass

        def call(self, prompt, tool, model, max_tokens):
            return seen.call(prompt, tool, model, max_tokens)

    monkeypatch.setattr(api_app, "AnthropicClient", Model)

    def improved(req):
        return "(improved)" in (Path(req.skills[0]) / "workflow.json").read_text()

    def reward(req):
        if not req.skills:
            return 0.0
        held = "q4-batch" in str(req.task_dir)
        return 1.0 if held != improved(req) else 0.0  # parent: only held-out; child: only visible

    c, _calls = _lab_client(tmp_path, monkeypatch, reward)
    inner = harbor.harbor_executor
    n = iter(range(10_000))

    def with_logs(req):
        r = inner(req)
        r.trial_name = f"t{next(n)}"
        v = req.trials_dir / r.trial_name / "verifier"
        v.mkdir(parents=True, exist_ok=True)
        held = "q4-batch" in str(req.task_dir)
        (v / "check.log").write_text("HELD-OUT-LOG" if held else "VISIBLE-LOG: wrong route")
        return r

    monkeypatch.setattr(harbor, "harbor_executor", with_logs)
    a = _starter(c, "Fix a bug")
    step = a["steps"][0]["id"]
    seen.changes = [
        {
            "step_id": step,
            "field": "does",
            "new": "Check every route twice.",
            "why": "wrong routes",
        },
        {"step_id": "nope", "field": "does", "new": "x", "why": "dropped"},
    ]
    run = {"workflow": a, "bench": "finance", "budget": 5, "auto": False}
    parent = c.post("/api/lab/run", json=run, headers=ORIGIN).json()
    rows = _wait(c, 1)
    assert rows[0]["visible"]["failing"] == 4 and rows[0]["overfit"] is None

    got = c.post(
        "/api/lab/improve",
        json={"workflow": a, "bench": "finance", "experiment": parent["id"]},
        headers=ORIGIN,
    )
    assert got.status_code == 200, got.text
    body = got.json()
    assert [ch["step_id"] for ch in body["proposal"]["changes"]] == [step]
    assert body["proposal"]["changes"][0]["old"] == a["steps"][0]["does"]
    assert body["workflow"]["steps"][0]["does"] == "Check every route twice."
    assert body["workflow"]["id"] != a["id"]
    assert len(seen.prompts) == 1  # one call
    assert "VISIBLE-LOG" in seen.prompts[0]
    assert "HELD-OUT" not in seen.prompts[0] and "q4" not in seen.prompts[0]

    child = c.post(
        "/api/lab/run",
        json=run | {"workflow": body["workflow"], "improved_from": parent["id"]},
        headers=ORIGIN,
    ).json()
    rows = _wait(c, 2)
    row = next(r for r in rows if r["id"] == child["id"])
    assert row["improved_from"] == parent["id"]
    assert row["overfit"]["verdict"] == "overfit" and row["overfit"]["visible_gain_pts"] >= 10
    assert row["overfit"]["held_out_gain_pts"] <= 0


def test_api_improve_refuses_without_failures_or_model(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    a = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/run",
        json={"workflow": a, "bench": "finance", "budget": 5, "auto": False},
        headers=ORIGIN,
    ).json()
    _wait(c, 1)
    got = c.post(
        "/api/lab/improve",
        json={"workflow": a, "bench": "finance", "experiment": r["id"]},
        headers=ORIGIN,
    )
    assert got.status_code == 422 and "no failing visible" in got.json()["detail"]
    missing = c.post(
        "/api/lab/improve",
        json={"workflow": a, "bench": "finance", "experiment": 999},
        headers=ORIGIN,
    )
    assert missing.status_code == 404
