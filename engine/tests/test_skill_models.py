"""The skill matcher's models, with a fake embedder and reranker: no network, no weights.

Candidates are the embedding's nearest and the word rules' best, less those the names rule
out; the reranker decides, under a threshold; scores are cached in memory and on disk; and
when the models are missing, fail to download or fail to load, the word rules match."""

import hashlib
import json
import time
from pathlib import Path

import httpx
import pytest

from proving_ground import lab, skill_match, skill_models

VOCAB = ["test", "review", "diff", "plan", "deploy", "chart", "python", "lint", "invoice"]


class FakeEmbedder:
    """A word-count vector over VOCAB, so "nearest" is predictable."""

    def __init__(self):
        self.calls = 0

    def embed(self, texts, query=False):
        self.calls += 1
        out = []
        for t in texts:
            v = [float(t.lower().count(w)) for w in VOCAB] + [0.01]
            n = sum(x * x for x in v) ** 0.5
            out.append([x / n for x in v])
        return out


class FakeReranker:
    """Scores from a table (skill name -> chance of yes); records what it was asked."""

    def __init__(self, table):
        self.table, self.asked, self.calls = table, [], 0

    def score(self, query, docs):
        self.calls += 1
        self.asked += [d.split(":")[0] for d in docs]
        return [self.table.get(d.split(":")[0].replace(" ", "-"), 0.05) for d in docs]


def models(table, cache=None):
    return skill_models.Models(FakeEmbedder(), FakeReranker(table), cache)


def sk(name, description):
    return {"path": f"/s/{name}", "name": name, "description": description}


LIB = [
    sk("code-review", "Review code changes before merging"),
    sk("test-driven-development", "Write the failing test first"),
    sk("helm-chart-scaffolding", "Template Kubernetes deploy charts"),
    sk("python-lint", "Lint python code"),
    sk("invoice-matching", "Match invoices to orders"),
    sk("writing-plans", "Plan a multi-step task"),
]
STEP = {
    "name": "Review the code diff",
    "does": "Review the code diff for missing tests.",
    "words": [],
    "discipline": "development",
}


@pytest.fixture
def few(monkeypatch):
    """Two candidates from each source, so the union is visible."""
    monkeypatch.setitem(skill_match.M["models"], "candidates", 2)


def test_candidates_are_the_nearest_and_the_word_rules_best(few):
    m = models({"code-review": 0.9})
    got = lab.step_skills(STEP, LIB, 1, m)
    asked = set(m.reranker.asked)
    # Nearest by meaning (review, diff, test) and the word rules' best both reach the reranker...
    assert {"code review", "test driven development"} <= asked
    # ...and nothing else does: neither source ranks these two among its top 2.
    assert "invoice matching" not in asked and "writing plans" not in asked
    assert [s["name"] for s in got] == ["code-review"]


def test_names_that_rule_a_skill_out_keep_it_from_the_reranker(few):
    # python-lint is nearest for a lint step, but the step doesn't say python (specific).
    m = models({"python-lint": 0.99})
    step = {"name": "Lint the code", "does": "Lint lint lint the code.", "words": []}
    assert lab.step_skills(step, LIB, 1, m) == []
    assert "python lint" not in m.reranker.asked
    said = {"name": "Lint the python code", "does": "Lint it.", "words": []}
    assert [s["name"] for s in lab.step_skills(said, LIB, 1, m)] == ["python-lint"]


def test_below_the_threshold_nothing_is_attached():
    th = skill_match.M["models"]["threshold"]
    assert lab.step_skills(STEP, LIB, 1, models({"code-review": th - 0.01})) == []
    assert lab.step_skills(STEP, LIB, 1, models({"code-review": th}))[0]["name"] == "code-review"


def test_best_first_up_to_the_limit_each_saying_why():
    m = models({"code-review": 0.83, "test-driven-development": 0.6})
    got = lab.step_skills(STEP, LIB, 3, m)
    assert [s["name"] for s in got] == ["code-review", "test-driven-development"]
    assert got[0]["why"].startswith("picked by Qwen3-Reranker-0.6B (0.83): the step says ")
    assert "review" in got[0]["why"] and got[0]["path"] == "/s/code-review"
    assert lab.step_skills(STEP, LIB, 1, m) == got[:1]


def test_scores_and_embeddings_are_cached_in_memory_and_on_disk(tmp_path: Path):
    cache = tmp_path / "cache.json"
    m = models({"code-review": 0.9}, cache)
    first = lab.step_skills(STEP, LIB, 1, m)
    calls = (m.embedder.calls, m.reranker.calls)
    assert lab.step_skills(STEP, LIB, 1, m) == first
    assert (m.embedder.calls, m.reranker.calls) == calls  # nothing worked out twice
    m.save()
    again = models({"code-review": 0.1}, cache)  # a reranker that would say otherwise
    assert lab.step_skills(STEP, LIB, 1, again) == first
    assert again.reranker.calls == 0 and again.embedder.calls == 0
    # A changed description is new text: it is embedded and scored again.
    lib = [{**s, "description": s["description"] + "."} for s in LIB]
    lab.step_skills(STEP, lib, 1, again)
    assert again.reranker.calls == 1
    # Another model revision doesn't read the old scores.
    data = json.loads(cache.read_text())
    cache.write_text(json.dumps({**data, "tag": "other"}))
    assert models({}, cache).pair == {}


