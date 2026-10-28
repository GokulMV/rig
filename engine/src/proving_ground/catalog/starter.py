"""Skills preloaded from GitHub for the Workflow Lab, so a workflow has skills to use before you
have any of your own.

The repositories and limits are in the starter-skills skill. Only names and descriptions are
fetched (in the background, cached on disk); a skill's folder is downloaded when a workflow
that uses it is saved or run.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from proving_ground import skills
from proving_ground.catalog import (
    MAX_SKILL_BYTES,
    MAX_SKILL_FILES,
    REPO_NAME,
    GitHub,
    _frontmatter,
    _safe,
    _text,
    _tree,
    install_skill,
    installed_path,
)

T = skills.load("starter-skills").values
REPOS: list[str] = [r["repo"] for r in T["repos"]]
LABELS: dict[str, str] = {r["repo"]: r["label"] for r in T["repos"]}
TTL_S = T["cache_ttl_hours"] * 3600
RETRY_S = T["retry_minutes"] * 60
MAX_PER_REPO = T["max_skills_per_repo"]
SKIP = set(T["skip_folders"])
BINARY = tuple(T["binary_extensions"])
PREFIX = "github:"  # a GitHub skill's path until it is downloaded: github:<owner>/<repo>/<folder>


def _spread(items: list[str], n: int) -> list[str]:
    """At most n items, evenly spaced, so one end of a long list doesn't fill it."""
    if len(items) <= n:
        return items
    return [items[i * len(items) // n] for i in range(n)]


def index_repo(gh: GitHub, repo: str) -> list[dict]:
    """The installable skill folders in one repository, with their names and descriptions."""
    tree = _tree(gh, repo)
    folders = sorted(
        {str(PurePosixPath(t["path"]).parent) for t in tree if t["path"].endswith("SKILL.md")}
    )
    keep = []
    for folder in folders:
        folder = "" if folder == "." else folder
        prefix = f"{folder}/" if folder else ""
        files = [t for t in tree if t["path"].startswith(prefix)]
        if (
            any(part in SKIP for part in PurePosixPath(folder).parts)
            or not any(t["path"] == f"{prefix}SKILL.md" for t in files)
            or any(t["path"].lower().endswith(BINARY) for t in files)
            or len(files) > MAX_SKILL_FILES
            or sum(t.get("size", 0) for t in files) > MAX_SKILL_BYTES
        ):
            continue
        keep.append(folder)
    out = []
    for folder in _spread(keep, MAX_PER_REPO):
        fm = _frontmatter(_text(gh, repo, f"{folder}/SKILL.md" if folder else "SKILL.md"))
        out.append(
            {
                "path": f"{PREFIX}{repo}/{folder}".rstrip("/"),
                "name": str(fm.get("name") or PurePosixPath(folder).name or repo.split("/")[1]),
                "description": " ".join(str(fm.get("description") or "").split())[:300],
                "source": "github",
                "repo": repo,
                "label": LABELS.get(repo, repo),
                "folder": folder,
                "url": f"https://github.com/{repo}/tree/HEAD/{folder}".rstrip("/"),
            }
        )
    return out


def parse_path(path: str) -> tuple[str, str]:
    """(repo, folder) from a github: path; ValueError unless it names a starter repository."""
    rest = path.removeprefix(PREFIX)
    parts = rest.split("/")
    repo, folder = "/".join(parts[:2]), "/".join(parts[2:])
    if not path.startswith(PREFIX) or not REPO_NAME.match(repo):
        raise ValueError(f"not a GitHub skill: {path!r}")
    if repo not in REPOS:
        raise ValueError(f"{repo} isn't one of the GitHub repositories skills are preloaded from")
    if folder:
        _safe(folder)
    return repo, folder


class StarterLibrary:
    """The index of the starter repositories' skills, built in the background and cached."""

    def __init__(self, github: Callable[[], GitHub], cache: Path):
        self._github = github
        self._cache = cache
        self._lock = threading.Lock()
        self._building = False
        self.error: str | None = None

    def _read(self) -> dict | None:
        try:
            return json.loads(self._cache.read_text()) if self._cache.is_file() else None
        except ValueError:
            return None

    def _fresh(self, data: dict | None) -> bool:
        if data is None or data.get("repos") != REPOS:  # the list of repositories changed
            return False
        ttl = RETRY_S if data.get("failed") else TTL_S
        return time.time() - data.get("fetched_at", 0) < ttl

    def load(self, refresh: bool = False) -> dict:
        """The index, fetching it now if it is stale: {"skills", "fetched_at", "failed", "repos"}.
        A repository that can't be read keeps its skills from the last index."""
        old = self._read()
        if not refresh and self._fresh(old):
            return old  # type: ignore[return-value]
        before = {r: [s for s in (old or {}).get("skills", []) if s["repo"] == r] for r in REPOS}
        found, failed, errors = [], [], []
        try:
            gh = self._github()
        except Exception as e:  # noqa: BLE001 - no GitHub at all: same as every repo failing
            gh, errors = None, [str(e)]
        for repo in REPOS:
            try:
                if gh is None:
                    raise RuntimeError(errors[0])
                found += index_repo(gh, repo)
            except Exception as e:  # noqa: BLE001 - offline, rate-limited, renamed: keep the old list
                failed.append(repo)
                errors.append(f"{repo}: {e}")
                found += before[repo]
        data = {
            "fetched_at": time.time(),
            "skills": found,
            "failed": failed,
            "repos": REPOS,
            "error": "; ".join(errors)[:500] or None,
        }
        self._cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._cache.with_name(self._cache.name + ".part")  # the page reads it meanwhile
        tmp.write_text(json.dumps(data))
        tmp.replace(self._cache)
        return data

    def snapshot(self) -> dict:
        """What the Lab shows now, starting a fetch in the background when the index is stale:
        {"skills", "state": ready | loading | partial | offline, "note"}."""
        data = self._read()
        if not self._fresh(data):
            self.refresh()
        skills_ = (data or {}).get("skills", [])
        failed = (data or {}).get("failed", [])
        if data is None:
            state = "offline" if self.error and not self._building else "loading"
        elif failed and len(failed) == len(REPOS) and not skills_:
            state = "offline"
        elif failed:
            state = "partial"
        else:
            state = "ready"
        note = {
            "loading": "Loading skills from GitHub…",
            "offline": "Couldn't reach GitHub, so only your own skills are used for now.",
            "partial": f"Couldn't read {', '.join(failed)} from GitHub; showing the last list.",
            "ready": None,
        }[state]
        return {"skills": skills_, "state": state, "note": note}

    def refresh(self) -> None:
        with self._lock:
            if self._building:
                return
            self._building = True

        def work() -> None:
            try:
                self.load(refresh=True)
                self.error = None
            except Exception as e:  # noqa: BLE001 - shown to the page
                self.error = str(e)
            finally:
                self._building = False

        threading.Thread(target=work, daemon=True).start()

    @property
    def building(self) -> bool:
        return self._building

    def ensure(self, path: str, library: Path) -> Path:
        """The local folder for a github: skill, downloading it into the library the first time.
        ValueError for a path that isn't a starter skill or a folder that can't be installed."""
        repo, folder = parse_path(path)
        dest = installed_path(library, repo, folder)
        if (dest / "SKILL.md").is_file():
            return dest
        return install_skill(self._github(), repo, folder, library)
