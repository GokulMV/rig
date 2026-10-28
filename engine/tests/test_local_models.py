import json
from pathlib import Path

import httpx
import pytest

from proving_ground import local_models as lm
from proving_ground.agents import model_hosts
from proving_ground.generate.prompt import Prompt


def server(tools: bool = True, anthropic: bool = True, reply: dict | None = None):
    """A fake local machine: Ollama on 11434, another app (HTML) on 8080, nothing else."""
    seen: list[dict] = []

    def handle(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url == "http://127.0.0.1:11434/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "qwen3:8b"}, {"name": "llama3.2"}]}
            )
        if url == "http://127.0.0.1:8080/v1/models":
            return httpx.Response(
                200, text="<!doctype html>", headers={"content-type": "text/html"}
            )
        if url.endswith("/v1/messages"):
            if anthropic:
                return httpx.Response(400, json={"error": "messages required"})
            return httpx.Response(404, text="not found")
        if url.endswith("/v1/chat/completions"):
            body = json.loads(req.content)
            seen.append(body)
            if "tools" in body and not tools:
                return httpx.Response(400, json={"error": "tools not supported"})
            if "tools" in body:
                args = json.dumps(reply or {"answer": 42, "word": "ready"})
                msg = {
                    "tool_calls": [
                        {
                            "function": {
                                "name": body["tools"][0]["function"]["name"],
                                "arguments": args,
                            }
                        }
                    ]
                }
            else:
                msg = {
                    "content": "<think>hmm {not json}</think>\nHere: "
                    + json.dumps(reply or {"answer": 42, "word": "ready"})
                }
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": msg}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3},
                },
            )
        raise httpx.ConnectError("refused", request=req)

    return httpx.Client(transport=httpx.MockTransport(handle)), seen


def test_only_local_hosts_are_accepted():
    for ok in (
        "http://127.0.0.1:11434",
        "http://localhost:1234",
        "http://192.168.1.9:8000",
        "http://gpu-box.local:8080",
        "http://host.docker.internal:11434",
        "http://[::1]:8080",
    ):
        assert lm.is_local(ok), ok
    for bad in (
        "https://api.openai.com",
        "http://8.8.8.8:11434",
        "ftp://127.0.0.1",
        "http://169.254.1.1",
    ):
        assert not lm.is_local(bad), bad
    with pytest.raises(ValueError, match="nothing you test leaves"):
        lm.make("https://models.example.com", "x")


def test_detect_finds_real_servers_and_skips_other_apps():
    http, _ = server()
    found = lm.detect(http)
    assert [m.model for m in found] == ["qwen3:8b", "llama3.2"]
    assert all(m.kind == "ollama" and m.anthropic for m in found)
    assert found[0].id == "local:ollama-11434-qwen3-8b"


def test_forced_tool_call_then_json_fallback():
    http, seen = server()
    m = lm.make("http://127.0.0.1:11434/v1", "qwen3:8b", "ollama")
    assert m.base == "http://127.0.0.1:11434"
    assert lm.try_model(lm.OpenAICompatClient(m, http))["ok"]
    assert (
        seen[-1]["model"] == "qwen3:8b"
        and seen[-1]["tool_choice"]["function"]["name"] == "emit_check"
    )

    http, seen = server(tools=False)
    call = lm.OpenAICompatClient(m, http).call(
        Prompt("sys", [{"type": "text", "text": "q"}]), lm.PING, "claude-haiku-5-5", 100
    )
    assert call.input == {"answer": 42, "word": "ready"} and call.tokens_in == 7
    assert "tools" not in seen[-1] and seen[-1]["max_tokens"] >= 4096

    http, _ = server(reply={"answer": 41, "word": "ready"})
    r = lm.try_model(lm.OpenAICompatClient(m, http))
    assert not r["ok"] and "instead of answer 42" in r["why"]


def test_registry_keeps_no_secrets_and_tracks_the_helper(tmp_path: Path):
    reg = lm.Registry(tmp_path / "local-models.json")
    m = reg.add(lm.make("http://127.0.0.1:11434", "qwen3:8b", "ollama"))
    reg.set_helper(m.id)
    assert reg.helper() == m
    reg.remove(m.id)
    assert reg.helper() is None and reg.models() == []
    with pytest.raises(KeyError):
        reg.set_helper("local:nope")


def test_sandbox_reaches_only_the_model_host():
    assert model_hosts("claude-code") == ["api.anthropic.com"]
    assert model_hosts(
        "claude-code", {"ANTHROPIC_BASE_URL": "http://host.docker.internal:8089"}
    ) == ["host.docker.internal"]
    assert model_hosts("unknown-agent") == []


