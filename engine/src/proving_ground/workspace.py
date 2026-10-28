"""The repos attached to Rig on this machine."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_FILE = Path.home() / ".proving-ground" / "workspace.json"


@dataclass(frozen=True)
class Repo:
    id: str
    root: str
    name: str
    remote: str | None = None  # where a cloned repo came from (never holds a login)
    provider: str | None = None  # github | gitlab


def repo_id(root: Path) -> str:
    return hashlib.sha256(str(root).encode()).hexdigest()[:10]


def _key(root: str | Path) -> str:
    """What makes two repos the same: the folder they really are (symlinks, `..`, `~` and a
    trailing slash resolved), so one folder is attached once however it was named."""
    return os.path.realpath(os.path.expanduser(str(root)))


def _same(a: Repo, b: Repo) -> bool:
    if _key(a.root) == _key(b.root):
        return True
    try:  # the same folder by another spelling (a case-insensitive disk, a hard-linked path)
        return os.path.samefile(a.root, b.root)
    except OSError:
        return False


class Workspace:
    """A list of repo roots, saved to `path` (or kept in memory when `path` is None)."""

    def __init__(self, path: Path | None = None):
        self._path = path
        self._repos: list[Repo] = []
        if path and path.is_file():
            try:
                loaded = [Repo(**r) for r in json.loads(path.read_text()).get("repos", [])]
            except (ValueError, TypeError):
                loaded = []
            # One entry per folder: a folder attached twice (an older id scheme, `serve --root ..`)
            # keeps its first entry. Both share the folder's own .proving-ground, so nothing moves.
            for r in loaded:
                if not any(_same(r, kept) for kept in self._repos):
                    self._repos.append(r)
            if len(self._repos) < len(loaded):
                self._save()

    def _save(self) -> None:
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps({"repos": [asdict(r) for r in self._repos]}, indent=2))

    def repos(self) -> list[Repo]:
        return list(self._repos)

    def get(self, rid: str) -> Repo | None:
        return next((r for r in self._repos if r.id == rid), None)

    def add(self, root: Path, remote: str | None = None, provider: str | None = None) -> Repo:
        root = root.expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"{root} is not a folder on this machine.")
        repo = Repo(repo_id(root), str(root), root.name, remote, provider)
        existing = next((r for r in self._repos if r.id == repo.id or _same(r, repo)), None)
        if existing:
            return existing
        self._repos.append(repo)
        self._save()
        return repo

    def remove(self, rid: str) -> None:
        self._repos = [r for r in self._repos if r.id != rid]
        self._save()
