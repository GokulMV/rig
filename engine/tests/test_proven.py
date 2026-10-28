"""PROVEN.md and the `proven:` badge on workflows and skills."""

from pathlib import Path

import yaml
from test_api_workspace import ORIGIN
from test_bench import _lab_client, _starter, _wait

from proving_ground import proven

SKILL = "---\nname: w\ndescription: Does a thing,\n  over two lines.\n---\n\n# W\n\nBody stays.\n"


def row(**kw):
    base = {
        "id": 1,
        "bench": "bugfix",
        "bench_version": "abc",
        "agent": "claude-code",
        "model": "claude-sonnet-5-5",
        "verdict": "helps",
        "diff": 0.4,
        "ci_low": 0.1,
        "ci_high": 0.7,
        "n_pairs": 5,
        "status": "done",
        "adherence": {"followed": 4, "read": 5},
        "costs": {"per_extra_solved_usd": 0.12},
        "date": "2026-10-25",
    }
    return base | kw


def test_refresh_writes_table_yaml_and_one_frontmatter_line(tmp_path: Path):
    (tmp_path / "SKILL.md").write_text(SKILL)
    rows = [
        row(),
        row(id=2, verdict="inconclusive", diff=0.0, n_pairs=3),
        row(id=3, status="running"),  # not finished
        row(id=4, n_pairs=0, diff=None),  # nothing measured
    ]
    claim = proven.refresh(tmp_path, "My flow", rows)
    assert claim == {"verdict": "helps", "diff_pts": 40.0, "pairs": 5, "bench": "bugfix"}
    md = (tmp_path / "PROVEN.md").read_text()
    assert md.startswith("# Proven results: My flow")
    assert (
        "| bugfix | claude-code | claude-sonnet-5-5 | helps | +40.0 pts | +10.0 to +70.0 | 5 | 4/5 | 0.12 |  | 2026-10-25 |"
        in md
    )
    data = yaml.safe_load(md.split("```yaml\n")[1].split("```")[0])["proven_results"]
    assert [e["experiment"] for e in data] == [1, 2]
    assert data[0]["adherence"] == {"followed": 4, "read": 5} and data[0]["bench_version"] == "abc"
    new = (tmp_path / "SKILL.md").read_text()
    assert (
        new.replace("proven: {verdict: helps, diff_pts: 40.0, pairs: 5, bench: bugfix}\n", "")
        == SKILL
    ), "only the proven line may differ"
    assert proven.read(tmp_path) == claim
    # Refreshing again replaces the line, never stacks a second one.
    proven.refresh(tmp_path, "My flow", [row(diff=0.5)])
    assert (tmp_path / "SKILL.md").read_text().count("proven:") == 1
    assert proven.read(tmp_path)["diff_pts"] == 50.0
    # No finished results: both go away and the rest of SKILL.md is as it was.
    assert proven.refresh(tmp_path, "My flow", [row(status="running")]) is None
    assert not (tmp_path / "PROVEN.md").exists()
    assert (tmp_path / "SKILL.md").read_text() == SKILL


def test_read_falls_back_to_proven_md(tmp_path: Path):
    (tmp_path / "SKILL.md").write_text(SKILL)
    proven.refresh(tmp_path, "w", [row()])
    (tmp_path / "SKILL.md").write_text(SKILL)  # frontmatter line lost, PROVEN.md kept
    assert proven.read(tmp_path)["verdict"] == "helps"
    assert proven.read(tmp_path / "missing") is None


def test_saved_and_measured_workflow_carries_proven(tmp_path: Path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    wf = _starter(c, "Fix a bug")
    folder = tmp_path / "home" / "library" / "workflows" / f"workflow-{wf['id']}"
    c.post("/api/lab/save", json=wf, headers=ORIGIN)
    assert [w["proven"] for w in c.get("/api/lab").json()["saved"]] == [None]
    assert not (folder / "PROVEN.md").exists()
    r = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "bugfix", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    rows = _wait(c, 1)
    # The finished run wrote the folder before the page could see it finished.
    md = (folder / "PROVEN.md").read_text()
    assert "| bugfix | claude-code | claude-sonnet-5-5 | helps | +100.0 pts |" in md
    entry = yaml.safe_load(md.split("```yaml\n")[1].split("```")[0])["proven_results"][0]
    assert (
        entry["experiment"] == rows[0]["id"] and entry["bench_version"] == rows[0]["bench_version"]
    )
    saved = c.get("/api/lab").json()["saved"]
    assert saved[0]["proven"] == {
        "verdict": "helps",
        "diff_pts": 100.0,
        "pairs": 5,
        "bench": "bugfix",
        # The same run's Rig score: every pair helped, but 5 pairs is under the minimum.
        "rig": 59,
        "rig_band": "not_proven",
        "rig_tone": "warning",
        "rig_provisional": True,
    }
    # Saving again recompiles the folder from scratch; the claim comes back with it.
    c.post("/api/lab/save", json=wf, headers=ORIGIN)
    assert (folder / "PROVEN.md").is_file()
    assert "proven: {verdict: helps" in (folder / "SKILL.md").read_text()
    assert c.get("/api/lab").json()["saved"][0]["proven"]["verdict"] == "helps"
    # A skill folder with the same frontmatter shows it in the Repos library listing.
    from proving_ground.api.views import treatments_json

    lib = tmp_path / "home" / "library"
    out = treatments_json(tmp_path, None, [], [], tmp_path / "none", lib)
    assert out["workflows"][0]["proven"]["diff_pts"] == 100.0
