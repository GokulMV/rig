"""What in the library would help this repo, and what to create or rewrite when nothing does.

Rules and values live in the recommend-for-repo skill. Picks always name the need they serve.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from proving_ground import skills
from proving_ground.architecture.verify import ALIASES
from proving_ground.generate.client import GenerationError, ModelClient
from proving_ground.generate.prompt import Prompt

R = skills.load("recommend-for-repo").values
IGNORE = set(R["ignore_terms"])
STOP = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "when",
    "what",
    "each",
    "its",
    "are",
    "not",
    "one",
}

PICK_TOOL = {
    "name": "emit_recommendations",
    "description": "Return picks, skills to create, and skills to improve.",
    "input_schema": {
        "type": "object",
        "required": ["picks", "create", "improve"],
        "properties": {
            "picks": {"type": "array", "items": {"type": "object", "required": ["id", "need", "why"], "properties": {
                "id": {"type": "string"}, "need": {"type": "string"}, "why": {"type": "string"}}}},
            "create": {"type": "array", "items": {"type": "object", "required": ["name", "need", "what", "why"], "properties": {
                "name": {"type": "string"}, "need": {"type": "string"}, "what": {"type": "string"}, "why": {"type": "string"}}}},
            "improve": {"type": "array", "items": {"type": "object", "required": ["path", "need", "how", "why"], "properties": {
                "path": {"type": "string"}, "need": {"type": "string"}, "how": {"type": "string"}, "why": {"type": "string"}}}},
        },
    },
}  # fmt: skip
DRAFT_TOOL = {
    "name": "emit_skill",
    "description": "Return the SKILL.md text.",
    "input_schema": {
        "type": "object",
        "required": ["skill_md"],
        "properties": {"skill_md": {"type": "string"}},
    },
}


@dataclass
class Need:
    text: str
    source: str  # architecture | step | scenario | suggestion | result | use case
    terms: set[str] = field(default_factory=set)
    step: str | None = None


def terms(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z0-9+#-]{2,}", text.lower())
    return {w for w in words if w not in IGNORE and w not in STOP}


def needs_for(
    arch,
    steps: list[tuple[str, str, str]],  # (name, type, why)
    scenarios: list[str],
    suggestions: list[str],
    weak_skills: list[str],
    use_case: str | None,
) -> list[Need]:
    out: list[Need] = []
    verbs = {
        "external": "calls",
        "cloud": "runs on",
        "database": "stores data in",
        "messagebus": "queues work in",
    }
    for c in arch.components:
        if c.type in verbs and c.role != "Person":
            text = f"{verbs[c.type]} {c.label}" + (f" ({c.sublabel})" if c.sublabel else "")
            aliases = " ".join(
                ALIASES.get(c.id, set()) | ALIASES.get(c.label.lower().replace(" ", "-"), set())
            )
            out.append(Need(text, "architecture", terms(f"{c.label} {c.sublabel or ''} {aliases}")))
        elif (
            c.type == "backend"
            and c.sublabel
            and re.match(r"(FastAPI|Flask|Django|Spring|Express|NestJS)", c.sublabel)
        ):
            out.append(
                Need(
                    f"serves {c.label} with {c.sublabel.split(' ·')[0]}",
                    "architecture",
                    terms(c.sublabel),
                )
            )
    for name, typ, why in steps:
        out.append(
            Need(
                f"step '{name}' ({typ}){': ' + why if why else ''}",
                "step",
                terms(f"{name} {typ} {why}"),
                name,
            )
        )
    if scenarios:
        joined = "; ".join(scenarios[:6])
        out.append(Need(f"tasks it's measured on: {joined}", "scenario", terms(joined)))
    for s in suggestions[:4]:
        out.append(Need(s, "suggestion", terms(s)))
    for s in weak_skills[:3]:
        out.append(
            Need(
                f"a better version of {s}, which didn't help when measured here", "result", terms(s)
            )
        )
    if use_case:
        out.append(Need(f"use case: {use_case[:200]}", "use case", terms(use_case)))
    return out[: R["max_needs"]]


def item_languages(name: str, description: str = "") -> list[str]:
    """The languages an item is written for (item_languages, language_min)."""
    name_words = set(re.split(r"[-_\s]+", name.lower()))
    out = []
    for lang, words in R["item_languages"].items():
        score = 0
        for w in words:
            score += 2 * (w.lower() in name_words)
            score += len(re.findall(rf"(?<![\w.#+]){re.escape(w)}(?![\w#+])", description))
        if score >= R["language_min"]:
            out.append(lang)
    return out


def language_note(name: str, description: str, repo_languages) -> str | None:
    """`language_note` when the item is for languages the repo has no files in, else None."""
    langs = item_languages(name, description)
    have = set(repo_languages or ())
    for fam in R["language_families"]:
        if have & set(fam):
            have |= set(fam)
    if not langs or have & set(langs):
        return None
    return R["language_note"].format(langs=" or ".join(langs))


def _item_text(i: dict) -> str:
    return f"{i.get('name', '')} {i.get('description', '')} {' '.join(i.get('topics', []))}"


def fitting(items: list[dict], repo_languages) -> list[dict]:
    """Items not written for a language the repo has none of: only these can be picked."""
    if not repo_languages:  # nothing known about the repo's code: no item is ruled out
        return items
    return [
        i
        for i in items
        if not language_note(i.get("name", ""), i.get("description", ""), repo_languages)
    ]


def rough(needs: list[Need], items: list[dict], local: list[dict]) -> dict:
    """No model: items that mention what the needs are about, and a skill to create per uncovered step."""
    picks = []
    for i in items:
        t = terms(_item_text(i))
        best, best_score, hits, total = None, 0, set(), 0
        for n in needs:
            shared = t & n.terms
            score = len(shared) * (
                R["step_term_weight"] if n.source == "step" else R["need_term_weight"]
            )
            total += score  # fit adds up across every need the item touches
            if score > best_score:
                best, best_score = n, score
            hits |= shared
        if best and total >= R["rough_min_score"]:
            why = f"Mentions {', '.join(sorted(hits)[:3])}, which this repo's needs are about."
            picks.append((total, {"id": i["id"], "need": best.text, "why": why}))
    picks.sort(key=lambda x: -x[0])
    chosen = [p for _, p in picks[: R["max_picks"]]]
    served = {p["need"] for p in chosen}
    create = [
        {
            "name": f"{n.step}-here".replace(" ", "-").lower(),
            "need": n.text,
            "what": f"How to do '{n.step}' in this repo: the commands, the files involved, and what its checks expect.",
            "why": "Nothing in the library is written for this step of this repo.",
        }
        for n in needs
        if n.source == "step" and n.text not in served
    ][: R["max_create"]]
    improve = [
        {
            "path": x["path"],
            "need": n.text,
            "how": "Rewrite it around what this repo's checks expect, and measure the two versions.",
            "why": "It was measured here and didn't help.",
        }
        for n in needs
        if n.source == "result"
        for x in local
        if x["name"] in n.text
    ][: R["max_improve"]]
    return {"picks": chosen, "create": create, "improve": improve, "basis": "rough"}


def with_model(
    model: ModelClient, needs: list[Need], items: list[dict], local: list[dict], kind_label: str
) -> dict:
    cands = items[: R["max_candidates"]]
    text = (
        "<needs>\n" + "\n".join(f"- {n.text}" for n in needs) + "\n</needs>\n"
        f'<candidates kind="{kind_label}">\n'
        + "\n".join(
            f"- id={i['id']} | {i.get('name')} | ★{i.get('stars', 0)} | {i.get('description', '')[:200]}"
            for i in cands
        )
        + "\n</candidates>\n<local>\n"
        + "\n".join(
            f"- path={x['path']} | {x['name']} | {x.get('description', '')[:160]}" for x in local
        )
        + "\n</local>"
    )
    call = model.call(
        Prompt(
            skills.section("recommend-for-repo", "Pick prompt"), [{"type": "text", "text": text}]
        ),
        PICK_TOOL,
        R["model"],
        1500,
    )
    data = call.input if isinstance(call.input, dict) else {}
    ids = {i["id"] for i in cands}
    paths = {x["path"] for x in local}
    need_texts = [n.text for n in needs]

    def need_of(s: str) -> str:
        # Keep the model's wording only if it names a real need.
        return next((n for n in need_texts if s and (s in n or n in s)), s)

    picks = [
        {"id": p["id"], "need": need_of(p.get("need", "")), "why": str(p.get("why", ""))[:300]}
        for p in data.get("picks", [])
        if isinstance(p, dict) and p.get("id") in ids
    ][: R["max_picks"]]
    create = [
        {k: str(c.get(k, ""))[:300] for k in ("name", "need", "what", "why")}
        for c in data.get("create", [])
        if isinstance(c, dict) and re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", str(c.get("name", "")))
    ][: R["max_create"]]
    improve = [
        {k: str(c.get(k, ""))[:300] for k in ("path", "need", "how", "why")}
        for c in data.get("improve", [])
        if isinstance(c, dict) and c.get("path") in paths
    ][: R["max_improve"]]
    return {"picks": picks, "create": create, "improve": improve, "basis": "model"}


def cache_key(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def draft(
    model: ModelClient | None,
    name: str,
    need: str,
    what: str,
    repo_summary: str = "",
    base: str | None = None,
) -> str:
    """A SKILL.md for this repo: written by the model, or a template from the repo's facts."""
    if model is None:
        return (
            f"---\nname: {name}\ndescription: {what[:200]}\n---\n\n# {name}\n\n"
            f"> Template: no model was reachable. Fill in the steps before measuring it.\n\n"
            f"## When to use\n{need}\n\n## Steps\n1. …\n\n## Checks before finishing\n- Run the repo's tests.\n\n"
            "## Avoid\n- …\n"
        )
    text = f"Skill name: {name}\nNeed: {need}\nWhat it should tell the agent: {what}\n\n<repo>\n{repo_summary[:9000]}\n</repo>"
    if base:
        text += f"\n\nThis is a rewrite of the existing skill below; keep what works, fix what doesn't:\n<existing>\n{base[:8000]}\n</existing>"
    call = model.call(
        Prompt(
            skills.section("recommend-for-repo", "Draft prompt"), [{"type": "text", "text": text}]
        ),
        DRAFT_TOOL,
        R["draft_model"],
        4000,
    )
    md = call.input.get("skill_md") if isinstance(call.input, dict) else None
    if not isinstance(md, str) or not md.strip():
        raise GenerationError("The model returned no SKILL.md.")
    return md.strip() + "\n"


def save_draft(library: Path, name: str, text: str, improves: str | None = None) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", name):
        raise ValueError("Use a short kebab-case name.")
    dest = library / "created" / name
    n = 2
    while dest.exists():
        dest = library / "created" / f"{name}-v{n}"
        n += 1
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text(text)
    (dest / ".source.json").write_text(json.dumps({"created": True, "improves": improves}))
    return dest
