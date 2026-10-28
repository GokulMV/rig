"""A repo's architecture as components, boundaries and connections.

The model follows Archify's architecture spec (tt-a1i/archify, MIT): an existing spec is
imported as is; otherwise a first pass is inferred from docker-compose, manifests and imports.
Nothing here calls a model.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from proving_ground.files import PG_DIR

Kind = Literal["frontend", "backend", "database", "cloud", "security", "messagebus", "external"]
ORDER: dict[str, int] = {
    "external": 0,
    "frontend": 1,
    "cloud": 2,
    "security": 2,
    "backend": 3,
    "messagebus": 4,
    "database": 5,
}
# Bump when reading the code changes what it finds, so cached architectures are read again.
READ_VERSION = 3

# Where "Map with Archify" keeps the spec an agent wrote: ours, not the repo's own .archify/.
MAPPED_SPEC = "archify.json"
SKIP = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", PG_DIR, ".archify"}


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Component(_Loose):
    id: str = Field(min_length=1)
    type: Kind = "backend"
    label: str = Field(min_length=1)
    sublabel: str | None = None
    role: str | None = None  # what it really is ("Surface driver"); `type` only sets the colour
    pos: tuple[float, float] | None = None
    source: str | None = None  # the file this component was read from
    # Map with Archify asks the agent for the files that show the component exists.
    evidence: list[str] = Field(default_factory=list)
    # Set by checking the spec against the code: found, weak or missing, and why.
    check: Literal["found", "weak", "missing"] | None = None
    why: str | None = None


class Connection(_Loose):
    from_: str = Field(alias="from")
    to: str
    label: str | None = None
    variant: str | None = None  # "planned": should exist, isn't built yet
    evidence: list[str] = Field(default_factory=list)
    check: Literal["found", "unchecked"] | None = None


class FlowStep(_Loose):
    from_: str = Field(alias="from")
    to: str
    what: str = ""


class Flow(_Loose):
    """A journey through the system, step by step: what really happens, in order."""

    name: str
    steps: list[FlowStep] = Field(default_factory=list)


class Boundary(_Loose):
    kind: str = "region"
    label: str = ""
    wraps: list[str] = Field(default_factory=list)


class Architecture(_Loose):
    title: str = "Architecture"
    source: Literal["archify", "mapped", "inferred"] = "inferred"
    spec_path: str | None = None
    components: list[Component] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)
    boundaries: list[Boundary] = Field(default_factory=list)
    flows: list[Flow] = Field(default_factory=list)
    # A spec (mapped, or found in the repo) checked against the code; None when read from the code.
    check: dict | None = None
    # How it was read: a cache from an older way of reading the code is read again.
    version: int = 0

    def dump(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)


def layout(a: Architecture) -> Architecture:
    """Give unplaced components a position, left to right along the connections.

    Each block sits one column right of the furthest block that points at it, so lines read
    left to right. Blocks with no lines go by kind (ways in on the left, stores and outside
    services on the right). With no lines at all, columns are by kind.
    """
    unplaced = [c for c in a.components if c.pos is None]
    if not unplaced:
        return a
    ids = {c.id for c in unplaced}
    preds: dict[str, list[str]] = {i: [] for i in ids}
    for link in a.connections:
        if link.from_ in ids and link.to in ids and link.from_ != link.to:
            preds[link.to].append(link.from_)
    linked = {i for i in ids if preds[i]} | {p for ps in preds.values() for p in ps}

    col: dict[str, int] = {}
    kind_of = {c.id: c.type for c in unplaced}
    outside = {i for i in ids if kind_of[i] in ("database", "external", "messagebus")}
    if not linked:
        kinds = sorted({ORDER.get(c.type, 3) for c in unplaced})
        col = {c.id: kinds.index(ORDER.get(c.type, 3)) for c in unplaced}
    else:
        succ: dict[str, list[str]] = {i: [] for i in ids}
        for t, ps in preds.items():
            for p in ps:
                succ[p].append(t)
        # Ways in: frontends, else blocks nothing points at. Columns are steps away from them,
        # which stays readable even where the code has cycles.
        starts = (
            [i for i in sorted(linked) if kind_of[i] == "frontend"]
            or [i for i in sorted(linked) if not preds[i]]
            or sorted(linked)[:1]
        )
        frontier = list(starts)
        for i in starts:
            col[i] = 0
        while frontier:
            nxt = []
            for n in frontier:
                for t in succ[n]:
                    if t not in col:
                        col[t] = col[n] + 1
                        nxt.append(t)
            frontier = nxt
        inner = [col[i] for i in col if i not in outside] or [0]
        last = max(inner) + 1
        for c in unplaced:
            if c.id in outside and (c.id in col or c.id not in linked):
                col[c.id] = (
                    max(col.get(c.id, 0), last) if c.type != "messagebus" else col.get(c.id, 1)
                )
            elif c.id not in col:
                col[c.id] = 0 if ORDER.get(c.type, 3) <= 1 else 1
        # Close the gaps left by empty columns.
        used = sorted(set(col.values()))
        col = {i: used.index(k) for i, k in col.items()}

    # Rows: within a column, by kind, then near the blocks that point at them.
    row: dict[str, float] = {}
    by_col: dict[int, list[Component]] = {}
    for c in unplaced:
        by_col.setdefault(col[c.id], []).append(c)
    for k in sorted(by_col):

        def key(c: Component) -> tuple[float, int]:
            placed = [row[p] for p in preds.get(c.id, []) if p in row]
            return (sum(placed) / len(placed) if placed else 0.0, ORDER.get(c.type, 3))

        for r, c in enumerate(sorted(by_col[k], key=key)):
            row[c.id] = r
            c.pos = (40 + k * 248, 60 + r * 128)
    return a


# ---------- Archify specs ----------


def _is_architecture(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("diagram_type") == "architecture"


def find_specs(root: Path) -> list[Path]:
    """Archify architecture specs in the repo: `.archify/**/candidate.json` or `*.architecture.json`."""
    found: list[Path] = []
    for pattern in (".archify/**/candidate.json", "**/*.architecture.json"):
        for p in sorted(root.glob(pattern)):
            parts = set(p.relative_to(root).parts[:-1])
            if parts & (SKIP - {".archify"}):
                continue
            if p not in found and _is_architecture(p):
                found.append(p)
    return found


def parse_spec(path: Path) -> Architecture:
    data = json.loads(path.read_text(encoding="utf-8"))
    return parse_data(data, name=path.name, spec_path=str(path))


def parse_data(
    data: object, name: str = "spec", spec_path: str | None = None, source: str = "archify"
) -> Architecture:
    """Check an Archify architecture spec (already parsed JSON) and give it a layout."""
    if not isinstance(data, dict) or data.get("diagram_type") != "architecture":
        raise ValueError(f"{name} is not an architecture diagram")
    try:
        a = Architecture(
            title=(data.get("meta") or {}).get("title") or "Architecture",
            source=source,
            spec_path=spec_path,
            components=data.get("components", []),
            connections=data.get("connections", []),
            boundaries=data.get("boundaries", []),
            flows=data.get("flows", []),
        )
    except ValidationError as e:
        raise ValueError(f"{name}: {e.errors()[0]['msg']}") from e
    if not a.components:
        raise ValueError(f"{name} has no components")
    ids = {c.id for c in a.components}
    # A line to a component that isn't there can't be drawn: drop it rather than fail the spec.
    a.connections = [c for c in a.connections if c.from_ in ids and c.to in ids]
    for f in a.flows:
        f.steps = [s for s in f.steps if s.from_ in ids and s.to in ids]
    a.flows = [f for f in a.flows if f.steps]
    return layout(a)


# ---------- Inferred first pass ----------

IMAGE_KINDS: list[tuple[str, Kind, str | None]] = [
    (r"postgres|mysql|mariadb|mongo|cockroach|clickhouse|cassandra|sqlserver", "database", None),
    (r"redis|valkey|memcached", "database", "cache"),
    (r"rabbitmq|kafka|nats|redpanda|pulsar|activemq|localstack", "messagebus", None),
    (r"nginx|traefik|envoy|caddy|haproxy", "cloud", "proxy"),
    (r"keycloak|vault|oauth|authelia", "security", None),
]
FRONTEND = {"react": "React", "next": "Next.js", "vue": "Vue", "svelte": "Svelte", "vite": "Vite"}
BACKEND_JS = {"express": "Express", "fastify": "Fastify", "@nestjs/core": "NestJS"}
STORES = [
    (r"\b(psycopg2?|asyncpg|pg)\b", "postgres", "Postgres"),
    (r"\b(pymongo|mongoose|motor)\b", "mongo", "MongoDB"),
    (r"\b(mysqlclient|pymysql|mysql2)\b", "mysql", "MySQL"),
    (r"\b(redis|ioredis)\b", "redis", "Redis"),
    (r"\b(kafka-python|confluent-kafka|kafkajs)\b", "kafka", "Kafka"),
    (r"\b(pika|amqplib|celery)\b", "queue", "Message queue"),
]


def _compose(root: Path) -> tuple[list[Component], list[Connection]]:
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml"):
        path = root / name
        if path.is_file():
            break
    else:
        return [], []
    try:
        services = (yaml.safe_load(path.read_text()) or {}).get("services") or {}
    except yaml.YAMLError:
        return [], []
    comps, links = [], []
    for sid, svc in services.items():
        svc = svc or {}
        image = str(svc.get("image") or "")
        build = svc.get("build")
        context = (
            build if isinstance(build, str) else (build or {}).get("context", "") if build else ""
        )
        kind: Kind = "backend"
        sub: str | None = image.split(":")[0] or None
        for pattern, k, label in IMAGE_KINDS:
            if re.search(pattern, image.lower()):
                kind, sub = k, label or image.split(":")[0]
                break
        else:
            if re.search(r"web|front|ui|client", f"{sid} {context}".lower()):
                kind = "frontend"
        comps.append(Component(id=sid, type=kind, label=sid, sublabel=sub, source=name))
        deps = svc.get("depends_on") or []
        for dep in deps if isinstance(deps, list) else list(deps):
            links.append(Connection(**{"from": sid, "to": dep}))
    return comps, links


# Outside services, found in the code that reaches them: (pattern, id, label, kind, sublabel, line).
EXTERNALS: list[tuple[str, str, str, Kind, str | None, str]] = [
    (
        r"^\s*(?:import|from)\s+anthropic\b",
        "claude-api",
        "Claude API",
        "external",
        None,
        "messages",
    ),
    (r"^\s*(?:import|from)\s+openai\b", "openai-api", "OpenAI API", "external", None, "API calls"),
    (
        r"^\s*(?:import|from)\s+(?:litellm)\b",
        "llm-api",
        "Model APIs",
        "external",
        "LiteLLM",
        "API calls",
    ),
    (
        r"^\s*(?:import|from)\s+harbor\b",
        "harbor",
        "Harbor sandboxes",
        "external",
        "Docker",
        "trials",
    ),
    (r"^\s*(?:import|from)\s+docker\b", "docker", "Docker", "external", None, "containers"),
    (
        r"[\[(]\s*[\"']gh[\"']\s*,|api\.github\.com|^\s*(?:import|from)\s+github\b",
        "github",
        "GitHub API",
        "external",
        None,
        "search",
    ),
    (r"^\s*(?:import|from)\s+boto3\b", "aws", "AWS", "external", None, "SDK"),
    (r"^\s*(?:import|from)\s+stripe\b", "stripe", "Stripe", "external", None, "payments"),
    (
        r"^\s*import\s+sqlite3|sqlite(?:\+\w+)?://",
        "sqlite",
        "SQLite",
        "database",
        "local file",
        "SQL",
    ),
]
WEB_FRAMEWORKS = [
    (r"^\s*(?:import|from)\s+fastapi\b", "FastAPI"),
    (r"^\s*(?:import|from)\s+flask\b", "Flask"),
    (r"^\s*(?:import|from)\s+django\b", "Django"),
]
SHARED = {"models", "types", "schemas", "files", "utils", "util", "common", "constants", "errors"}
SHARED |= {"config", "settings", "logging", "log"}
IMPORT = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import\s+(?:\(([^)]*)\)|([\w, ]+))|import\s+([\w.]+))", re.M
)


def _doc(path: Path) -> str | None:
    """The first line of a module's docstring: what that part of the code is for."""
    try:
        m = re.match(
            r'\s*(?:#[^\n]*\n\s*)*[rRuU]?("""|\'\'\')(.*?)(?:\1|\n)',
            path.read_text(errors="ignore"),
        )
    except OSError:
        return None
    line = re.split(r"(?<=[a-z0-9)])\.\s", (m.group(2) if m else "").strip())[0].rstrip(".")
    return _clip(line) or None


