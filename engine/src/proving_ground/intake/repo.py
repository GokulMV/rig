"""Walk a repository and read only the files that describe its stack and agent setup."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from proving_ground import skills as rules

TK = rules.load("treatment-kinds").values
# Bumped when the rule for which SKILL.md files are the repo's skills changes: an older scan is
# read again (api: repo_meta).
SKILL_RULE = 2

SKIP_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "venv",
    ".venv",
    "__pycache__",
    "target",
    "vendor",
    ".cache",
    "coverage",
    ".turbo",
    ".idea",
    ".vscode",
    ".proving-ground",
}
EXT_LANG = {
    "ts": "TypeScript",
    "tsx": "TypeScript",
    "js": "JavaScript",
    "jsx": "JavaScript",
    "mjs": "JavaScript",
    "py": "Python",
    "go": "Go",
    "rs": "Rust",
    "java": "Java",
    "kt": "Kotlin",
    "swift": "Swift",
    "rb": "Ruby",
    "php": "PHP",
    "cs": "C#",
    "cpp": "C++",
    "c": "C",
    "scala": "Scala",
    "ex": "Elixir",
    "dart": "Dart",
    "vue": "Vue",
    "svelte": "Svelte",
    "sql": "SQL",
    "tf": "Terraform",
}
NPM_STACK = {
    "react": "React",
    "next": "Next.js",
    "vue": "Vue",
    "svelte": "Svelte",
    "express": "Express",
    "fastify": "Fastify",
    "@nestjs/core": "NestJS",
    "prisma": "Prisma",
    "pg": "Postgres",
    "mongoose": "MongoDB",
    "redis": "Redis",
    "ioredis": "Redis",
    "openai": "OpenAI SDK",
    "@anthropic-ai/sdk": "Anthropic SDK",
    "langchain": "LangChain",
    "@langchain/core": "LangChain",
    "stripe": "Stripe",
    "tailwindcss": "Tailwind",
    "vite": "Vite",
    "jest": "Jest",
    "vitest": "Vitest",
    "playwright": "Playwright",
    "@playwright/test": "Playwright",
}
PY_STACK = {
    "django": "Django",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "sqlalchemy": "SQLAlchemy",
    "pandas": "pandas",
    "anthropic": "Anthropic SDK",
    "openai": "OpenAI SDK",
    "langchain": "LangChain",
    "pytest": "pytest",
    "celery": "Celery",
    "psycopg": "Postgres",
    "redis": "Redis",
}
KEY_NAMES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yaml",
    "claude.md",
    "agents.md",
    ".mcp.json",
    "gemfile",
    "composer.json",
}
KEY_PATTERNS = [
    re.compile(p)
    for p in (
        r"(^|/)readme(\.[a-z]+)?$",
        r"\.claude/(settings\.json|agents/.+\.md)$",
        r"\.cursor/rules/",
        r"\.github/workflows/.+\.ya?ml$",
        r"(openapi|swagger)[^/]*\.(ya?ml|json)$",
        r"(^|/)(docs|adr|architecture)/[^/]+\.md$",
        r"\.tf$",
        r"(^|/)(k8s|kubernetes|deploy|charts)/.+\.ya?ml$",
    )
]


@dataclass(frozen=True)
class RepoSkill:
    name: str
    description: str
    path: str
    tokens_est: int


@dataclass
class RepoScan:
    root: str
    file_count: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    stack: list[str] = field(default_factory=list)
    agent_setup: list[str] = field(default_factory=list)
    skills: list[RepoSkill] = field(default_factory=list)
    key_files: list[str] = field(default_factory=list)
    truncated: bool = False


def _is_key(rel: str) -> bool:
    low = rel.lower()
    return low.rsplit("/", 1)[-1] in KEY_NAMES or any(p.search(low) for p in KEY_PATTERNS)


def _read(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def parse_skill(rel: str, text: str) -> RepoSkill:
    name, desc = rel.split("/")[-2], ""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if m:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            fm = {}
        if isinstance(fm, dict):
            name = str(fm.get("name") or name)
            desc = str(fm.get("description") or "")
    return RepoSkill(name=name, description=desc[:300], path=rel, tokens_est=max(1, len(text) // 4))


def _manifest_paths(root: Path, rel_dir: str, entry: dict) -> list[str]:
    """The folders a plugin manifest (or a marketplace entry) names in `skills`."""
    v = entry.get("skills")
    base = (root / rel_dir).resolve()
    out = []
    for x in [v] if isinstance(v, str) else v if isinstance(v, list) else []:
        p = (base / x).resolve() if isinstance(x, str) else None
        # A path outside the plugin doesn't load (plugins-reference: containment).
        if p is not None and (p == base or base in p.parents):
            out.append("" if p == root else p.relative_to(root).as_posix())
    return out


def plugin_skill_dirs(root: Path, manifests: list[str]) -> tuple[set[str], set[str]]:
    """From the plugin and marketplace manifests found: (folders whose <name>/SKILL.md are
    skills, folders that are one skill themselves). Paths are relative to the repo root."""
    root = root.resolve()
    lists: set[str] = set()
    single: set[str] = set()

    def plugin(rel_dir: str, extra: list[str], has_key: bool, default: bool = True) -> None:
        skills_dir = f"{rel_dir}/skills".lstrip("/")
        if default:
            lists.add(skills_dir)
        for d in extra:
            (single if (root / d / TK["skill_file"]).is_file() else lists).add(d)
        if not (root / skills_dir).is_dir() and not has_key:
            single.add(rel_dir)

    for rel in manifests:
        rel_dir = rel.rsplit("/", 2)[0] if rel.count("/") >= 2 else ""
        try:
            data = json.loads((root / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        if rel.endswith(TK["plugin_manifest"]):
            plugin(rel_dir, _manifest_paths(root, rel_dir, data), "skills" in data)
            continue
        for e in data.get("plugins") or []:
            src = e.get("source") if isinstance(e, dict) else None
            if not isinstance(src, str):  # a plugin fetched from elsewhere: not in this repo
                continue
            base = (root / rel_dir / src).resolve()
            if base != root and root not in base.parents:
                continue
            at = base.relative_to(root).as_posix() if base != root else ""
            # A marketplace entry that lists its skills loads only those (marketplace-reference).
            plugin(at, _manifest_paths(root, at, e), "skills" in e, default="skills" not in e)
    return lists, single


def is_agent_skill(rel: str, plugins: tuple[set[str], set[str]] = (set(), set())) -> bool:
    """Whether a coding agent loads this SKILL.md (treatment-kinds: skill_dirs, plugins)."""
    parts = rel.split("/")
    if parts[-1] != TK["skill_file"]:
        return False
    lists, single = plugins
    if "/".join(parts[:-1]) in single:
        return True
    if len(parts) < 3:
        return False
    folder = "/".join(parts[:-2])  # the folder that holds <name>/SKILL.md
    return (
        any(folder == d or folder.endswith(f"/{d}") for d in TK["skill_dirs"])
        or folder in TK["root_skill_dirs"]
        or folder in lists
    )


def scan_repo(root: Path, max_files: int = 20_000, max_key_files: int = 120) -> RepoScan:
    root = root.resolve()
    scan = RepoScan(root=str(root))
    langs: Counter[str] = Counter()
    stack: set[str] = set()
    agent: set[str] = set()
    found_skills: list[str] = []
    manifests: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fname in sorted(filenames):
            if scan.file_count >= max_files:
                scan.truncated = True
                break
            scan.file_count += 1
            path = Path(dirpath) / fname
            rel = path.relative_to(root).as_posix()
            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
            if ext in EXT_LANG:
                langs[EXT_LANG[ext]] += 1
            if fname == TK["skill_file"]:
                found_skills.append(rel)
            if rel.endswith((TK["plugin_manifest"], TK["marketplace_manifest"])):
                manifests.append(rel)
            if not _is_key(rel) or len(scan.key_files) >= max_key_files:
                continue
            scan.key_files.append(rel)
            low = rel.lower()
            text = _read(path)
            if low.endswith("package.json"):
                try:
                    pkg = json.loads(text)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    stack.update(NPM_STACK[d] for d in deps if d in NPM_STACK)
                except (json.JSONDecodeError, AttributeError):
                    pass
            if low.endswith(("pyproject.toml", "requirements.txt")):
                for key, label in PY_STACK.items():
                    if re.search(rf"(^|[\s\"'\[,]){re.escape(key)}\b", text, re.I | re.M):
                        stack.add(label)
            if re.search(r"(^|/)dockerfile$|compose\.ya?ml$", low):
                stack.add("Docker")
            if low.endswith(".tf"):
                stack.add("Terraform")
            if "/.github/workflows/" in f"/{low}":
                stack.add("GitHub Actions")
            if re.search(r"apiversion:\s*\S+", text, re.I) and re.search(
                r"kind:\s*(deployment|service|statefulset)", text, re.I
            ):
                stack.add("Kubernetes")
            if low.endswith("claude.md"):
                agent.add("CLAUDE.md")
            if low.endswith("agents.md"):
                agent.add("AGENTS.md")
            if low.endswith(".mcp.json"):
                agent.add("MCP servers")
            if low.endswith(".claude/settings.json"):
                agent.add("Claude Code settings")
            if "/.claude/agents/" in f"/{low}":
                agent.add("Subagents")
            if ".cursor/rules/" in low:
                agent.add("Cursor rules")
        if scan.truncated:
            break
    plugins = plugin_skill_dirs(root, manifests)
    for rel in found_skills:
        if not is_agent_skill(rel, plugins):
            continue
        agent.add("Skills")
        skill = parse_skill(rel, _read(root / rel))
        # Repos often ship one skill in a folder per agent (.claude/, .agents/, ...).
        if all(s.name != skill.name for s in scan.skills):
            scan.skills.append(skill)
        if len(scan.key_files) < max_key_files:
            scan.key_files.append(rel)
    scan.languages = dict(langs.most_common())
    scan.stack = sorted(stack)
    scan.agent_setup = sorted(agent)
    return scan


def scan_to_text(scan: RepoScan, per_file_chars: int = 6_000) -> str:
    langs = ", ".join(f"{k}: {v}" for k, v in scan.languages.items()) or "unknown"
    head = (
        f"Repository {Path(scan.root).name}: {scan.file_count} files"
        f"{' (truncated)' if scan.truncated else ''}.\n"
        f"Languages: {langs}\n"
        f"Stack: {', '.join(scan.stack) or 'none detected'}\n"
        f"Agent setup: {', '.join(scan.agent_setup) or 'none'}\n"
    )
    parts = [head]
    for rel in scan.key_files:
        parts.append(f"### {rel}\n{_read(Path(scan.root) / rel, per_file_chars)}")
    return "\n\n".join(parts)
