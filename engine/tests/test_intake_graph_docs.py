import json
from pathlib import Path

import pytest
from fpdf import FPDF

from proving_ground.intake import run_intake
from proving_ground.intake.docs import read_pdf, read_text_file
from proving_ground.intake.graphify import parse_graph
from proving_ground.store import Store

GRAPH = {
    "directed": False,
    "graph": {"schema_version": "3", "graphify_version": "0.9.1"},
    "nodes": [
        {"id": "api", "label": "APIRouter", "community": 0},
        {"id": "dep", "label": "Depends", "community": 0},
        {"id": "db", "label": "Session", "community": 1},
        {"id": "m", "label": "Model", "community": 1},
    ],
    "links": [
        {"source": "api", "target": "dep"},
        {"source": "api", "target": "db"},
        {"source": "api", "target": "m"},
        {"source": "db", "target": "m"},
    ],
}


def test_parse_graph(tmp_path: Path):
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(GRAPH))
    g = parse_graph(p)
    assert (g.nodes, g.edges, g.communities, g.schema_version) == (4, 4, 2, "3")
    assert g.top_nodes[0] == "APIRouter"
    assert g.community_tops[0].startswith("Community 0 (2 nodes): APIRouter")
    assert "4 nodes, 4 edges, 2 communities" in g.to_text()


def test_parse_graph_accepts_edges_key_and_object_endpoints(tmp_path: Path):
    data = {
        "nodes": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}],
        "edges": [{"source": {"id": 1}, "target": {"id": 2}}],
    }
    p = tmp_path / "g.json"
    p.write_text(json.dumps(data))
    g = parse_graph(p)
    assert (g.nodes, g.edges, g.communities) == (2, 1, 0)
    assert set(g.top_nodes) == {"A", "B"}


def test_parse_graph_rejects_non_graph(tmp_path: Path):
    p = tmp_path / "x.json"
    p.write_text('{"hello": 1}')
    with pytest.raises(ValueError, match="not a graph"):
        parse_graph(p)


def make_pdf(path: Path, pages: list[str]) -> None:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    for text in pages:
        pdf.add_page()
        pdf.cell(0, 10, text)
    pdf.output(str(path))


def test_read_pdf(tmp_path: Path):
    p = tmp_path / "spec.pdf"
    make_pdf(p, ["Checkout service design", "Refund policy limits"])
    text, pages = read_pdf(p)
    assert pages == 2
    assert "Checkout service design" in text
    assert "Refund policy limits" in text
    text1, _ = read_pdf(p, max_pages=1)
    assert "Refund policy" not in text1


def test_read_text_file_truncates(tmp_path: Path):
    p = tmp_path / "a.md"
    p.write_text("x" * 100)
    assert read_text_file(p, max_chars=10) == "x" * 10 + "\n[cut]"


def test_run_intake_stores_sources(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "graphify-out").mkdir(parents=True)
    (repo / "README.md").write_text("Payments service")
    (repo / "graphify-out" / "graph.json").write_text(json.dumps(GRAPH))
    (repo / "graphify-out" / "GRAPH_REPORT.md").write_text("God nodes: APIRouter")
    design = tmp_path / "design.md"
    design.write_text("# Design\nUse queues.")
    pdf = tmp_path / "arch.pdf"
    make_pdf(pdf, ["Architecture overview"])
    img = tmp_path / "diagram.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    weird = tmp_path / "data.bin"
    weird.write_bytes(b"\0\1")

    store = Store("sqlite://")
    res = run_intake(store, repo, [design, pdf, img, weird])
    kinds = sorted(k for k, _ in res.sources)
    assert kinds == ["graph", "image", "md", "md", "pdf", "repo"]
    assert res.graph is not None and res.graph.nodes == 4
    assert res.skipped == ["data.bin"]
    rows = {r.kind: r for r in store.list_sources(res.project_id)}
    assert "Payments service" in rows["repo"].text
    assert rows["image"].meta["path"] == str(img.resolve())
    assert rows["pdf"].meta["pages"] == 1
    assert {r.name for r in store.list_sources(res.project_id) if r.kind == "md"} == {
        "design.md",
        "GRAPH_REPORT.md",
    }
