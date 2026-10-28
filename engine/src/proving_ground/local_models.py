"""Models people run themselves (Ollama, LM Studio, llama.cpp, vLLM, Jan), next to the hosted ones.

Found on this machine or added by URL; only local hosts are accepted. They answer helper calls
(estimates, picks, drafts, the judge) through the OpenAI-style chat API, and can be the model an
agent runs on. Rules and values: the local-models skill. Nothing secret is written to disk.
"""

from __future__ import annotations

import ipaddress
import json
import re
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from proving_ground import skills
from proving_ground.generate.client import GenerationError, ToolCall
from proving_ground.generate.prompt import Prompt

L = skills.load("local-models").values
THINK = re.compile(r"<think>.*?</think>", re.S)


@dataclass(frozen=True)
class LocalModel:
    id: str  # "local:<slug>": how steps, runs and settings name it
    label: str
    base: str  # the server root, e.g. http://127.0.0.1:11434
    model: str  # the model's id as the server lists it
    kind: str  # ollama | lmstudio | llamacpp | vllm | jan | openai
    anthropic: bool = False  # also speaks Anthropic's Messages API (so Claude Code can use it)

    def dump(self) -> dict:
        return asdict(self)


def is_local(url: str) -> bool:
    """On this machine or the person's own network, never a public host."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    host = u.hostname.lower()
    if host in L["local_hosts"] or any(host.endswith(s) for s in L["local_suffixes"]):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or (L["private_networks"] and ip.is_private and not ip.is_link_local)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "model"


def make(base: str, model: str, kind: str = "openai", label: str | None = None) -> LocalModel:
    base = base.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    if not is_local(base):
        raise ValueError(
            f"{base} isn't on this machine or your network. Only local servers can be added, "
            "so nothing you test leaves."
        )
    name = model.rsplit("/", 1)[-1].removesuffix(".gguf")
    port = urlparse(base).port or ""
    return LocalModel(
        f"local:{_slug(f'{kind}-{port}-{name}')}", label or f"{name} · {kind}", base, model, kind
    )


def _listed(shape: str, data: Any) -> list[str]:
    if shape == "ollama" and isinstance(data, dict) and isinstance(data.get("models"), list):
        return [m["name"] for m in data["models"] if isinstance(m, dict) and m.get("name")]
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return [m["id"] for m in data["data"] if isinstance(m, dict) and m.get("id")]
    return []


def speaks_anthropic(base: str, http: httpx.Client | None = None) -> bool:
    """Whether /v1/messages exists (an empty ask: a 4xx naming the body, not a 404)."""
    c = http or httpx.Client(timeout=L["probe_timeout_s"] * 3)
    try:
        r = c.post(f"{base}/v1/messages", json={})
    except httpx.HTTPError:
        return False
    return r.status_code not in (404, 405) and "json" in r.headers.get("content-type", "")


def detect(http: httpx.Client | None = None, extra: list[str] | None = None) -> list[LocalModel]:
    """Servers answering on the usual ports (and any `extra` bases), with the models they list.
    A port that answers with something else (another app) is skipped."""
    c = http or httpx.Client(timeout=L["probe_timeout_s"])
    probes = list(L["probes"]) + [
        {
            "kind": "openai",
            "label": "Server",
            "base": b.rstrip("/"),
            "list": "/v1/models",
            "shape": "openai",
        }
        for b in extra or []
    ]
    found: list[LocalModel] = []
    for p in probes:
        try:
            r = c.get(p["base"] + p["list"])
            names = _listed(p["shape"], r.json()) if r.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            continue
        if not names:
            continue
        anth = speaks_anthropic(p["base"], c)
        for n in names:
            m = make(p["base"], n, p["kind"])
            found.append(LocalModel(m.id, m.label, m.base, m.model, m.kind, anth))
    return found


def agent_env(lm: LocalModel) -> tuple[str, dict[str, str]]:
    """The model name and env that point Claude Code in the sandbox at a local server."""
    u = urlparse(lm.base)
    host = u.hostname or ""
    if host in ("localhost", "127.0.0.1", "::1"):
        host = L["sandbox_host"]
    base = f"{u.scheme}://{host}" + (f":{u.port}" if u.port else "")
    # With a base URL, Harbor passes the name through as is: the server's own model id.
    return lm.model, {
        "ANTHROPIC_BASE_URL": base,
        "ANTHROPIC_API_KEY": "local",  # local servers don't check it; Claude Code wants one
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }


class Registry:
    """The local models a person added, in <home>/local-models.json (no secrets), plus which one
    answers the helper calls."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            d = json.loads(self.path.read_text())
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, d: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(d, indent=2))

    def models(self) -> list[LocalModel]:
        out = []
        for m in self._read().get("models", []):
            try:
                out.append(LocalModel(**m))
            except TypeError:
                continue
        return out

    def get(self, mid: str) -> LocalModel | None:
        return next((m for m in self.models() if m.id == mid), None)

    def add(self, m: LocalModel) -> LocalModel:
        if not is_local(m.base):
            raise ValueError(f"{m.base} isn't a local server.")
        with self._lock:
            d = self._read()
            d["models"] = [x for x in d.get("models", []) if x.get("id") != m.id] + [m.dump()]
            self._write(d)
        return m

    def remove(self, mid: str) -> None:
        with self._lock:
            d = self._read()
            d["models"] = [x for x in d.get("models", []) if x.get("id") != mid]
            if d.get("helper") == mid:
                d["helper"] = None
            self._write(d)

    def helper(self) -> LocalModel | None:
        mid = self._read().get("helper")
        return self.get(mid) if mid else None

    def set_helper(self, mid: str | None) -> None:
        if mid is not None and self.get(mid) is None:
            raise KeyError(f"No local model {mid!r}.")
        with self._lock:
            d = self._read()
            d["helper"] = mid
            self._write(d)


