from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from proving_ground.api.app import create_app
from proving_ground.cli import app

BASE = "http://127.0.0.1:7357"


def test_serves_the_built_app_next_to_the_api(tmp_path: Path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Rig</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    c = TestClient(create_app(tmp_path, web_dist=dist), base_url=BASE)
    assert "<title>Rig</title>" in c.get("/").text
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/api/project").status_code == 200


def test_the_page_is_never_cached_but_its_hashed_assets_are(tmp_path: Path):
    """After an update the browser must fetch the new page, which names the new assets."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Rig</title>")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)")
    c = TestClient(create_app(tmp_path, web_dist=dist), base_url=BASE)
    assert c.get("/").headers["cache-control"] == "no-cache"
    assert c.get("/index.html").headers["cache-control"] == "no-cache"
    assert "immutable" in c.get("/assets/index-abc123.js").headers["cache-control"]


def test_explains_how_to_build_when_the_app_is_missing(tmp_path: Path):
    c = TestClient(create_app(tmp_path, web_dist=tmp_path / "nope"), base_url=BASE)
    r = c.get("/")
    assert r.status_code == 200 and "npm run build" in r.text


def test_pg_serve_binds_to_localhost_only(tmp_path: Path, monkeypatch):
    seen = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: seen.update(kw, app=app))
    monkeypatch.setattr("proving_ground.api.app.HOME", tmp_path / "home")  # never the real one
    repo = tmp_path / "repo"
    repo.mkdir()
    r = CliRunner().invoke(app, ["serve", "--port", "7400", "--root", str(repo)])
    assert r.exit_code == 0, r.output
    assert seen["host"] == "127.0.0.1" and seen["port"] == 7400
    assert "http://127.0.0.1:7400" in r.output and "(repo)" in r.output
    assert "repo" in (tmp_path / "home" / "workspace.json").read_text()