def _wait(cond, s=10.0):
    end = time.monotonic() + s
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def _on(monkeypatch):
    monkeypatch.delenv(skill_models.OFF, raising=False)


def test_until_the_models_are_ready_the_word_rules_match(monkeypatch, tmp_path: Path):
    _on(monkeypatch)
    gate = []
    fake = models({"code-review": 0.9})

    def slow_download(home, progress):
        progress(123_000_000)
        while not gate:
            time.sleep(0.01)

    m = skill_models.Matcher(tmp_path, download=slow_download, load=lambda h: fake)
    skill_models.use(m)
    m.turn(True)
    st = m.status()
    assert st["state"] == "downloading" and st["note"].startswith("Getting the skill matcher (≈")
    assert "123 so far" in st["note"]
    words = lab.step_skills(STEP, LIB, 1)
    assert words and words[0]["why"].startswith("matched: ")  # the word rules
    gate.append(1)
    assert _wait(lambda: m.state == "ready")
    # Ready, but not warm for this library: still the word rules, and it warms in the background.
    assert lab.step_skills(STEP, LIB, 1)[0]["why"].startswith("matched: ")
    assert _wait(lambda: m.status(LIB)["state"] == "ready")
    assert lab.step_skills(STEP, LIB, 1)[0]["why"].startswith("picked by ")
    assert m.status(LIB)["note"] == "Skills matched by Qwen3-Reranker-0.6B, on this machine."


def test_one_request_is_matched_one_way_even_if_warming_finishes():
    with skill_models.pinned(None):
        assert lab.step_skills(STEP, LIB, 1, None)[0]["why"].startswith("matched: ")
    with skill_models.pinned(models({"code-review": 0.9})):
        assert lab.step_skills(STEP, LIB, 1)[0]["why"].startswith("picked by ")


@pytest.mark.parametrize("where", ["download", "load", "warm"])
def test_a_failure_anywhere_falls_back_to_the_word_rules(monkeypatch, tmp_path: Path, where):
    _on(monkeypatch)

    def boom(*a, **k):
        raise OSError("offline")

    m = skill_models.Matcher(
        tmp_path,
        download=boom if where == "download" else (lambda h, progress: None),
        load=boom if where == "load" else (lambda h: models({"code-review": 0.9})),
        warm=boom if where == "warm" else None,
    )
    skill_models.use(m)
    m.turn(True)
    if where == "warm":
        assert _wait(lambda: m.state == "ready")
        m.ready(LIB)
    assert _wait(lambda: m.state == "failed")
    assert m.status(LIB)["note"] == (
        "Couldn't get the skill matcher (offline); skills matched by word rules."
    )
    assert lab.step_skills(STEP, LIB, 1)[0]["why"].startswith("matched: ")
    m.start()  # no retry before retry_after_s
    assert m.state == "failed"
    m.failed_at -= skill_models.V["retry_after_s"] + 1
    m.start()
    assert m.state != "failed" or m.error == "offline"


def test_nothing_is_downloaded_until_the_user_asks(monkeypatch, tmp_path: Path):
    _on(monkeypatch)
    called = []
    m = skill_models.Matcher(tmp_path, download=lambda *a, **k: called.append(1))
    m.start()  # every Lab visit does this: off stays off
    st = m.status(LIB)
    assert m.state == "off" and not called and m.ready(LIB) is None
    assert st["note"] == "Skills are matched by word rules." and not st["can_turn_off"]
    assert st["offer"] == (
        "Get the better skill matcher (≈1,140 MB download, runs on this machine, ~1.9 GB memory)"
    )


def test_the_choice_is_remembered_and_can_be_undone(monkeypatch, tmp_path: Path):
    _on(monkeypatch)
    m = skill_models.Matcher(
        tmp_path, download=lambda h, progress: None, load=lambda h: models({"code-review": 0.9})
    )
    st = m.turn(True)
    assert st["offer"] is None and st["can_turn_off"]
    assert _wait(lambda: m.state == "ready")
    # After a restart it comes back on by itself: the user asked once.
    again = skill_models.Matcher(
        tmp_path, download=lambda h, progress: None, load=lambda h: models({})
    )
    assert again.state == "idle"
    again.start()
    assert _wait(lambda: again.state == "ready")
    st = again.turn(False)
    assert again.state == "off" and again.models is None and again.ready(LIB) is None
    assert st["offer"] and not st["can_turn_off"]
    assert skill_models.Matcher(tmp_path).state == "off"