def _clip(text: str, n: int = 56) -> str:
    """At most n characters, cut at a word (or list) boundary."""
    if len(text) <= n:
        return text
    cut = text[: n - 1]
    return cut[: max(cut.rfind(" "), cut.rfind(","))].rstrip(" ,") + "…"


class _Unit:
    def __init__(self, comp: Component, files: list[Path]):
        self.comp, self.files = comp, files
        self.text = ""
        for f in files[:400]:
            try:
                self.text += f.read_text(errors="ignore") + "\n"
            except OSError:
                pass


def _script_targets(root: Path, bases: list[Path]) -> list[tuple[str, str]]:
    """(command, module) for each console script in the pyproject.toml files."""
    import tomllib

    out = []
    files = {(b.parent if b.name == "src" else b) / "pyproject.toml" for b in bases}
    for pp in sorted(files | {root / "pyproject.toml"}):
        try:
            scripts = tomllib.loads(pp.read_text()).get("project", {}).get("scripts", {})
        except (OSError, tomllib.TOMLDecodeError):
            continue
        out += [(name, str(t).split(":")[0]) for name, t in sorted(scripts.items())]
    return out


def _python_packages(root: Path) -> tuple[list[_Unit], list[Connection], list[Path]]:
    # src/ layouts, at the root or one level down (monorepos such as engine/src/).
    nested = [d / "src" for d in sorted(root.iterdir()) if d.is_dir() and d.name not in SKIP]
    bases = [b for b in [root / "src", *nested] if b.is_dir()] or [root]
    units: list[_Unit] = []

    def is_pkg(p: Path) -> bool:
        # Has __init__.py, or holds sub-packages (a namespace package such as src/shop/).
        return (p / "__init__.py").is_file() or any(
            (s / "__init__.py").is_file() for s in p.iterdir() if s.is_dir()
        )

    pkgs: set[str] = set()
    scripts = _script_targets(root, bases)
    for name, module in scripts:
        # The command line is a way in, like the UI: its own block, reading its own module.
        f = next(
            (
                b / Path(*module.split("."))
                for b in bases
                if (b / Path(*module.split("."))).with_suffix(".py").is_file()
            ),
            None,
        )
        units.append(
            _Unit(
                Component(
                    id="cli" if not any(u.comp.id == "cli" for u in units) else f"cli-{name}",
                    type="frontend",
                    label=f"{name} CLI",
                    sublabel="command line",
                    source=module,
                ),
                [f.with_suffix(".py")] if f else [],
            )
        )
    script_files = {p for u in units for p in u.files}
    for base in bases:
        for pkg in sorted(p for p in base.iterdir() if p.is_dir() and is_pkg(p)):
            if pkg.name in SKIP or pkg.name.startswith((".", "test")):
                continue
            subs = sorted(
                s
                for s in pkg.iterdir()
                if s.is_dir() and (s / "__init__.py").is_file() and s.name not in SKIP
            )
            for unit in subs:
                units.append(
                    _Unit(
                        Component(
                            id=f"{pkg.name}.{unit.name}",
                            type="backend",
                            label=unit.name,
                            sublabel=_doc(unit / "__init__.py"),
                            source=str(unit.relative_to(root)),
                        ),
                        list(unit.rglob("*.py")),
                    )
                )
            # Modules at the package root (or a package with no sub-packages): one block.
            top = [
                f
                for f in sorted(pkg.glob("*.py"))
                if (f.name != "__init__.py" or not subs) and f not in script_files
            ]
            if not subs or any(f.stat().st_size > 0 for f in top):
                pkgs.add(pkg.name)
                units.append(
                    _Unit(
                        Component(
                            id=pkg.name,
                            type="backend",
                            label=f"{pkg.name} core" if subs else pkg.name,
                            role="Shared code" if subs else "Package",
                            sublabel=(
                                _clip(
                                    "shared: "
                                    + ", ".join(f.stem for f in top if f.name != "__init__.py")
                                )
                                if subs
                                else _doc(pkg / "__init__.py")
                            ),
                            source=str(pkg.relative_to(root)),
                        ),
                        top if subs else list(pkg.rglob("*.py")),
                    )
                )
    ids = {u.comp.id for u in units}

    def resolve(target: str) -> str | None:
        parts = target.split(".")
        two = ".".join(parts[:2])
        if two in ids:
            return two
        return parts[0] if parts[0] in pkgs else None

    links: set[tuple[str, str]] = set()
    for u in units:
        for m in IMPORT.finditer(u.text):
            mod, grouped, inline, plain = m.groups()
            names = re.sub(r"#[^\n]*", "", grouped or inline or "")
            if plain:
                targets = [plain]
            else:
                # `from shop import billing` points at billing, not at shop's core.
                targets = [f"{mod}.{n.strip()}" for n in names.split(",") if n.strip()]
                if not any(resolve(t) not in (None, mod.split(".")[0]) for t in targets):
                    targets = [mod]
            for t in targets:
                h = resolve(t)
                if not h or h == u.comp.id:
                    continue
                if h in pkgs and u.comp.id.startswith(f"{h}."):
                    # Into its own package's core: only real logic (service, store) is a line;
                    # shared models, types and helpers are used by everything and say nothing.
                    module = t.split(".")[1] if "." in t else ""
                    if not module or module in SHARED:
                        continue
                links.add((u.comp.id, h))
        for pattern, name in WEB_FRAMEWORKS:
            if re.search(pattern, u.text, re.M):
                u.comp.sublabel = " · ".join(x for x in (name, u.comp.sublabel) if x)
                break
    return units, [Connection(**{"from": a, "to": b}) for a, b in sorted(links)], bases