def test_harbor_gets_the_hosts_for_the_agent_phase_only(tmp_path: Path):
    from proving_ground.runner.harbor import HarborRunner

    seen = []

    class R:
        exception_info = None
        verifier_result = type("V", (), {"rewards": {"reward": 1.0}})()
        trial_name = "t"
        started_at = finished_at = None
        agent_result = None

    def executor(req):
        seen.append(req)
        return R()

    from proving_ground.models import Scenario

    sc = Scenario(id="s", kind="typical", title="t", instruction="i", check="true")
    runner = HarborRunner(
        {"s": tmp_path},
        tmp_path,
        "anthropic/x",
        executor=executor,
        env={"ANTHROPIC_BASE_URL": "http://host.docker.internal:11434"},
    )
    runner.preflight(sc, tmp_path)
    assert seen[-1].hosts == ()  # the check-only preflight gets no network
    assert runner._hosts == ("host.docker.internal",)


def test_api_adds_tests_and_uses_a_local_model_for_helper_calls(tmp_path: Path):
    from fastapi.testclient import TestClient
    from test_api_workspace import BASE, ORIGIN
    from test_catalog import FakeGitHub

    from proving_ground.agents import Credentials
    from proving_ground.api.app import create_app
    from proving_ground.workspace import Workspace

    http, seen = server()
    c = TestClient(
        create_app(
            workspace=Workspace(tmp_path / "ws.json"),
            credentials=Credentials(env={}, home=tmp_path / "h"),
            github=FakeGitHub(),
            home=tmp_path / "home",
            user_skills_dir=tmp_path / "skills",
            web_dist=tmp_path / "nodist",
            host_login=lambda: None,
            local_http=http,
        ),
        base_url=BASE,
    )
    got = c.get("/api/local-models?scan=true").json()
    assert got["models"] == [] and [f["model"] for f in got["found"]] == ["qwen3:8b", "llama3.2"]
    r = c.post(
        "/api/local-models", json={"base": "https://api.openai.com", "model": "gpt"}, headers=ORIGIN
    )
    assert r.status_code == 422
    added = c.post(
        "/api/local-models",
        json={"base": "http://127.0.0.1:11434", "model": "qwen3:8b", "kind": "ollama"},
        headers=ORIGIN,
    ).json()
    mid = added["models"][0]["id"]
    assert added["models"][0]["anthropic"] is True
    assert c.post(f"/api/local-models/{mid}/test", headers=ORIGIN).json()["ok"]
    assert (
        c.post("/api/local-models/helper", json={"id": mid}, headers=ORIGIN).json()["helper"] == mid
    )
    assert c.get("/api/lab").json()["local_models"][0]["id"] == mid
    # The judge's calibration now runs on the local model: no key, no Claude login.
    n = len(seen)
    cal = c.post("/api/lab/benches/product/calibrate", headers=ORIGIN)
    assert cal.status_code == 200, cal.text
    assert len(seen) > n and all(b["model"] == "qwen3:8b" for b in seen[n:])
    assert not (tmp_path / "home" / "local-models.json").read_text().count("key")


QWEN_LIKE = (
    "{%- for m in messages %}{%- if m.role == 'system' and not loop.first %}\n"
    '    {{- raise_exception("System message must be at the beginning.") }}\n'
    "{%- endif %}{{- '<|im_start|>' + m.role + '\\n' + m.content + '<|im_end|>' + '\\n' }}{%- endfor %}"
)