def _json_in(text: str) -> Any:
    text = THINK.sub("", text or "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object")
    return json.loads(text[start : end + 1])


class OpenAICompatClient:
    """A ModelClient on a local OpenAI-compatible server. The `model` callers pass (a Claude
    model's name) is ignored: the local model answers every call."""

    def __init__(self, local: LocalModel, http: httpx.Client | None = None):
        self.local = local
        self._http = http or httpx.Client(timeout=L["call_timeout_s"])

    def _post(self, body: dict) -> dict:
        try:
            r = self._http.post(f"{self.local.base}/v1/chat/completions", json=body)
        except httpx.HTTPError as e:
            raise GenerationError(f"{self.local.label} didn't answer: {e}") from e
        if r.status_code >= 400:
            raise _Refused(r.status_code, r.text[:300])
        try:
            return r.json()
        except ValueError as e:
            raise GenerationError(
                f"{self.local.label} answered with something that isn't JSON."
            ) from e

    def call(self, prompt: Prompt, tool: dict[str, Any], model: str, max_tokens: int) -> ToolCall:
        text = "\n\n".join(b.get("text", "") for b in prompt.content if b.get("type") == "text")
        base = {
            "model": self.local.model,
            "max_tokens": max(max_tokens, L["min_max_tokens"]),
            "temperature": 0,
        }
        messages = [{"role": "system", "content": prompt.system}, {"role": "user", "content": text}]
        fn = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool["input_schema"],
            },
        }
        try:
            data = self._post(
                base
                | {
                    "messages": messages,
                    "tools": [fn],
                    "tool_choice": {"type": "function", "function": {"name": tool["name"]}},
                }
            )
        except _Refused:
            data = None  # the server doesn't do forced tools: ask for the JSON instead
        args = _arguments(data, tool["name"]) if data else None
        if args is None:
            ask = (
                f"{text}\n\nReply with ONE JSON object for `{tool['name']}` and nothing else. "
                f"It must match this JSON schema:\n{json.dumps(tool['input_schema'])}"
            )
            try:
                data = self._post(
                    base | {"messages": [messages[0], {"role": "user", "content": ask}]}
                )
            except _Refused as e:
                raise GenerationError(f"{self.local.label} refused the request: {e}") from e
            try:
                args = _json_in(data["choices"][0]["message"].get("content") or "")
            except (KeyError, IndexError, ValueError, TypeError) as e:
                raise GenerationError(f"{self.local.label}'s reply had no JSON in it.") from e
        usage = data.get("usage") or {}
        return ToolCall(
            args, "tool_use", usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        )


