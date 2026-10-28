from pathlib import Path

from proving_ground.estimate import EstimateInput, Estimator
from proving_ground.generate.client import ToolCall


class FakeModel:
    def __init__(self, data):
        self.data, self.calls = data, 0

    def call(self, prompt, tool, model, max_tokens):
        self.calls += 1
        assert tool["name"] == "emit_estimate"
        assert '<skill name="tdd">' in prompt.content[0]["text"]
        return ToolCall(self.data, "tool_use", 800, 120)


def inp(**kw):
    base = dict(
        name="tdd",
        skill_text="Write the failing test first.",
        steps=["fix", "verify"],
        scenarios=["Refund under limit (typical)", "Config missing (failure)"],
        repo_summary="Python FastAPI service for refunds.",
        measured=None,
    )
    return EstimateInput(**(base | kw))


def test_measured_results_come_first_and_cost_nothing(tmp_path: Path):
    model = FakeModel({})
    e = Estimator(model, cache=tmp_path / "e.json")
    out = e.estimate(
        inp(
            measured={
                "diff": 0.18,
                "ci_low": 0.05,
                "ci_high": 0.31,
                "n_pairs": 40,
                "experiment_id": 3,
            }
        )
    )
    assert out["basis"] == "measured" and out["low"] == 5 and out["high"] == 31 and model.calls == 0


def test_model_estimate_is_a_labelled_range_and_cached(tmp_path: Path):
    model = FakeModel(
        {
            "low": -2,
            "high": 12,
            "likely": 6,
            "confidence": "low",
            "reason": "Tests exist; skill pushes TDD.",
        }
    )
    e = Estimator(model, cache=tmp_path / "e.json")
    out = e.estimate(inp())
    assert out == {
        "basis": "estimate",
        "low": -2,
        "high": 12,
        "likely": 6,
        "confidence": "low",
        "reason": "Tests exist; skill pushes TDD.",
    }
    Estimator(model, cache=tmp_path / "e.json").estimate(inp())
    assert model.calls == 1  # same inputs: from the cache


def test_ranges_are_clamped_and_ordered(tmp_path: Path):
    model = FakeModel({"low": 80, "high": -150, "likely": 300, "confidence": "high", "reason": "x"})
    out = Estimator(model, cache=tmp_path / "e.json").estimate(inp())
    assert (out["low"], out["high"], out["likely"]) == (-100, 80, 80)


def test_no_model_still_gives_a_rough_number(tmp_path: Path):
    out = Estimator(None, cache=tmp_path / "e.json").estimate(inp())
    assert out["basis"] == "rough" and out["low"] < out["likely"] < out["high"]
    assert out["reason"].startswith("Rough guess") and "no model" in out["reason"]


def test_rough_guess_follows_the_fit_between_skill_and_repo():
    from proving_ground.estimate import EstimateInput, rough

    base = dict(steps=[], scenarios=["refund over limit (edge)"], measured=None)
    fits = rough(
        EstimateInput(
            name="tdd",
            skill_text="Write a failing pytest test first, then fix. Python and FastAPI.",
            repo_summary="Python FastAPI service with pytest tests",
            **base,
        )
    )
    misfit = rough(
        EstimateInput(
            name="swift-ui",
            skill_text="SwiftUI layout rules for Swift apps.",
            repo_summary="Python FastAPI service",
            **base,
        )
    )
    assert fits["likely"] > misfit["likely"]
    assert "python" in fits["reason"] and "not this repo's stack" in misfit["reason"]


def test_quick_skips_the_model(tmp_path: Path):
    model = FakeModel({"low": 1, "high": 9, "likely": 5, "confidence": "low", "reason": "x"})
    out = Estimator(model, cache=tmp_path / "e.json").estimate(inp(), quick=True)
    assert out["basis"] == "rough" and model.calls == 0


def test_claude_cli_client_parses_the_reply():
    import json
    import subprocess

    from proving_ground.estimate import MODEL, SYSTEM, TOOL
    from proving_ground.generate.client import ClaudeCliClient
    from proving_ground.generate.prompt import Prompt

    seen = {}

    def run(cmd, **kw):
        seen["cmd"] = cmd
        reply = 'Here: {"low": -2, "high": 10, "likely": 4, "confidence": "low", "reason": "ok"}'
        out = json.dumps({"result": reply, "usage": {"input_tokens": 10, "output_tokens": 5}})
        return subprocess.CompletedProcess(cmd, 0, out, "")

    call = ClaudeCliClient(run=run).call(
        Prompt(SYSTEM, [{"type": "text", "text": "x"}]), TOOL, MODEL, 600
    )
    assert call.input["likely"] == 4 and call.tokens_in == 10
    cmd = seen["cmd"]
    assert cmd[cmd.index("--tools") + 1] == "" and "--no-session-persistence" in cmd
    assert cmd[cmd.index("--model") + 1] == MODEL
