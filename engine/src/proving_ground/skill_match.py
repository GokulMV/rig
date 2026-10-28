"""Which library skills fit a workflow step, and why, without a model.

The rules and every value are in the match-skills skill: words brought to one form, rare words
weighted up (IDF over the library), a skill's name having to cover the step's kind of work
(facets, specific), and a reason with each match.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from proving_ground import skills

M = skills.load("match-skills").values
TOKEN = re.compile(r"[a-z0-9_+#]+")


def _canon_table() -> tuple[dict[str, str], list[tuple[re.Pattern, str]]]:
    words, phrases = {}, []
    for canon, forms in M["same"].items():
        words[canon] = canon
        for f in forms:
            parts = re.split(r"[\s-]+", f)
            if len(parts) == 1:
                words[f] = canon
            else:  # a phrase becomes one token before the text is cut into words
                pat = re.compile(r"\b" + r"[\s-]+".join(map(re.escape, parts)) + r"\b")
                phrases.append((pat, canon.replace("-", "_")))
    # Longest first, so "failing tests" goes before "failing test" could cut it.
    phrases.sort(key=lambda p: -len(p[0].pattern))
    return words, phrases


SAME, PHRASES = _canon_table()
STOP = set(M["stopwords"])


def stem(word: str) -> str:
    """One form for a word: the `same` table, else the word without its suffix."""
    if word in SAME:
        return SAME[word]
    w = word
    for suf in M["suffixes"]:
        if w.endswith(suf) and len(w) - len(suf) >= M["stem_min"]:
            if suf == "s" and w.endswith(("ss", "us", "is")):
                break
            w = w[: -len(suf)] + ("y" if suf in ("ies", "ied") else "")
            break
    if len(w) > M["stem_min"] and w.endswith("e"):
        w = w[:-1]
    if len(w) > M["stem_min"] and w[-1] == w[-2] and w[-1] not in "aeiouylsz":
        w = w[:-1]
    return w


def terms(text: str) -> dict[str, str]:
    """{form: the first word of the text that had it}, stopwords left out."""
    low, said = text.lower(), {}
    for pat, canon in PHRASES:  # "failing test" is one word, tdd, but is shown as written

        def one(m: re.Match, c: str = canon) -> str:
            said.setdefault(c, m.group(0))
            return c

        low = pat.sub(one, low)
    out: dict[str, str] = {}
    for tok in TOKEN.findall(low):
        shown = said.get(tok, tok)
        tok = tok.replace("_", "-")
        if tok in STOP:
            continue
        t = stem(tok)
        if t not in STOP:
            out.setdefault(t, shown)
    return out


def _forms(words: Iterable[str]) -> set[str]:
    return {t for w in words for t in terms(w)}


SPECIFIC = _forms(M["specific"])
GENERIC = _forms(M["generic_name_words"])
FACETS = {stem(k): _forms(v) | {stem(k)} for k, v in M["facets"].items()}
CONTEXT = {d: _forms(v) for d, v in M["context"].items()}
GATE = M["discipline_gate"]
CODE_FACETS = {stem(f) for f in GATE["code_facets"]}
CODE_ONLY = re.compile(
    r"(?<![a-z0-9])("
    + "|".join(re.escape(w).replace(r"\ ", r"[\s-]+") for w in GATE["code_only"])
    + r")(?![a-z0-9])"
)


def code_discipline(discipline: str | None) -> bool:
    """Whether a step's discipline works on code: no discipline (a plain step) counts as code."""
    return not discipline or discipline in GATE["code_disciplines"]


@lru_cache(maxsize=4096)
def code_only(name: str, description: str = "") -> bool:
    """A skill made for code work: a code facet in its name, or a code_only word in its name or
    description (match-skills: discipline_gate)."""
    if set(terms(name)) & CODE_FACETS:
        return True
    return CODE_ONLY.search(f"{name.replace('-', ' ')} {description}".lower()) is not None


RELATED: dict[str, set[str]] = {}
for _group in M["related"]:
    _g = _forms(_group)
    for _t in _g:
        RELATED.setdefault(_t, set()).update(_g - {_t})


@dataclass(frozen=True)
class _Indexed:
    name: frozenset[str]  # the words the name is judged on
    gates: frozenset[str]  # every word of the name (for specific and facets)
    desc: frozenset[str]


@lru_cache(maxsize=8)
def _index(key: tuple) -> tuple[list[_Indexed], dict[str, float]]:
    """Each skill's words, and each word's weight: ln((skills + prior) / (skills using it + 1))."""
    items, df = [], {}
    for name, description in key:
        gates = frozenset(terms(name))
        core = gates - GENERIC
        desc = frozenset(set(terms(description)) | (gates & GENERIC)) - core
        items.append(_Indexed(core, gates, desc))
        for t in core | desc:
            df[t] = df.get(t, 0) + 1
    n = len(key) + M["idf_prior_skills"]
    return items, {t: math.log(n / (c + 1)) for t, c in df.items()}


