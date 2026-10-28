"""RAG: the rag-qa bench grades strictly, and the RAG architectures are runnable Lab workflows."""

import json
import subprocess
import sys
from pathlib import Path

from bench_solutions.solutions import RAG_ANSWERS
from test_bench import _lab_client, _wait
from test_lab import LIB

from proving_ground.bench import bench, benches, materialize, run_check_locally
from proving_ground.lab import compile_workflow, levels, rag


def _grade(tmp_path: Path, sid: str, answers: dict) -> subprocess.CompletedProcess:
    project = materialize(bench("rag-qa"), tmp_path / "project")
    work = tmp_path / "work"
    run_check_locally(project, sid, work)
    (work / "app" / "out" / "answers.json").write_text(json.dumps(answers))
    return subprocess.run(
        [sys.executable, str(work / "tests" / "checks" / sid / "check.py")],
        cwd=work / "app",
        capture_output=True,
        text=True,
    )


def test_bench_shape():
    b = bench("rag-qa")
    assert {"research", "data", "support"} == set(b.disciplines)
    assert len(list((b.path / "project" / "corpus").rglob("*.md"))) >= 38
    sizes = {s["id"]: len(RAG_ANSWERS[s["id"]]) for s in b.scenarios}
    assert sizes == {
        "lookup": 6,
        "multi-hop": 4,
        "conflicting": 3,
        "table": 3,
        "unanswerable": 3,
        "held-out-batch": 4,
    }
    assert [s["id"] for s in b.scenarios if s.get("held_out")] == ["held-out-batch"]
    # Every doc says when it was updated; every cited source in the solutions exists.
    for p in (b.path / "project" / "corpus").rglob("*.md"):
        assert "\nUpdated: 20" in p.read_text(), p
    for answers in RAG_ANSWERS.values():
        for a in answers.values():
            assert all((b.path / "project" / s).is_file() for s in a["sources"])


def test_the_default_fit_for_research_workflows_includes_rag_qa():
    assert "rag-qa" in [b.id for b in benches() if "research" in b.disciplines]


def test_grading_normalises_but_does_not_forgive(tmp_path: Path):
    good = RAG_ANSWERS["lookup"]
    ok = {**good, "L1": {"answer": "Fourteen days.", "sources": good["L1"]["sources"]}}
    ok["L4"] = {"answer": "25mb", "sources": good["L4"]["sources"]}
    assert _grade(tmp_path / "a", "lookup", ok).returncode == 0
    wrong = {**good, "L2": {"answer": "50", "sources": good["L2"]["sources"]}}
    assert "wrong answer" in _grade(tmp_path / "b", "lookup", wrong).stderr
    # Right answer, source that doesn't hold the evidence.
    miscited = {**good, "L2": {"answer": "10", "sources": ["corpus/product/api.md"]}}
    assert "without the evidence" in _grade(tmp_path / "c", "lookup", miscited).stderr
    nosrc = {**good, "L2": {"answer": "10", "sources": []}}
    assert "no sources" in _grade(tmp_path / "d", "lookup", nosrc).stderr
    fake = {**good, "L2": {"answer": "10", "sources": ["corpus/nope.md"]}}
    assert "not a corpus document" in _grade(tmp_path / "e", "lookup", fake).stderr


def test_outdated_documents_multi_hop_and_unanswerable_are_enforced(tmp_path: Path):
    conf = RAG_ANSWERS["conflicting"]
    stale = {
        **conf,
        "C1": {"answer": "14 days", "sources": ["corpus/archive/refund-policy-2023.md"]},
    }
    assert "wrong answer" in _grade(tmp_path / "a", "conflicting", stale).stderr
    # Newest answer, but citing the outdated copy.
    cites_old = {
        **conf,
        "C1": {"answer": "30 days", "sources": ["corpus/archive/refund-policy-2023.md"]},
    }
    assert "without the evidence" in _grade(tmp_path / "b", "conflicting", cites_old).stderr
    mh = RAG_ANSWERS["multi-hop"]
    one_hop = {**mh, "M1": {"answer": "49", "sources": ["corpus/policies/pricing.md"]}}
    assert "do not cover" in _grade(tmp_path / "c", "multi-hop", one_hop).stderr
    stale_price = {**mh, "M1": {"answer": "39", "sources": ["corpus/archive/pricing-2024.md"]}}
    assert "wrong answer" in _grade(tmp_path / "d", "multi-hop", stale_price).stderr
    un = RAG_ANSWERS["unanswerable"]
    guess = {**un, "U1": {"answer": "$4 million", "sources": []}}
    assert "wrong answer" in _grade(tmp_path / "e", "unanswerable", guess).stderr
    padded = {**un, "U1": {"answer": "Not in the docs.", "sources": ["corpus/company/about.md"]}}
    assert "cite no sources" in _grade(tmp_path / "f", "unanswerable", padded).stderr
    assert (
        _grade(
            tmp_path / "g", "unanswerable", {**un, "U1": {"answer": "Not in the docs."}}
        ).returncode
        == 0
    )


def test_rag_workflows_load_normalise_and_compile(tmp_path: Path):
    wfs = rag(LIB)
    assert [w.name.split(" (")[0] for w in wfs] == [
        "Naive RAG",
        "HyDE",
        "Corrective RAG",
        "Hybrid RAG",
        "Adaptive RAG",
        "Agentic RAG",
        "GraphRAG",
        "Self-RAG",
        "Reranked RAG",
        "RAG-Fusion",
    ]
    for w in wfs:
        assert w.origin == "rag" and w.discipline == "research"
        assert w.why[0].startswith("Modelled on: ")
        assert {s.kind for s in w.steps} <= {"think", "do", "check", "judge"}
        levels(w)  # no cycle
        text = compile_workflow(w, tmp_path / w.id).joinpath("SKILL.md").read_text()
        assert all(s.name in text for s in w.steps)
    by = {w.name.split(" (")[0]: w for w in wfs}
    assert by["Corrective RAG"].loops and any(s.kind == "judge" for s in by["Corrective RAG"].steps)
    assert by["Agentic RAG"].loops
    assert max(len(s) for s in levels(by["Agentic RAG"])) == 3
    assert {"keyword", "semantic"} in [set(s) for s in levels(by["Hybrid RAG"])]
    assert max(len(s) for s in levels(by["Naive RAG"])) == 1  # a plain chain


def test_a_rag_workflow_runs_on_rag_qa_with_and_without(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    flows = c.get("/api/lab").json()["rag"]
    assert len(flows) == 10
    wf = next(w for w in flows if w["name"] == "Corrective RAG (grade, rewrite, search again)")
    r = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "rag-qa", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    row = _wait(c, 1)[0]
    assert row["bench"] == "rag-qa" and row["verdict"] == "helps" and row["diff"] == 1.0
    assert row["held_out"]["tasks"] == 1
    with_arm = [q for q in calls if q.agent != "nop" and q.skills]
    assert with_arm
    text = (Path(with_arm[0].skills[0]) / "SKILL.md").read_text()
    assert "Grade relevance" in text and "Write the search query" in text
    assert any("held-out-batch" in str(q.task_dir) for q in calls)
