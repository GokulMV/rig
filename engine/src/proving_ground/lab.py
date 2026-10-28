"""The Workflow Lab: starter workflows per discipline, random workflows, patterns, and compiling
any of them into something an agent runs.

Rules and values live in the starter-workflows and workflow-patterns skills. No model calls.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from proving_ground import skill_match, skill_models, skills

S = skills.load("starter-workflows").values
W = skills.load("workflow-patterns").values
P = skills.load("learned-priors").values
B = skills.load("business-workflows").values
R = skills.load("rag-workflows").values
G = skills.load("goal-rules").values
# Disciplines the business workflows add (finance, compliance) build and randomise like the rest.
for _did, _d in B["disciplines"].items():
    S["disciplines"].setdefault(_did, {**_d, "starters": []})


@dataclass
class Step:
    id: str
    name: str
    does: str
    kind: str  # think | do | check | judge
    model: str
    skills: list[dict] = field(default_factory=list)  # {path, name}, and source/repo/url if known
    pos: list[float] | None = None  # where it sits on the builder canvas


@dataclass
class Workflow:
    id: str
    name: str
    discipline: str  # a discipline id, or "pattern"
    origin: str  # starter | business | rag | random | pattern | custom
    steps: list[Step]
    loop: list | None = None  # [from step id, to step id, max] (the one loop of older workflows)
    harness: list[str] = field(default_factory=list)
    # A graph: edges [from, to] say what follows what (branches run in parallel, several inputs
    # join); loops [from, to, max] go back to fix. With no edges, the steps run in order.
    edges: list[list] = field(default_factory=list)
    loops: list[list] = field(default_factory=list)
    prior: float = 0.0
    cost: float = 1.0
    why: list[str] = field(default_factory=list)
    # What the use case said that the wording uses, e.g. {"limit": "$200"} (facts_from).
    facts: dict = field(default_factory=dict)
    # The goal it was built for, whole ("Goal & rules" in the Lab, editable there): its rule
    # lines (goal_rules) reach the first step and BUILD.md. None when it wasn't built from one.
    brief: str | None = None
    # The workflow-patterns pattern it was made from: while unedited (origin "pattern") its guess
    # starts from the pattern's prior, so pricing it again gives the same number.
    pattern: str | None = None

    def dump(self) -> dict:
        # Every harness rule as this workflow's discipline says it, so a page shows the same words.
        return asdict(self) | {
            "harness_text": {h: harness_text(h, self.discipline, self.facts) for h in W["harness"]},
            "rules": goal_rules(self.brief),
        }


MONEY = re.compile(r"(?<![\w$€£])([$€£]\s?\d+(?:,\d{3})*(?:\.\d+)?(?:\s?[kKmM](?![a-zA-Z]))?)")


def facts_from(use_case: str | None) -> dict:
    """What a use case says that a workflow's wording can use: the first amount it names
    ("refunds over $200 need a manager" gives {"limit": "$200"})."""
    m = MONEY.search(use_case or "")
    return {"limit": m.group(1).replace(" ", "")} if m else {}


_SPLIT = re.compile(G["split"])
_STRIP = re.compile(G["strip"])
_RULE_WORDS = re.compile(
    r"(?<![\w'])(?:" + "|".join(re.escape(w) for w in G["rule_words"]) + r")(?![\w'])", re.I
)


def goal_rules(goal: str | None) -> list[str]:
    """The rule lines of a goal (goal-rules): cut at new lines, semicolons, bullets and sentence
    ends; a line with a number or a rule word ("must", "only", "needs a manager") is a rule.
    The goal's own words, in its order: "refund within 30 days → full refund; 30–60 days →
    store credit" gives both lines."""
    out: list[str] = []
    for part in _SPLIT.split(goal or ""):
        line = " ".join(_STRIP.sub("", part or "").split()).rstrip(" ,.")
        if not line or not (re.search(r"\d", line) or _RULE_WORDS.search(line)):
            continue
        if len(line) > G["max_chars"]:
            line = line[: G["max_chars"] - 1].rstrip() + "…"
        if line not in out:
            out.append(line)
        if len(out) >= G["max_rules"]:
            break
    return out