def rank(
    step_words: Iterable[str] | str,
    library: list[dict],
    body: str = "",
    context=(),
    discipline: str | None = None,
) -> list[tuple[float, dict, str]]:
    """Every library skill the gates allow, scored, best first: (points, skill, why).

    step_words: the step's headline (its name and given words): a skill must match one of these,
    and only these score name points. body: what the step does, which scores like description
    words. context: words its discipline is about, which open facets and score nothing.
    discipline: outside a code discipline, skills made for code are left out (discipline_gate)."""
    head = terms(step_words if isinstance(step_words, str) else " ".join(step_words))
    want = {**terms(body), **head}
    have = set(want) | _forms(context)
    key = tuple((s["name"], s.get("description", "")) for s in library)
    index, idf = _index(key)
    gate = not code_discipline(discipline)
    out = []
    for s, ix in zip(library, index, strict=True):
        if (ix.gates & SPECIFIC) - set(want):
            continue
        if gate and code_only(s["name"], s.get("description", "")):
            continue
        if any(not (FACETS[t] & have) for t in ix.gates if t in FACETS):
            continue
        exact = ix.name & set(want)
        in_head = exact & set(head)
        # A name word close to a headline word (critique for review), unless the headline has it.
        near = {t for t in ix.name - in_head if RELATED.get(t, set()) & set(head)}
        if not (in_head or near or ix.desc & (set(head) - GENERIC)):
            continue  # nothing in the step's headline fits it
        in_desc = (ix.desc & set(want)) | (exact - in_head)  # a name word said in the body
        if not (in_head or near) and len(in_desc) < M["description_words_min"]:
            continue  # one word of a description is a coincidence
        cover = len(exact | near) / len(ix.name) if ix.name else 0.0
        name_pts = (
            M["name_word"]
            * cover
            * (sum(idf[t] for t in in_head) + M["related_word"] * sum(idf[t] for t in near))
        )
        points = name_pts + M["description_word"] * sum(idf[t] for t in in_desc)
        said = [want[t] for t in sorted(exact | in_desc, key=lambda t: (-idf[t], t))]
        said += [f"{head[min(RELATED[t] & set(head))]}≈{t}" for t in sorted(near - exact)]
        why = "matched: " + ", ".join(said)
        if exact & ix.name or near:
            why += f"; name {len(exact | near)}/{len(ix.name)}"
        out.append((points, s, why))
    out.sort(key=lambda x: (-x[0], x[1]["name"]))
    return out


def allowed(
    step_words: Iterable[str] | str,
    library: list[dict],
    body: str = "",
    context=(),
    facets: bool = True,
    discipline: str | None = None,
) -> list[bool]:
    """For each library skill, whether its name lets it fit the step at all: a skill named for
    one language or tool (`specific`) needs the step to say it, (facets) one named for a kind of
    work needs the step to be about it, and outside a code discipline one made for code is out
    (discipline_gate). rank's other rules score; these rule out."""
    head = terms(step_words if isinstance(step_words, str) else " ".join(step_words))
    want = set({**terms(body), **head})
    have = want | _forms(context)
    key = tuple((s["name"], s.get("description", "")) for s in library)
    index, _ = _index(key)
    gate = not code_discipline(discipline)
    return [
        not ((ix.gates & SPECIFIC) - want)
        and not (facets and any(not (FACETS[t] & have) for t in ix.gates if t in FACETS))
        and not (gate and code_only(s["name"], s.get("description", "")))
        for s, ix in zip(library, index, strict=True)
    ]


def match(
    step_words: Iterable[str] | str,
    library: list[dict],
    limit: int,
    body: str = "",
    context=(),
    discipline: str | None = None,
) -> list[dict]:
    """The library skills that fit a step (at least skill_match_min points), best first, each
    with `why`: the step's words that matched and how much of the skill's name they cover."""
    keep = ("path", "name", "source", "repo", "url")
    return [
        {**{k: s[k] for k in keep if k in s}, "why": why}
        for points, s, why in rank(step_words, library, body, context, discipline)
        if points >= M["skill_match_min"]
    ][:limit]


def step_text(step: dict) -> str:
    """A step as the models read it: its name, what it does, and its words."""
    words = " ".join(step.get("words", []))
    return f"{step.get('name', '')}: {step.get('does', '')} {words}".strip()


def skill_text(skill: dict) -> str:
    return f"{skill['name'].replace('-', ' ')}: {skill.get('description', '')}"


def pick(step: dict, library: list[dict], limit: int, models) -> list[dict]:
    """The library skills that fit a step, by the models (skill_models): the embedding's
    `candidates` nearest skills and the word rules' best as many, less those whose names rule
    them out (`allowed`); each read with the step by the reranker, and attached only if its
    chance of fitting is at least `threshold`. Best first, each with `why`."""
    import numpy as np

    mv = M["models"]
    head = " ".join([step.get("name", ""), *step.get("words", [])])
    body, context = step.get("does", ""), CONTEXT.get(step.get("discipline", ""), ())
    fits = allowed(head, library, body, context, discipline=step.get("discipline"))
    q, docs = step_text(step), [skill_text(s) for s in library]
    qv = np.array(models.embed([q], query=True)[0])
    sims = np.array(models.embed(docs)) @ qv if docs else np.zeros(0)
    near = [int(j) for j in np.argsort(-sims, kind="stable")[: mv["candidates"]]]
    at = {id(s): j for j, s in enumerate(library)}
    ranked = rank(head, library, body, context, step.get("discipline"))[: mv["candidates"]]
    said = {at[id(s)]: why for _, s, why in ranked}
    cands = [j for j in dict.fromkeys(near + list(said)) if fits[j]]
    scores = models.score(q, [docs[j] for j in cands]) if cands else []
    models.save_soon()
    best = sorted(
        ((p, j) for p, j in zip(scores, cands, strict=True) if p >= mv["threshold"]),
        key=lambda x: (-x[0], library[x[1]]["name"]),
    )[:limit]
    keep = ("path", "name", "source", "repo", "url")
    name = mv["rerank"]["name"]
    out = []
    for p, j in best:
        s = library[j]
        reason = (
            "the step says " + said[j].removeprefix("matched: ").split("; name")[0]
            if j in said
            else "its description fits what the step does"
        )
        out.append(
            {**{k: s[k] for k in keep if k in s}, "why": f"picked by {name} ({p:.2f}): {reason}"}
        )
    return out