class _Refused(GenerationError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body}")
        self.status = status


def _arguments(data: dict, name: str) -> Any:
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None
    for c in msg.get("tool_calls") or []:
        f = c.get("function") or {}
        if f.get("name") == name:
            a = f.get("arguments")
            try:
                return json.loads(a) if isinstance(a, str) else a
            except ValueError:
                return None
    try:
        return _json_in(msg.get("content") or "")
    except ValueError:
        return None


PING = {
    "name": "emit_check",
    "description": "Answer the check.",
    "input_schema": {
        "type": "object",
        "properties": {"answer": {"type": "integer"}, "word": {"type": "string"}},
        "required": ["answer", "word"],
    },
}


def _helper_stage(client: OpenAICompatClient) -> dict:
    """One small forced-JSON ask: can it return the JSON the helper calls need?"""
    try:
        call = client.call(
            Prompt(
                "You answer checks exactly.",
                [{"type": "text", "text": "What is 17 + 25? Also give the word 'ready'."}],
            ),
            PING,
            "local",
            256,
        )
    except GenerationError as e:
        return {"name": "helper", "ok": False, "why": str(e)}
    a = call.input if isinstance(call.input, dict) else {}
    ok = a.get("answer") == 42 and str(a.get("word", "")).strip().lower() == "ready"
    why = (
        "Returned the right JSON."
        if ok
        else f"Returned {json.dumps(a)[:200]} instead of answer 42, word ready."
    )
    return {"name": "helper", "ok": ok, "why": why}


READY_TOOL = {
    "name": "ready_check",
    "input_schema": {
        "type": "object",
        "properties": {"status": {"type": "string"}},
        "required": ["status"],
    },
}
TEMPLATE_ERROR = "System message must be at the beginning"
TEMPLATE_FIX = (
    'Click "Save a fixed template" for this server, then restart it with the command shown.'
)


def _agent_stage(m: LocalModel, http: httpx.Client) -> tuple[dict, bool]:
    """What Claude Code does on every turn, in miniature: a later user turn after a reply, tools
    on, a tool forced. Returns the stage and whether the template refused (so a fix is offered)."""
    body = {
        "model": m.model,
        "max_tokens": L["agent_max_tokens"],
        "system": "You are a coding agent.",
        "messages": [
            {"role": "user", "content": "Ping"},
            {"role": "assistant", "content": "Pong"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Call the ready_check tool with status='ok'."}
                ],
            },
        ],
        "tools": [READY_TOOL],
        "tool_choice": {"type": "any"},
    }
    try:
        r = http.post(f"{m.base}/v1/messages", json=body)
    except httpx.HTTPError as e:
        return {"name": "agent", "ok": False, "why": f"{m.label} didn't answer: {e}"}, False
    if r.status_code >= 400:
        if TEMPLATE_ERROR in r.text:
            why = "the template refuses later system messages, which Claude Code sends."
            return {"name": "agent", "ok": False, "why": why}, True
        return {"name": "agent", "ok": False, "why": f"HTTP {r.status_code}: {r.text[:200]}"}, False
    try:
        blocks = r.json().get("content") or []
    except (ValueError, AttributeError):
        blocks = []
    if any(isinstance(b, dict) and b.get("type") == "tool_use" for b in blocks):
        return {"name": "agent", "ok": True, "why": "Called the tool it was asked to call."}, False
    why = "the chat template drops tool calls (chatml does)."
    return {"name": "agent", "ok": False, "why": why}, False