def with_brief(wf: Workflow, goal: str | None) -> Workflow:
    """The workflow with the goal it is built for as its brief (only when there is one)."""
    if goal and goal.strip():
        wf.brief = goal.strip()
    return wf


class _Fill(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _nouns(discipline: str, facts: dict | None) -> dict:
    """A discipline's words for a pattern's placeholders (workflow-patterns: phrasing)."""
    d = W["phrasing"]["disciplines"].get(discipline, {})
    nouns = {k: v for k, v in d.items() if isinstance(v, str)}
    nouns.setdefault("maker", "maker")
    nouns["Maker"] = nouns["maker"][:1].upper() + nouns["maker"][1:]
    limit = (facts or {}).get("limit")
    nouns["limit"] = limit or nouns.get("limit", "the limit")
    nouns["over"] = f", and anything over {limit}," if limit else ""
    return nouns


def is_code(discipline: str) -> bool:
    return discipline in W["code_disciplines"] or discipline not in W["phrasing"]["disciplines"]


def phrase(pid: str, role: dict, discipline: str, facts: dict | None = None) -> tuple[str, str]:
    """A pattern role's name and what it does, in the discipline's words: as written for code
    work; for any other discipline its own text, else the neutral one, with its nouns filled in."""
    if is_code(discipline):
        return role["name"], role["does"]
    key = f"{pid}.{role['id']}"
    own = W["phrasing"]["disciplines"][discipline]
    neutral = W["phrasing"]["neutral"]
    fill = _Fill(_nouns(discipline, facts))
    name = (own.get("names") or {}).get(key) or neutral["names"].get(key) or role["name"]
    does = (own.get("roles") or {}).get(key) or neutral["roles"].get(key) or role["does"]
    return name.format_map(fill), does.format_map(fill)


def harness_text(h: str, discipline: str, facts: dict | None = None) -> str:
    """A harness rule as the discipline says it (workflow-patterns: harness)."""
    t = W["harness"][h]
    if is_code(discipline):
        return t["does"]
    text = (t.get("by_discipline") or {}).get(discipline) or t.get("neutral") or t["does"]
    return text.format_map(_Fill(_nouns(discipline, facts)))


def match_skills(
    step_words, library: list[dict], limit: int, body: str = "", context=(), discipline=None
) -> list[dict]:
    """Library skills that fit a step, best first, each with `why` (the words that matched and
    how much of its name they cover). The rules are in the match-skills skill: rare words count
    more, a skill must fit the step's headline (name and words), and one named for a kind of
    work (review, test, code) or one tool fits only a step about it."""
    return skill_match.match(step_words, library, limit, body, context, discipline)


def step_skills(step: dict, library: list[dict], limit: int, models=None) -> list[dict]:
    """The skills for a step: picked by the skill matcher's models once they're on this
    machine (skill_models), else match_skills: its name and words as the headline, what it
    does as the body, in its discipline's context."""
    models = models or skill_models.active(library)
    if models is not None:
        return skill_match.pick(step, library, limit, models)
    head = " ".join([step.get("name", ""), *step.get("words", [])])
    context = skill_match.CONTEXT.get(step.get("discipline", ""), ())
    return match_skills(head, library, limit, step.get("does", ""), context, step.get("discipline"))


def warm_skills(library: list[dict], models) -> None:
    """Match every step the Lab builds workflows from against the library with the models, so
    their scores are cached before the Lab uses them."""
    k = S["random_skills_per_step"]
    for did, d in S["disciplines"].items():
        for p in d["steps"].values():
            step_skills({**p, "discipline": did}, library, k, models)
    for wf in [*B["workflows"], *R["workflows"]]:
        for st in wf["steps"]:
            step_skills({**st, "discipline": wf["discipline"]}, library, k, models)
    for p in W["patterns"].values():
        for r in p["roles"]:
            step_skills({**r, "discipline": "pattern"}, library, k, models)


def features(wf: Workflow) -> set[str]:
    """The shape a workflow's result is learned from (learned-priors): kinds of steps, a review,
    loops, parallel steps, harness rules and the main model's tier."""
    f = {f"kind:{st.kind}" for st in wf.steps}
    if any(st.name.lower().startswith(("review", "critique")) for st in wf.steps):
        f.add("review")
    if wf.loops:
        f.add("loop")
    if max((len(lv) for lv in levels(wf)), default=1) > 1:
        f.add("parallel")
    f |= {f"harness:{h}" for h in wf.harness}
    tiers = [W["models"].get(st.model, {}).get("tier", "other") for st in wf.steps]
    if tiers:
        # Ties go to the earliest step's tier: the same workflow always has the same shape.
        f.add(f"tier:{max(tiers, key=tiers.count)}")
    return f


def model_part(wf: Workflow) -> tuple[float, str | None]:
    """What the steps' models add to the guess (learned-priors: model_weight_by_kind): each
    step's model prior (workflow-patterns, points against Sonnet) weighted by how much its kind
    of step depends on the model. A guess, like the rest of the prior."""
    weights = P["model_weight_by_kind"]
    num = den = 0.0
    for st in wf.steps:
        w = float(weights.get(st.kind, weights["do"]))
        num += w * float(W["models"].get(st.model, {}).get("prior", 0))
        den += w
    pts = round(num / den, 1) if den else 0.0
    if not pts:
        return 0.0, None
    by: dict[str, list[str]] = {}
    for st in wf.steps:
        by.setdefault(W["models"].get(st.model, {}).get("label", st.model), []).append(st.kind)
    said = "; ".join(
        f"{', '.join(sorted(set(kinds)))} on {label}" for label, kinds in sorted(by.items())
    )
    sign = "+" if pts > 0 else "\u2212"
    return pts, f"Models ({said}): {sign}{abs(pts)} pts, a guess (learned-priors)."


def _pattern_helps(pid: str, discipline: str) -> str:
    p = W["patterns"][pid]
    if is_code(discipline):
        return p["helps"]
    return W["phrasing"]["neutral"]["helps"].get(pid, p["helps"])


def _price(wf: Workflow) -> Workflow:
    """Prior (a guess until measured) and relative cost, with the reasons."""
    kinds = [st.kind for st in wf.steps]
    pr = S["prior"]
    prior, why = 0.0, []
    if wf.origin == "pattern" and wf.pattern in W["patterns"]:
        # An unedited pattern: its own prior (on Sonnet), not the sum of its parts.
        return _priced_pattern(wf)
    if "think" in kinds:
        prior += pr["plan"]
        why.append("Plans or decides before doing.")
    if "check" in kinds:
        prior += pr["check"]
        why.append("Checks its own work with a command.")
    if "judge" in kinds:
        prior += pr["judge"]
        why.append("A step judges the quality of the result.")
    if any(st.name.lower().startswith(("review", "critique")) for st in wf.steps):
        prior += pr["review"]
        why.append("Has a review step.")
    for frm, to, mx in wf.loops:
        prior += pr["loop"]
        why.append(
            f"Loops back from {_name(wf, frm)} to {_name(wf, to)} to fix, at most "
            + (f"{mx} times." if mx != 1 else "once.")
        )
    width = max((len(lv) for lv in levels(wf)), default=1)
    if width > 1:
        why.append(f"Runs up to {width} steps in parallel.")
    for h in wf.harness:
        t = W["harness"][h]
        prior += t["prior"]
        why.append(f"{t['name']}: {harness_text(h, wf.discipline, wf.facts)}")
    _set_cost(wf)
    pts, said = model_part(wf)
    if said:
        why.append(said)
    wf.prior = round(prior + pts, 1)
    wf.why = why
    return wf


def _set_cost(wf: Workflow) -> None:
    base = W["models"][W["baseline_model"]]
    costs = [W["models"][st.model]["cost"] for st in wf.steps]
    # Each step is a share of the work; a loop repeats its part about once on average.
    loops = 1 + 0.5 * len(wf.loops)
    wf.cost = round(sum(costs) / len(costs) * (0.6 + 0.2 * len(wf.steps)) * loops / base["cost"], 2)


def _priced_pattern(wf: Workflow) -> Workflow:
    """A pattern's guess: its prior plus what its steps' models add (model_part)."""
    _set_cost(wf)
    pts, said = model_part(wf)
    wf.prior = round(W["patterns"][wf.pattern]["prior"] + pts, 1)
    wf.why = [_pattern_helps(wf.pattern, wf.discipline), *([said] if said else [])]
    return wf


def _name(wf: Workflow, sid: str) -> str:
    return next((st.name for st in wf.steps if st.id == sid), sid)


MAX_STEPS = 24


def normalize(wf: Workflow) -> Workflow:
    """One shape for every workflow: a list becomes a chain, the old single loop joins loops,
    and the graph is checked (known steps, no cycle except through loops)."""
    ids = [st.id for st in wf.steps]
    if not ids:
        raise ValueError("a workflow needs at least one step")
    if len(ids) > MAX_STEPS:
        raise ValueError(f"at most {MAX_STEPS} steps")
    if len(set(ids)) != len(ids):
        raise ValueError("step ids must be unique")
    if not wf.edges:
        wf.edges = [[a, b] for a, b in zip(ids, ids[1:], strict=False)]
    if wf.loop and not wf.loops:
        wf.loops = [list(wf.loop)]
    known = set(ids)
    wf.edges = [list(e[:2]) for e in wf.edges if e[0] in known and e[1] in known and e[0] != e[1]]
    wf.loops = [
        [a, b, max(1, min(5, int(m)))]
        for a, b, m in (x[:3] for x in wf.loops)
        if a in known and b in known
    ]
    wf.loop = wf.loops[0] if wf.loops else None
    levels(wf)  # raises on a cycle
    return wf


def levels(wf: Workflow) -> list[list[str]]:
    """Steps in stages: each stage can start once everything pointing into it is done."""
    ids = [st.id for st in wf.steps]
    edges = wf.edges or [[a, b] for a, b in zip(ids, ids[1:], strict=False)]
    indeg = {i: 0 for i in ids}
    out: dict[str, list[str]] = {i: [] for i in ids}
    for a, b in edges:
        if a in out and b in indeg:
            out[a].append(b)
            indeg[b] += 1
    stage = [i for i in ids if indeg[i] == 0]
    result, seen = [], 0
    while stage:
        result.append(stage)
        seen += len(stage)
        nxt = []
        for a in stage:
            for b in out[a]:
                indeg[b] -= 1
                if indeg[b] == 0:
                    nxt.append(b)
        stage = [i for i in ids if i in nxt]
    if seen != len(ids):
        raise ValueError("the connections go round in a circle: draw a loop (back to fix) instead")
    return result


def _wid(*parts: object) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:10]


