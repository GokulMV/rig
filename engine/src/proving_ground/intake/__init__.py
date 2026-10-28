"""Turn repos, graphs and documents into project sources."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from proving_ground.intake.docs import IMAGE_SUFFIXES, TEXT_SUFFIXES, read_pdf, read_text_file
from proving_ground.intake.graphify import GraphSummary, parse_graph
from proving_ground.intake.repo import SKILL_RULE, RepoScan, scan_repo, scan_to_text
from proving_ground.store import Store

GRAPH_LOCATIONS = ("graphify-out/graph.json",)


@dataclass
class IntakeResult:
    project_id: int
    scan: RepoScan
    graph: GraphSummary | None = None
    sources: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _add_graph(store: Store, pid: int, path: Path, res: IntakeResult) -> bool:
    try:
        g = parse_graph(path)
    except (ValueError, OSError):
        return False
    res.graph = g
    meta = {"nodes": g.nodes, "edges": g.edges, "communities": g.communities, "top": g.top_nodes}
    store.add_source(pid, "graph", path.name, g.to_text(), meta)
    res.sources.append(("graph", path.name))
    return True


def run_intake(store: Store, root: Path, extra: Sequence[Path] = ()) -> IntakeResult:
    root = root.resolve()
    pid = store.ensure_project(str(root))
    scan = scan_repo(root)
    res = IntakeResult(project_id=pid, scan=scan)
    store.add_source(
        pid,
        "repo",
        f"{root.name}/",
        scan_to_text(scan),
        {
            "files": scan.file_count,
            "stack": scan.stack,
            "agent_setup": scan.agent_setup,
            "skills": [s.name for s in scan.skills],
            "languages": scan.languages,
            "skill_details": [
                {"name": s.name, "description": s.description, "path": s.path} for s in scan.skills
            ],
            "truncated": scan.truncated,
            "skill_rule": SKILL_RULE,
        },
    )
    res.sources.append(("repo", f"{root.name}/"))
    for rel in GRAPH_LOCATIONS:
        if (root / rel).is_file():
            _add_graph(store, pid, root / rel, res)
    graph_report = root / "graphify-out" / "GRAPH_REPORT.md"
    if graph_report.is_file():
        store.add_source(pid, "md", graph_report.name, read_text_file(graph_report))
        res.sources.append(("md", graph_report.name))
    for path in extra:
        suffix = path.suffix.lower()
        if suffix == ".json" and _add_graph(store, pid, path, res):
            continue
        if suffix == ".pdf":
            text, pages = read_pdf(path)
            store.add_source(pid, "pdf", path.name, text, {"pages": pages})
            res.sources.append(("pdf", path.name))
        elif suffix in TEXT_SUFFIXES:
            kind = "md" if suffix in {".md", ".markdown"} else suffix.lstrip(".")
            store.add_source(pid, kind, path.name, read_text_file(path))
            res.sources.append((kind, path.name))
        elif suffix in IMAGE_SUFFIXES:
            store.add_source(pid, "image", path.name, "", {"path": str(path.resolve())})
            res.sources.append(("image", path.name))
        else:
            res.skipped.append(path.name)
    return res