def test_turning_it_off_stops_a_download_and_keeps_no_result(monkeypatch, tmp_path: Path):
    _on(monkeypatch)
    started, stopped = [], []

    def download(home, progress):
        started.append(1)
        try:
            while True:
                progress(1)
                time.sleep(0.01)
        except BaseException:
            stopped.append(1)
            raise

    m = skill_models.Matcher(tmp_path, download=download, load=lambda h: models({}))
    m.turn(True)
    assert _wait(lambda: started)
    m.turn(False)
    assert _wait(lambda: stopped)
    time.sleep(0.05)
    assert m.state == "off" and m.error is None and m.models is None


def test_the_override_keeps_it_off_whatever_was_chosen(monkeypatch, tmp_path: Path):
    _on(monkeypatch)
    skill_models.Matcher(tmp_path).turn(True)
    monkeypatch.setenv(skill_models.OFF, "off")
    called = []
    m = skill_models.Matcher(tmp_path, download=lambda *a, **k: called.append(1))
    m.start()
    st = m.status()
    assert m.state == "disabled" and not called and st["offer"] is None
    assert not st["can_turn_off"] and "PG_SKILL_MODELS" in st["note"]
    with pytest.raises(PermissionError):
        m.turn(True)


def test_models_already_on_disk_are_loaded_not_downloaded(monkeypatch, tmp_path: Path):
    _on(monkeypatch)
    pins = _tiny_pins(monkeypatch)
    for k, (path, data) in pins.items():
        p = skill_models.model_dir(skill_models.V[k], tmp_path) / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    called = []
    m = skill_models.Matcher(
        tmp_path, download=lambda *a, **k: called.append(1), load=lambda h: models({})
    )
    m.turn(True)
    assert _wait(lambda: m.state == "ready") and not called


def _tiny_pins(monkeypatch) -> dict:
    """Replace each model's pinned files with one small file, for download tests."""
    out = {}
    for k in ("embed", "rerank"):
        data = f"weights of {k}".encode()
        spec = {
            **skill_models.V[k],
            "files": {"w.bin": {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}},
        }
        monkeypatch.setitem(skill_models.V, k, spec)
        out[k] = ("w.bin", data)
    return out


def test_fetch_gets_the_pinned_files_from_hugging_face_with_no_credentials(
    monkeypatch, tmp_path: Path
):
    pins = _tiny_pins(monkeypatch)
    seen = []

    def serve(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        k = "embed" if "bge" in req.url.path else "rerank"
        return httpx.Response(200, content=pins[k][1])

    got = []
    with httpx.Client(transport=httpx.MockTransport(serve)) as http:
        skill_models.fetch(tmp_path, progress=got.append, http=http)
    assert skill_models.present(tmp_path)
    e = skill_models.V["embed"]
    assert str(seen[0].url) == (f"https://huggingface.co/{e['repo']}/resolve/{e['revision']}/w.bin")
    assert all("authorization" not in r.headers for r in seen)
    assert got[-1] == sum(len(d) for _, d in pins.values())
    # Already there: nothing is downloaded again.
    seen.clear()
    with httpx.Client(transport=httpx.MockTransport(serve)) as http:
        skill_models.fetch(tmp_path, http=http)
    assert seen == []


def test_fetch_throws_away_a_file_that_isnt_the_pinned_one(monkeypatch, tmp_path: Path):
    pins = _tiny_pins(monkeypatch)
    n = len(pins["embed"][1])
    bad = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * n))
    with httpx.Client(transport=bad) as http, pytest.raises(RuntimeError, match="pinned hash"):
        skill_models.fetch(tmp_path, http=http)
    assert not skill_models.present(tmp_path)
    assert not list(tmp_path.rglob("*.bin")) and not list(tmp_path.rglob("*.part"))


