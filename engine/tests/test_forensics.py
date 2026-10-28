"""Failure forensics: buckets, discordant pairs, and the real trial's timeline. No model calls."""

import json
from pathlib import Path
from types import SimpleNamespace

from proving_ground import forensics, skills
from proving_ground.trial import TrialOutcome

REAL = Path(__file__).parent / "fixtures" / "real-trial"


def use(name, **inp):
    return {"type": "tool_use", "name": name, "input": inp}


def say(text):
    return {"type": "text", "text": text}


def trial(tmp_path, blocks, check_log=None, result=None, name="t"):
    d = tmp_path / name
    s = d / "agent" / "sessions" / "projects" / "-app"
    s.mkdir(parents=True)
    lines = [json.dumps({"message": {"role": "assistant", "content": [b]}}) for b in blocks]
    (s / "a.jsonl").write_text("\n".join(lines))
    if check_log is not None:
        (d / "verifier").mkdir()
        (d / "verifier" / "check.log").write_text(check_log)
    if result is not None:
        (d / "result.json").write_text(json.dumps(result))
    return d


SC = SimpleNamespace(check="bash tests/test.sh")
EDIT = use("Edit", file_path="/app/a.py")
RUN = use("Bash", command="python -m pytest -q")


def bucket(d, outcome="fail", wf=None):
    return forensics.classify(d, outcome, SC, wf)["bucket"]


def test_timeline_of_the_real_trial():
    tl = forensics.timeline(REAL)
    assert tl[0] == {"tool": "Agent", "summary": "Find bulk discount logic"}
    assert {"tool": "Read", "summary": "/app/shop/pricing.py"} in tl
    assert tl[-1]["tool"] == "Final message" and tl[-1]["summary"].startswith("The bulk discount")
    assert len(tl[-1]["summary"]) <= 300
    assert all(len(e["summary"]) <= 300 for e in tl)


def test_timeline_summaries(tmp_path):
    d = trial(tmp_path, [use("Bash", command="x" * 200), use("Write", file_path="/f"), say("ok")])
    tl = forensics.timeline(d)
    assert len(tl[0]["summary"]) == 120 and tl[1] == {"tool": "Write", "summary": "/f"}
    assert forensics.timeline(tmp_path / "none") == []


def test_solved(tmp_path):
    assert bucket(trial(tmp_path, [say("x")]), "pass") == "solved"


def test_timeout(tmp_path):
    d = trial(tmp_path, [EDIT, RUN, say("done")], result={"exception_info": "AgentTimeoutError"})
    assert bucket(d, "errored") == "timeout"
    assert bucket(trial(tmp_path, [EDIT, RUN], name="nofinal"), "errored") == "timeout"
    # An agent timeout is recorded as a fail now ("timed out after N s"): still a timeout.
    assert bucket(d, "fail") == "timeout"
    other = trial(tmp_path, [EDIT, say("hi")], result={"exception_info": "Boom"}, name="o")
    assert bucket(other, "errored") == "errored"


def test_premature_stop(tmp_path):
    assert bucket(trial(tmp_path, [RUN, EDIT, say("fixed")])) == "premature_stop"
    assert bucket(trial(tmp_path, [say("nothing")], name="n")) == "premature_stop"


def test_scenario_check_command_counts_as_a_check(tmp_path):
    sc = SimpleNamespace(check="./verify-it")
    d = trial(tmp_path, [EDIT, use("Bash", command="./verify-it now"), say("x")], check_log="")
    assert forensics.classify(d, "fail", sc)["bucket"] == "wrong_fix"


def test_regression(tmp_path):
    log = "FAILED tests/test_a.py::test_a\nFAILED tests/test_b.py::test_b\n"
    assert bucket(trial(tmp_path, [EDIT, RUN, say("x")], check_log=log)) == "regression"


def test_wrong_fix(tmp_path):
    d = trial(tmp_path, [EDIT, RUN, say("x")], check_log="FAILED t::one\nAssertionError: 1 != 2\n")
    assert bucket(d) == "wrong_fix"


def test_over_engineering(tmp_path):
    edits = [use("Edit", file_path=f"/app/f{i}.py") for i in range(5)]
    d = trial(tmp_path, [*edits, RUN, say("x")], check_log="AssertionError\n")
    assert bucket(d) == "over_engineering"
    assert skills.value("failure-forensics", "max_files_touched") == forensics.MAX_FILES == 4


def test_loop_thrash(tmp_path):
    wf = {
        "id": "w",
        "steps": [
            {"id": "impl", "name": "implement", "model": "sonnet"},
            {"id": "test", "name": "test", "model": "sonnet"},
        ],
        "loops": [["test", "impl", 1]],
    }
    calls = [use("Agent", description="implement it", model="sonnet") for _ in range(3)]
    d = trial(tmp_path, [*calls, EDIT, RUN, say("x")], check_log="")
    assert bucket(d, wf=wf) == "loop_thrash"
    assert bucket(d) == "wrong_fix"


def test_no_logs_is_unknown(tmp_path):
    assert bucket(tmp_path) == "unknown"


def t(arm, outcome, uri=None, sid="s1", repeat=0):
    return TrialOutcome(sid, "typical", arm, repeat, outcome, transcript_uri=uri)


def test_discordant_pairs(tmp_path):
    good = trial(tmp_path, [use("Read", file_path="/a"), EDIT, RUN, say("done")], name="g")
    bad = trial(tmp_path, [use("Bash", command="ls"), EDIT, say("done")], name="b")
    trials = [
        t("with", "fail", str(bad)),
        t("without", "pass", str(good)),
        t("with", "pass", str(good), repeat=1),
        t("without", "pass", str(good), repeat=1),
        t("with", "fail", None, sid="s2"),  # no partner
    ]
    assert forensics.discordant_count(trials) == 1
    [p] = forensics.discordant(trials, {"s1": SC})
    assert p["scenario_id"] == "s1" and p["with"]["bucket"] == "premature_stop"
    assert p["without"] == {"outcome": "pass", "bucket": "solved", "why": "The check passed."}
    assert p["diverged_at"] == 0
    assert [e["tool"] for e in p["timeline_with"]] == ["Bash", "Edit", "Final message"]


def test_diverged_at_cases():
    a = [{"tool": "Read"}, {"tool": "Edit"}]
    assert forensics._diverged_at(a, a) is None
    assert forensics._diverged_at(a, a[:1]) == 1
    assert forensics._diverged_at(a, [{"tool": "Read"}, {"tool": "Bash"}]) == 1


def test_timeline_is_capped(tmp_path):
    d = trial(tmp_path, [use("Read", file_path=f"/{i}") for i in range(60)])
    trials = [t("with", "fail", str(d)), t("without", "pass", str(d))]
    [p] = forensics.discordant(trials)
    assert len(p["timeline_with"]) == 40
