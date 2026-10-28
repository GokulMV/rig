"""The architecture catalog: RAG and agent designs you can browse, rank for a use case, and draw.

The entries and the ranking rules live in the architecture-catalog skill. Nothing here calls a
model, and the same input always gives the same ranking.
"""

from __future__ import annotations

import re
from typing import Any

from proving_ground import skills
from proving_ground.architecture import Architecture, Component, Connection, layout

SKILL = "architecture-catalog"


def entries() -> list[dict[str, Any]]:
    """Every entry, in the order the skill lists them."""
    return [dict(e) for e in skills.value(SKILL, "entries")]


def entry(entry_id: str) -> dict[str, Any] | None:
    return next((e for e in entries() if e["id"] == entry_id), None)


def grouped() -> dict[str, list[dict[str, Any]]]:
    """Entries by family, families in the skill's order."""
    out: dict[str, list[dict[str, Any]]] = {f: [] for f in skills.value(SKILL, "families")}
    for e in entries():
        out.setdefault(e["family"], []).append(e)
    return out


def _has(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}", text) is not None


def repo_text(repo_signals: dict | None) -> tuple[str, list[str]]:
    """The words a repo adds to the use case, and the facts they came from.

    `repo_signals` is the repo's intake meta: languages, stack, files, docs_words, key_files.
    """
    meta = repo_signals or {}
    rules = skills.value(SKILL, "repo_rules")
    words: list[str] = []
    facts: list[str] = []
    if rules["stack_as_signals"]:
        words += [str(s) for s in meta.get("stack", [])]
        words += [str(k) for k in meta.get("languages", {})]
        words += [str(k).rsplit("/", 1)[-1] for k in meta.get("key_files", [])]
    if (meta.get("docs_words") or 0) >= rules["docs_words_min"]:
        words += rules["docs_signals"]
        facts.append(f"{meta['docs_words']:,} words of docs")
    if (meta.get("files") or 0) >= rules["files_min"]:
        words += rules["files_signals"]
        facts.append(f"{meta['files']:,} files")
    return " ".join(words).lower(), facts


_FORMS = "(?:s|es|ed|ing)?"


def _phrase_rx(phrase: str) -> re.Pattern:
    """A phrase as whole words, in any of its simple forms (document, documents). The first word
    takes them too, where a phrase starts with its verb: "hand off" finds "hands off" and
    "handed off"; inflected, it needs a space after it, so "hands-off" (the adjective) doesn't."""
    words = [re.escape(w) for w in re.split(r"[\s-]+", phrase.lower()) if w]
    body = r"[\s-]+".join(words)
    if len(words) > 1:
        rest = r"[\s-]+".join(words[1:])
        body = rf"{words[0]}(?:(?:s|es|ed|ing)\s+|[\s-]+){rest}"
    return re.compile(rf"(?<![a-z0-9]){body}{_FORMS}(?![a-z0-9])")


_WORD = re.compile(r"[^\s.,;:!?()\"']+")
# A quote stops at these: the end of a sentence or clause (a comma before a space included).
_STOP = re.compile(r"[.;:!?\n]|,(?=\s)")
_JOINS = {"and", "or", "but", "so", "then", "before", "after", "while", "because", "when"}
_LOOSE = {"in", "of", "the", "a", "an", "to", "our", "for", "with", "on", "at", "by"}


def _window(text: str, start: int, end: int) -> tuple[int, int]:
    """The few words a match sits in, to quote back (architecture-catalog: reasons): a short
    clause whole ("anything over $200 needs a manager"); in a long one the matched words and up
    to three after them, never across "and", "before" and the like, else the two before."""
    stops = [m.start() for m in _STOP.finditer(text)]
    a = max((k + 1 for k in stops if k < start), default=0)
    b = min((k for k in stops if k >= end), default=len(text))
    words = [(m.start() + a, m.end() + a, m.group().lower()) for m in _WORD.finditer(text[a:b])]
    while words and words[0][2] in _JOINS and words[0][1] <= start:
        words.pop(0)  # "and refunds over $200 ..." is quoted from "refunds"
    hit = [n for n, (x, y, _) in enumerate(words) if y > start and x < end]
    if not hit:
        return start, end
    if len(words) <= 6:
        return words[0][0], words[-1][1]
    lo, hi = hit[0], hit[-1]
    while hi + 1 < len(words) and hi - hit[-1] < 3 and words[hi + 1][2] not in _JOINS:
        hi += 1
    while hi > hit[-1] and words[hi][2] in _LOOSE:
        hi -= 1
    if hi == hit[-1]:
        while lo > 0 and hit[0] - lo < 2 and words[lo - 1][2] not in _JOINS:
            lo -= 1
    return words[lo][0], words[hi][1]


