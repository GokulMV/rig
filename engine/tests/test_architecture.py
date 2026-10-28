import json
from pathlib import Path

import pytest

from proving_ground.architecture import (
    Architecture,
    find_specs,
    infer_architecture,
    load_architecture,
    parse_spec,
)

ARCHIFY = {
    "schema_version": 1,
    "diagram_type": "architecture",
    "meta": {"title": "Checkout", "output": "checkout.html", "visual_preset": "signal-flow"},
    "components": [
        {
            "id": "buyers",
            "type": "external",
            "label": "Buyers",
            "pos": [40, 250],
            "size": [120, 60],
        },
        {"id": "api", "type": "backend", "label": "Checkout API", "sublabel": "v1"},
        {"id": "orders", "type": "database", "label": "Orders", "sublabel": "PostgreSQL"},
    ],
    "boundaries": [{"kind": "region", "label": "Production", "wraps": ["api", "orders"]}],
    "connections": [
        {"id": "c1", "from": "buyers", "to": "api", "label": "HTTPS", "variant": "emphasis"},
        {"id": "c2", "from": "api", "to": "orders", "label": "SQL"},
    ],
}


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def test_imports_an_archify_spec_and_ignores_extra_fields(tmp_path: Path):
    write(tmp_path, {".archify/architecture-x/candidate.json": json.dumps(ARCHIFY)})
    [spec] = find_specs(tmp_path)
    a = parse_spec(spec)
    assert a.source == "archify" and a.title == "Checkout"
    assert [c.id for c in a.components] == ["buyers", "api", "orders"]
    assert a.connections[0].label == "HTTPS"
    assert a.boundaries[0].wraps == ["api", "orders"]
    # Components without positions get one, so the canvas can draw everything.
    assert all(c.pos is not None for c in a.components)


def test_rejects_other_diagram_types(tmp_path: Path):
    p = tmp_path / "x.sequence.json"
    p.write_text(json.dumps(ARCHIFY | {"diagram_type": "sequence"}))
    assert find_specs(tmp_path) == []
    with pytest.raises(ValueError, match="not an architecture"):
        parse_spec(p)


COMPOSE = """
services:
  api:
    build: ./backend
    depends_on: [db, cache]
  worker:
    build: ./backend
    depends_on:
      - queue
      - db
  db:
    image: postgres:16
  cache:
    image: redis:7
  queue:
    image: rabbitmq:3
  web:
    build: ./web
    depends_on: [api]
"""


def test_infers_components_and_links_from_compose(tmp_path: Path):
    write(tmp_path, {"docker-compose.yml": COMPOSE})
    a = infer_architecture(tmp_path)
    kinds = {c.id: c.type for c in a.components}
    assert kinds == {
        "api": "backend",
        "worker": "backend",
        "db": "database",
        "cache": "database",
        "queue": "messagebus",
        "web": "frontend",
    }
    links = {(c.from_, c.to) for c in a.connections}
    assert ("api", "db") in links and ("web", "api") in links and ("worker", "queue") in links
    assert a.source == "inferred"


def test_infers_from_python_packages_and_their_imports(tmp_path: Path):
    write(
        tmp_path,
        {
            "pyproject.toml": "[project]\nname='shop'\ndependencies=['fastapi','sqlalchemy','redis']\n",
            "src/shop/api/routes.py": "from shop.billing import charge\nfrom shop import store\n",
            "src/shop/api/__init__.py": "",
            "src/shop/billing/__init__.py": "import shop.store\n",
            "src/shop/store/__init__.py": "",
            "web/package.json": '{"dependencies": {"react": "19.0.0"}}',
        },
    )
    a = infer_architecture(tmp_path)
    ids = {c.id: c for c in a.components}
    assert {"shop.api", "shop.billing", "shop.store"} <= set(ids)
    assert ids["web"].type == "frontend" and ids["web"].sublabel == "React"
    assert ids["redis"].type == "database"  # from the redis dependency; nothing is invented
    links = {(c.from_, c.to) for c in a.connections}
    assert ("shop.api", "shop.billing") in links and ("shop.billing", "shop.store") in links


def test_load_prefers_a_spec_and_caches(tmp_path: Path):
    write(
        tmp_path,
        {"docs/checkout.architecture.json": json.dumps(ARCHIFY), "docker-compose.yml": COMPOSE},
    )
    a = load_architecture(tmp_path)
    assert a.source == "archify" and a.title == "Checkout"
    cached = tmp_path / ".proving-ground" / "architecture.json"
    assert Architecture.model_validate_json(cached.read_text()).title == "Checkout"


