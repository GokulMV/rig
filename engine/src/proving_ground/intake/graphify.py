"""Summarize a Graphify graph.json (node-link format)."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class GraphSummary:
    nodes: int
    edges: int
    communities: int
    top_nodes: list[str] = field(default_factory=list)
    community_tops: list[str] = field(default_factory=list)
    schema_version: str | None = None

    def to_text(self) -> str:
        lines = [
            f"Graphify knowledge graph: {self.nodes} nodes, {self.edges} edges, "
            f"{self.communities} communities (schema {self.schema_version or 'unknown'}).",
            f"Most connected: {', '.join(self.top_nodes)}",
            *self.community_tops,
        ]
        return "\n".join(lines)


def _endpoint(v) -> str:
    return str(v.get("id")) if isinstance(v, dict) else str(v)


def parse_graph(path: Path) -> GraphSummary:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"not a graph: {path.name}")
    nodes = data.get("nodes")
    edges = data.get("links", data.get("edges", []))
    if not isinstance(nodes, list) or not nodes or not isinstance(edges, list):
        raise ValueError(f"not a graph: {path.name} has no nodes list")
    label = {str(n.get("id")): str(n.get("label") or n.get("name") or n.get("id")) for n in nodes}
    degree: Counter[str] = Counter()
    for e in edges:
        degree[_endpoint(e.get("source"))] += 1
        degree[_endpoint(e.get("target"))] += 1
    communities: dict[object, list[str]] = {}
    for n in nodes:
        c = n.get("community", n.get("group", n.get("cluster")))
        if c is not None:
            communities.setdefault(c, []).append(str(n.get("id")))
    ranked = sorted(label, key=lambda nid: (-degree[nid], label[nid]))
    tops = []
    for c, members in sorted(communities.items(), key=lambda kv: -len(kv[1]))[:12]:
        best = sorted(members, key=lambda nid: (-degree[nid], label[nid]))[:6]
        tops.append(f"Community {c} ({len(members)} nodes): {', '.join(label[m] for m in best)}")
    meta = data.get("graph") if isinstance(data.get("graph"), dict) else {}
    version = meta.get("schema_version")
    return GraphSummary(
        nodes=len(nodes),
        edges=len(edges),
        communities=len(communities),
        top_nodes=[label[n] for n in ranked[:8]],
        community_tops=tops,
        schema_version=str(version) if version is not None else None,
    )
