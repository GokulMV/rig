"""Where a library item goes on the canvas, by the rules in the place-in-architecture skill."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from proving_ground import skills
from proving_ground.recommend import language_note

P = skills.load("place-in-architecture").values
GENERIC = {"the", "and", "for", "with", "your", "agent", "agents", "skill",
           "skills", "tool", "tools", "open", "source", "based", "using", "that", "from", "into",
           # everyday verbs and words: a match on one says nothing about where an item acts
           "read", "write", "make", "use", "run", "runs", "check", "find", "get", "set", "add",
           "before", "after", "finishing", "work", "works", "any", "all", "new", "help", "helps",
           "when", "what", "this", "them", "each", "every", "more", "than", "its", "are", "can",
           "not", "only", "also", "change", "changes", "setup"}  # fmt: skip


@dataclass
class Block:
    id: str  # canvas id: arch:<id>, step:<name>, setup:<label>
    kind: str  # an architecture type, "step", or "setup"
    name: str
    detail: str = ""
    step_type: str = ""
    index: int = 0
    present: bool = True  # False for a placeholder the canvas says to add (a CLAUDE.md)


def _words(text: str) -> set[str]:
    # "Claude Code" names the agent most items are written for, not what they do.
    text = re.sub(r"claude[\s-]+code", " ", text.lower())
    return {w for w in re.findall(r"[a-z0-9]+", text) if len(w) >= 3 and w not in GENERIC}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def theme_of(text: str) -> str:
    """The theme whose words the text uses most (theme_words), else ""."""
    have = _tokens(text)
    best, n = "", 0
    for theme, words in P["theme_words"].items():
        hits = len(have & set(words))
        if hits > n:
            best, n = theme, hits
    return best


def _places(block: Block) -> set[str]:
    """The kinds of place a block counts as, in the skill's terms."""
    out = {block.kind}
    if block.kind == "setup" and block.name in P["setup_places"]:
        out.add(P["setup_places"][block.name])
    if block.kind == "step":
        if block.index == 0:
            out.add("first-step")
        for place, types in P["step_types"].items():
            if block.step_type in types or any(t in block.name.lower() for t in types):
                out.add(place)
    return out


def _list(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _root(blocks: list[Block]) -> Block | None:
    """The agent setup's instructions: one the repo has, else the one the canvas says to add."""
    roots = [b for b in blocks if "root" in _places(b)]
    return next((b for b in roots if b.present), roots[0] if roots else None)


def place(
    blocks: list[Block],
    name: str,
    description: str = "",
    topics: list[str] | None = None,
    category: str = "skill",
    theme: str = "",
    languages: Mapping[str, int] | None = None,
) -> dict:
    """Where an item goes: {targets: [{id, why}], reason, beside, note}. Linked only for a reason
    a person can check (a word of the block's name, a theme that fits, a kind with one place);
    else beside the agent setup with no link, and P["unlinked"]. `note`: written for a language
    the repo has none of (recommend-for-repo), also at the end of `reason`."""
    text = f"{name} {description} {' '.join(topics or [])}"
    item = _words(text)
    theme = theme or theme_of(text)
    wanted = set(P["categories"].get(category, ["setup"]))
    themed = set(P["themes"].get(theme, []))
    noun = P["nouns"].get(category, "item")
    reasons = P["reasons"]
    note = language_note(name, description, languages) if languages else None

    def said(why: str) -> str:
        return f"{why} {note}" if note else why

    one = P["one_place"].get(category) or {}
    home = next((b for b in blocks if one.get("at") and b.name == one["at"]), None)
    if home is not None:  # a kind with one place, and the canvas has it
        why = reasons["one_place"].format(block=home.name, why=one["why"])
        return {
            "targets": [{"id": home.id, "why": why}],
            "reason": said(why),
            "beside": home.id,
            "note": note,
        }

    per_place: dict[str, int] = {}
    for b in blocks:
        for pl in _places(b) & themed:
            per_place[pl] = per_place.get(pl, 0) + 1
    theme_words = set(P["theme_words"].get(theme, []))
    root = _root(blocks)
    scored = []
    for b in blocks:
        places = _places(b)
        name_hits = sorted(item & _words(b.name))
        detail_hits = sorted((item & _words(b.detail)) - set(name_hits))
        fits = places & themed
        on_name = _tokens(b.name) & theme_words
        on_detail = sorted((_tokens(b.detail) & theme_words) - on_name)
        on_block = on_name | set(on_detail)
        # A theme alone links only where it can't be confused: the block has the theme's words,
        # or it is the one block of that place (the one test command, the one front end).
        theme_link = bool(fits) and (bool(on_block) or any(per_place[x] == 1 for x in fits))
        score = (
            P["name_match"] * len(name_hits)
            + P["detail_match"] * len(detail_hits)
            + P["kind_match"] * bool(places & wanted)
            + P["theme_match"] * bool(fits)
            + P["theme_word_match"] * len(on_block)
        )
        if b is root and theme_link and "root" in fits:
            why = reasons["whole_repo"].format(block=b.name, theme=theme.lower())
        elif name_hits:
            why = reasons["words"].format(block=b.name, noun=noun, words=_list(name_hits[:3]))
        elif theme_link and on_detail:
            why = reasons["theme_words"].format(
                block=b.name, noun=noun, theme=theme.lower(), words=_list(on_detail[:3])
            )
        elif theme_link:
            place_ = sorted(fits)[0]
            why = reasons["theme"].format(
                block=b.name,
                noun=noun,
                theme=theme.lower(),
                place=P["place_names"].get(place_, place_),
            )
        elif one.get("why") and places & wanted:  # a kind with one place: any block of it
            why = reasons["one_place"].format(block=b.name, why=one["why"])
        else:
            continue  # only its kind, or words of its description: not enough to link it
        scored.append((score, b, why))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return {
            "targets": [],
            "reason": said(P["unlinked"]),
            "beside": root.id if root else None,
            "note": note,
        }
    best = scored[0][0]
    picks = [x for x in scored if x[0] >= best * P["second_target_ratio"]][: P["max_targets"]]
    targets = [{"id": b.id, "why": why} for _, b, why in picks]
    return {
        "targets": targets,
        "reason": said(" ".join(t["why"] for t in targets)),
        "beside": targets[0]["id"],
        "note": note,
    }
