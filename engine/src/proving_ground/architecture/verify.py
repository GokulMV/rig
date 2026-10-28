"""Check an architecture spec (mapped by an agent, or found in the repo) against the code.

A spec is only as good as what the repo shows. Each component is marked:
- found: its evidence files exist and name it, a folder or file is named after it, or reading
  the code found the same thing independently;
- weak: the repo mentions it, but nothing shows it is a part of its own;
- missing: nothing in the repo shows it.
Parts that reading the code found but the spec leaves out are listed as missed. A line is found
when the code shows the same connection. Nothing here calls a model.
"""

from __future__ import annotations

import re
from pathlib import Path

from proving_ground.architecture import SKIP, Architecture, Component

GENERIC = {
    "the", "and", "for", "app", "apps", "service", "services", "server", "system", "layer",
    "module", "core", "data", "backend", "frontend", "client", "web", "main", "src", "lib",
    "shared", "common", "engine", "local", "file", "files", "command", "line", "external",
}  # fmt: skip
# Names an outside service goes by in code.
ALIASES = {
    "claude-api": {"claude", "anthropic"},
    "openai-api": {"openai", "gpt"},
    "github": {"github", "gh"},
    "harbor": {"harbor", "sandbox", "sandboxes", "docker"},
    "docker": {"docker", "container", "containers"},
    "sqlite": {"sqlite", "sqlite3"},
    "aws": {"aws", "boto3", "s3"},
    "stripe": {"stripe"},
}
TEXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs"}
TEXT |= {".toml", ".json", ".yaml", ".yml", ".md", ".cfg", ".ini", ".env", ".sql", ".vue"}


def _tokens(*texts: str | None) -> set[str]:
    words = set()
    for t in texts:
        for w in re.findall(r"[a-z0-9]+", (t or "").lower().replace("_", " ")):
            if len(w) >= 2 and w not in GENERIC:
                words.add(w)
    return words


def _names(c: Component) -> set[str]:
    return _tokens(c.id, c.label, c.sublabel) | ALIASES.get(c.id, set())


class _Repo:
    """Paths and a capped read of text files, enough to look names up."""

    def __init__(self, root: Path, max_files: int = 4000, max_read: int = 1500):
        self.root = root
        self.paths: list[str] = []
        self.text: dict[str, str] = {}
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root)
            if set(rel.parts) & SKIP or any(
                x.startswith(".") and x != ".env" for x in rel.parts[:-1]
            ):
                continue
            self.paths.append(str(rel))
            if p.is_file() and p.suffix in TEXT and len(self.text) < max_read:
                try:
                    self.text[str(rel)] = p.read_text(errors="ignore")[:6000].lower()
                except OSError:
                    pass
            if len(self.paths) >= max_files:
                break
        self.segments = {
            seg.lower().removesuffix(Path(seg).suffix) for x in self.paths for seg in Path(x).parts
        }

    def mentions(self, words: set[str]) -> bool:
        pats = [re.compile(rf"\b{re.escape(w)}\b") for w in words if len(w) >= 4]
        return any(p.search(t) for t in self.text.values() for p in pats)

    def evidence(self, c: Component) -> tuple[list[str], bool]:
        """(evidence paths that exist, whether one of them names the component)."""
        found, names = [], _names(c)
        for e in c.evidence[:6]:
            rel = e.strip().lstrip("./")
            if not rel or ".." in Path(rel).parts:
                continue
            p = self.root / rel
            if not p.exists():
                continue
            found.append(rel)
            if _tokens(rel) & names:
                return found, True
            files = [p] if p.is_file() else [x for x in p.rglob("*") if x.is_file()][:40]
            for f in files:
                key = str(f.relative_to(self.root))
                text = self.text.get(key)
                if text is None and f.suffix in TEXT:
                    try:
                        text = f.read_text(errors="ignore")[:6000].lower()
                    except OSError:
                        text = ""
                if text and any(
                    re.search(rf"\b{re.escape(w)}\b", text) for w in names if len(w) >= 3
                ):
                    return found, True
        return found, False


def _match(c: Component, inferred: list[Component]) -> Component | None:
    """The part reading the code found that is the same thing: by name, then by kind."""
    names = _names(c)
    best, score = None, 0
    for i in inferred:
        # The other side by its name only: a description mentioning "Claude" isn't the Claude API.
        common = len(names & (_tokens(i.id, i.label) | ALIASES.get(i.id, set())))
        if not common:
            continue
        common += (2 if i.id == c.id else 0) + (1 if i.type == c.type else 0)
        if common > score:
            best, score = i, common
    return best


def verify(root: Path, spec: Architecture, inferred: Architecture) -> Architecture:
    repo = _Repo(root)
    twin: dict[str, str] = {}  # spec id -> inferred id
    counts = {"found": 0, "weak": 0, "missing": 0}
    for c in spec.components:
        paths, named = repo.evidence(c)
        m = _match(c, inferred.components)
        names = _names(c)
        if named:
            c.check, c.why = "found", f"Shown in {paths[0]}."
        elif m is not None:
            c.check, c.why = "found", f"Reading the code found it too ({m.label})."
        elif names & repo.segments:
            seg = sorted(names & repo.segments)[0]
            c.check, c.why = "found", f"There is a folder or file named {seg}."
        elif paths:
            c.check, c.why = "weak", f"{paths[0]} exists but doesn't name it."
        elif repo.mentions(names):
            c.check, c.why = (
                "weak",
                "The code mentions it, but nothing shows it's a part of its own.",
            )
        else:
            listed = (
                f" (it cited {', '.join(c.evidence[:2])}, which aren't in the repo)"
                if c.evidence
                else ""
            )
            c.check, c.why = "missing", f"Nothing in the repo shows this{listed}."
        if m is not None:
            twin[c.id] = m.id
        counts[c.check] += 1

    covered = set(twin.values())
    missed = [
        i.label
        for i in inferred.components
        if i.id not in covered and not i.label.endswith(" core") and i.type != "backend"
    ]
    edges = {(x.from_, x.to) for x in inferred.connections}
    lines_found = 0
    for link in spec.connections:
        a, b = twin.get(link.from_), twin.get(link.to)
        if a and b and ((a, b) in edges or (b, a) in edges):
            link.check = "found"
            lines_found += 1
        else:
            link.check = "unchecked"
    # Where does each part get its input? Actors and outside services start flows; every other
    # part needs a line coming in, or the diagram hides how it is driven.
    fed = {x.to for x in spec.connections}
    no_input = [
        c.label for c in spec.components if c.id not in fed and c.type not in ("external", "cloud")
    ]
    planned = [f"{x.from_} → {x.to}" for x in spec.connections if x.variant == "planned"]
    total = len(spec.components)
    spec.check = {
        "no_input": no_input,
        "planned": planned,
        **counts,
        "total": total,
        "missed": missed,
        "lines_found": lines_found,
        "lines_total": len(spec.connections),
        "summary": f"{counts['found']} of {total} parts found in the code"
        + (f", {counts['missing']} not found" if counts["missing"] else "")
        + (f"; it leaves out {', '.join(missed[:3])}" if missed else "")
        + (f"; no input shown for {', '.join(no_input[:3])}" if no_input else ""),
    }
    return spec