def _build(
    did: str, name: str, origin: str, step_ids: list[str], loop, harness, library
) -> Workflow:
    d = S["disciplines"][did]
    steps = []
    for sid in step_ids:
        p = d["steps"][sid]
        steps.append(
            Step(
                sid,
                p["name"],
                p["does"],
                p["kind"],
                S["model_for"][p["kind"]],
                step_skills({**p, "discipline": did}, library, S["random_skills_per_step"]),
            )
        )
    wf = Workflow(
        _wid(did, step_ids, loop, harness),
        name,
        did,
        origin,
        steps,
        list(loop) if loop else None,
        list(harness or []),
    )
    return _price(normalize(wf))


def starters(library: list[dict]) -> list[dict]:
    """Every discipline with its ready-made workflows."""
    out = []
    for did, d in S["disciplines"].items():
        wfs = [
            _build(
                did, s["name"], "starter", s["steps"], s.get("loop"), s.get("harness"), library
            ).dump()
            for s in d["starters"]
        ]
        if wfs:
            out.append({"id": did, "label": d["label"], "workflows": wfs})
    return out


def _graph_workflows(items: list[dict], origin: str, library: list[dict]) -> list[Workflow]:
    """Workflows written as graphs in a skill: steps, edges, loops, and the `source` each is
    modelled on (the first `why`)."""
    out = []
    for b in items:
        steps = [
            Step(
                s["id"],
                s["name"],
                s["does"],
                s["kind"],
                S["model_for"][s["kind"]],
                step_skills(
                    {**s, "discipline": b["discipline"]}, library, S["random_skills_per_step"]
                ),
            )
            for s in b["steps"]
        ]
        wf = Workflow(
            _wid(origin, b["id"]),
            b["name"],
            b["discipline"],
            origin,
            steps,
            harness=list(b.get("harness") or []),
            edges=[list(e) for e in b["edges"]],
            loops=[list(lp) for lp in b.get("loops") or []],
        )
        wf = _price(normalize(wf))
        wf.why = [f"Modelled on: {b['source']}.", *wf.why]
        out.append(wf)
    return out


