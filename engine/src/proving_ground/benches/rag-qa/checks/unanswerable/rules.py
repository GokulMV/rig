"""Shared grading for the rag-qa checks: normalised answer match, and every cited source must
hold the evidence for the answer."""

import json
import re
from pathlib import Path

NOT_IN_DOCS = "not in the docs"
NUMBERS = {
    w: str(i)
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
}
NUMBERS.update({"thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "ninety": "90"})


def norm(text: str) -> str:
    """Lowercase; thousands commas out; punctuation out (a point between digits stays);
    number words as digits; spaces collapsed."""
    t = str(text).lower()
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)
    t = re.sub(r"[^a-z0-9.\s]", " ", t)
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)
    return " ".join(NUMBERS.get(w, w) for w in t.split())


def source_text(rel: str) -> str | None:
    rel = re.sub(r"^(/app/|\./)", "", str(rel).strip())
    p = Path("/app") / rel
    if not rel.startswith("corpus/") or ".." in rel or not p.is_file():
        return None
    return norm(p.read_text())


def items(right: int, total: int) -> None:
    """Partial credit for Rig: how many questions came out right (pass/fail is still the exit)."""
    print(f"RIG_ITEMS {right}/{total}", flush=True)


def check(spec: dict) -> None:
    # A question counts as right when its answer matches and its sources hold the evidence; an
    # answers file that is missing, not JSON or not an object counts none right.
    f = Path("/app/out/answers.json")
    try:
        data = json.loads(f.read_text()) if f.is_file() else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        items(0, len(spec))
    assert f.is_file(), "no out/answers.json"
    data = json.loads(f.read_text())
    assert isinstance(data, dict), "answers.json must be an object keyed by question id"
    bad = []
    for qid, want in spec.items():
        got = data.get(qid)
        if not isinstance(got, dict) or "answer" not in got:
            bad.append(f"{qid}: missing or not {{answer, sources}}")
            continue
        if norm(got["answer"]) not in {norm(a) for a in want["answers"]}:
            bad.append(f"{qid}: wrong answer {got['answer']!r}")
            continue
        sources = got.get("sources") or []
        evidence = [norm(e) for e in want["evidence"]]
        if not evidence:
            if sources:
                bad.append(f"{qid}: nothing supports this answer, so cite no sources")
            continue
        if not isinstance(sources, list) or not sources:
            bad.append(f"{qid}: no sources cited")
            continue
        texts = [source_text(s) for s in sources]
        if None in texts:
            bad.append(f"{qid}: a cited source is not a corpus document: {sources}")
            continue
        unsupported = [
            s for s, t in zip(sources, texts, strict=True) if not any(e in t for e in evidence)
        ]
        if unsupported:
            bad.append(f"{qid}: cited sources without the evidence: {unsupported}")
        elif not all(any(e in t for t in texts) for e in evidence):
            bad.append(f"{qid}: the cited sources do not cover all the evidence")
    # Each question adds at most one line to `bad`.
    items(len(spec) - len(bad), len(spec))
    assert not bad, "; ".join(bad)
