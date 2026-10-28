"""The skills are the rules: every one parses, and the code runs on their values."""

from proving_ground import catalog, estimate, skills, stats
from proving_ground.architecture import mapper
from proving_ground.generate import prompt


def test_every_skill_parses_with_a_description_and_values():
    for name in skills.NAMES:
        s = skills.load(name)
        assert s.name == name and s.description and s.values and s.body.startswith("# ")


def test_the_code_uses_the_skill_values():
    assert estimate.MODEL == skills.value("estimate-effect", "model") == "claude-haiku-5-5"
    assert estimate.SYSTEM.startswith("You estimate whether adding an agent skill")
    assert mapper.PROMPT.startswith("Map the architecture of the repository")
    assert "Read,Glob,Grep" in mapper.READ_ONLY["claude-code"]("x")
    assert prompt.SYSTEM.startswith("You design test scenarios")
    assert prompt.MAX_SOURCE_CHARS == skills.value("generate-scenarios", "max_source_chars")
    assert set(catalog.QUERIES) == {"skill", "agent", "mcp", "hook", "harness", "workflow", "eval"}
    assert catalog.CACHE_TTL_S == 24 * 3600
    assert stats.UNRELIABLE_ERROR_RATE == skills.value("judge-experiment", "unreliable_error_rate")


def test_rough_estimate_follows_its_skill():
    r = skills.load("rough-estimate").values
    out = estimate.rough(
        estimate.EstimateInput(
            name="x", skill_text="nothing", steps=[], scenarios=[], repo_summary="", measured=None
        )
    )
    assert out["likely"] == r["base_points"]
    assert out["high"] - out["likely"] == r["half_width"]


def test_the_web_apps_copy_of_the_shared_rules_is_current():
    """web/src/fixtures/rules.json is what /api/rules returns, for the web's unit tests. Regenerate:
    uv run python -c "import json; from proving_ground import skills; print(json.dumps({n:
    skills.load(n).values for n in ('measurability', 'repo-goals')}, indent=2, ensure_ascii=False))"
    > ../web/src/fixtures/rules.json"""
    import json
    from pathlib import Path

    copy = Path(__file__).resolve().parents[2] / "web" / "src" / "fixtures" / "rules.json"
    if not copy.exists():  # an engine-only checkout
        return
    got = json.loads(copy.read_text(encoding="utf-8"))
    assert got == {n: skills.load(n).values for n in ("measurability", "repo-goals")}