def business(library: list[dict]) -> list[Workflow]:
    """The complex workflows from business-workflows: graphs with parallel branches, joins and
    several loops, each modelled on a published procedure (its source is the first `why`)."""
    return _graph_workflows(B["workflows"], "business", library)


def rag(library: list[dict]) -> list[Workflow]:
    """The retrieval-augmented generation architectures from rag-workflows (research
    discipline). Apart from business because the simple ones are chains, not parallel graphs."""
    return _graph_workflows(R["workflows"], "rag", library)


def random_workflow(
    library: list[dict],
    discipline: str | None = None,
    seed: int | None = None,
    shown: set[str] | None = None,
) -> Workflow:
    """A new workflow for a discipline: steps in a working order, a check after the work, a loop."""
    rng = random.Random(seed)
    shown = set(shown or ())
    for _ in range(60):
        did = discipline if discipline in S["disciplines"] else rng.choice(list(S["disciplines"]))
        d = S["disciplines"][did]
        pool = list(d["steps"])
        lo, hi = S["random_steps"]
        n = min(len(pool), rng.randint(lo, hi))
        picked = sorted(rng.sample(range(len(pool)), n))
        ids = [pool[i] for i in picked]
        kinds = {i: d["steps"][i]["kind"] for i in pool}
        if not any(kinds[i] == "do" for i in ids):
            ids.append(next(i for i in pool if kinds[i] == "do"))
            ids.sort(key=pool.index)
        last_do = max(n for n, i in enumerate(ids) if kinds[i] == "do")
        checks = [i for i in pool if kinds[i] in ("check", "judge")]
        if checks and not any(kinds[i] in ("check", "judge") for i in ids[last_do + 1 :]):
            after = [c for c in checks if pool.index(c) > pool.index(ids[last_do]) and c not in ids]
            if after:
                ids.append(rng.choice(after))
        loop = None
        do_ids = [i for i in ids if kinds[i] == "do"]
        chk = [i for i in ids if kinds[i] in ("check", "judge")]
        if do_ids and chk and ids.index(chk[-1]) > ids.index(do_ids[-1]):
            loop = [chk[-1], do_ids[-1], 2]
        harness = rng.sample(list(W["harness"]), rng.randint(0, 1))
        name = (
            f"{d['label']}: "
            + " → ".join(d["steps"][i]["name"] for i in ids[:3])
            + ("…" if len(ids) > 3 else "")
        )
        wf = _build(did, name, "random", ids, loop, harness, library)
        if wf.id not in shown:
            return wf
    return wf