def intents(use_case: str) -> list[dict]:
    """The intents a use case says (architecture-catalog: intents): [{id, says, quote, span,
    fits}]. `quote` is the few words that said it ("over $200 needs a manager"), not the clause."""
    text = use_case or ""
    low = text.lower()
    out = []
    for iid, it in skills.value(SKILL, "intents").items():
        hit = None
        for ph in it.get("phrases", []):
            m = _phrase_rx(str(ph)).search(low)
            if m and (hit is None or m.start() < hit.start()):
                hit = m
        for pat in it.get("patterns", []):
            m = re.search(pat, low)
            if m and (hit is None or m.start() < hit.start()):
                hit = m
        if hit is not None:
            a, b = _window(text, hit.start(), hit.end())
            out.append(
                {
                    "id": iid,
                    "says": it["says"],
                    "quote": " ".join(text[a:b].split()),
                    "span": [a, b],
                    "fits": it["fits"],
                }
            )
    return out


def _quoted(text: str, hits: list[dict]) -> list[tuple[str, list[str]]]:
    """What one design's intents quote, overlapping words joined into one quote, in the use
    case's order: [(quote, [what each intent asks for])]."""
    groups: list[list] = []  # [start, end, says]
    for it in sorted(hits, key=lambda h: h["span"][0]):
        a, b = it["span"]
        if groups and a <= groups[-1][1]:
            groups[-1][1] = max(groups[-1][1], b)
            groups[-1][2].append(it["says"])
        else:
            groups.append([a, b, [it["says"]]])
    return [(" ".join(text[a:b].split()), says) for a, b, says in groups]


def fit_of(points: float) -> str:
    lv = skills.value(SKILL, "fit_levels")
    return "strong" if points >= lv["strong"] else "good" if points >= lv["good"] else "possible"


def recommend(
    use_case_text: str, repo_signals: dict | None = None, models: Any = None
) -> list[dict[str, Any]]:
    """Rank entries for a use case: [{id, score, fit, fit_label, reasons, weak}], best first,
    deterministic for the same input (and the same embedding model, when one is given).

    Intents the use case says decide most (the reason quotes it); entry signals it says add a
    little; signals from the repo's files add less and never list an entry alone."""
    return ranked(scored(use_case_text, repo_signals, models))


def ranked(all_scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The entries `scored` lists as recommendations, best first."""
    v = skills.load(SKILL).values
    labels = v["fit_labels"]
    out = []
    for s in all_scored:
        if not s["own"] or s["score"] < v["min_points"]:
            continue  # repo files or a preference alone never make it a recommendation
        fit = fit_of(s["score"])
        out.append(
            {
                "id": s["id"],
                "score": s["score"],
                "fit": fit,
                "fit_label": labels[fit],
                "reasons": s["reasons"],
                "weak": fit == "possible",
            }
        )
    out.sort(key=lambda r: (-r["score"], r["id"]))
    return out[: v["max_results"]]


def scored(
    use_case_text: str, repo_signals: dict | None = None, models: Any = None
) -> list[dict[str, Any]]:
    """Every entry's points for a use case, listed or not: [{id, score, own, reasons, matched,
    said}]. `own` counts what the use case itself says for it; `matched` is those words (signals
    and intent quotes), `said` the intent ids."""
    v = skills.load(SKILL).values
    levels = v["preference_levels"]
    text = (use_case_text or "").lower()
    extra, facts = repo_text(repo_signals)
    said = intents(use_case_text or "")
    wanted: list[tuple[str, str, str]] = []  # (trade-off, side, the word that asked for it)
    for axis, sides in v["preferences"].items():
        for side, terms in sides.items():
            hit = next((t for t in terms if _has(text, t)), None)
            if hit:
                wanted.append((axis, side, hit))
    sims: dict[str, float] = {}
    if models is not None and text.strip():
        try:
            import numpy as np

            es = entries()
            docs = [f"{e['name']}: {e['summary']} Use when: {e['when_to_use']}" for e in es]
            q = np.array(models.embed([use_case_text], query=True)[0])
            m = np.array(models.embed(docs))
            sims = {e["id"]: float(x) for e, x in zip(es, m @ q, strict=True)}
        except Exception:  # noqa: BLE001 - the rules decide without it
            sims = {}
    out = []
    for e in entries():
        score = 0.0
        reasons: list[str] = []
        own = 0  # what the use case itself says for this entry
        mine = []
        for it in said:
            pts = it["fits"].get(e["id"], 0)
            if pts:
                own += 1
                score += pts
                mine.append(it)
        # One reason per phrase quoted (only the words that matched, joined where they overlap):
        # what it asks for, in the order the use case says them.
        reasons += [
            f"Because you said '{q}' ({'; '.join(w)})." for q, w in _quoted(use_case_text, mine)
        ]
        found = 0
        from_repo: list[str] = []
        for sig in e["signals"]:
            if found >= v["signal_cap"]:
                break
            if _has(text, sig.lower()):
                found += 1
                own += 1
                score += v["use_case_signal"]
            elif extra and _has(extra, sig.lower()):
                found += 1
                score += v["repo_signal"]
                from_repo.append(sig)
        if from_repo:
            more = f" ({', '.join(facts)})" if facts else ""
            reasons.append(f"Your repo also points at {', '.join(from_repo[:3])}{more}.")
        for axis, side, word in wanted:
            level = levels[e["tradeoffs"][axis]]
            fit = 2 - level if side == "low" else level  # "low" wanted at level 0, "high" at 2
            delta = (fit - 1) * v["preference_weight"]
            if delta:
                score += delta
                reasons.append(
                    f"You asked for {side} {axis} ('{word}'); this is {e['tradeoffs'][axis]}."
                    if delta > 0
                    else f"Against '{word}': {axis} is {e['tradeoffs'][axis]} here, you wanted {side}."
                )
        if e["id"] in sims:
            score += round(max(0.0, sims[e["id"]]) * v["embedding_weight"], 2)
        signals_said = [sg for sg in e["signals"] if _has(text, sg.lower())][: v["signal_cap"]]
        if own and not any(r.startswith("Because you said") for r in reasons):
            reasons.insert(0, f"Your use case mentions {', '.join(signals_said[:3])}.")
        matched = [q for q, _ in _quoted(use_case_text, mine)] + signals_said
        out.append(
            {
                "id": e["id"],
                "score": round(score, 2),
                "own": own,
                "reasons": reasons,
                "matched": list(dict.fromkeys(m.lower() for m in matched)),
                "said": [it["id"] for it in mine],
            }
        )
    return out


def _listed(items: list[str], last: str = "and") -> str:
    """a; a and b; a, b and c."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {last} {items[-1]}"


