"""The coding agents Rig can run (through Harbor) and how each one signs in.

Keys typed into the app are held in this process's memory only: never written to disk,
never returned by the API. Logins already on this machine (a Codex or Gemini login file) are
used by passing Harbor the flag that tells it to read them.
"""

from __future__ import annotations

import json
import os
import re
import select
import shutil
import subprocess
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

# Pinned to releases at least two weeks old on 2026-10-25.
NODE = (
    "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash"
    ' && export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh" && nvm install 22 && nvm alias default 22'
)


# "On" for a sign-in flag. Harbor scrubs the value of every env var whose name looks secret
# (…AUTH…, …KEY…) out of a trial's logs, so a plain "1" there blanked every 1 in them and broke
# the JSON (no final answer, no costs read). Harbor strips the value before reading it as a bool;
# a vertical tab never occurs in its JSON logs or in prose, so this one is only ever itself.
FLAG_ON = "\v1\v"


@dataclass(frozen=True)
class SignIn:
    id: str
    label: str
    env: str  # the variable a typed value is passed as
    login_file: str | None = None  # relative to home: a login already on this machine
    flags: Mapping[str, str] = field(default_factory=dict)  # extra variables when this is used
    help: str = ""


@dataclass(frozen=True)
class Login:
    """How the app signs an agent in through its own CLI on this machine."""

    cmd: tuple[str, ...] | None  # None: the CLI has no scriptable login; `manual` says what to do
    option: str  # the SignIn it completes
    token: bool = False  # the CLI prints a token (kept in memory); else it writes a login file
    manual: str = ""
    install: str = ""  # how to get the CLI when it's missing


@dataclass(frozen=True)
class Agent:
    id: str  # Harbor's agent name
    label: str
    sign_in: tuple[SignIn, ...]
    npm: str | None = None  # npm package@version installed in the sandbox image
    default_model: str | None = None
    login: Login | None = None
    # Where the agent talks to its model: the only hosts its sandbox may reach, while it runs.
    hosts: tuple[str, ...] = ()


AGENTS: tuple[Agent, ...] = (
    Agent(
        "claude-code",
        "Claude Code",
        (
            SignIn("api-key", "Anthropic API key", "ANTHROPIC_API_KEY"),
            SignIn(
                "subscription",
                "Claude subscription token",
                "CLAUDE_CODE_OAUTH_TOKEN",
                flags={"CLAUDE_FORCE_OAUTH": FLAG_ON},
                help="Sign in with your Claude plan: approve in the browser.",
            ),
        ),
        default_model="anthropic/claude-sonnet-5-5",
        login=Login(
            ("claude", "setup-token"),
            "subscription",
            token=True,
            install="curl -fsSL https://claude.ai/install.sh | bash",
        ),
        hosts=("api.anthropic.com",),
    ),
    Agent(
        "codex",
        "Codex",
        (
            SignIn("api-key", "OpenAI API key", "OPENAI_API_KEY"),
            SignIn(
                "login",
                "ChatGPT login on this machine",
                "",
                login_file=".codex/auth.json",
                flags={"CODEX_FORCE_AUTH_JSON": FLAG_ON},
                help="Sign in with your ChatGPT plan: approve in the browser.",
            ),
        ),
        npm="@openai/codex@0.162.1",
        login=Login(("codex", "login"), "login", install="npm install -g @openai/codex@0.162.1"),
        hosts=("api.openai.com", "chatgpt.com", "auth.openai.com"),
    ),
    Agent(
        "opencode",
        "OpenCode",
        (
            SignIn("anthropic-key", "Anthropic API key", "ANTHROPIC_API_KEY"),
            SignIn("openai-key", "OpenAI API key", "OPENAI_API_KEY"),
            SignIn(
                "login",
                "OpenCode login on this machine",
                "",
                login_file=".local/share/opencode/auth.json",
                help="Or sign in once in a terminal with `opencode auth login`.",
            ),
        ),
        npm="opencode-ai@1.18.35",
        login=Login(
            None,
            "login",
            manual="Run `opencode auth login` in a terminal and pick a provider. This page notices when you're done.",
            install="npm install -g opencode-ai@1.18.35",
        ),
        default_model="anthropic/claude-sonnet-5-5",
        hosts=("api.anthropic.com", "api.openai.com"),
    ),
    Agent(
        "gemini-cli",
        "Gemini CLI",
        (
            SignIn("api-key", "Gemini API key", "GEMINI_API_KEY"),
            SignIn(
                "login",
                "Google login on this machine",
                "",
                login_file=".gemini/oauth_creds.json",
                flags={"GEMINI_FORCE_OAUTH": FLAG_ON},
                help="Sign in with your Google account.",
            ),
        ),
        npm="@google/gemini-cli@0.63.0",
        login=Login(
            None,
            "login",
            manual='Run `gemini` in a terminal and choose "Login with Google". This page notices when you\'re done.',
            install="npm install -g @google/gemini-cli@0.63.0",
        ),
        hosts=(
            "generativelanguage.googleapis.com",
            "cloudcode-pa.googleapis.com",
            "oauth2.googleapis.com",
        ),
    ),
)


