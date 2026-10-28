"""Generate a plan from sources and write it to the project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from proving_ground.files import load_scenarios
from proving_ground.generate.apply import write_plan
from proving_ground.generate.client import GenerationError, ModelClient
from proving_ground.generate.prompt import Prompt, build_prompt
from proving_ground.generate.schema import GeneratedPlan, parse_plan, plan_json_schema
from proving_ground.models import Scenario, ScenarioKind
from proving_ground.store import SourceRow

TOOL_NAME = "emit_plan"


@dataclass
class GenerateResult:
    plan: GeneratedPlan
    scenarios: list[Scenario]
    written: list[Path]
    prompt: Prompt
    tokens_in: int
    tokens_out: int


def plan_tool() -> dict:
    return {
        "name": TOOL_NAME,
        "description": "Return the workflow, scenarios and suggested treatments.",
        "input_schema": plan_json_schema(),
    }


def generate(
    root: Path,
    sources: list[SourceRow],
    mix: dict[ScenarioKind, int],
    client: ModelClient,
    model: str,
    max_tokens: int = 32_000,
) -> GenerateResult:
    existing = {s.id for s in load_scenarios(root)}
    prompt = build_prompt(sources, mix, existing)
    call = client.call(prompt, plan_tool(), model, max_tokens)
    if call.stop_reason == "max_tokens":
        raise GenerationError(
            f"The output was cut off at {max_tokens} tokens. Ask for fewer tasks "
            "with --mix or raise --max-tokens."
        )
    if call.input is None:
        raise GenerationError(f"The model did not call {TOOL_NAME}. Run the command again.")
    plan, scenarios = parse_plan(call.input, mix, existing)
    written = write_plan(root, plan, scenarios)
    return GenerateResult(plan, scenarios, written, prompt, call.tokens_in, call.tokens_out)
