import stat
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from proving_ground.files import load_scenarios, load_workflows, save_scenario
from proving_ground.generate.apply import PlanConflictError
from proving_ground.generate.client import AnthropicClient, GenerationError, ToolCall
from proving_ground.generate.prompt import Prompt
from proving_ground.generate.run import TOOL_NAME, generate
from proving_ground.generate.schema import InvalidPlanError, parse_mix
from proving_ground.models import Scenario
from proving_ground.store import SourceRow

MIX = parse_mix("typical=1,failure=1,imaginary=1")
SOURCES = [SourceRow(1, "usecase", "use-case", "Handle refunds.", {})]


class FakeClient:
    def __init__(self, data, stop_reason="tool_use"):
        self.data, self.stop_reason, self.calls = data, stop_reason, []

    def call(self, prompt, tool, model, max_tokens):
        self.calls.append((prompt, tool, model, max_tokens))
        return ToolCall(self.data, self.stop_reason, 1200, 3400)


def test_generate_writes_the_whole_plan(tmp_path: Path, plan_data):
    client = FakeClient(plan_data)
    res = generate(tmp_path, SOURCES, MIX, client, "claude-opus-5-5")
    prompt, tool, model, max_tokens = client.calls[0]
    assert tool["name"] == TOOL_NAME and model == "claude-opus-5-5" and max_tokens == 32_000
    assert (res.tokens_in, res.tokens_out) == (1200, 3400)
    assert [w.id for w in load_workflows(tmp_path)] == ["support"]
    assert [s.id for s in load_scenarios(tmp_path)] == [
        "config-missing",
        "future-scale",
        "refund-basic",
    ]
    pg = tmp_path / ".proving-ground"
    check = pg / "checks" / "refund-basic" / "check.sh"
    assert check.read_text() == "grep -q refunded out.txt\n"
    assert check.stat().st_mode & stat.S_IXUSR
    assert (pg / "fixtures" / "future-scale" / "tickets.json").read_text() == "[]\n"
    sugg = yaml.safe_load((pg / "suggestions" / "support.yaml").read_text())
    assert sugg == [{"name": "tdd", "kind": "skill", "why": "Fixes need tests", "step": "fix"}]
    assert len(res.written) == 8


def test_invalid_output_writes_nothing(tmp_path: Path, plan_data):
    plan_data["scenarios"].pop()
    with pytest.raises(InvalidPlanError):
        generate(tmp_path, SOURCES, MIX, FakeClient(plan_data), "m")
    assert not (tmp_path / ".proving-ground").exists()


def test_existing_files_block_the_write(tmp_path: Path, plan_data):
    (tmp_path / ".proving-ground" / "checks" / "refund-basic").mkdir(parents=True)
    with pytest.raises(PlanConflictError, match="checks/refund-basic"):
        generate(tmp_path, SOURCES, MIX, FakeClient(plan_data), "m")
    assert load_scenarios(tmp_path) == []


def test_existing_scenario_ids_are_sent_and_enforced(tmp_path: Path, plan_data):
    save_scenario(tmp_path, Scenario(id="refund-basic", instruction="x"))
    client = FakeClient(plan_data)
    with pytest.raises(InvalidPlanError, match="'refund-basic' already exists"):
        generate(tmp_path, SOURCES, MIX, client, "m")
    assert "do not reuse): refund-basic." in client.calls[0][0].content[-1]["text"]


def test_truncated_or_missing_tool_call_is_an_error(tmp_path: Path, plan_data):
    with pytest.raises(GenerationError, match="cut off at 32000 tokens"):
        generate(tmp_path, SOURCES, MIX, FakeClient(plan_data, "max_tokens"), "m")
    with pytest.raises(GenerationError, match="did not call emit_plan"):
        generate(tmp_path, SOURCES, MIX, FakeClient(None, "end_turn"), "m")


def test_anthropic_client_forces_the_tool_and_reads_its_input():
    seen = {}
    msg = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="hi"),
            SimpleNamespace(type="tool_use", name="emit_plan", input={"a": 1}),
        ],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=5, output_tokens=7),
    )

    @contextmanager
    def stream(**kwargs):
        seen.update(kwargs)
        yield SimpleNamespace(get_final_message=lambda: msg)

    fake = SimpleNamespace(messages=SimpleNamespace(stream=stream))
    prompt = Prompt(system="sys", content=[{"type": "text", "text": "go"}])
    call = AnthropicClient(fake).call(prompt, {"name": "emit_plan"}, "m", 100)
    assert call == ToolCall({"a": 1}, "tool_use", 5, 7)
    assert seen["tool_choice"] == {"type": "tool", "name": "emit_plan"}
    assert seen["system"] == "sys"
    assert seen["messages"] == [{"role": "user", "content": [{"type": "text", "text": "go"}]}]
