"""The document judge: steady at temperature 0, strict calibration, kept on disk, and gated for
local models."""

import json
from pathlib import Path
from types import SimpleNamespace

from test_api_workspace import BASE, ORIGIN
from test_bench import _lab_client, _starter, _wait

from proving_ground import judge
from proving_ground import local_models as lm
from proving_ground.generate.client import AnthropicClient, ToolCall
from proving_ground.generate.prompt import Prompt


class Scored:
    """A judge that scores a document 5 if it says GOOD, 4 if MID, else 1 or 2 by the BAD2 tag."""

    def __init__(self):
        self.temps = []

    def with_temperature(self, t):
        self.temps.append(t)
        return self

    def call(self, prompt, tool, model, max_tokens):
        text = prompt.content[0]["text"]
        doc = text[text.index("<document>") : text.index("</document>")]
        n = text.count("\n", text.index("<rubric>"), text.index("</rubric>")) - 1
        score = 5 if "GOOD" in doc else 3 if "MID" in doc else 1
        return ToolCall(
            {"scores": [{"criterion": "c", "score": score, "evidence": "e"}] * n}, "tool_use", 1, 1
        )


def test_anthropic_client_passes_temperature():
    seen = []

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return SimpleNamespace(
                content=[SimpleNamespace(type="tool_use", name="t", input={})],
                stop_reason="tool_use",
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    fake = SimpleNamespace(
        messages=SimpleNamespace(stream=lambda **kw: (seen.append(kw), Stream())[1])
    )
    c = AnthropicClient(fake)
    c.call(Prompt("s", [{"type": "text", "text": "x"}]), {"name": "t"}, "m", 5)
    c.with_temperature(0).call(Prompt("s", [{"type": "text", "text": "x"}]), {"name": "t"}, "m", 5)
    assert "temperature" not in seen[0] and seen[1]["temperature"] == 0


def test_grade_and_calibrate_ask_for_temperature_zero():
    m = Scored()
    judge.grade(m, "t", ["a"], "GOOD")
    judge.calibrate(m, "t", ["a"], "GOOD", "bad")
    assert m.temps == [0, 0, 0, 0]


def cal(good, bad):
    return judge.calibrate(Scored(), "t", ["a", "b"], good, bad)


def test_calibration_edge_cases():
    ok = cal("GOOD", "bad")
    assert ok["trustworthy"] and ok["reason"] == ""
    # Gap is wide enough but the bad example still passes the bar.
    assert not cal("GOOD", "GOOD")["trustworthy"]
    # Good example below the bar (mean 3 < 3.5).
    low = cal("MID", "bad")
    assert not low["trustworthy"] and "good example failed" in low["reason"].lower()
    # Everything scores good: bad passes, no gap.
    allgood = cal("GOOD", "GOOD")
    assert not allgood["trustworthy"] and "bad example passed" in allgood["reason"]
    # Bad fails the bar but is not far enough under it / apart (3 vs 3.5 good would need a 4 good).
    close = judge.calibrate(Scored(), "t", ["a"], "GOOD", "MID")
    assert not close["trustworthy"] and close["gap"] == 2.0 and "not below" in close["reason"]


def test_calibration_persists_across_apps(tmp_path: Path, monkeypatch):
    import proving_ground.api.app as api_app

    monkeypatch.setattr(api_app, "AnthropicClient", lambda *a, **k: ProductJudge())
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    assert c.post("/api/lab/benches/product/calibrate", headers=ORIGIN).json()["trustworthy"]
    assert (tmp_path / "home" / "calibrations.json").is_file()
    c2, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    row = next(b for b in c2.get("/api/lab/benches").json() if b["id"] == "product")
    assert row["calibration"]["trustworthy"] is True
    # A different judge sees none.
    reg = lm.Registry(tmp_path / "home" / "local-models.json")
    m = reg.add(lm.make("http://127.0.0.1:11434", "qwen3:8b", "ollama"))
    reg.set_helper(m.id)
    row = next(b for b in c2.get("/api/lab/benches").json() if b["id"] == "product")
    assert row["calibration"] is None


class ProductJudge:
    def call(self, prompt, tool, model, max_tokens):
        text = prompt.content[0]["text"]
        doc = text[text.index("<document>") : text.index("</document>")]
        n = text.count("\n", text.index("<rubric>"), text.index("</rubric>")) - 1
        bad = "TBD" in doc or "None expected" in doc or "chatbot that answers" in doc
        return ToolCall(
            {"scores": [{"criterion": "c", "score": 2 if bad else 5, "evidence": "e"}] * n},
            "tool_use",
            1,
            1,
        )


def test_local_judge_is_gated_until_calibrated(tmp_path: Path, monkeypatch):
    import httpx

    import proving_ground.api.app as api_app

    def chat(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)

        user = body["messages"][1]["content"]
        doc = user[user.index("<document>") : user.index("</document>")]
        bad = "TBD" in doc or "None expected" in doc or "chatbot that answers" in doc
        n = user.count("\n", user.index("<rubric>"), user.index("</rubric>")) - 1
        args = {"scores": [{"criterion": "c", "score": 2 if bad else 5, "evidence": "e"}] * n}
        msg = {
            "tool_calls": [
                {
                    "function": {
                        "name": body["tools"][0]["function"]["name"],
                        "arguments": json.dumps(args),
                    }
                }
            ]
        }
        return httpx.Response(200, json={"choices": [{"message": msg}], "usage": {}})

    monkeypatch.setattr(api_app, "AnthropicClient", lambda *a, **k: ProductJudge())
    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    # Rebuild the app with a local transport so the helper is reachable.
    from fastapi.testclient import TestClient
    from test_catalog import FakeGitHub

    from proving_ground.agents import Credentials
    from proving_ground.api.app import create_app
    from proving_ground.workspace import Workspace

    reg = lm.Registry(tmp_path / "home" / "local-models.json")
    m = reg.add(lm.make("http://127.0.0.1:11434", "qwen3:8b", "ollama"))
    reg.set_helper(m.id)
    c = TestClient(
        create_app(
            workspace=Workspace(tmp_path / "ws2.json"),
            credentials=Credentials(env={"ANTHROPIC_API_KEY": "k"}, home=tmp_path / "h"),
            github=FakeGitHub(),
            home=tmp_path / "home",
            user_skills_dir=tmp_path / "none",
            web_dist=tmp_path / "nodist",
            host_login=lambda: None,
            local_http=httpx.Client(transport=httpx.MockTransport(chat)),
        ),
        base_url=BASE,
    )
    a = _starter(c, "Write a PRD") if _has(c, "Write a PRD") else _any_starter(c)
    body = {"workflow": a, "bench": "product", "budget": 5, "auto": False}
    r = c.post("/api/lab/run", json=body, headers=ORIGIN)
    assert r.status_code == 409 and "Check the judge first" in r.json()["detail"]
    cal = c.post("/api/lab/benches/product/calibrate", headers=ORIGIN).json()
    assert cal["trustworthy"], cal
    r = c.post("/api/lab/run", json=body, headers=ORIGIN)
    assert r.status_code == 200, r.text
    _wait(c, 1)


def _names(c):
    return [w["name"] for d in c.get("/api/lab").json()["disciplines"] for w in d["workflows"]]


def _has(c, name):
    return name in _names(c)


def _any_starter(c):
    return _starter(c, _names(c)[0])