def ready_server(
    messages=None, props=None, show=None, helper: bool = True
) -> tuple[httpx.Client, list[dict]]:
    """A fake server for the readiness stages. `messages` is the /v1/messages reply (a Response)."""
    seen: list[dict] = []
    tool_use = {"content": [{"type": "tool_use", "name": "ready_check", "input": {"status": "ok"}}]}

    def handle(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/v1/chat/completions":
            args = json.dumps({"answer": 42, "word": "ready"})
            msg = {"tool_calls": [{"function": {"name": "emit_check", "arguments": args}}]}
            return httpx.Response(200, json={"choices": [{"message": msg}]})
        if path == "/v1/messages":
            seen.append(json.loads(req.content))
            return messages or httpx.Response(200, json=tool_use)
        if path == "/props":
            return httpx.Response(200, json=props if props is not None else {})
        if path == "/api/show":
            return httpx.Response(200, json=show or {})
        raise httpx.ConnectError("refused", request=req)

    return httpx.Client(transport=httpx.MockTransport(handle)), seen


def probe(http, kind="llamacpp", anthropic=True) -> dict:
    m = lm.make("http://127.0.0.1:8089", "qwen3.5-9b", kind)
    m = lm.LocalModel(m.id, m.label, m.base, m.model, m.kind, anthropic)
    return lm.try_model(lm.OpenAICompatClient(m, http))


def test_ready_everywhere_sends_claude_codes_shape():
    http, seen = ready_server(props={"default_generation_settings": {"n_ctx": 65536}})
    r = probe(http)
    assert r["ok"] and r["helper_ok"] and r["claude_code_ok"] is True
    assert r["context_tokens"] == 65536 and r["warnings"] == [] and r["fix_command"] is None
    assert [s["name"] for s in r["stages"]] == ["helper", "agent", "context"]
    body = seen[0]
    assert body["tool_choice"] == {"type": "any"} and body["system"] == "You are a coding agent."
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert body["tools"][0]["name"] == "ready_check" and body["model"] == "qwen3.5-9b"


def test_template_that_refuses_later_system_messages_offers_a_fix():
    err = httpx.Response(
        500, json={"error": {"message": "System message must be at the beginning."}}
    )
    r = probe(ready_server(messages=err)[0])
    assert r["helper_ok"] and r["claude_code_ok"] is False
    agent = r["stages"][1]
    assert not agent["ok"] and "refuses later system messages" in agent["why"]
    assert "Save a fixed template" in r["fix_command"]


def test_dropped_tool_calls_are_named():
    text_only = httpx.Response(200, json={"content": [{"type": "text", "text": "Sure!"}]})
    r = probe(ready_server(messages=text_only)[0])
    assert r["claude_code_ok"] is False and r["fix_command"] is None
    assert "drops tool calls (chatml does)" in r["stages"][1]["why"]


def test_small_context_warns_and_blocks_claude_code():
    r = probe(ready_server(props={"n_ctx": 8192})[0])
    assert r["context_tokens"] == 8192 and r["claude_code_ok"] is False and r["helper_ok"]
    assert r["warnings"] == [
        "Context is 8192 tokens; Claude Code needs at least 32k (-c 65536 recommended)."
    ]


def test_ollama_context_from_api_show_and_unknown_is_none():
    show = {"model_info": {"qwen3.context_length": 40960}, "parameters": "stop <x>"}
    r = probe(ready_server(show=show)[0], kind="ollama")
    assert r["context_tokens"] == 40960 and r["claude_code_ok"] is True
    low = {"model_info": {"qwen3.context_length": 40960}, "parameters": "num_ctx 4096\nstop x"}
    r = probe(ready_server(show=low)[0], kind="ollama")
    assert r["context_tokens"] == 4096 and r["claude_code_ok"] is False
    r = probe(ready_server(show={})[0], kind="ollama")
    assert r["context_tokens"] is None and r["claude_code_ok"] is True and not r["warnings"]


def test_no_anthropic_api_means_claude_code_unknown():
    r = probe(ready_server()[0], anthropic=False)
    assert r["claude_code_ok"] is None and [s["name"] for s in r["stages"]] == ["helper", "context"]


def test_patched_template_turns_the_check_into_a_system_turn():
    out = lm.patched_template(QWEN_LIKE)
    assert out and "raise_exception" not in out
    assert "{{- '<|im_start|>system\\n' + content + '<|im_end|>' + '\\n' }}" in out
    assert "{%- endfor %}" in out  # the rest is untouched
    loose = "<|im_start|>{{raise_exception('System message must be at the beginning')-}}"
    assert "raise_exception" not in (lm.patched_template(loose) or "raise_exception")
    assert lm.patched_template(loose) is not None
    assert lm.patched_template(QWEN_LIKE.replace("<|im_start|>", "<s>")) is None
    assert lm.patched_template("<|im_start|>{{ content }}") is None


def test_template_fix_endpoint_saves_under_home(tmp_path: Path):
    from fastapi.testclient import TestClient
    from test_api_workspace import BASE, ORIGIN
    from test_catalog import FakeGitHub

    from proving_ground.agents import Credentials
    from proving_ground.api.app import create_app
    from proving_ground.workspace import Workspace

    http, _ = ready_server(props={"chat_template": QWEN_LIKE})
    c = TestClient(
        create_app(
            workspace=Workspace(tmp_path / "ws.json"),
            credentials=Credentials(env={}, home=tmp_path / "h"),
            github=FakeGitHub(),
            home=tmp_path / "home",
            user_skills_dir=tmp_path / "skills",
            web_dist=tmp_path / "nodist",
            host_login=lambda: None,
            local_http=http,
        ),
        base_url=BASE,
    )
    m = lm.make("http://127.0.0.1:8089", "qwen3.5-9b", "llamacpp")
    lm.Registry(tmp_path / "home" / "local-models.json").add(m)
    r = c.post(f"/api/local-models/{m.id}/template-fix", headers=ORIGIN)
    assert r.status_code == 200, r.text
    got = r.json()
    saved = Path(got["path"])
    assert (
        saved.parent == tmp_path / "home" / "templates"
        and "raise_exception" not in saved.read_text()
    )
    assert got["command"].startswith("llama-server -m <your model.gguf> --alias qwen3.5-9b ")
    assert "--port 8089 -c 65536 --jinja --chat-template-file " + got["path"] in got["command"]
    assert c.post("/api/local-models/local:nope/template-fix", headers=ORIGIN).status_code == 404


def test_agent_env_points_claude_code_in_the_sandbox_at_the_host_server():
    m = lm.make("http://127.0.0.1:8096", "qwen3.5-9b", "llamacpp")
    model, env = lm.agent_env(m)
    assert model == "qwen3.5-9b"  # the server's own id, passed through as is
    assert env["ANTHROPIC_BASE_URL"] == "http://host.docker.internal:8096"
    assert env["ANTHROPIC_API_KEY"] == "local"
    # Only the local server is reachable from the sandbox: never Anthropic's API.
    assert model_hosts("claude-code", env) == ["host.docker.internal"]