def from_pattern(
    pid: str, model: str, library: list[dict], discipline: str = "pattern", use_case: str = ""
) -> Workflow:
    """A pattern from workflow-patterns as a workflow, so it compiles and runs the same way.
    With a `discipline`, it is that discipline's: its roles are said in its words (phrasing),
    skills are matched in its context, and it is measured on its benches. The use case's
    numbers (an amount it names) go into the wording."""
    p = W["patterns"][pid]
    facts = facts_from(use_case)
    steps = []
    for r in p["roles"]:
        name, does = phrase(pid, r, discipline, facts)
        said = {**r, "name": name, "does": does, "discipline": discipline}
        steps.append(
            Step(
                r["id"],
                name,
                does,
                r.get("kind", "do"),
                r.get("model") or model,
                step_skills(said, library, S["random_skills_per_step"]),
            )
        )
    neutral = W["phrasing"]["neutral"]
    code = is_code(discipline)
    title = p["name"] if code else neutral["patterns"].get(pid, p["name"])
    loop = [p["loop"]["from"], p["loop"]["to"], p["loop"]["max"]] if p.get("loop") else None
    wf = Workflow(
        _wid("pattern", pid, model)
        if discipline == "pattern"
        else _wid("pattern", pid, model, discipline),
        title.format_map(_Fill(_nouns(discipline, facts))),
        discipline,
        "pattern",
        steps,
        loop,
        edges=[list(e) for e in p.get("edges") or []],
        facts=facts,
        pattern=pid,
    )
    return with_brief(_price(normalize(wf)), use_case)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "step"


