"""Grading for the rag-qa hard checks: the standard rag-qa grading (normalised answer match, and
every cited source must hold the evidence for the answer), plus:

- "value"/"units": a numeric answer also matches when, with the listed unit words taken out, it
  is that number ("$80.00", "80 per month" and "80" all match 80);
- "optional": phrases that make a document fair to cite without being needed;
- one line `RIG_ITEMS <right>/<total>` on stdout in every case, mistakes on stderr, exit 0 only
  when every question is right.
"""

import json
import re
import sys
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


def answer_ok(answer, want: dict) -> bool:
    n = norm(answer)
    if n in {norm(a) for a in want.get("answers", [])}:
        return True
    if "value" not in want:
        return False
    padded = f" {n} "
    for unit in sorted((norm(u) for u in want.get("units", [])), key=len, reverse=True):
        padded = padded.replace(f" {unit} ", " ")
    try:
        return float(padded.strip()) == float(want["value"])
    except ValueError:
        return False


def grade(qid: str, got, want: dict) -> str | None:
    """None when the question is right, else what is wrong with it."""
    if not isinstance(got, dict) or "answer" not in got:
        return f"{qid}: missing or not {{answer, sources}}"
    if not answer_ok(got["answer"], want):
        return f"{qid}: wrong answer {got['answer']!r}"
    sources = got.get("sources") or []
    evidence = [norm(e) for e in want["evidence"]]
    if not evidence:
        return f"{qid}: nothing supports this answer, so cite no sources" if sources else None
    if not isinstance(sources, list) or not sources:
        return f"{qid}: no sources cited"
    texts = [source_text(s) for s in sources]
    if None in texts:
        return f"{qid}: a cited source is not a corpus document: {sources}"
    fair = evidence + [norm(e) for e in want.get("optional", [])]
    unsupported = [s for s, t in zip(sources, texts, strict=True) if not any(e in t for e in fair)]
    if unsupported:
        return f"{qid}: cited sources without the evidence: {unsupported}"
    if not all(any(e in t for t in texts) for e in evidence):
        return f"{qid}: the cited sources do not cover all the evidence"
    return None


def check(spec: dict, out: str) -> None:
    total = len(spec)
    f = Path("/app") / out
    try:
        data = json.loads(f.read_text())
        if not isinstance(data, dict):
            raise ValueError(f"{out} must be an object keyed by question id")
    except (OSError, ValueError) as e:
        print(f"RIG_ITEMS 0/{total}")
        print(f"{out}: {e}", file=sys.stderr)
        sys.exit(1)
    bad = [m for qid, want in spec.items() if (m := grade(qid, data.get(qid), want))]
    print(f"RIG_ITEMS {total - len(bad)}/{total}")
    for m in bad:
        print(m, file=sys.stderr)
    sys.exit(1 if bad else 0)
