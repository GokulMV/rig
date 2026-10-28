"""The workspace keys repos by the folder they really are: one folder is attached once."""

import json
from pathlib import Path

from proving_ground.workspace import Workspace, repo_id


def test_a_folder_attached_twice_is_merged_on_load_keeping_the_first_id(tmp_path: Path):
    repo = tmp_path / "my-app"
    (repo / "engine").mkdir(parents=True)
    other = tmp_path / "blog"
    other.mkdir()
    f = tmp_path / "workspace.json"
    # As found on a real machine: an older id and the current one for the same folder.
    f.write_text(
        json.dumps(
            {
                "repos": [
                    {"id": "00efe09671", "root": str(repo), "name": "my-app"},
                    {"id": "b69b2bd858", "root": str(other), "name": "blog"},
                    {"id": repo_id(repo), "root": str(repo), "name": "my-app"},
                    {"id": "7c2e4eae85", "root": f"{repo}/", "name": "my-app"},
                    {"id": "31b1234c54", "root": f"{repo}/engine/..", "name": "my-app"},
                ]
            }
        )
    )
    ws = Workspace(f)
    assert [(r.id, r.name) for r in ws.repos()] == [
        ("00efe09671", "my-app"),
        ("b69b2bd858", "blog"),
    ]
    # The merge is written back, so the duplicate is gone for good.
    assert [r["id"] for r in json.loads(f.read_text())["repos"]] == ["00efe09671", "b69b2bd858"]
    # Adding the folder again, by any spelling, returns the kept entry.
    for spelling in (repo, Path(f"{repo}/engine/.."), Path(f"{repo}/")):
        assert ws.add(spelling).id == "00efe09671"
    assert len(ws.repos()) == 2


def test_a_symlink_to_an_attached_folder_is_the_same_repo(tmp_path: Path):
    real = tmp_path / "code" / "app"
    real.mkdir(parents=True)
    link = tmp_path / "app-link"
    link.symlink_to(real)
    ws = Workspace(tmp_path / "ws.json")
    first = ws.add(real)
    assert ws.add(link) == first
    assert Workspace(tmp_path / "ws.json").repos() == [first]


def test_a_clean_workspace_file_is_not_rewritten(tmp_path: Path):
    a = tmp_path / "a"
    a.mkdir()
    f = tmp_path / "ws.json"
    Workspace(f).add(a)
    before = f.stat().st_mtime_ns
    text = f.read_text()
    assert len(Workspace(f).repos()) == 1
    assert f.read_text() == text and f.stat().st_mtime_ns == before