def workflow_name(wf: Workflow, agent: str = "claude-code") -> str:
    """The compiled skill's name (and folder): one per agent form."""
    return f"workflow-{wf.id}" + ("" if agent == "claude-code" else f"-{agent}")


def compile_workflow(
    wf: Workflow,
    dest: Path,
    skill_texts: dict[str, str] | None = None,
    agent: str = "claude-code",
) -> Path:
    """Write the workflow as a skill folder the agent runs: SKILL.md (the protocol, by stage),
    in the agent's form (workflow-patterns: agent_forms), and for Claude Code agents/<step>.md,
    one subagent per step on its model. The folder is a treatment like any skill.
    """
    form = W["agent_forms"].get(agent)
    if form is None:
        raise ValueError(f"No way to write a workflow for {agent!r} yet.")
    saved = (dest / ".saved").is_file()  # compiling again for a run must not un-save it
    # Written beside it, then swapped in: a run (or a page polling one) reading the folder never
    # sees it missing or half-written, and an unchanged workflow leaves the folder as it was.
    dest.parent.mkdir(parents=True, exist_ok=True)
    new = Path(tempfile.mkdtemp(prefix=f".{dest.name}.", dir=dest.parent))
    try:
        _write_workflow(wf, new, skill_texts, agent, form, saved)
        if _same_tree(new, dest):
            return dest
        if dest.exists():
            old = Path(tempfile.mkdtemp(prefix=f".{dest.name}.old.", dir=dest.parent))
            dest.rename(old / "folder")
            new.rename(dest)
            shutil.rmtree(old, ignore_errors=True)
        else:
            new.rename(dest)
        return dest
    finally:
        shutil.rmtree(new, ignore_errors=True)


def _same_tree(a: Path, b: Path) -> bool:
    """The same files with the same bytes, in folders a and b."""
    if not b.is_dir():
        return False

    def files(d: Path) -> dict[str, bytes]:
        return {str(f.relative_to(d)): f.read_bytes() for f in d.rglob("*") if f.is_file()}

    return files(a) == files(b)


