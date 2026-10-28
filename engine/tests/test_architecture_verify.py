import json
from pathlib import Path

from test_architecture import TOOL, write

from proving_ground.architecture import infer_architecture, load_architecture, parse_data
from proving_ground.architecture.verify import verify


def spec(components, connections=()):
    return parse_data(
        {
            "diagram_type": "architecture",
            "components": components,
            "connections": list(connections),
        },
        source="mapped",
    )


def test_a_spec_is_checked_against_the_code(tmp_path: Path):
    write(tmp_path, TOOL)
    s = spec(
        [
            {
                "id": "ui",
                "type": "frontend",
                "label": "Web UI",
                "sublabel": "React",
                "evidence": ["web/"],
            },
            {
                "id": "gen",
                "type": "backend",
                "label": "Generator",
                "evidence": ["engine/src/tool/gen/__init__.py"],
            },
            {"id": "claude", "type": "external", "label": "Claude API"},
            # Invented: nothing in the repo is a Redis cache.
            {
                "id": "redis",
                "type": "database",
                "label": "Redis cache",
                "evidence": ["infra/redis.conf"],
            },
            # Its evidence exists, but doesn't name it.
            {
                "id": "ledger",
                "type": "backend",
                "label": "Ledger",
                "evidence": ["engine/src/tool/hub/__init__.py"],
            },
        ],
        [{"from": "gen", "to": "claude"}, {"from": "ui", "to": "redis"}],
    )
    out = verify(tmp_path, s, infer_architecture(tmp_path))
    c = {x.id: x for x in out.components}
    assert c["ui"].check == "found" and c["gen"].check == "found"
    assert c["claude"].check == "found" and "found it too" in c["claude"].why
    assert c["redis"].check == "missing" and "infra/redis.conf" in c["redis"].why
    assert c["ledger"].check == "weak"
    # What reading the code found and the spec left out.
    assert {"tl CLI", "SQLite", "GitHub API", "Harbor sandboxes"} <= set(out.check["missed"])
    lines = {(x.from_, x.to): x.check for x in out.connections}
    assert lines[("gen", "claude")] == "found" and lines[("ui", "redis")] == "unchecked"
    assert out.check["found"] == 3 and out.check["missing"] == 1
    assert out.check["summary"].startswith("3 of 5 parts found in the code, 1 not found")


def test_loading_a_mapped_spec_checks_it(tmp_path: Path):
    write(tmp_path, TOOL)
    (tmp_path / ".proving-ground").mkdir()
    (tmp_path / ".proving-ground" / "archify.json").write_text(
        json.dumps(
            {
                "diagram_type": "architecture",
                "components": [{"id": "ghost", "type": "backend", "label": "Billing service"}],
            }
        )
    )
    a = load_architecture(tmp_path, refresh=True)
    assert a.source == "mapped" and a.components[0].check == "missing"
    assert a.check["missing"] == 1
