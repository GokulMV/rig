"""Public benchmarks from the Harbor registry, as benches: a seeded sample of one benchmark's
tasks, downloaded at the registry's pinned commit and recorded as an imported suite.

The rules and every number are in skills/public-benchmarks/SKILL.md.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import fnmatch
import json
import random
import re
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import httpx

from proving_ground import bench as bench_mod
from proving_ground import skills

P = skills.load("public-benchmarks").values

COMMIT = re.compile(r"^[0-9a-f]{40}$")
# A path part: plain characters only. No glob or pattern characters either (* ? [ ] ! #):
# the paths become git sparse-checkout patterns, and a pattern could pull in more than a task.
PART = re.compile(r"^[A-Za-z0-9_$][A-Za-z0-9._@+$-]*$")
# A Hugging Face repo URL: https://huggingface.co/[datasets/|spaces/]<owner>/<name>[.git]
HF_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"
HF_REPO = re.compile(rf"^/(?:(datasets|spaces)/)?({HF_NAME})/({HF_NAME}?)(?:\.git)?/?$")


class PublicBenchError(Exception):
    pass


@dataclass(frozen=True)
class Task:
    """One registry task entry, checked: safe to hand to git."""

    name: str
    git_url: str
    commit: str | None  # None: not pinned in the registry, fetched at the repo's head
    path: str  # relative, inside the repo

    @property
    def folder(self) -> str:  # the folder it lands in
        return PurePosixPath(self.path).name


def key(d: dict) -> str:
    return f"{d['name']}@{d['version']}"


def _matches(d: dict, patterns: list[str]) -> bool:
    return any(
        fnmatch.fnmatchcase(d["name"], p) or fnmatch.fnmatchcase(key(d), p) for p in patterns
    )


def safe_path(path: object) -> str:
    """A task path inside its repo: relative, plain parts only. Anything else is refused."""
    if not isinstance(path, str) or not path or "\\" in path or path.startswith("/"):
        raise PublicBenchError(f"Refused task path {path!r}: it must be relative.")
    parts = path.split("/")
    if not all(PART.match(p) for p in parts):  # no "..", ".", empty parts or pattern characters
        raise PublicBenchError(f"Refused task path {path!r}: it must stay inside its repository.")
    return path


def checked(entry: dict, schemes: list[str]) -> Task:
    url = entry.get("git_url")
    u = urlsplit(url) if isinstance(url, str) else None
    if (
        u is None
        or u.scheme not in schemes
        or url.startswith("-")
        or not (u.netloc or u.scheme == "file")
    ):
        raise PublicBenchError(f"Refused repository {url!r}: only {', '.join(schemes)} URLs.")
    if u.username or u.password:
        raise PublicBenchError(f"Refused repository {url!r}: no logins in URLs.")
    commit = entry.get("git_commit_id")
    if commit in (None, "", "HEAD", "head"):
        commit = None
    elif not isinstance(commit, str) or not COMMIT.match(commit):
        raise PublicBenchError(f"Refused commit {commit!r}: a full commit id or none.")
    path = safe_path(entry.get("path"))
    hf_repo(url)  # a Hugging Face URL must name exactly one repo
    return Task(str(entry.get("name") or PurePosixPath(path).name), url, commit, path)


def sample(d: dict, n: int, schemes: list[str]) -> list[Task]:
    """`n` of the benchmark's tasks, the same ones every time for the same benchmark and n.
    Every entry is checked first: one bad entry refuses the whole benchmark."""
    seen: dict[tuple, Task] = {}
    for e in d.get("tasks") or []:
        t = checked(e, schemes)
        seen.setdefault((t.git_url, t.commit, t.path), t)  # dedupe by URL, commit and path
    by_folder: dict[str, Task] = {}
    for t in sorted(seen.values(), key=lambda t: (t.path, t.git_url, t.commit or "")):
        by_folder.setdefault(t.folder, t)  # one folder per task name
    pool = list(by_folder.values())
    rng = random.Random(f"{P['seed']}:{key(d)}")
    picked = rng.sample(pool, min(n, len(pool)))
    return sorted(picked, key=lambda t: t.path)


def harbor_download(tasks: list[Task], dest: Path, timeout_s: float) -> dict[str, str | None]:
    """Harbor's own task client: a shallow, sparse checkout of just these folders at their
    commits (git run without a shell, links checked to stay inside each task). Returns the
    commit each task folder came from."""
    from harbor.models.task.id import GitTaskId
    from harbor.tasks.client import TaskClient

    ids = [GitTaskId(git_url=t.git_url, git_commit_id=t.commit, path=Path(t.path)) for t in tasks]

    async def go():
        return await asyncio.wait_for(
            TaskClient().download_tasks(ids, overwrite=True, output_dir=dest, export=True),
            timeout_s,
        )

    got = asyncio.run(go())
    return {r.path.name: r.resolved_git_commit_id for r in got.results}


def hf_repo(git_url: str) -> tuple[str, str] | None:
    """(repo_id, repo_type) for a Hugging Face repo URL; None for any other host."""
    u = urlsplit(git_url)
    if (u.hostname or "").lower() not in P["hf_hosts"]:
        return None
    m = HF_REPO.match(u.path)
    if (
        u.query
        or u.fragment
        or not m
        or m.group(3).endswith((".", "-"))
        or ".." in u.path
        or (m.group(1) is None and m.group(2) in ("datasets", "spaces", "models"))
    ):
        raise PublicBenchError(f"Refused repository {git_url!r}: not one Hugging Face repo.")
    kind = {"datasets": "dataset", "spaces": "space", None: "model"}[m.group(1)]
    return f"{m.group(2)}/{m.group(3)}", kind


def _safe_file(rel: str) -> bool:
    """A file path the Hub listed under a task: relative, no "..", "." or empty parts."""
    parts = rel.split("/")
    return (
        bool(rel)
        and "\\" not in rel
        and "\0" not in rel
        and all(p not in ("", ".", "..") for p in parts)
    )


def _shebang(f: Path) -> bool:
    with f.open("rb") as fh:
        return fh.read(2) == b"#!"


def _gb(n: int) -> str:
    if n >= 1e9:
        return f"{n / 1e9:.1f} GB"
    return f"{n / 1e6:.0f} MB" if n >= 1e6 else f"{n:,} bytes"


def hf_download(tasks: list[Task], dest: Path, deadline: float, api=None) -> dict[str, str | None]:
    """Only the sampled task folders from a Hugging Face repo, file by file over HTTP, at the
    pinned commit (or the head, resolved once and recorded). The folders are listed first, so
    a sample over `download_max_bytes` or `download_max_files` is refused before anything
    downloads. `api`: a HfApi (tests pass a fake)."""
    if api is None:
        from huggingface_hub import HfApi
        from huggingface_hub.utils import disable_progress_bars

        disable_progress_bars()
        api = HfApi()

    def left() -> float:
        r = deadline - time.monotonic()
        if r <= 0:
            raise TimeoutError
        return r

    heads: dict[str, str] = {}  # repo -> its head commit, resolved once
    plan: list[tuple[Task, str, str, str, list[tuple[str, int]]]] = []
    total = count = 0
    for t in tasks:
        repo_id, kind = hf_repo(t.git_url)  # type: ignore[misc]
        rev = t.commit
        if rev is None:
            if repo_id not in heads:
                left()
                heads[repo_id] = str(api.repo_info(repo_id, repo_type=kind).sha or "")
            rev = heads[repo_id]
        if not COMMIT.match(rev):
            raise PublicBenchError(f"Couldn't resolve {t.git_url} to a commit.")
        left()
        files = []
        for item in api.list_repo_tree(
            repo_id, path_in_repo=t.path, recursive=True, repo_type=kind, revision=rev
        ):
            size = getattr(item, "size", None)
            if size is None:  # a folder
                continue
            path = str(item.path)
            rel = path[len(t.path) + 1 :]
            if not path.startswith(t.path + "/") or not _safe_file(rel):
                raise PublicBenchError(f"Refused file {path!r}: it is outside task {t.path}.")
            files.append((path, int(size)))
            total, count = total + int(size), count + 1
        plan.append((t, repo_id, kind, rev, files))
    where = f"The {len(tasks)} sampled task{'s' if len(tasks) != 1 else ''}"
    if total > P["download_max_bytes"]:
        raise PublicBenchError(
            f"{where} are {_gb(total)}, over the {_gb(P['download_max_bytes'])} one download "
            "may be. Pick a smaller sample."
        )
    if count > P["download_max_files"]:
        raise PublicBenchError(
            f"{where} are {count} files, over the {P['download_max_files']} one download may "
            "be. Pick a smaller sample."
        )

    raw = dest / ".hf"  # the repo's layout; the task folders move out of it
    raw.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()

    def one(repo_id: str, kind: str, rev: str, path: str, size: int) -> None:
        if stop.is_set():
            return
        got = Path(
            api.hf_hub_download(
                repo_id, path, repo_type=kind, revision=rev, local_dir=raw, etag_timeout=30
            )
        )
        target = raw / path
        if got.resolve() != target.resolve() or target.is_symlink() or not target.is_file():
            raise PublicBenchError(f"Refused file {path!r}: it didn't land in its task.")
        if target.stat().st_size != size:
            raise PublicBenchError(f"{path} came down at a different size than the Hub listed.")

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=P["hf_workers"])
    try:
        jobs = [
            pool.submit(one, repo_id, kind, rev, path, size)
            for _, repo_id, kind, rev, files in plan
            for path, size in files
        ]
        for j in concurrent.futures.as_completed(jobs, timeout=left()):
            j.result()
    except BaseException:
        stop.set()
        raise
    finally:  # wait for files in flight: nothing may write here after the caller cleans up
        pool.shutdown(wait=True, cancel_futures=True)

    commits: dict[str, str | None] = {}
    for t, _, _, rev, files in plan:
        if files:
            src = raw / t.path
            for f in src.rglob("*"):  # git keeps the executable bit; HTTP doesn't send it
                if f.is_file() and not f.is_symlink() and _shebang(f):
                    f.chmod(f.stat().st_mode | 0o111)
            src.replace(dest / t.folder)
        commits[t.folder] = rev
    shutil.rmtree(raw)
    return commits


def download_tasks(
    tasks: list[Task], dest: Path, timeout_s: float, *, hf_api=None, git=None
) -> dict[str, str | None]:
    """Each task from where it lives: Hugging Face over HTTP, any other host through Harbor's
    git checkout. One time budget for all of it."""
    deadline = time.monotonic() + timeout_s
    hf = [t for t in tasks if hf_repo(t.git_url)]
    rest = [t for t in tasks if t not in hf]
    commits = hf_download(hf, dest, deadline, hf_api) if hf else {}
    if rest:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError
        commits |= (git or harbor_download)(rest, dest, left)
    return commits


Fetch = Callable[[str], bytes]
Download = Callable[[list[Task], Path, float], dict]


def _http_fetch(url: str) -> bytes:
    r = httpx.get(url, timeout=P["fetch_timeout_s"], follow_redirects=True)
    r.raise_for_status()
    return r.content


class PublicBenches:
    """The registry (cached under the app home) and the benchmarks added from it."""

    def __init__(
        self,
        home: Path,
        fetch: Fetch = _http_fetch,
        download: Download = download_tasks,
        schemes: list[str] | None = None,
    ):
        self.cache = home / "public-registry.json"
        self.root = home / "public-benches"
        self.fetch, self.download = fetch, download
        self.schemes = list(schemes or P["url_schemes"])
        self._memo: tuple[float, list[dict]] | None = None  # (cache mtime, datasets)
        self._lock = threading.Lock()  # one download at a time
        self._failed_at = 0.0  # the last failed fetch: offline, don't wait on the network each time

    # ---------- the registry ----------

    def registry(self, refresh: bool = False) -> tuple[list[dict], str | None]:
        """The datasets, and a note when they are not fresh (offline: the last copy, or none)."""
        fresh = self.cache.is_file() and time.time() - self.cache.stat().st_mtime < P["cache_ttl_s"]
        note = None
        retry = time.time() - self._failed_at >= P["retry_after_s"]
        if refresh or (not fresh and retry):
            try:
                data = json.loads(self.fetch(P["registry_url"]))
                if not isinstance(data, list):
                    raise ValueError("the registry is not a list")
                self.cache.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.cache.with_suffix(".tmp")
                tmp.write_text(json.dumps(data))
                tmp.replace(self.cache)
            except (httpx.HTTPError, OSError, ValueError) as e:
                self._failed_at = time.time()
                note = self._offline(f" ({type(e).__name__})")
        elif not fresh:  # failed a moment ago: not trying again yet
            note = self._offline("")
        if not self.cache.is_file():
            return [], note
        mtime = self.cache.stat().st_mtime
        if self._memo is None or self._memo[0] != mtime:
            try:
                raw = json.loads(self.cache.read_text())
            except (OSError, ValueError):
                return [], "The saved copy of the Harbor registry is unreadable."
            ok = [
                d
                for d in (raw if isinstance(raw, list) else [])
                if isinstance(d, dict)
                and isinstance(d.get("name"), str)
                and isinstance(d.get("version"), str)
                and isinstance(d.get("tasks"), list)
            ]
            self._memo = (mtime, ok)
        return self._memo[1], note

    def _offline(self, why: str) -> str:
        if not self.cache.is_file():
            return f"Couldn't reach the Harbor registry{why}, and there is no saved copy yet."
        day = time.strftime("%Y-%m-%d", time.localtime(self.cache.stat().st_mtime))
        return f"Couldn't reach the Harbor registry{why}: showing the copy from {day}."

    def dataset(self, k: str) -> dict:
        for d in self.registry()[0]:
            if key(d) == k and not _matches(d, P["exclude"]):
                return d
        raise KeyError(f"No public benchmark {k!r} in the Harbor registry.")

    def listing(self, refresh: bool = False) -> dict:
        data, note = self.registry(refresh)
        added = {
            b.public["key"]: b.id for b in bench_mod.benches() if b.public and "key" in b.public
        }
        rows = []
        for d in data:
            if _matches(d, P["exclude"]):
                continue
            urls = [str(t.get("git_url", "")) for t in d["tasks"] if isinstance(t, dict)]
            rows.append(
                {
                    "key": key(d),
                    "name": d["name"],
                    "version": d["version"],
                    "description": str(d.get("description") or "").strip(),
                    "tasks": len(d["tasks"]),
                    "disciplines": P["disciplines"].get(d["name"], []),
                    "heavy": _matches(d, P["heavy_images"]),
                    "source": _web_url(urls[0] if urls else None),
                    "added": added.get(key(d)),
                }
            )
        return {
            "datasets": rows,
            "note": note,
            "default_sample": P["default_sample"],
            "max_sample": P["max_sample"],
        }

    # ---------- adding one ----------

    def folder(self, d: dict) -> Path:
        return self.root / re.sub(r"[^A-Za-z0-9._@-]+", "-", key(d))

    def add(self, k: str, n: int) -> tuple[bench_mod.Bench, list[str]]:
        """Download a seeded sample of `n` tasks and record it as a bench. Returns the bench and
        the sampled tasks that were not valid Harbor tasks (dropped)."""
        if not 1 <= n <= P["max_sample"]:
            raise PublicBenchError(f"A sample is 1 to {P['max_sample']} tasks.")
        d = self.dataset(k)
        tasks = sample(d, n, self.schemes)
        if not tasks:
            raise PublicBenchError(f"{k} lists no tasks.")
        if not self._lock.acquire(blocking=False):
            raise PublicBenchError(
                "Another public benchmark is downloading. Wait for it to finish."
            )
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            staging = self.root / f".staging-{uuid.uuid4().hex[:8]}"
            try:
                commits = self.download(tasks, staging, P["download_timeout_s"])
                kept = [
                    t
                    for t in tasks
                    if bench_mod.harbor_tasks(staging / t.folder) == [staging / t.folder]
                ]
                dropped = [t.name for t in tasks if t not in kept]
                if not kept:
                    raise PublicBenchError(
                        f"None of the {len(tasks)} downloaded tasks is a Harbor task "
                        "(task.toml, instruction.md, environment/, tests/test.sh)."
                    )
                for t in tasks:
                    if t not in kept:
                        shutil.rmtree(staging / t.folder, ignore_errors=True)
                dest = self.folder(d)
                if dest.exists():
                    shutil.rmtree(dest)
                staging.replace(dest)
            except TimeoutError as e:
                raise PublicBenchError(
                    f"Downloading {k} took longer than {P['download_timeout_s']} s."
                ) from e
            except PublicBenchError:
                raise
            except Exception as e:  # git or the Hub failed, the network dropped, a link escaped
                raise PublicBenchError(f"Couldn't download {k}: {_short(e)}") from e
            finally:
                shutil.rmtree(staging, ignore_errors=True)
            source = kept[0].git_url
            info = {
                "key": k,
                "dataset": d["name"],
                "version": d["version"],
                "total": len(d["tasks"]),
                "sample": len(kept),
                "source": _web_url(source),
                "tasks": [
                    {
                        "name": t.name,
                        "path": t.path,
                        "git_url": t.git_url,
                        "commit": commits.get(t.folder) or t.commit,
                        "pinned": t.commit is not None,
                    }
                    for t in kept
                ],
                "heavy": _matches(d, P["heavy_images"]),
            }
            (dest / "public.json").write_text(json.dumps(info, indent=2))
            b = bench_mod.import_suite(
                dest,
                f"{d['name']} {d['version']}",
                P["disciplines"].get(d["name"], []),
                public=info,
            )
            return b, dropped
        finally:
            self._lock.release()

    def remove(self, folder: Path) -> None:
        """Delete a downloaded sample: only ever a folder under public-benches/."""
        folder = folder.resolve()
        if folder.parent == self.root.resolve() and folder.is_dir():
            shutil.rmtree(folder)


def _web_url(git_url: str | None) -> str | None:
    if not git_url:
        return None
    return re.sub(r"\.git$", "", git_url) if git_url.startswith("https://") else None


def _short(e: Exception) -> str:
    err = getattr(e, "stderr", None)
    text = err.decode(errors="replace") if isinstance(err, bytes) else str(err or e)
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return (lines[-1] if lines else type(e).__name__)[:300]
