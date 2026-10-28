"""Copy the project into a build context, pinned to a commit when it is a git repo."""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path

from proving_ground.files import PG_DIR
from proving_ground.intake.repo import SKIP_DIRS


@dataclass(frozen=True)
class Snapshot:
    path: Path
    commit: str | None
    dirty: bool


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)


def snapshot_repo(root: Path, dest: Path) -> Snapshot:
    """Export HEAD (git) or a filtered copy (not git). Never includes .proving-ground/."""
    root = root.resolve()
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    head = _git(root, "rev-parse", "HEAD")
    if head.returncode == 0:
        archive = _git(root, "archive", "--format=tar", "HEAD")
        if archive.returncode != 0:
            raise RuntimeError(archive.stderr.decode(errors="replace"))
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(dest, filter="data")
        status = _git(root, "status", "--porcelain", "--", ".", f":!{PG_DIR}")
        commit, dirty = head.stdout.decode().strip(), bool(status.stdout.strip())
    else:
        shutil.copytree(root, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SKIP_DIRS))
        commit, dirty = None, False
    shutil.rmtree(dest / PG_DIR, ignore_errors=True)
    return Snapshot(path=dest, commit=commit, dirty=dirty)


def snapshot_rev(root: Path, rev: str, dest: Path) -> Path:
    """Export one commit or tree (a sha) to `dest` with `git archive`: the live checkout is never
    read or touched. Never includes .proving-ground/."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    archive = _git(root.resolve(), "archive", "--format=tar", rev)
    if archive.returncode != 0:
        raise RuntimeError(archive.stderr.decode(errors="replace"))
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(dest, filter="data")
    shutil.rmtree(dest / PG_DIR, ignore_errors=True)
    return dest
