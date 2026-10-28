"""Suggest changes to a repo's architecture, from the rules in the improve-architecture skill.

Works on any architecture (read from the code, mapped by an agent, or an Archify spec in the
repo) and any language: it reads the shape of the diagram and the size of the code behind each
block. Nothing here calls a model and nothing is changed in the repo.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from proving_ground import skills
from proving_ground.architecture import SKIP, Architecture, Component

V = skills.load("improve-architecture").values
CODE = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".java", ".kt", ".swift"}
CODE |= {".rb", ".php", ".cs", ".scala", ".vue", ".svelte", ".c", ".cc", ".cpp", ".h"}
INTERNAL = {"backend", "frontend"}
EFFORT_ORDER = {"S": 0, "M": 1, "L": 2}


@dataclass
class Proposal:
    id: str
    title: str
    kind: str
    targets: list[str]
    why: str
    what: str
    impact: dict[str, str]
    effort: str
    evidence: list[str] = field(default_factory=list)
    delta: dict = field(default_factory=dict)
    source: str = "rules"  # rules | review
    # What it adds to the coding agent rather than the app (measurability: adds): a treatment
    # kind ("instructions"), "task" or "step"; "" for a change to the app.
    adds: str = ""

    def dump(self) -> dict:
        return asdict(self)


def _pid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


def _words(c: Component) -> str:
    return f"{c.id} {c.label} {c.sublabel or ''}".lower()


def _has(c: Component, words: list[str]) -> bool:
    text = _words(c)
    return any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", text) for w in words)


@dataclass
class _Stats:
    files: int = 0
    lines: int = 0
    biggest: tuple[str, int] | None = None
    parts: list[tuple[str, int]] = field(default_factory=list)  # sub-folders by lines


def _stats(root: Path, c: Component, claimed: set[Path] | None = None) -> _Stats | None:
    """How much code sits behind a block: from its source folder, or the first evidence path.

    Code inside a folder another block stands for (`claimed`) is that block's, not this one's.
    """
    claimed = claimed or set()
    for rel in [c.source, *c.evidence]:
        if not rel or "/" not in rel and "." not in rel:
            continue
        p = (root / rel.strip().lstrip("./")).resolve()
        if not p.exists() or not p.is_relative_to(root.resolve()):
            continue
        if p.is_file():
            if p.suffix not in CODE:
                continue
            p = p.parent if c.source != rel else p
        files = [p] if p.is_file() else [
            f for f in p.rglob("*") if f.is_file() and f.suffix in CODE
            and not set(f.relative_to(p).parts) & SKIP
            and not any(f.is_relative_to(x) for x in claimed if x != p)
        ][:3000]  # fmt: skip
        s = _Stats()
        by_part: dict[str, int] = {}
        for f in files:
            try:
                n = sum(1 for _ in f.open(errors="ignore"))
            except OSError:
                continue
            s.files += 1
            s.lines += n
            rel_f = str(f.relative_to(root))
            if not s.biggest or n > s.biggest[1]:
                s.biggest = (rel_f, n)
            if p.is_dir():
                head = f.relative_to(p).parts
                if len(head) > 1:
                    by_part[head[0]] = by_part.get(head[0], 0) + n
        s.parts = sorted(by_part.items(), key=lambda x: -x[1])
        return s if s.files else None
    return None


def advise(
    root: Path,
    arch: Architecture,
    workflow_steps: list[tuple[str, str]] | None = None,  # (name, type)
    approved_by_step: dict[str, int] | None = None,
    agent_setup: list[str] | None = None,
) -> list[Proposal]:
    comps = {c.id: c for c in arch.components}
    out_edges: dict[str, set[str]] = {i: set() for i in comps}
    in_edges: dict[str, set[str]] = {i: set() for i in comps}
    for link in arch.connections:
        if link.from_ in comps and link.to in comps and link.from_ != link.to:
            out_edges[link.from_].add(link.to)
            in_edges[link.to].add(link.from_)
    internal = {i for i, c in comps.items() if c.type in INTERNAL}
    ways_in = [i for i, c in comps.items() if c.type == "frontend"]
    out: list[Proposal] = []
    name = lambda i: comps[i].label  # noqa: E731

    # Ways in that already share a flow get that proposal, not a hub of their own.
    covered = {
        x
        for a_i, a in enumerate(ways_in)
        for b in ways_in[a_i + 1 :]
        if len(out_edges[a] & out_edges[b] & internal) >= V["shared_targets_min"]
        for x in (a, b)
    }

    # 1. Hub
    for i, c in comps.items():
        targets = sorted(t for t in out_edges[i] if comps[t].type == "backend")
        if c.type in INTERNAL and len(targets) >= V["hub_fan_out"] and i not in covered:
            layer = f"{i}-service"
            entry = c.type == "frontend"
            out.append(
                Proposal(
                    _pid("hub", i),
                    f"Give {c.label} one service layer to call",
                    "add",
                    [i, *targets],
                    f"{c.label} calls {len(targets)} parts directly ({', '.join(name(t) for t in targets)}), "
                    f"so it holds the order of the work as well as its own job.",
                    f"Add a service layer that owns the flow: {c.label} calls it with one request, and it "
                    f"calls {', '.join(name(t) for t in targets[:4])}{'…' if len(targets) > 4 else ''} in order. "
                    f"{c.label} keeps only {'reading input and showing results' if entry else 'its own job'}.",
                    {
                        "clarity": f"One place to read the flow instead of {len(targets)} call sites.",
                        "agent": "An agent changing the flow edits one file, and can test it without the "
                        + ("UI." if entry else "caller."),
                    },
                    "M",
                    [f"{len(targets)} direct lines out of {c.label}"],
                    {
                        "add": [
                            {
                                "id": layer,
                                "type": "backend",
                                "label": f"{c.label} service",
                                "sublabel": "owns the flow",
                            }
                        ],
                        "disconnect": [[i, t] for t in targets],
                        "connect": [[i, layer, "one call"], *[[layer, t, ""] for t in targets]],
                    },
                )
            )

    # 2. Shared flow between two ways in
    for a_i, a in enumerate(ways_in):
        for b in ways_in[a_i + 1 :]:
            shared = sorted(out_edges[a] & out_edges[b] & internal)
            if len(shared) >= V["shared_targets_min"]:
                svc = f"shared-{a}-{b}"
                out.append(
                    Proposal(
                        _pid("shared", a, b),
                        f"Let {name(a)} and {name(b)} share one flow",
                        "merge",
                        [a, b, *shared],
                        f"{name(a)} and {name(b)} both call {', '.join(name(s) for s in shared)}: the same "
                        "steps are wired twice and can drift apart.",
                        f"Put the steps they share in one service. {name(a)} and {name(b)} become thin: each "
                        "reads its input, calls the service, and shows the result its own way.",
                        {
                            "reliability": "A fix to the flow reaches both ways in at once.",
                            "agent": "One flow to test instead of two that should behave the same.",
                        },
                        "M",
                        [f"{len(shared)} parts called by both"],
                        {
                            "add": [
                                {
                                    "id": svc,
                                    "type": "backend",
                                    "label": "Shared flow",
                                    "sublabel": f"used by {name(a)} and {name(b)}",
                                }
                            ],
                            "disconnect": [[x, s] for x in (a, b) for s in shared],
                            "connect": [
                                [a, svc, ""],
                                [b, svc, ""],
                                *[[svc, s, ""] for s in shared],
                            ],
                        },
                    )
                )

    # 3. Cycles
    seen: set[frozenset[str]] = set()
    for i in internal:
        for t in out_edges[i]:
            pair = frozenset((i, t))
            if t in internal and i in out_edges[t] and pair not in seen:
                seen.add(pair)
                lo, hi = sorted((i, t))
                contracts = f"{lo}-{hi}-contracts"
                out.append(
                    Proposal(
                        _pid("cycle", lo, hi),
                        f"Break the loop between {name(lo)} and {name(hi)}",
                        "reconnect",
                        [lo, hi],
                        f"{name(lo)} calls {name(hi)} and {name(hi)} calls {name(lo)}: neither can be changed, "
                        "tested or understood alone.",
                        f"Move what both need (shared types, small helpers) into a contracts block. Both depend on "
                        f"it; only {name(lo)} calls {name(hi)}, never back.",
                        {
                            "clarity": "Dependencies point one way, so the diagram reads left to right.",
                            "agent": "Each side can be tested with the other faked.",
                        },
                        "M",
                        [f"{name(lo)} ⇄ {name(hi)}"],
                        {
                            "add": [
                                {
                                    "id": contracts,
                                    "type": "backend",
                                    "label": "Contracts",
                                    "sublabel": f"shared by {name(lo)} and {name(hi)}",
                                }
                            ],
                            "disconnect": [[hi, lo]],
                            "connect": [[lo, contracts, ""], [hi, contracts, ""]],
                        },
                    )
                )

    # 4. Model calls on the request path
    for i, c in comps.items():
        if c.type != "backend" or not _has(c, V["server_words"]):
            continue
        models = sorted(
            t
            for t in out_edges[i]
            if comps[t].type in ("external", "cloud") and _has(comps[t], V["model_words"])
        )
        # A direct line from the server to a model API is on the request path, whatever else it
        # queues: work sent through a queue reaches the model API from a worker, not from here.
        if models:
            q, w = f"{i}-jobs", f"{i}-model-worker"
            out.append(
                Proposal(
                    _pid("hotpath", i),
                    "Move model calls off the request path",
                    "move",
                    [i, *models],
                    f"{c.label} answers requests and calls {', '.join(name(m) for m in models)} itself: a request "
                    "waits as long as the slowest model call, and fails when it does.",
                    "Put the call behind a job queue. The server records the job and answers at once; a worker "
                    "makes the model call with a timeout and a retry, and stores the result for the client to "
                    "pick up.",
                    {
                        "speed": "Requests answer at once instead of after a model call (seconds).",
                        "reliability": "A slow or failing model API no longer takes requests down; retries happen "
                        "in the worker.",
                    },
                    "M",
                    [f"{c.label} → {name(m)}" for m in models],
                    {
                        "add": [
                            {
                                "id": q,
                                "type": "messagebus",
                                "label": "Job queue",
                                "sublabel": "model work",
                            },
                            {
                                "id": w,
                                "type": "backend",
                                "label": "Model worker",
                                "sublabel": "timeouts, retries",
                            },
                        ],
                        "disconnect": [[i, m] for m in models],
                        "connect": [[i, q, "jobs"], [q, w, ""], *[[w, m, "calls"] for m in models]],
                    },
                )
            )

    # 5. One store, many writers
    for i, c in comps.items():
        writers = sorted(in_edges[i])
        if c.type == "database" and len(writers) >= V["store_writers"]:
            sqlite = "sqlite" in _words(c)
            dal = f"{i}-access"
            out.append(
                Proposal(
                    _pid("store", i),
                    f"Give {c.label} one owner"
                    if not sqlite
                    else "SQLite: one writer, write-ahead log",
                    "add" if not sqlite else "check",
                    [i, *writers],
                    f"{len(writers)} parts write {c.label} directly ({', '.join(name(x) for x in writers)}).",
                    (
                        "Turn on write-ahead logging (PRAGMA journal_mode=WAL) and send writes through one "
                        "connection, so background work and requests stop locking each other out."
                        if sqlite
                        else f"Put one data-access block in front of {c.label}: queries and migrations live there, "
                        "and the others call it."
                    ),
                    {
                        "reliability": "No more 'database is locked' under concurrent work."
                        if sqlite
                        else "Schema changes touch one place.",
                        "clarity": "One place to see how the data is read and written.",
                    },
                    "S" if sqlite else "M",
                    [f"{len(writers)} lines into {c.label}"],
                    {}
                    if sqlite
                    else {
                        "add": [
                            {
                                "id": dal,
                                "type": "backend",
                                "label": f"{c.label} access",
                                "sublabel": "queries, migrations",
                            }
                        ],
                        "disconnect": [[x, i] for x in writers],
                        "connect": [*[[x, dal, ""] for x in writers], [dal, i, ""]],
                    },
                )
            )

    # 6, 7. Big blocks and big files
    claimed = {
        (root / x.source).resolve()
        for x in comps.values()
        if x.source and (root / x.source).is_dir()
    }
    seen_files: set[str] = set()
    for i, c in comps.items():
        if c.type not in INTERNAL:
            continue
        s = _stats(root, c, claimed)
        if not s:
            continue
        if s.lines >= V["big_lines"] or s.files >= V["big_files"]:
            parts = [p for p in s.parts[: V["max_split_parts"]] if p[1] > s.lines * 0.1]
            if len(parts) >= 2:
                out.append(
                    Proposal(
                        _pid("split", i),
                        f"Split {c.label} along its folders",
                        "split",
                        [i],
                        f"{c.label} is {s.lines:,} lines in {s.files} files; most of it sits in "
                        + ", ".join(f"{n}/ ({lines:,})" for n, lines in parts)
                        + ".",
                        "Make each of those folders its own part with a small interface, and keep in "
                        f"{c.label} only what ties them together.",
                        {
                            "clarity": "Each part fits in one read.",
                            "agent": "An agent loads one part's code, not all of it: less context, fewer wrong edits.",
                        },
                        "L",
                        [f"{c.source or c.evidence[0]}: {s.lines:,} lines"],
                        {
                            "add": [
                                {
                                    "id": f"{i}-{n}",
                                    "type": c.type,
                                    "label": n,
                                    "sublabel": f"from {c.label}, {lines:,} lines",
                                }
                                for n, lines in parts
                            ],
                            "connect": [[i, f"{i}-{n}", ""] for n, _ in parts],
                        },
                    )
                )
        if s.biggest and s.biggest[1] >= V["big_file_lines"] and s.biggest[0] not in seen_files:
            f, n = s.biggest
            seen_files.add(f)
            out.append(
                Proposal(
                    _pid("bigfile", i, f),
                    f"Split {Path(f).name}",
                    "split",
                    [i],
                    f"{f} is {n:,} lines, the largest file in {c.label}.",
                    "Move each group of related functions into its own module and keep the file as the entry "
                    "point that imports them.",
                    {
                        "agent": "Edits stop needing the whole file in context.",
                        "clarity": "Smaller files, clearer names.",
                    },
                    "S" if n < 1500 else "M",
                    [f"{f}: {n:,} lines"],
                    {},
                )
            )

    # 8. Isolated blocks
    for i, c in comps.items():
        if c.type in INTERNAL and not out_edges[i] and not in_edges[i]:
            out.append(
                Proposal(
                    _pid("isolated", i),
                    f"Connect or remove {c.label}",
                    "check",
                    [i],
                    f"Nothing calls {c.label} and it calls nothing.",
                    "Either it's used in a way the diagram misses (add the line), or it's dead code (remove it).",
                    {"clarity": "The diagram matches what runs."},
                    "S",
                    [c.source or (c.evidence[0] if c.evidence else c.label)],
                    {},
                )
            )

    # 8b. Parts with no input, and links that are planned but not built
    fed = {t for t in in_edges if in_edges[t]}
    for i, c in comps.items():
        # Outside services, and infrastructure driven by deploys and pushes, start flows themselves.
        if c.type not in ("external", "cloud") and i not in fed:
            out.append(
                Proposal(
                    _pid("noinput", i),
                    f"Show where {c.label} gets its input",
                    "check",
                    [i],
                    f"Nothing on the diagram feeds {c.label}: it isn't clear what starts it or what it works on.",
                    f"Add the line into {c.label} from what drives it (a person, the OS, another part). If that "
                    "link isn't built yet, add it as planned so the gap is visible.",
                    {
                        "clarity": "Every part shows its input, so the flow can be followed end to end."
                    },
                    "S",
                    c.evidence[:2] or ([c.source] if c.source else []),
                    {},
                )
            )
    for link in arch.connections:
        if link.variant == "planned" and link.from_ in comps and link.to in comps:
            a, b = comps[link.from_], comps[link.to]
            out.append(
                Proposal(
                    _pid("planned", link.from_, link.to),
                    f"Build the link from {a.label} to {b.label}",
                    "add",
                    [link.from_, link.to],
                    f"The diagram marks {a.label} → {b.label} ({link.label or 'planned'}) as planned: the parts "
                    "exist but aren't connected yet, so this flow can't run end to end.",
                    f"Write the client side in {a.label} and the handler in {b.label} for this link, behind the "
                    "same protocol the other clients use, then turn the planned line into a real one.",
                    {"reliability": "The flow runs end to end and can be tested as one."},
                    "M",
                    link.evidence[:2],
                    {},
                )
            )

    # 9. Unverified blocks
    for i, c in comps.items():
        if c.check in ("weak", "missing"):
            out.append(
                Proposal(
                    _pid("verify", i),
                    f"Confirm {c.label} is real",
                    "check",
                    [i],
                    c.why or "Checking against the code didn't find it.",
                    "Point it at the code that runs it, or take it off the diagram.",
                    {"clarity": "Every block on the diagram is something in the repo."},
                    "S",
                    c.evidence[:2],
                    {"remove": [i]} if c.check == "missing" else {},
                )
            )

    # 10. Agent readiness
    setup = {s.lower() for s in agent_setup or []}
    if not ({"claude.md", "agents.md"} & setup):
        out.append(
            Proposal(
                _pid("claudemd"),
                "Add a CLAUDE.md with the commands",
                "add",
                [],
                "There is no CLAUDE.md or AGENTS.md: an agent has to guess how to build, test and run the repo.",
                "Add one at the root with the build, test and run commands, where things live, and the rules "
                "the team keeps (style, what not to touch).",
                {"agent": "The agent starts from the right commands instead of trying them out."},
                "S",
                ["no CLAUDE.md / AGENTS.md at the root"],
                {},
                adds="instructions",
            )
        )
    steps = workflow_steps or []
    if steps:
        approved = approved_by_step or {}
        empty = [n for n, _ in steps if not approved.get(n)]
        if empty:
            out.append(
                Proposal(
                    _pid("scenarios", *empty),
                    f"Add a task for {', '.join(empty[:3])}",
                    "add",
                    [f"step:{n}" for n in empty],
                    f"{len(empty)} of {len(steps)} workflow steps have no approved task, so a skill's effect "
                    "on them can't be measured.",
                    "Write or approve one task per step (in step 4, Measure), with a check that fails until the "
                    "step is done right.",
                    {"agent": "Every step of the flow is measured, not just some."},
                    "S",
                    [f"step {n}: 0 approved" for n in empty[:3]],
                    {},
                    adds="task",
                )
            )
        if not any(t in ("test", "verify", "qa", "review") for _, t in steps):
            out.append(
                Proposal(
                    _pid("verifystep"),
                    "Add a verify step to the workflow",
                    "add",
                    [],
                    "The workflow has no test or review step, so nothing checks the work before it's done.",
                    "Add a last step that runs the tests and reviews the diff; give it a task.",
                    {
                        "reliability": "Mistakes are caught inside the flow.",
                        "agent": "Skills like TDD have a place to act.",
                    },
                    "S",
                    [f"steps: {', '.join(n for n, _ in steps)}"],
                    {},
                    adds="step",
                )
            )

    order = {k: n for n, k in enumerate(V["impact_order"])}
    out.sort(
        key=lambda p: (
            min((order.get(k, 9) for k in p.impact), default=9),
            EFFORT_ORDER.get(p.effort, 1),
        )
    )
    return out[: V["max_proposals"]]


def apply(arch: Architecture, proposals: list[dict], keep_removed: bool = False) -> Architecture:
    """The architecture with the proposals' deltas applied: what it would look like.

    With keep_removed, what a proposal takes away stays on the canvas, marked: removed parts get
    source "removed" and cut links variant "removed"; new links get variant "added". That is
    what lets "Suggested" show the difference instead of just the result."""
    from proving_ground.architecture import Connection, layout

    a = arch.model_copy(deep=True)
    for p in proposals:
        d = p.get("delta") or {}
        ids = {c.id for c in a.components}
        for add in d.get("add", []):
            if add.get("id") and add["id"] not in ids:
                fields = {k: v for k, v in add.items() if k in Component.model_fields}
                a.components.append(Component(**(fields | {"source": "proposed"})))  # drawn as new
                ids.add(add["id"])
        drop = set(d.get("remove", []))
        cut = {tuple(x[:2]) for x in d.get("disconnect", [])}
        if keep_removed:
            for c in a.components:
                if c.id in drop:
                    c.source = "removed"
            for c in a.connections:
                if (c.from_, c.to) in cut or c.from_ in drop or c.to in drop:
                    c.variant = "removed"
        else:
            a.components = [c for c in a.components if c.id not in drop]
            a.connections = [
                c
                for c in a.connections
                if (c.from_, c.to) not in cut and c.from_ not in drop and c.to not in drop
            ]
        ids = {c.id for c in a.components if c.source != "removed"}
        have = {(c.from_, c.to) for c in a.connections if c.variant != "removed"}
        for x in d.get("connect", []):
            if x[0] in ids and x[1] in ids and (x[0], x[1]) not in have:
                a.connections.append(
                    Connection(
                        **{
                            "from": x[0],
                            "to": x[1],
                            "label": (x[2] if len(x) > 2 else "") or None,
                            "variant": "added" if keep_removed else None,
                        }
                    )
                )
                have.add((x[0], x[1]))
    for c in a.components:
        c.pos = None
    a.title = f"{arch.title} (proposed)"
    return layout(a)