def test_fetch_refuses_models_over_the_size_limit(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(skill_models.V, "download_max_mb", 1)
    never = httpx.MockTransport(lambda r: pytest.fail("downloaded anyway"))
    with httpx.Client(transport=never) as http, pytest.raises(RuntimeError, match="1 MB limit"):
        skill_models.fetch(tmp_path, http=http)


def test_the_pinned_models_fit_the_download_limit():
    v = skill_models.V
    assert skill_models.total_bytes() <= v["download_max_mb"] * 1e6
    for k in ("embed", "rerank"):
        assert len(v[k]["revision"]) == 40 and v[k]["model"] in v[k]["files"]
        assert all(len(f["sha256"]) == 64 for f in v[k]["files"].values())


def test_the_lab_says_which_matcher_picked_its_skills(monkeypatch, tmp_path: Path):
    from fastapi.testclient import TestClient
    from test_api_workspace import BASE, ORIGIN
    from test_catalog import FakeGitHub

    from proving_ground.agents import Credentials
    from proving_ground.api.app import create_app
    from proving_ground.workspace import Workspace

    _on(monkeypatch)
    skills_dir = tmp_path / "skills" / "tdd"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: tdd\ndescription: Write a failing test first\n---\nRed, green.\n"
    )
    matcher = skill_models.Matcher(
        tmp_path / "models",
        download=lambda h, progress: None,
        load=lambda h: models({"tdd": 0.9}),
        warm=lambda m, lib: lab.warm_skills(lib, m),
    )
    c = TestClient(
        create_app(
            workspace=Workspace(tmp_path / "ws.json"),
            credentials=Credentials(env={}, home=tmp_path / "h"),
            github=FakeGitHub(),
            home=tmp_path / "home",
            user_skills_dir=tmp_path / "skills",
            web_dist=tmp_path / "nodist",
            host_login=lambda: None,
            skill_matcher=matcher,
        ),
        base_url=BASE,
    )
    first = c.get("/api/lab").json()["matcher"]
    assert first["model"] == "Qwen3-Reranker-0.6B" and first["mb"] > 1000
    assert first["state"] == "off" and first["offer"].startswith("Get the better skill matcher")
    assert c.post("/api/lab/matcher", json={"on": True}).status_code == 403  # not from the app
    on = c.post("/api/lab/matcher", json={"on": True}, headers=ORIGIN).json()
    assert on["state"] in ("downloading", "loading", "warming") and on["can_turn_off"]
    assert _wait(lambda: c.get("/api/lab").json()["matcher"]["state"] == "ready", 30)
    lab_ = c.get("/api/lab").json()
    dev = next(d for d in lab_["disciplines"] if d["id"] == "development")
    whys = [s["why"] for w in dev["workflows"] for st in w["steps"] for s in st["skills"]]
    assert whys and all(w.startswith("picked by Qwen3-Reranker-0.6B (0.90)") for w in whys)
    r = c.post("/api/lab/random", json={"discipline": "development", "seed": 3}, headers=ORIGIN)
    wf = r.json()
    assert r.status_code == 200, wf
    assert all(s["why"].startswith("picked by ") for st in wf["steps"] for s in st["skills"])


def test_fetch_stops_at_its_deadline_and_leaves_no_half_file(monkeypatch, tmp_path: Path):
    _tiny_pins(monkeypatch)
    monkeypatch.setitem(skill_models.V, "download_timeout_s", -1)  # already past it
    slow = httpx.MockTransport(lambda r: httpx.Response(200, content=b"partial"))
    with httpx.Client(transport=slow) as http, pytest.raises(TimeoutError):
        skill_models.fetch(tmp_path, http=http)
    assert not list(tmp_path.rglob("*.part")) and not skill_models.present(tmp_path)


def test_a_server_error_leaves_no_half_file(monkeypatch, tmp_path: Path):
    _tiny_pins(monkeypatch)
    down = httpx.MockTransport(lambda r: httpx.Response(503))
    with httpx.Client(transport=down) as http, pytest.raises(httpx.HTTPStatusError):
        skill_models.fetch(tmp_path, http=http)
    assert not list(tmp_path.rglob("*.part"))


def test_the_lab_can_turn_it_off_again(monkeypatch, tmp_path: Path):
    from fastapi.testclient import TestClient
    from test_api_workspace import BASE, ORIGIN
    from test_catalog import FakeGitHub

    from proving_ground.agents import Credentials
    from proving_ground.api.app import create_app
    from proving_ground.workspace import Workspace

    def app_(env_off: bool):
        if env_off:
            monkeypatch.setenv(skill_models.OFF, "off")
        else:
            monkeypatch.delenv(skill_models.OFF, raising=False)
        return TestClient(
            create_app(
                workspace=Workspace(tmp_path / "ws.json"),
                credentials=Credentials(env={}, home=tmp_path / "h"),
                github=FakeGitHub(),
                home=tmp_path / "home",
                web_dist=tmp_path / "nodist",
                host_login=lambda: None,
                skill_matcher=skill_models.Matcher(
                    tmp_path / "models",
                    download=lambda h, progress: None,
                    load=lambda h: models({}),
                ),
            ),
            base_url=BASE,
        )

    c = app_(False)
    c.post("/api/lab/matcher", json={"on": True}, headers=ORIGIN)
    off = c.post("/api/lab/matcher", json={"on": False}, headers=ORIGIN).json()
    assert off["state"] == "off" and off["offer"] and not off["can_turn_off"]
    r = app_(True).post("/api/lab/matcher", json={"on": True}, headers=ORIGIN)
    assert r.status_code == 409 and "PG_SKILL_MODELS" in r.json()["detail"]
