import subprocess
from pathlib import Path

from proving_ground.sandbox.snapshot import snapshot_repo


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def make_repo(root: Path) -> None:
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    (root / "app.py").write_text("print('v1')\n")
    (root / ".proving-ground" / "scenarios").mkdir(parents=True)
    (root / ".proving-ground" / "scenarios" / "a.yaml").write_text("id: a\ninstruction: x\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")


def test_git_snapshot_pins_head_and_excludes_scenarios(tmp_path: Path):
    repo = tmp_path / "repo"
    make_repo(repo)
    (repo / "app.py").write_text("print('uncommitted')\n")
    snap = snapshot_repo(repo, tmp_path / "out")
    assert (snap.path / "app.py").read_text() == "print('v1')\n"
    assert not (snap.path / ".proving-ground").exists()
    assert snap.commit is not None and len(snap.commit) == 40
    assert snap.dirty is True


def test_scenario_edits_do_not_count_as_dirty(tmp_path: Path):
    repo = tmp_path / "repo"
    make_repo(repo)
    (repo / ".proving-ground" / "scenarios" / "b.yaml").write_text("id: b\ninstruction: y\n")
    assert snapshot_repo(repo, tmp_path / "out").dirty is False


def test_plain_folder_copy_skips_build_output(tmp_path: Path):
    src = tmp_path / "src"
    (src / "node_modules" / "x").mkdir(parents=True)
    (src / "main.py").write_text("x")
    (src / ".proving-ground").mkdir()
    snap = snapshot_repo(src, tmp_path / "out")
    assert (snap.path / "main.py").is_file()
    assert not (snap.path / "node_modules").exists()
    assert not (snap.path / ".proving-ground").exists()
    assert (snap.commit, snap.dirty) == (None, False)


def test_snapshot_replaces_previous_output(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("a")
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("old")
    snapshot_repo(src, out)
    assert not (out / "stale.txt").exists()