def empty_state(use_case_text: str, all_scored: list[dict[str, Any]]) -> dict[str, Any]:
    """What to say when `ranked` lists nothing (architecture-catalog: empty_state): the designs
    the use case's own words pointed at, below `min_points`, and what to add to rank them.
    {title, matched, heading, near: [{id, name, matched}], asks_lead, asks, words, browse}. A close
    design is never a pick.
    """
    v = skills.load(SKILL).values
    rules = v["empty_state"]
    near = sorted((s for s in all_scored if s["own"]), key=lambda s: (-s["score"], s["id"]))
    near = near[: rules["max_near"]]
    if not near:
        return {
            "title": rules["title"],
            "matched": rules["nothing"],
            "near": [],
            "heading": None,
            "asks_lead": None,
            "asks": [],
            "words": None,
            "browse": rules["browse"],
        }
    text = (use_case_text or "").lower()
    words = sorted(
        dict.fromkeys(w for s in near for w in s["matched"]), key=lambda w: text.find(w)
    )  # in the order the use case says them
    said = {i for s in near for i in s["said"]}
    unsaid = [it for iid, it in v["intents"].items() if iid not in said and it.get("ask")]
    asks: list[str] = []
    counts: dict[str, int] = {}
    order: list[str] = []
    for s in near:
        e = entry(s["id"]) or {}
        # Its strongest intent not said yet: the one sentence most likely to rank it.
        top = max(unsaid, key=lambda it: it["fits"].get(s["id"], 0), default=None)
        if top and top["fits"].get(s["id"]) and top["ask"] not in asks:
            asks.append(top["ask"])
        for sg in e.get("signals", []):
            if not _has(text, sg.lower()):
                counts[sg] = counts.get(sg, 0) + 1
                if sg not in order:
                    order.append(sg)
    more = sorted(order, key=lambda w: (-counts[w], order.index(w)))[: rules["max_words"]]
    return {
        "title": rules["title"],
        "matched": rules["matched"].format(words=_listed([f"'{w}'" for w in words])),
        "near": [
            {
                "id": s["id"],
                "name": (entry(s["id"]) or {}).get("name", s["id"]),
                "matched": s["matched"],
            }
            for s in near
        ],
        "heading": rules["heading"],
        "asks_lead": rules["asks_lead"] if asks else None,
        "asks": asks,
        "words": rules["words"].format(words=_listed(more, "or")) if more else None,
        "browse": rules["browse_near"],  # the asks above already say what more to say
    }


