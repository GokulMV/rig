"""Repos that aren't on this machine yet: find them on GitHub or GitLab, clone them, keep them current.

Sign-in works like the agents': the `gh` / `glab` login on this machine is used when there is
one; otherwise a token typed into the app, held in this process's memory only. A token is
never written to disk, never returned by the API, never put in the clone's remote URL or in a
command line: git reads it from the environment of the one command, through an askpass script
that holds no secret. Public repos need no sign-in.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

PROVIDERS = {
    "github": {
        "label": "GitHub",
        "cli": "gh",
        "host": "github.com",
        "hint": (
            "A read-only token: classic with the repo scope, or fine-grained with Contents "
            "set to read-only. It stays in this app's memory until you quit."
        ),
    },
    "gitlab": {
        "label": "GitLab",
        "cli": "glab",
        "host": "gitlab.com",
        "hint": (
            "A read-only token with the read_repository and read_api scopes. It stays in this "
            "app's memory until you quit."
        ),
    },
}

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SECRETS = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_\-]{10,}"
    r"|(?<=://)[^/\s:@]+:[^/\s@]+(?=@))"
)


class RemoteError(Exception):
    pass


@dataclass(frozen=True)
class Remote:
    provider: str  # github | gitlab
    host: str
    owner: str  # the user, organisation or GitLab group path ("grp/sub")
    name: str

    @property
    def url(self) -> str:
        return f"https://{self.host}/{self.owner}/{self.name}"

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


def parse_remote(text: str) -> Remote:
    """A repo URL (https or ssh), `host/owner/name`, or `owner/name` (GitHub) -> a Remote.

    github.com and gitlab.com are known; any other host is taken as a self-hosted GitLab.
    Anything after the repo (`/tree/main`, `/-/issues`) is ignored, and so is a login typed
    into the URL: it never reaches the remote we record.
    """
    s = text.strip()
    if not s:
        raise RemoteError("Paste a repo URL or owner/name.")
    if m := re.match(r"^(?:ssh://)?[\w.-]+@([\w.-]+)(?::\d+)?[:/](.+)$", s):  # git@host:o/n
        host, path = m.group(1), m.group(2)
    elif "://" in s:
        u = urlsplit(s)
        if u.scheme not in ("http", "https", "ssh", "git") or not u.hostname:
            raise RemoteError(f"{s!r} isn't a repo URL.")
        host, path = u.hostname, u.path
    else:
        parts = s.strip("/").split("/")
        if len(parts) >= 3 and "." in parts[0]:  # host/owner/name
            host, path = parts[0], "/".join(parts[1:])
        elif len(parts) == 2:
            host, path = "github.com", s
        else:
            raise RemoteError(f"{s!r} isn't owner/name or a repo URL.")
    host = host.lower()
    segs = [p for p in path.split("?")[0].split("#")[0].strip("/").split("/") if p]
    if "-" in segs:  # GitLab's /-/ separator
        segs = segs[: segs.index("-")]
    provider = "github" if host in ("github.com", "www.github.com") else "gitlab"
    if host == "www.github.com":
        host = "github.com"
    if provider == "github":
        segs = segs[:2]
    elif host == "gitlab.com" and len(segs) > 2 and segs[-2] in ("tree", "blob"):
        segs = segs[:-2]
    if len(segs) < 2:
        raise RemoteError(f"{s!r} needs both an owner and a repo name.")
    segs[-1] = segs[-1].removesuffix(".git")
    if any(not NAME.match(p) or p.endswith(".git") for p in segs):
        raise RemoteError(f"{s!r} isn't a valid repo address.")
    return Remote(provider, host, "/".join(segs[:-1]), segs[-1])


def redact(text: str, *secrets: str | None) -> str:
    """`text` with any token (one we hold, or anything shaped like one) blanked out."""
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return SECRETS.sub("***", text)


Runner = Callable[..., subprocess.CompletedProcess]


def run_command(cmd, *, env=None, cwd=None, timeout=900) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
        env={**os.environ, **(env or {})},
    )


class Tokens:
    """Provider tokens typed into the app: process memory only."""

    def __init__(self):
        self._t: dict[str, str] = {}

    def set(self, provider: str, value: str) -> None:
        if provider not in PROVIDERS:
            raise RemoteError(f"No provider {provider!r}.")
        if not value.strip():
            raise RemoteError("The token is empty.")
        self._t[provider] = value.strip()

    def clear(self, provider: str) -> None:
        self._t.pop(provider, None)

    def get(self, provider: str) -> str | None:
        return self._t.get(provider)


ASKPASS = '#!/bin/sh\ncase "$1" in\n  Username*) printf "%s" "$PG_GIT_USER" ;;\n  *) printf "%s" "$PG_GIT_TOKEN" ;;\nesac\n'
LOGGED_IN = re.compile(r"Logged in to (\S+) (?:account|as) (\S+)")


class Remotes:
    def __init__(
        self,
        home: Path,
        run: Runner = run_command,
        http: httpx.Client | None = None,
        which: Callable[[str], str | None] = shutil.which,
        tokens: Tokens | None = None,
    ):
        self.home = home
        self.run, self.which = run, which
        self.http = http or httpx.Client(timeout=20)
        self.tokens = tokens or Tokens()

    # ---------- sign-in ----------

    def _cli(self, provider: str, *args: str, timeout: int = 20):
        cli = PROVIDERS[provider]["cli"]
        if self.which(cli) is None:
            return None
        try:
            return self.run([cli, *args], timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return None

    def cli_login(self, provider: str) -> dict | None:
        """The gh / glab login on this machine: {"account", "host"}, or None. Never a token."""
        host = PROVIDERS[provider]["host"]
        done = self._cli(provider, "auth", "status", "--hostname", host)
        if done is None or done.returncode != 0:
            return None
        for m in LOGGED_IN.finditer((done.stdout or "") + "\n" + (done.stderr or "")):
            if m.group(1) == host:
                return {"account": m.group(2).rstrip(".:"), "host": host}
        return None

    def _cli_token(self, provider: str) -> str | None:
        host = PROVIDERS[provider]["host"]
        args = (
            ("auth", "token", "--hostname", host)
            if provider == "github"
            else ("config", "get", "token", "--host", host)
        )
        done = self._cli(provider, *args)
        if done is None or done.returncode != 0:
            return None
        return (done.stdout or "").strip() or None

    def token_for(self, remote: Remote) -> str | None:
        """What to sign in with for this repo: a typed token, else the CLI login, else nothing."""
        typed = self.tokens.get(remote.provider)
        if typed:
            return typed
        if remote.host == PROVIDERS[remote.provider]["host"] and self.cli_login(remote.provider):
            return self._cli_token(remote.provider)
        return None

    def status(self) -> list[dict]:
        out = []
        for pid, p in PROVIDERS.items():
            cli = p["cli"]
            installed = self.which(cli) is not None
            login = self.cli_login(pid) if installed else None
            typed = self.tokens.get(pid) is not None
            out.append(
                {
                    "id": pid,
                    "label": p["label"],
                    "cli": cli,
                    "installed": installed,
                    "cli_account": login["account"] if login else None,
                    "token_set": typed,
                    "signed_in": typed or login is not None,
                    "via": "token" if typed else "cli" if login else None,
                    "hint": p["hint"],
                }
            )
        return out

    def verify_token(self, provider: str, token: str) -> str | None:
        """Who the token belongs to. Raises RemoteError when the provider rejects it; None if
        the provider can't be reached (the token is kept and fails later, plainly)."""
        url, headers = self._api(provider, token, "user")
        try:
            r = self.http.get(url, headers=headers)
        except httpx.HTTPError:
            return None
        if r.status_code in (401, 403):
            raise RemoteError(f"{PROVIDERS[provider]['label']} rejected that token.")
        if r.status_code != 200:
            return None
        data = r.json()
        return data.get("login") or data.get("username")

    # ---------- finding repos ----------

    @staticmethod
    def _api(provider: str, token: str | None, path: str) -> tuple[str, dict]:
        if provider == "github":
            h = {"Accept": "application/vnd.github+json"}
            if token:
                h["Authorization"] = f"Bearer {token}"
            return f"https://api.github.com/{path}", h
        return f"https://gitlab.com/api/v4/{path}", ({"PRIVATE-TOKEN": token} if token else {})

    def list_mine(self, provider: str, query: str = "") -> list[dict]:
        """Your repos (up to 100, newest first), narrowed by `query`."""
        if provider not in PROVIDERS:
            raise RemoteError(f"No provider {provider!r}.")
        q = query.strip().lower()
        typed = self.tokens.get(provider)
        try:
            if provider == "github" and not typed:
                rows = self._gh_list()
            else:
                token = typed or (self._cli_token(provider) if self.cli_login(provider) else None)
                if not token:
                    raise RemoteError(
                        f"Sign in to {PROVIDERS[provider]['label']} to see your repos."
                    )
                rows = self._rest_list(provider, token, q)
        except RemoteError:
            raise
        except (httpx.HTTPError, OSError, subprocess.SubprocessError) as e:
            raise RemoteError(
                redact(f"Couldn't list your {PROVIDERS[provider]['label']} repos: {e}", typed)
            ) from e
        if q:
            rows = [r for r in rows if q in r["full_name"].lower() or q in r["description"].lower()]
        return rows

    def _gh_list(self) -> list[dict]:
        fields = "name,owner,description,isPrivate,updatedAt"
        done = self._cli("github", "repo", "list", "--json", fields, "--limit", "100", timeout=60)
        if done is None:
            raise RemoteError("Sign in to GitHub to see your repos.")
        if done.returncode != 0:
            raise RemoteError(redact((done.stderr or "gh failed").strip().splitlines()[-1]))
        import json

        try:
            items = json.loads(done.stdout or "[]")
        except ValueError as e:
            raise RemoteError("gh returned something unreadable.") from e
        return [
            self._row(
                "github",
                i["owner"]["login"] if isinstance(i.get("owner"), dict) else str(i.get("owner")),
                i["name"],
                i.get("description"),
                bool(i.get("isPrivate")),
                i.get("updatedAt"),
            )
            for i in items
        ]

    def _rest_list(self, provider: str, token: str, q: str) -> list[dict]:
        if provider == "github":
            path = "user/repos?per_page=100&sort=updated"
        else:
            path = "projects?membership=true&per_page=100&order_by=last_activity_at"
            if q:
                path += f"&search={q}"
        url, headers = self._api(provider, token, path)
        r = self.http.get(url, headers=headers)
        if r.status_code in (401, 403):
            raise RemoteError(f"{PROVIDERS[provider]['label']} rejected the token.")
        if r.status_code != 200:
            raise RemoteError(f"{PROVIDERS[provider]['label']} answered {r.status_code}.")
        rows = []
        for i in r.json():
            if provider == "github":
                rows.append(
                    self._row(
                        "github",
                        i["owner"]["login"],
                        i["name"],
                        i.get("description"),
                        bool(i.get("private")),
                        i.get("updated_at"),
                    )
                )
            else:
                ns, _, name = i["path_with_namespace"].rpartition("/")
                rows.append(
                    self._row(
                        "gitlab",
                        ns,
                        name,
                        i.get("description"),
                        i.get("visibility") != "public",
                        i.get("last_activity_at"),
                    )
                )
        return rows

    @staticmethod
    def _row(provider, owner, name, description, private, updated) -> dict:
        host = PROVIDERS[provider]["host"]
        return {
            "owner": owner,
            "name": name,
            "full_name": f"{owner}/{name}",
            "description": description or "",
            "private": private,
            "updated": updated,
            "url": f"https://{host}/{owner}/{name}",
        }

    # ---------- clone and pull ----------

    def dest_for(self, remote: Remote) -> Path:
        return self.home / "repos" / remote.host / remote.owner / remote.name

    def _git(self, args: list[str], token: str | None, *, cwd=None, timeout=900):
        """One git command. The token travels only in this call's environment, read by an
        askpass script that holds no secret; the helper list is cleared so nothing else is asked."""
        env = {"GIT_TERMINAL_PROMPT": "0"}
        script = None
        cmd = ["git"]
        if token:
            fd, name = tempfile.mkstemp(prefix="pg-askpass-", suffix=".sh")
            script = Path(name)
            with os.fdopen(fd, "w") as f:
                f.write(ASKPASS)
            script.chmod(stat.S_IRWXU)
            env.update(GIT_ASKPASS=str(script), PG_GIT_USER="x-access-token", PG_GIT_TOKEN=token)
            cmd += ["-c", "credential.helper="]
        try:
            return self.run([*cmd, *args], env=env, cwd=cwd, timeout=timeout)
        except FileNotFoundError as e:
            raise RemoteError("git isn't installed on this machine.") from e
        except subprocess.TimeoutExpired as e:
            raise RemoteError("Timed out talking to the remote.") from e
        finally:
            if script:
                script.unlink(missing_ok=True)

    def _fail(self, what: str, done, token: str | None, url: str) -> RemoteError:
        err = redact((done.stderr or done.stdout or "").strip(), token)
        last = next((ln for ln in reversed(err.splitlines()) if ln.strip()), "git failed")
        low = err.lower()
        if any(k in low for k in ("authentication", "could not read username", "not found")):
            last = (
                f"Couldn't read {url}. If it's private, sign in first; otherwise check the "
                f"address. ({last})"
            )
        return RemoteError(f"{what} failed: {last}")

    def clone(self, url: str, dest: Path, token: str | None = None, depth: int = 1) -> None:
        """A shallow clone of `url` into `dest`. The remote URL stays free of any login."""
        if dest.exists() and any(dest.iterdir()):
            raise RemoteError(f"{dest} already exists and isn't empty.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        args = ["clone", "--quiet"] + (["--depth", str(depth)] if depth else [])
        done = self._git([*args, "--", url, str(dest)], token)
        if done.returncode != 0:
            shutil.rmtree(dest, ignore_errors=True)
            raise self._fail("Clone", done, token, url)

    def pull(self, dest: Path, token: str | None = None) -> str:
        """Bring a clone up to date (fast-forward only: it never rewrites local work)."""
        if not (dest / ".git").exists():
            raise RemoteError(f"{dest} isn't a git clone.")
        shallow = (dest / ".git" / "shallow").exists()
        args = ["pull", "--ff-only", "--quiet"] + (["--depth", "1"] if shallow else [])
        done = self._git(args, token, cwd=dest, timeout=600)
        if done.returncode != 0:
            raise self._fail("Pull", done, token, str(dest))
        head = self._git(["rev-parse", "--short", "HEAD"], None, cwd=dest, timeout=30)
        return (head.stdout or "").strip()


class CloneJobs:
    """Clones run in the background (big repos take a while); the page polls one by id."""

    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, url: str, work: Callable[[Callable[[str], None]], dict]) -> dict:
        jid = uuid.uuid4().hex[:10]
        job = {"id": jid, "url": url, "state": "running", "stage": "Starting…", "error": None}
        with self._lock:
            self._jobs[jid] = job

        def go():
            try:
                result = work(lambda s: job.update(stage=s))
                job.update(state="done", stage="Done", **result)
            except Exception as e:  # shown to the person, token stripped by `work`
                job.update(state="error", error=str(e))

        threading.Thread(target=go, daemon=True).start()
        return dict(job)

    def get(self, jid: str) -> dict | None:
        job = self._jobs.get(jid)
        return dict(job) if job else None