def _externals(units: list[_Unit]) -> tuple[list[Component], list[Connection]]:
    comps: dict[str, Component] = {}
    links = []
    for u in units:
        for pattern, cid, label, kind, sub, line in EXTERNALS:
            if re.search(pattern, u.text, re.M):
                comps.setdefault(
                    cid, Component(id=cid, type=kind, label=label, sublabel=sub, source="code")
                )
                links.append(Connection(**{"from": u.comp.id, "to": cid, "label": line}))
    return list(comps.values()), links


def _js_apps(root: Path) -> list[Component]:
    comps = []
    candidates = (
        [root / "package.json"]
        + sorted(root.glob("*/package.json"))
        + sorted(root.glob("*/*/package.json"))
    )
    for pj in candidates:
        if not pj.is_file() or set(pj.relative_to(root).parts) & SKIP:
            continue
        try:
            data = json.loads(pj.read_text())
        except ValueError:
            continue
        deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
        fe_tags = [v for k, v in FRONTEND.items() if k in deps]
        fe = " · ".join(fe_tags) if any(k in deps for k in FRONTEND if k != "vite") else None
        be = next((v for k, v in BACKEND_JS.items() if k in deps), None)
        if not fe and not be:
            continue
        name = pj.parent.name if pj.parent != root else (data.get("name") or "app")
        comps.append(
            Component(
                id=name,
                type="frontend" if fe else "backend",
                label=name,
                sublabel=fe or be,
                source=str(pj.relative_to(root)),
            )
        )
    return comps


