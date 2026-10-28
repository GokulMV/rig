"""Put a hook, MCP server or instructions treatment into a compiled task's repo copy.

Design: the arms differ in files, so a scenario compiles into two Harbor task folders when the
treatment is one of these kinds: `tasks/<sid>` is the "without" arm (exactly what a skill
experiment compiles today, so shared baselines stay valid) and `tasks-with/<sid>` is the "with"
arm, the same task with the treatment written into the repo that is copied to /app. Doing it at
compile time keeps the sandbox free of arm flags: the files are simply there or not. An MCP
server's `install.sh` is the one thing both arms get, so they share one image and differ only in
config. Nothing here runs a model or touches the network.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from proving_ground import skills
from proving_ground.models import Treatment, TreatmentKind

CONFIG_KINDS = (TreatmentKind.HOOK, TreatmentKind.MCP, TreatmentKind.INSTRUCTIONS)
INSTALL_TARGET = "mcp-install.sh"  # inside the task's pg/ folder

_INSTALLERS = re.compile(
    r"\b(npm\s+(?:install|i)|npx|pip3?\s+install|uv\s+pip\s+install|uvx|pipx\s+install)\b(.*)"
)


def _v(key: str):
    return skills.value("treatment-kinds", key)


def is_config(t: Treatment | None) -> bool:
    return t is not None and t.kind in CONFIG_KINDS


def _read_json(path: Path, what: str) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise ValueError(f"{path}: {what} is not valid JSON ({e})") from e
    if not isinstance(data, dict):
        raise ValueError(f"{path}: {what} must be a JSON object")
    return data


def hooks_of(folder: Path) -> dict:
    """The `hooks` object from hooks.json (either the bare object or {"hooks": {...}})."""
    data = _read_json(folder / _v("hooks_file"), "hooks.json")
    hooks = data["hooks"] if set(data) == {"hooks"} else data
    if not isinstance(hooks, dict) or not hooks:
        raise ValueError(f"{folder / _v('hooks_file')}: no hooks found")
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise ValueError(f"hooks.json: {event} must be a list of hook groups")
    return hooks


def mcp_servers(folder: Path) -> dict:
    """The `mcpServers` object from mcp.json."""
    data = _read_json(folder / _v("mcp_file"), "mcp.json")
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        raise ValueError(f"{folder / _v('mcp_file')}: needs a non-empty mcpServers object")
    for name, cfg in servers.items():
        if not isinstance(cfg, dict) or not cfg.get("command"):
            raise ValueError(f"mcp.json: server {name!r} needs a command")
    return servers


def server_names(treatment_path: str | Path) -> list[str]:
    """Names of the MCP servers a treatment folder adds (for adherence)."""
    return sorted(mcp_servers(Path(treatment_path)))


def unpinned_installs(script: str) -> list[str]:
    """Install commands in an install.sh whose packages lack an exact version."""
    bad = []
    for raw in script.splitlines():
        line = raw.strip()
        m = _INSTALLERS.search(line) if not line.startswith("#") else None
        if not m:
            continue
        for tok in m.group(2).replace("&&", " ").split("&")[0].split():
            if tok.startswith("-") or tok in ("|", ";") or "/" in tok or "." in tok[-4:]:
                continue
            pinned = re.search(r"@\d[\w.\-]*$", tok) or re.search(r"==\d[\w.\-]*$", tok)
            if not pinned or tok.endswith("@latest"):
                bad.append(line)
                break
    return bad


def merge_settings(existing: dict, hooks: dict, approve_servers: list[str] | None = None) -> dict:
    """Add `hooks` to a Claude Code settings object; the repo's own hooks per event run first."""
    out = dict(existing)
    merged = {k: list(v) for k, v in (out.get("hooks") or {}).items()}
    for event, groups in hooks.items():
        merged.setdefault(event, []).extend(groups)
    out["hooks"] = merged
    if approve_servers:
        enabled = list(out.get("enabledMcpjsonServers") or [])
        out["enabledMcpjsonServers"] = enabled + [s for s in approve_servers if s not in enabled]
    return out


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _load_if_file(path: Path) -> dict:
    return _read_json(path, path.name) if path.is_file() else {}


def apply_with_arm(t: Treatment, repo: Path) -> None:
    """Write the treatment into `repo` (the "with" arm). Raises ValueError on a bad treatment."""
    src = Path(t.path)
    settings = repo / _v("settings_path")
    if t.kind is TreatmentKind.HOOK:
        _write_json(settings, merge_settings(_load_if_file(settings), hooks_of(src)))
    elif t.kind is TreatmentKind.MCP:
        servers = mcp_servers(src)
        cfg = repo / _v("mcp_config_path")
        have = _load_if_file(cfg)
        have["mcpServers"] = {**(have.get("mcpServers") or {}), **servers}
        _write_json(cfg, have)
        if _v("approve_project_mcp"):
            _write_json(settings, merge_settings(_load_if_file(settings), {}, sorted(servers)))
    elif t.kind is TreatmentKind.INSTRUCTIONS:
        if src.is_file():
            name = src.name
        else:
            names = [n for n in _v("instruction_files") if (src / n).is_file()]
            name = names[0]
            src = src / name
        shutil.copyfile(src, repo / name)


def _committed(root: Path, name: str) -> bytes | None:
    """`name` at the repo's HEAD; None when it isn't committed or the folder isn't a git repo."""
    import subprocess

    got = subprocess.run(
        ["git", "-C", str(root), "show", f"HEAD:{name}"], capture_output=True, check=False
    )
    return got.stdout if got.returncode == 0 else None


def _is_git(root: Path) -> bool:
    import subprocess

    got = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, check=False
    )
    return got.returncode == 0


def instruction_file(path: Path) -> Path:
    """The instructions file a treatment path writes: the file itself, or a folder's first."""
    if path.is_file():
        return path
    return next(path / n for n in _v("instruction_files") if (path / n).is_file())


def instruction_compare(root: Path, path: Path) -> str:
    """What an instructions run compares (treatment-kinds: "What an instructions run
    compares"): "edited", "new" or "same" for the repo's own root file; "replaces" or "adds" for
    a copy anywhere else. The "without" arm is the committed snapshot (snapshot_repo)."""
    root, path = root.resolve(), path.resolve()
    f = instruction_file(path)
    git = _is_git(root)
    have = _committed(root, f.name) if git else None
    if f.parent == root:
        if not git:
            return "same"  # the snapshot is the working tree: both arms get this file
        if have is None:
            return "new"
        return "same" if have == f.read_bytes() else "edited"
    exists = have is not None if git else (root / f.name).is_file()
    return "replaces" if exists else "adds"


def install_script(t: Treatment | None) -> str | None:
    """An MCP treatment's install.sh, checked for pinned versions; None if it has none."""
    if t is None or t.kind is not TreatmentKind.MCP:
        return None
    f = Path(t.path) / _v("mcp_install_file")
    if not f.is_file():
        return None
    text = f.read_text()
    bad = unpinned_installs(text)
    if bad:
        raise ValueError(f"{f}: pin exact versions (name@1.2.3 / name==1.2.3): {bad[0]}")
    return text