def _write_workflow(
    wf: Workflow,
    dest: Path,
    skill_texts: dict[str, str] | None,
    agent: str,
    form: dict,
    saved: bool,
) -> None:
    if saved:
        (dest / ".saved").write_text("")
    if form["agent_files"]:
        (dest / "agents").mkdir()
    names = {st.id: st.name for st in wf.steps}
    lines = [
        "---",
        f"name: {workflow_name(wf, agent)}",
        # Agents pick skills by description: say it's required, or a "with" trial may never open it.
        f"description: Required for every task here. Use this skill first, before anything else, "
        f"and work through its steps: {wf.name}.",
        "---",
        "",
        f"# {wf.name}",
        "",
        form["intro"],
        "Keep the results of each step and pass them to the next. Use each step's name exactly",
        "as written, so the run can be checked afterwards.",
    ]
    rules = goal_rules(wf.brief)
    if wf.brief and wf.brief.strip():
        # The goal and its rules come first: the policy reaches every step (goal-rules).
        lines += ["", f"## {G['heading']}", "", " ".join(wf.brief.split())]
        if rules:
            lines += ["", f"{G['brief_rules']} (pass them to every step):"]
            lines += [f"- {r}" for r in rules]
    lines += ["", "## Steps"]
    first = set(levels(wf)[0])
    by_id = {st.id: st for st in wf.steps}
    preds = {st.id: [a for a, b in wf.edges if b == st.id] for st in wf.steps}
    n = 0
    for k, stage in enumerate(levels(wf), 1):
        if len(stage) > 1:
            lines += ["", f"**Stage {k}: {form['parallel'].format(n=len(stage))}:**"]
        for sid in stage:
            st = by_id[sid]
            n += 1
            if len(preds[sid]) > 1:
                lines.append(
                    f"   (Waits for: {', '.join(by_id[p].name for p in preds[sid])}; pass it all their results.)"
                )
            sub = _slug(st.id)
            short = st.model.removeprefix("claude-").split("-")[0]
            lines.append(
                f"{n}. **{st.name}**: "
                + form["step"].format(model=short, name=st.name, n=n, id=st.id)
            )
            follow = f" {G['first_step']} " + " ".join(f"({k}) {r}" for k, r in enumerate(rules, 1))
            follow = (follow if sid in first else f" {G['later_steps']}") if rules else ""
            brief = [
                f"   Brief: {st.does}{follow} Report back in a few lines: what you did, what you checked, what's left."
            ]
            body = [
                "---",
                f"name: {sub}",
                f"description: {st.name}: {st.does}",
                f"model: {short}",
                "---",
                "",
                f"You do one step of a workflow: **{st.name}**. {st.does}",
                *([G["first_step"], *[f"- {r}" for r in rules]] if rules and sid in first else []),
                *([G["later_steps"]] if rules and sid not in first else []),
                "Report back in a few lines: what you did, what you checked, what's left.",
            ]
            for s_ in st.skills:
                text = (skill_texts or {}).get(s_["path"], "")
                inner = (
                    text.split("\n---\n", 1)[-1].strip() if text.startswith("---") else text.strip()
                )
                if inner:
                    body += ["", f"## Follow the skill {s_['name']}", inner[:5000]]
                    brief.append(f"   Include in the brief, from the skill {s_['name']}:")
                    brief += ["   > " + ln for ln in inner[:3000].splitlines()]
            lines += brief
            if form[
                "agent_files"
            ]:  # also as a subagent file, for installs that read .claude/agents/
                (dest / "agents" / f"{sub}.md").write_text("\n".join(body) + "\n")
    if wf.loops:
        lines += ["", "## Loops"]
        for frm, to, mx in wf.loops:
            lines.append(
                f"- If **{names.get(frm, frm)}** finds problems, go back to **{names.get(to, to)}** and fix them; at most {mx} times. Then stop and report what's left."
            )
    if wf.harness:
        lines += ["", "## Rules"] + [
            f"- {W['harness'][h]['name']}: {harness_text(h, wf.discipline, wf.facts)}"
            for h in wf.harness
        ]
    lines += ["", "Before finishing, run the task's checks and show their output."]
    (dest / "SKILL.md").write_text("\n".join(lines) + "\n")
    (dest / "workflow.json").write_text(json.dumps(wf.dump(), indent=2))


def load_workflow(data: dict) -> Workflow:
    steps = [
        Step(**{k: v for k, v in s.items() if k in Step.__dataclass_fields__})
        for s in data["steps"]
    ]
    wf = Workflow(
        **{k: v for k, v in {**data, "steps": steps}.items() if k in Workflow.__dataclass_fields__}
    )
    return _price(normalize(wf))


GENERIC_STEPS = [
    {"id": "blank", "name": "New step", "does": "Describe what this step does.", "kind": "do"},
    {
        "id": "plan",
        "name": "Plan",
        "does": "Plan the work: steps, files or sources, and how to check it.",
        "kind": "think",
    },
    {
        "id": "decide",
        "name": "Decide",
        "does": "Choose between the options with the reasons, and say what would change the call.",
        "kind": "think",
    },
    {
        "id": "check",
        "name": "Check",
        "does": "Run the checks and report pass or exactly what failed.",
        "kind": "check",
    },
    {
        "id": "review",
        "name": "Review",
        "does": "Review the result against the task with fresh eyes; list concrete problems only.",
        "kind": "judge",
    },
    {
        "id": "summarise",
        "name": "Summarise",
        "does": "Write what was done, what was checked, and what's left.",
        "kind": "do",
    },
]


def templates() -> list[dict]:
    """Steps to build with: a generic set, then every discipline's steps."""
    out = [
        {
            "id": "generic",
            "label": "Any workflow",
            "steps": [dict(s, model=S["model_for"][s["kind"]]) for s in GENERIC_STEPS],
        }
    ]
    for did, d in S["disciplines"].items():
        out.append(
            {
                "id": did,
                "label": d["label"],
                "steps": [
                    {
                        "id": sid,
                        "name": p["name"],
                        "does": p["does"],
                        "kind": p["kind"],
                        "model": S["model_for"][p["kind"]],
                        "words": p.get("words", []),
                    }
                    for sid, p in d["steps"].items()
                ],
            }
        )
    return out