def agent(aid: str) -> Agent:
    for a in AGENTS:
        if a.id == aid:
            return a
    raise KeyError(f"unknown agent {aid!r}")


def model_hosts(aid: str, env: Mapping[str, str] | None = None) -> list[str]:
    """The hosts an agent's sandbox may reach while it runs: its model provider's, or the local
    server a base URL points at instead. The checks get no network at all."""
    from urllib.parse import urlparse

    env = env or {}
    bases = [env[k] for k in ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL") if env.get(k)]
    if bases:
        return sorted({urlparse(b).hostname for b in bases if urlparse(b).hostname})
    try:
        return list(agent(aid).hosts)
    except KeyError:
        return []


def install_snippet(aid: str) -> str:
    """Dockerfile lines that install the agent at build time (the sandbox has no internet later)."""
    a = agent(aid)
    if not a.npm:
        return ""  # Claude Code is in the base image
    return f"RUN bash -lc '{NODE} && npm install -g {a.npm}'\n"


class Credentials:
    def __init__(self, env: Mapping[str, str] | None = None, home: Path | None = None):
        self._env = os.environ if env is None else env
        self._home = home or Path.home()
        self._typed: dict[str, tuple[str, str]] = {}  # agent -> (sign-in id, value)

    def _option(self, aid: str, sid: str) -> SignIn:
        for s in agent(aid).sign_in:
            if s.id == sid:
                return s
        raise ValueError(f"{agent(aid).label} has no sign-in option {sid!r}")

    def set(self, aid: str, sid: str, value: str) -> None:
        s = self._option(aid, sid)
        if s.login_file:
            raise ValueError(f"{s.label} is read from this machine; nothing to type.")
        self._typed[aid] = (sid, value.strip())

    def clear(self, aid: str) -> None:
        self._typed.pop(aid, None)

    def status(self, aid: str) -> list[dict]:
        out = []
        typed = self._typed.get(aid)
        for s in agent(aid).sign_in:
            if typed and typed[0] == s.id:
                ready, how = True, "Entered in this session"
            elif s.login_file:
                ready = (self._home / s.login_file).is_file()
                how = f"~/{s.login_file} found" if ready else f"No ~/{s.login_file}"
            else:
                ready = bool(self._env.get(s.env))
                how = f"{s.env} is set" if ready else f"{s.env} is not set"
            out.append(
                {
                    "id": s.id,
                    "label": s.label,
                    "ready": ready,
                    "how": how,
                    "help": s.help,
                    "typed": not s.login_file,
                }
            )
        return out

    def ready(self, aid: str) -> bool:
        return any(o["ready"] for o in self.status(aid))

    def env_for(self, aid: str) -> dict[str, str]:
        """Variables for one Harbor trial: what was typed, else the first ready option."""
        typed = self._typed.get(aid)
        if typed:
            s = self._option(aid, typed[0])
            return {s.env: typed[1], **s.flags}
        for s in agent(aid).sign_in:
            if s.login_file and (self._home / s.login_file).is_file():
                return dict(s.flags)
            if not s.login_file and self._env.get(s.env):
                return {s.env: self._env[s.env], **s.flags}
        return {}


# ---------- Signing in from the app ----------

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)")
TOKEN = re.compile(r"sk-ant-oat\d*-[A-Za-z0-9_\-]{20,}")
URL = re.compile(r"https://[^\s\"'<>]+")