def discipline_for(use_case: str, family: str) -> tuple[str, list[str]]:
    """The Lab discipline a use case points at, and the words that said so (architecture-catalog:
    lab_handoff). The discipline whose label or step words appear most; ties go in the Lab's
    order; too few hits fall back to the family's default."""
    from proving_ground import lab

    rules = skills.value(SKILL, "lab_handoff")
    text = (use_case or "").lower()
    best: tuple[int, str, list[str]] | None = None
    for did, d in lab.S["disciplines"].items():
        words = {d["label"].lower(), did}
        for st in d["steps"].values():
            words |= {str(w).lower() for w in st.get("words", [])}
        hits = sorted(w for w in words if w and _has(text, w))
        if len(hits) >= rules["min_hits"] and (best is None or len(hits) > best[0]):
            best = (len(hits), did, hits)
    if best is None:
        return rules["default_discipline"][family], []
    return best[1], best[2]


def lab_workflow(entry_id: str, use_case: str, library: list[dict]) -> dict[str, Any]:
    """The Lab workflow that runs a design (its `lab_workflow`), set up for the use case:
    {workflow, discipline, matched, note}. Raises KeyError for an unknown entry or link."""
    from proving_ground import lab

    e = entry(entry_id)
    if e is None:
        raise KeyError(f"No architecture called {entry_id!r} in the catalog.")
    kind, _, ref = e["lab_workflow"].partition(":")
    if kind == "rag":
        ids = [w["id"] for w in lab.R["workflows"]]
        if ref not in ids:
            raise KeyError(f"{entry_id} links to rag:{ref}, which rag-workflows doesn't have.")
        wf = lab.rag(library)[ids.index(ref)]
        wf.facts = lab.facts_from(use_case)
        lab.with_brief(wf, use_case)
        did, matched = wf.discipline, []
    elif kind == "pattern":
        if ref not in lab.W["patterns"]:
            raise KeyError(
                f"{entry_id} links to pattern:{ref}, which workflow-patterns doesn't have."
            )
        did, matched = discipline_for(use_case, e["family"])
        wf = lab.from_pattern(
            ref, lab.W["baseline_model"], library, discipline=did, use_case=use_case
        )
    else:
        raise KeyError(f"{entry_id} has no Lab workflow ({e['lab_workflow']!r}).")
    return {"workflow": wf, "discipline": did, "matched": matched, "note": e.get("lab_note")}


def as_architecture(e: dict[str, Any]) -> Architecture:
    """An entry as the engine's Architecture, laid out left to right, so the canvas can draw it."""
    arch = Architecture(
        title=e["name"],
        source="archify",
        components=[
            # The role is a sentence: it reads as the block's text, not its (one-word) header.
            Component(id=c["id"], type=c["type"], label=c["label"], sublabel=c.get("role"))
            for c in e["components"]
        ],
        connections=[
            Connection(**{"from": a, "to": b, "label": lab}) for a, b, lab in e["connections"]
        ],
    )
    return layout(arch)


EXPLAIN_TOOL = {
    "name": "explain_picks",
    "description": "One short paragraph per architecture, about this use case.",
    "input_schema": {
        "type": "object",
        "properties": {
            "explanations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                    "required": ["id", "text"],
                },
            }
        },
        "required": ["explanations"],
    },
}


def explain(model: Any, use_case: str, ranked: list[dict[str, Any]]) -> dict[str, str]:
    """One helper-model call: a short paragraph for each of the top picks, by id.

    Only called when the person asks. The ranking never depends on it.
    """
    from proving_ground.generate.prompt import Prompt

    v = skills.load(SKILL).values
    top = ranked[: v["explain_top"]]
    blocks = []
    for r in top:
        e = entry(r["id"])
        if e:
            blocks.append(
                f"<architecture id={e['id']}>\n{e['name']}: {e['summary']}\n"
                f"Use when: {e['when_to_use']}\nAvoid when: {e['when_not_to_use']}\n"
                f"Trade-offs: {e['tradeoffs']}\nWhy it ranked: {' '.join(r['reasons'])}\n"
                "</architecture>"
            )
    text = f"<use_case>\n{use_case}\n</use_case>\n" + "\n".join(blocks)
    call = model.call(
        Prompt(skills.section(SKILL, "Explain prompt"), [{"type": "text", "text": text}]),
        EXPLAIN_TOOL,
        v["explain_model"],
        v["explain_max_tokens"],
    )
    data = call.input if isinstance(call.input, dict) else {}
    ids = {r["id"] for r in top}
    return {
        x["id"]: x["text"].strip()
        for x in data.get("explanations", [])
        if isinstance(x, dict) and x.get("id") in ids and str(x.get("text", "")).strip()
    }