def test_empty_repo_gives_an_empty_architecture(tmp_path: Path):
    a = load_architecture(tmp_path)
    assert a.components == [] and a.source == "inferred"


def test_layout_skips_empty_columns():
    from proving_ground.architecture import Architecture, Component, layout

    a = Architecture(
        source="inferred",
        components=[
            Component(id="web", type="frontend", label="web"),
            Component(id="api", type="backend", label="api"),
        ],
    )
    xs = [c.pos[0] for c in layout(a).components]
    # frontend and backend sit in adjacent columns: no gap left for the unused "cloud" kind.
    assert xs[1] - xs[0] == 248


# A repo shaped like Rig itself: a React UI over a FastAPI API, a CLI, modules at the
# package root, and outside services reached from the code.
TOOL = {
    "engine/pyproject.toml": (
        "[project]\nname='tool'\ndependencies=['fastapi','anthropic','sqlalchemy','typer']\n"
        "[project.scripts]\ntl = 'tool.cli:app'\n"
    ),
    "engine/src/tool/__init__.py": '"""Tool: grades agents."""\n',
    "engine/src/tool/cli.py": "import typer\nfrom tool.service import go\n",
    "engine/src/tool/service.py": '"""Set up and run a job."""\nfrom tool.store import Store\n',
    "engine/src/tool/store.py": (
        '"""Records in SQLite."""\nimport sqlalchemy\nE = sqlalchemy.create_engine("sqlite:///x.db")\n'
    ),
    "engine/src/tool/api/__init__.py": (
        '"""HTTP API over the engine."""\nfrom fastapi import FastAPI\n'
        "from tool.gen import make\nfrom tool.hub import fetch\nfrom tool.service import go\n"
    ),
    "engine/src/tool/gen/__init__.py": '"""Write tests with the Claude API."""\nimport anthropic\n',
    "engine/src/tool/hub/__init__.py": (
        '"""Skills from GitHub."""\nimport subprocess\n'
        'subprocess.run(["gh", "api", "search/repositories"])\n'
    ),
    "engine/src/tool/run/__init__.py": '"""Run trials."""\nfrom harbor import Job\n',
    "web/package.json": '{"dependencies": {"react": "19.0.0"}, "devDependencies": {"vite": "8"}}',
    "web/src/api.ts": 'export const get = () => fetch("/api/project");\n',
}


def test_infers_a_tool_like_this_one(tmp_path: Path):
    write(tmp_path, TOOL)
    a = infer_architecture(tmp_path)
    c = {x.id: x for x in a.components}
    links = {(x.from_, x.to): x.label for x in a.connections}

    # The UI talks to the API over HTTP.
    assert c["web"].sublabel == "React · Vite"
    assert links[("web", "tool.api")] == "HTTP /api"
    assert c["tool.api"].sublabel == "FastAPI · HTTP API over the engine"
    # The CLI is a way in, too.
    assert c["cli"].type == "frontend" and c["cli"].label == "tl CLI"
    # Modules at the package root are one "core" block, not dropped.
    assert c["tool"].label == "tool core"
    assert ("cli", "tool") in links and ("tool.api", "tool") in links
    # Sub-packages all use the core; that line would say nothing, so it isn't drawn.
    assert ("tool.gen", "tool") not in links
    # Outside services, each from the code that reaches them.
    assert c["claude-api"].type == "external" and ("tool.gen", "claude-api") in links
    assert c["github"].type == "external" and ("tool.hub", "github") in links
    assert c["harbor"].label == "Harbor sandboxes" and ("tool.run", "harbor") in links
    assert c["sqlite"].type == "database" and ("tool", "sqlite") in links
    # Docstrings say what each part does.
    assert c["tool.gen"].sublabel == "Write tests with the Claude API"


def test_layout_flows_left_to_right_along_the_lines(tmp_path: Path):
    write(tmp_path, TOOL)
    a = infer_architecture(tmp_path)
    x = {c.id: c.pos[0] for c in a.components}
    y = {c.id: c.pos[1] for c in a.components}
    assert x["web"] < x["tool.api"] < x["tool.gen"] < x["claude-api"]
    assert x["tool"] < x["sqlite"]
    # No two blocks in the same spot.
    assert len({(x[i], y[i]) for i in x}) == len(x)