def claude_host_login(run=subprocess.run) -> dict | None:
    """Claude Code's own login on this machine (`claude auth status`), or None.

    That login lives in the OS keychain: the claude CLI here can use it (Map with Archify),
    but a Docker sandbox can't, so sandboxed runs still need a token.
    """
    if run is subprocess.run and shutil.which("claude") is None:
        return None
    try:
        done = run(
            ["claude", "auth", "status", "--json"], capture_output=True, text=True, timeout=15
        )
        data = json.loads(done.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not data.get("loggedIn"):
        return None
    return {
        "email": data.get("email"),
        "plan": data.get("subscriptionType"),
        "method": data.get("authMethod"),
    }


class CliLogin:
    """Sign an agent in through its own CLI, in a pseudo-terminal.

    The person approves in the browser. A token the CLI prints goes straight into memory
    (Credentials), never to disk or the API; a CLI that writes its own login file is done when
    the file appears. A CLI with no scriptable login gets instructions, and the file is watched.
    """

    def __init__(
        self, creds: Credentials, aid: str, cmd: list[str] | None = None, timeout: int = 600
    ):
        self.creds, self.aid, self.timeout = creds, aid, timeout
        self.spec = agent(aid).login
        self.cmd = cmd or (list(self.spec.cmd) if self.spec and self.spec.cmd else None)
        self.state, self.url, self.error = "idle", None, None
        self._proc: subprocess.Popen | None = None
        self._cancel = threading.Event()

    def view(self) -> dict:
        spec = self.spec
        return {
            "state": self.state,
            "url": self.url,
            "error": self.error,
            "manual": spec.manual if spec and not spec.cmd else "",
        }

    def _file(self) -> Path | None:
        spec = self.spec
        if not spec or spec.token:
            return None
        s = self.creds._option(self.aid, spec.option)
        return self.creds._home / s.login_file if s.login_file else None

    def start(self) -> dict:
        if self.state == "running":
            return self.view()
        if not self.spec:
            self.state, self.error = "error", f"{agent(self.aid).label} signs in with a key only."
            return self.view()
        if self.cmd and shutil.which(self.cmd[0]) is None:
            self.state = "error"
            self.error = (
                f"The {self.cmd[0]} CLI isn't installed. Install it with: {self.spec.install}"
            )
            return self.view()
        self.state, self.url, self.error = "running", None, None
        self._cancel.clear()
        threading.Thread(target=self._run if self.cmd else self._watch, daemon=True).start()
        return self.view()

    def cancel(self) -> None:
        self._cancel.set()
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
        if self.state == "running":
            self.state = "idle"

    def _watch(self) -> None:
        """No CLI to drive: wait for the login file the person creates in a terminal."""
        f, deadline = self._file(), time.time() + self.timeout
        while not self._cancel.is_set() and time.time() < deadline:
            if f and f.is_file():
                self.state = "done"
                return
            time.sleep(1)
        if self.state == "running":
            self.state, self.error = (
                "error",
                "Still not signed in. Try again once the terminal says you're in.",
            )

    def _run(self) -> None:
        import fcntl
        import pty
        import struct
        import termios

        master, slave = pty.openpty()
        # Wide, so a token is printed on one line.
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 1000, 0, 0))
        env = {**os.environ, "COLUMNS": "1000", "LINES": "50"}
        try:
            self._proc = subprocess.Popen(
                self.cmd, stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True
            )
        except OSError as e:
            self.state, self.error = "error", str(e)
            return
        finally:
            os.close(slave)
        buf, deadline, f = "", time.time() + self.timeout, self._file()
        try:
            while time.time() < deadline and not self._cancel.is_set():
                ready, _, _ = select.select([master], [], [], 0.5)
                if ready:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        break
                    buf += ANSI.sub("", chunk.decode(errors="ignore"))
                    if not self.url and (m := URL.search(buf)):
                        self.url = m.group(0)
                    if self.spec.token and (m := TOKEN.search(buf)):
                        self.creds.set(self.aid, self.spec.option, m.group(0))
                        self.state = "done"
                        return
                elif self._proc.poll() is not None:
                    break
                if f and f.is_file():
                    self.state = "done"
                    return
            if f and f.is_file():
                self.state = "done"
            elif self.state == "running":
                self.state = "error"
                self.error = (
                    "Sign-in timed out."
                    if time.time() >= deadline
                    else "Sign-in ended without finishing. Try again."
                )
        finally:
            if self._proc.poll() is None:
                self._proc.kill()
            os.close(master)