def _int(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None


def context_tokens(m: LocalModel, http: httpx.Client) -> int | None:
    """The context the server runs with, if it says: llama.cpp /props, Ollama /api/show."""
    try:
        if m.kind == "ollama":
            d = http.post(f"{m.base}/api/show", json={"model": m.model}).json()
            hit = re.search(r"^\s*num_ctx\s+(\d+)", str(d.get("parameters") or ""), re.M)
            if hit:
                return _int(int(hit.group(1)))
            for k, v in (d.get("model_info") or {}).items():
                if k.endswith("context_length"):
                    return _int(v)
            return None
        d = http.get(f"{m.base}/props").json()
        gen = d.get("default_generation_settings") or {}
        return _int(gen.get("n_ctx")) or _int(d.get("n_ctx"))
    except (httpx.HTTPError, ValueError, AttributeError, TypeError):
        return None


def try_model(client: OpenAICompatClient) -> dict:
    """Is it ready? Three stages: the helper ask; what Claude Code needs from the server (a
    later user turn, a forced tool call); and room for Claude Code's prompt."""
    import time

    t0 = time.monotonic()
    m, http = client.local, client._http
    helper = _helper_stage(client)
    stages = [helper]
    warnings: list[str] = []
    fix: str | None = None
    claude_ok: bool | None = None
    if m.anthropic:
        agent, refused = _agent_stage(m, http)
        stages.append(agent)
        claude_ok = agent["ok"]
        if refused:
            fix = TEMPLATE_FIX
    n = context_tokens(m, http)
    need = L["min_ctx"]
    if n is None:
        why = f"The server doesn't say; start it with -c {L['recommended_ctx']}."
        stages.append({"name": "context", "ok": True, "why": why})
    elif 0 < n < need:
        warnings.append(
            f"Context is {n} tokens; Claude Code needs at least {need // 1024}k "
            f"(-c {L['recommended_ctx']} recommended)."
        )
        stages.append({"name": "context", "ok": False, "why": f"{n} tokens is too few."})
        if claude_ok is not None:
            claude_ok = False
    else:
        stages.append({"name": "context", "ok": True, "why": f"{n} tokens."})
    return {
        "ok": helper["ok"],  # kept for older callers
        "helper_ok": helper["ok"],
        "claude_code_ok": claude_ok,
        "context_tokens": n,
        "warnings": warnings,
        "fix_command": fix,
        "stages": stages,
        "why": helper["why"],
        "seconds": round(time.monotonic() - t0, 1),
    }


_RAISE = re.compile(
    r"\{\{-?\s*raise_exception\(\s*(['\"])System message must be at the beginning\.?\1\s*\)\s*-?\}\}"
)
_AS_SYSTEM = "{{- '<|im_start|>system\\n' + content + '<|im_end|>' + '\\n' }}"


def patched_template(text: str) -> str | None:
    """The server's own chat template with the check that refuses a later system message turned
    into a system turn. None when it isn't a ChatML-style template or has no such check."""
    if "<|im_start|>" not in text or not _RAISE.search(text):
        return None
    return _RAISE.sub(lambda _: _AS_SYSTEM, text)


def save_fixed_template(m: LocalModel, home: Path, http: httpx.Client | None = None) -> dict:
    """Fetch the llama.cpp server's template, patch it, save under <home>/templates (not secret)."""
    c = http or httpx.Client(timeout=L["probe_timeout_s"] * 10)
    try:
        props = c.get(f"{m.base}/props").json()
    except (httpx.HTTPError, ValueError) as e:
        raise ValueError(f"{m.label} didn't give its template (/props): {e}") from e
    text = props.get("chat_template") if isinstance(props, dict) else None
    if not isinstance(text, str) or not text:
        raise ValueError("This server doesn't expose its chat template (only llama.cpp does).")
    fixed = patched_template(text)
    if fixed is None:
        raise ValueError(
            "Its template has no 'System message must be at the beginning' check I can replace."
        )
    path = home / "templates" / f"{_slug(m.id.removeprefix('local:'))}.jinja"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fixed)
    port = urlparse(m.base).port or 8080
    command = (
        f"llama-server -m <your model.gguf> --alias {m.model} --host 127.0.0.1 --port {port} "
        f"-c {L['recommended_ctx']} --jinja --chat-template-file {path}"
    )
    return {"path": str(path), "command": command}
