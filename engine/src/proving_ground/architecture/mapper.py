""" "Map with Archify": the chosen agent reads the repo and writes an Archify architecture spec.

The agent's own CLI runs on this machine in the repo, with read-only tools only: it can read
files, but has no shell, no edits, no web and no MCP servers. Its answer is parsed, checked
against the Archify architecture schema and kept in `.proving-ground/archify.json`.
It costs one agent session, so the UI asks first.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from proving_ground import skills
from proving_ground.architecture import MAPPED_SPEC, Architecture, load_architecture, parse_data
from proving_ground.files import PG_DIR

M = skills.load("map-architecture").values
KINDS = ", ".join(M["kinds"])
PROMPT = skills.section("map-architecture", "Prompt")

# Agents whose CLI can be held to read-only tools, checked against the CLI itself.
READ_ONLY: dict[str, Callable[[str], list[str]]] = {
    "claude-code": lambda prompt: [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--tools",
        M["tools"],
        "--permission-mode",
        M["permission_mode"],
        "--strict-mcp-config",
    ],
}


class MapError(Exception):
    pass


def extract_spec(text: str) -> object:
    """The JSON object in an agent's reply: the whole reply, a ```json block, or the outer {...}."""
    text = text.strip()
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("result"), str):
        # claude --output-format json wraps the reply.
        if data.get("is_error"):
            raise MapError(f"The agent stopped: {data['result'][:300]}")
        return extract_spec(data["result"])
    if isinstance(data, dict):
        return data
    for block in reversed(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)):
        try:
            return json.loads(block)
        except ValueError:
            continue
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except ValueError:
            pass
    raise MapError("The agent's reply had no architecture JSON in it.")


def supported(agent: str) -> bool:
    return agent in READ_ONLY


def map_architecture(
    root: Path,
    agent: str,
    env: dict[str, str] | None = None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    timeout: int = M["timeout_s"],
) -> Architecture:
    if agent not in READ_ONLY:
        raise MapError(
            "Map with Archify runs through Claude Code for now: it is the agent here whose "
            "CLI can be held to read-only tools."
        )
    cmd = READ_ONLY[agent](PROMPT)
    if run is subprocess.run and shutil.which(cmd[0]) is None:
        raise MapError(f"The {cmd[0]} CLI isn't installed on this machine.")
    full_env = {**os.environ, **(env or {}), "ARCHIFY_UPDATE_CHECK_DISABLED": "1"}
    try:
        done = run(
            cmd,
            cwd=root,
            env=full_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as e:
        raise MapError(f"The agent took longer than {timeout // 60} minutes.") from e
    if done.returncode != 0 and not done.stdout.strip():
        raise MapError(f"The agent failed: {(done.stderr or '').strip()[:300] or done.returncode}")
    data = extract_spec(done.stdout)
    try:
        parse_data(data, "The agent's spec", source="mapped")
    except ValueError as e:
        raise MapError(str(e)) from e
    out = root / PG_DIR / MAPPED_SPEC
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2))
    return load_architecture(root, refresh=True)