def _stores(root: Path, taken: set[str]) -> list[Component]:
    text = ""
    for name in ("pyproject.toml", "requirements.txt", "package.json"):
        p = root / name
        if p.is_file():
            text += p.read_text(errors="ignore").lower() + "\n"
    out = []
    for pattern, cid, label in STORES:
        if cid not in taken and re.search(pattern, text):
            kind: Kind = "messagebus" if cid in {"kafka", "queue"} else "database"
            out.append(Component(id=cid, type=kind, label=label, sublabel="from dependencies"))
    return out


def _calls_api(app_dir: Path) -> bool:
    """A frontend that calls a same-origin HTTP API ("/api/...")."""
    for f in list(app_dir.glob("src/**/*"))[:600]:
        if f.suffix in {".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte"} and f.is_file():
            if re.search(r"[`'\"]/api/", f.read_text(errors="ignore")):
                return True
    return False


def infer_architecture(root: Path) -> Architecture:
    comps, links = _compose(root)
    if not comps:
        units, links, _ = _python_packages(root)
        comps = [u.comp for u in units]
        ext, ext_links = _externals(units)
        js = _js_apps(root)
        servers = [
            u.comp for u in units if re.search(r"^(FastAPI|Flask|Django)\b", u.comp.sublabel or "")
        ]
        for app in js:
            if (
                app.type == "frontend"
                and servers
                and _calls_api(root / Path(app.source or "").parent)
            ):
                links.append(
                    Connection(**{"from": app.id, "to": servers[0].id, "label": "HTTP /api"})
                )
        comps = js + comps + ext
        links = links + ext_links
        # Ways in are driven by people: show who, so every part has an input.
        entries = [c for c in comps if c.type == "frontend"]
        if entries:
            comps.insert(
                0,
                Component(
                    id="you", type="external", role="Person", label="You", sublabel="developer"
                ),
            )
            for c in entries:
                verb = "runs" if c.label.endswith("CLI") else "uses"
                links.append(Connection(**{"from": "you", "to": c.id, "label": verb}))
    taken = (
        {c.id for c in comps}
        | {(c.sublabel or "").lower() for c in comps}
        | {c.label.lower() for c in comps}
    )
    comps += _stores(root, taken)
    return layout(
        Architecture(title=f"{root.name} architecture", components=comps, connections=links)
    )


def load_architecture(root: Path, refresh: bool = False) -> Architecture:
    """The repo's own Archify spec, else one mapped by an agent, else the inferred first pass. Cached."""
    cache = root / PG_DIR / "architecture.json"
    if cache.is_file() and not refresh:
        try:
            cached = Architecture.model_validate_json(cache.read_text())
            # Read again when the way of reading changed, or a spec was cached before checks existed.
            if cached.version == READ_VERSION and (
                cached.source == "inferred" or cached.check is not None
            ):
                return cached
        except ValidationError:
            pass
    specs = find_specs(root)
    mapped = root / PG_DIR / MAPPED_SPEC
    if specs:
        a = verify(root, parse_spec(specs[0]), infer_architecture(root))
    elif mapped.is_file():
        data = json.loads(mapped.read_text(encoding="utf-8"))
        a = verify(
            root, parse_data(data, mapped.name, str(mapped), "mapped"), infer_architecture(root)
        )
    else:
        a = infer_architecture(root)
    a.version = READ_VERSION
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(a.dump(), indent=2))
    return a


from proving_ground.architecture.verify import verify  # noqa: E402 - uses the models above
