"""Call the Claude API and return the arguments of one forced tool call."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from proving_ground.generate.prompt import Prompt


class GenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolCall:
    input: Any
    stop_reason: str | None
    tokens_in: int
    tokens_out: int


class ModelClient(Protocol):
    def call(
        self, prompt: Prompt, tool: dict[str, Any], model: str, max_tokens: int
    ) -> ToolCall: ...


class AnthropicClient:
    def __init__(self, client: Any = None, temperature: float | None = None):
        self._client = client if client is not None else anthropic.Anthropic(max_retries=3)
        self._temperature = temperature

    def with_temperature(self, t: float) -> AnthropicClient:
        """The same client, asking for this temperature on every call."""
        return AnthropicClient(self._client, t)

    def call(self, prompt: Prompt, tool: dict[str, Any], model: str, max_tokens: int) -> ToolCall:
        extra = {} if self._temperature is None else {"temperature": self._temperature}
        try:
            with self._client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=prompt.system,
                messages=[{"role": "user", "content": prompt.content}],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                **extra,
            ) as stream:
                msg = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise GenerationError(
                f"The API key was rejected. Check ANTHROPIC_API_KEY. ({e})"
            ) from e
        except anthropic.APIError as e:
            raise GenerationError(f"The Claude API call failed: {e}") from e
        block = next(
            (b for b in msg.content if b.type == "tool_use" and b.name == tool["name"]), None
        )
        return ToolCall(
            input=None if block is None else block.input,
            stop_reason=msg.stop_reason,
            tokens_in=msg.usage.input_tokens,
            tokens_out=msg.usage.output_tokens,
        )


def make_client() -> ModelClient:
    return AnthropicClient()


class ClaudeCliClient:
    """The model through Claude Code's own login on this machine (`claude -p`): no API key.

    No tools, no MCP servers, no session saved. The reply must be the tool's JSON, which is
    parsed here, so callers see the same ToolCall as from the API.
    """

    def __init__(self, run=None, timeout: int = 120):
        import subprocess

        self._run = run or subprocess.run
        self._timeout = timeout

    def call(self, prompt: Prompt, tool: dict[str, Any], model: str, max_tokens: int) -> ToolCall:
        import subprocess

        text = "\n\n".join(b.get("text", "") for b in prompt.content if b.get("type") == "text")
        ask = (
            f"{text}\n\nReply with ONE JSON object for `{tool['name']}` and nothing else. "
            f"It must match this JSON schema:\n{json.dumps(tool['input_schema'])}"
        )
        cmd = [
            "claude", "-p", ask,
            "--system-prompt", prompt.system,
            "--model", model,
            "--output-format", "json",
            "--tools", "",
            "--strict-mcp-config",
            "--no-session-persistence",
        ]  # fmt: skip
        try:
            done = self._run(
                cmd, capture_output=True, text=True, timeout=self._timeout, stdin=subprocess.DEVNULL
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise GenerationError(f"Claude Code didn't answer: {e}") from e
        try:
            wrapper = json.loads(done.stdout)
            reply = wrapper.get("result", "") if isinstance(wrapper, dict) else ""
            if isinstance(wrapper, dict) and wrapper.get("is_error"):
                raise GenerationError(f"Claude Code stopped: {reply[:200]}")
            start, end = reply.find("{"), reply.rfind("}")
            data = json.loads(reply[start : end + 1])
        except (ValueError, AttributeError) as e:
            raise GenerationError("Claude Code's reply had no JSON in it.") from e
        usage = wrapper.get("usage") or {}
        return ToolCall(
            data, "tool_use", usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        )
