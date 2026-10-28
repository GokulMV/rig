"""A catalog from GitHub: skills, agents, MCP servers, hooks, harnesses, workflows, eval suites.

Repositories are found by GitHub topic search, cached for a day, and ranked four ways:
recommended, most starred, latest, and relevant to the current project (which keeps useful
low-star repositories in view). Nothing is downloaded until a skill is installed, and then
only that skill's folder, into a library outside every repo.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import yaml

from proving_ground import skills

C = skills.load("curate-catalog").values
CACHE_TTL_S = C["cache_ttl_hours"] * 3600
PARTIAL_TTL_S = C["partial_retry_minutes"] * 60  # retry soon when some searches failed
SEARCH_GAP_S = C["search_gap_s"]  # GitHub allows 30 searches a minute when signed in
MAX_SKILL_FILES = C["install_max_files"]
MAX_SKILL_BYTES = C["install_max_bytes"]
MAX_ITEMS_SHOWN = C["max_items_shown"]

# Topic queries per category, and the words an item must mention to count (topic tags alone are
# noisy). A repository goes to the category it matches best (curate-catalog `classify`).
QUERIES: dict[str, list[str]] = {k: v["queries"] for k, v in C["categories"].items()}
CATEGORY_LABEL: dict[str, str] = {k: v["label"] for k, v in C["categories"].items()}
CATEGORY_BLURB: dict[str, str] = {k: v["blurb"] for k, v in C["categories"].items()}
THEMES: list[tuple[str, str]] = list(C["themes"].items())


class GitHub(Protocol):
    def search(self, query: str, sort: str, per_page: int) -> list[dict]: ...
    def get(self, endpoint: str) -> Any: ...


class GhCli:
    """GitHub through the signed-in `gh` CLI (5,000 requests an hour, 30 searches a minute)."""

    def __init__(self) -> None:
        self._last = 0.0

    def search(self, query: str, sort: str, per_page: int) -> list[dict]:
        wait = SEARCH_GAP_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        data = self.get(
            f"search/repositories?{urllib.parse.urlencode({'q': query, 'sort': sort, 'per_page': per_page})}"
        )
        return data.get("items", [])

    def get(self, endpoint: str) -> Any:
        out = subprocess.run(
            ["gh", "api", "-H", "Accept: application/vnd.github+json", endpoint],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip() or f"gh api {endpoint} failed")
        return json.loads(out.stdout)


class Anonymous:
    """GitHub without signing in (60 requests an hour)."""

    def search(self, query: str, sort: str, per_page: int) -> list[dict]:
        q = urllib.parse.urlencode({"q": query, "sort": sort, "per_page": per_page})
        return self.get(f"search/repositories?{q}").get("items", [])

    def get(self, endpoint: str) -> Any:
        req = urllib.request.Request(
            f"https://api.github.com/{endpoint}",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "proving-ground"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed https host
            return json.loads(r.read())


def default_github() -> GitHub:
    try:
        ok = (
            subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=10).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    return GhCli() if ok else Anonymous()


def theme_of(item: dict) -> str:
    text = f"{item.get('name', '')} {item.get('description') or ''} {' '.join(item.get('topics', []))}".lower()
    for label, pattern in THEMES:
        if re.search(pattern, text):
            return label
    return "General"


def _words(text: str) -> str:
    return re.sub(r"[-_]+", " ", text.lower())


_RX = {
    k: (
        re.compile(v["must_mention"]),
        re.compile(C["agentic"] if v.get("context") == "agentic" else v["context"])
        if v.get("context")
        else None,
        re.compile(v["not_if"]) if v.get("not_if") else None,
    )
    for k, v in C["categories"].items()
}


_NOT_APPS = re.compile(C["not_apps"])
_IS_A = {k: re.compile(v) for k, v in (C.get("is_a") or {}).items()}


def category_scores(r: dict) -> dict[str, int]:
    """How strongly a repository says it is each kind of thing; 0 means it isn't one.

    Name and description must mention the category (topic tags are cheap to add and often
    wrong); topics only add weight. Rules: the curate-catalog skill's `classify`.
    """
    w = C["classify"]
    name = _words(r.get("name", ""))
    desc = (r.get("description") or "").lower()
    topics = _words(" ".join(r.get("topics", [])))
    text = f"{name} {desc}"
    out: dict[str, int] = {}
    if _NOT_APPS.search(text):
        return out
    for cat, (must, context, not_if) in _RX.items():
        hits = [{m.group(0) for m in must.finditer(f)} for f in (name, desc, topics)]
        if not (hits[0] or hits[1]):
            continue
        if context is not None and not context.search(f"{text} {topics}"):
            continue
        if not_if is not None and not_if.search(text):
            continue
        out[cat] = (
            w["name"] * len(hits[0]) + w["description"] * len(hits[1]) + w["topics"] * len(hits[2])
        )
        # What its description opens by saying it is outranks what it only mentions.
        first = re.split(r"[.,;:(]| - ", desc, maxsplit=1)[0].strip()
        if cat in _IS_A and _IS_A[cat].search(first):
            out[cat] += w["is_a"]
    return out


def classify(r: dict) -> str | None:
    """The category a repository matches best, a tie going to the first listed; None: it is none
    of them."""
    scores = category_scores(r)
    if not scores:
        return None
    best = max(scores.values())
    return next(c for c in C["categories"] if scores.get(c) == best)


def reclassified(data: dict | None) -> dict | None:
    """A cached catalog with every item in the category it matches best now (the rules may have
    changed since it was fetched). Pinned items keep theirs; items that match none are dropped."""
    if data is None:
        return None
    key = (data.get("fetched_at"), len(data.get("items", [])))
    if _reclassified.get("key") == key:
        return _reclassified["data"]
    items = []
    for i in data.get("items", []):
        if i["id"] in PINNED:
            items.append(i | {"category": PINNED[i["id"]], "pinned": True})
            continue
        cat = classify(i)
        if cat is not None:
            items.append(i | {"category": cat})
    out = data | {"items": items}
    _reclassified.update(key=key, data=out)
    return out


_reclassified: dict = {}
PINNED: dict[str, str] = {
    name: cat for cat, spec in C["categories"].items() for name in spec.get("pinned", [])
}


def _item(r: dict, category: str) -> dict:
    item = {
        "id": r["full_name"],
        "name": r["name"],
        "owner": r["owner"]["login"],
        "url": r["html_url"],
        "description": r.get("description") or "",
        "stars": r.get("stargazers_count", 0),
        "pushed_at": r.get("pushed_at") or "",
        "topics": r.get("topics", []),
        "category": category,
    }
    item["theme"] = theme_of(item)
    return item


class Catalog:
    def __init__(self, github: GitHub, cache: Path):
        self._gh = github
        self._cache = cache

    def items(self, refresh: bool = False) -> list[dict]:
        return self.load(refresh)["items"]

    def load(self, refresh: bool = False) -> dict:
        """{"items", "fetched_at", "partial"}; partial results are kept only briefly."""
        if not refresh and self._cache.is_file():
            try:
                data = json.loads(self._cache.read_text())
                ttl = PARTIAL_TTL_S if data.get("partial") else CACHE_TTL_S
                # A cache from before a category was added has nothing for it: fetch again.
                same = data.get("categories", sorted(C["categories"])) == sorted(C["categories"])
                if same and "categories" in data and time.time() - data.get("fetched_at", 0) < ttl:
                    return data
            except (ValueError, KeyError):
                pass
        items, failed = self._fetch()
        data = {
            "fetched_at": time.time(),
            "items": items,
            "partial": failed > 0,
            "failed": failed,
            "categories": sorted(C["categories"]),
        }
        self._cache.parent.mkdir(parents=True, exist_ok=True)
        self._cache.write_text(json.dumps(data))
        return data

    def _fetch(self) -> tuple[list[dict], int]:
        seen: dict[str, dict] = {}
        failed = 0
        # Hand-picked repositories first, so they keep their category.
        for category, spec in C["categories"].items():
            for name in spec.get("pinned", []):
                try:
                    r = self._gh.get(f"repos/{name}")
                    if r.get("archived") or r["full_name"] in seen:
                        continue
                    seen[r["full_name"]] = _item(r, category) | {"pinned": True}
                except Exception:  # noqa: BLE001 - renamed or gone: skip it, don't retry the catalog
                    continue
        for queries in QUERIES.values():
            for q in queries:
                q_ = C["per_query"]
                for sort, per_page, extra in (
                    ("stars", q_["by_stars"], ""),
                    ("updated", q_["by_recent"], f" stars:>={q_['recent_min_stars']}"),
                ):
                    try:
                        found = self._gh.search(q + extra, sort, per_page)
                    except Exception:  # noqa: BLE001 - counted; a partial catalog is retried soon
                        failed += 1
                        continue
                    for r in found:
                        if r.get("archived") or r["full_name"] in seen:
                            continue
                        # The category it matches best, not the first search that found it.
                        best = classify(r)
                        if best is not None:
                            seen[r["full_name"]] = _item(r, best)
        return list(seen.values()), failed

    def for_project(self, terms: set[str]) -> list[dict]:
        """Low-star repositories that match this project's stack, searched by its own terms."""
        out: dict[str, dict] = {}
        for term in sorted(terms)[:4]:
            for queries in QUERIES.values():
                try:
                    found = self._gh.search(f"{term} {queries[0]}", "stars", 10)
                except Exception:  # noqa: BLE001
                    continue
                for r in found:
                    # The same filter as the main catalog: it must be about its category.
                    best = None if r.get("archived") else classify(r)
                    if best is not None:
                        out.setdefault(r["full_name"], _item(r, best))
        return list(out.values())


# Languages say little about whether a skill fits (half of GitHub mentions JavaScript); frameworks
# and tools say a lot.
LANGUAGES = {
    "python", "javascript", "typescript", "java", "go", "rust", "ruby", "php", "c", "c++", "c#",
    "kotlin", "swift", "scala", "shell", "bash", "html", "css", "dart", "elixir", "lua",
}  # fmt: skip
NOISE = {"actions", "github-actions", "github", "docker", "make", "makefile", "yaml", "json"}
NOISE |= {"markdown", "shell", "bash", "html", "css", "dockerfile", "git"}
RELEVANT_MIN = C["recommended"]["relevant_min"]  # one framework or tool, or two languages
GENERIC_TERMS = set(C["recommended"]["generic_terms"])


def relevance(item: dict, terms: set[str]) -> int:
    """How well an item fits the project: 2 per framework or tool it names, 1 per language."""
    text = f"{item['name']} {item['description']} {' '.join(item['topics'])}".lower()
    return sum(
        1 if t in LANGUAGES else 2
        for t in terms
        if re.search(rf"(?<![\w-]){re.escape(t).replace('\\-', '[- ]')}(?![\w-])", text)
    )


def goal_terms(use_case: str | None) -> set[str]:
    """The goal's own words, for Recommended: less the words that say nothing about the work."""
    from proving_ground.skill_match import STOP as WORDS_THAT_SAY_NOTHING

    stop = set(C["goal_stop"]) | GENERIC_TERMS | STOP | WORDS_THAT_SAY_NOTHING
    return {w for w in re.findall(r"[a-z][a-z0-9-]{2,}", (use_case or "").lower()) if w not in stop}


def goal_hits(item: dict, goal: set[str]) -> int:
    """How strongly an item says the goal's words, in any form (bug in bugfix, bugs in bug):
    2 for each in its name, 1 for each only in its description or topics."""
    name = _tokens(item["name"])
    rest = _tokens(f"{item.get('description') or ''} {' '.join(item.get('topics', []))}")

    def says(g: str, words: list[str]) -> bool:
        return any(word_match(g, w) >= S["prefix"] for w in words)

    return sum(2 if says(g, name) else 1 if says(g, rest) else 0 for g in goal)


def rank(
    items: list[dict], view: str, terms: set[str] | None = None, goal: set[str] | None = None
) -> list[dict]:
    """Sorted for a view. Recommended with a goal: items saying the goal's words first."""
    terms = terms or set()
    scored = [
        i | {"relevance": relevance(i, terms), "goal": goal_hits(i, goal) if goal else 0}
        for i in items
    ]
    if view == "stars":
        return sorted(scored, key=lambda i: -i["stars"])
    if view == "latest":
        return sorted(scored, key=lambda i: i["pushed_at"], reverse=True)
    if view == "relevant":
        return sorted(
            (i for i in scored if i["relevance"] >= RELEVANT_MIN),
            key=lambda i: (-i["relevance"], -i["stars"]),
        )

    # Recommended: widely used and still maintained; relevance breaks ties.
    rec = C["recommended"]

    def score(i: dict) -> float:
        fresh = 1.0 if i["pushed_at"] >= rec["fresh_since"] else rec["stale_weight"]
        return (i["stars"] ** 0.5) * fresh + rec["relevance_weight"] * i["relevance"]

    if goal:
        # The goal's words first (most matched first), then what fits the stack, then the rest.
        return sorted(
            scored,
            key=lambda i: (i["goal"], i["relevance"] >= RELEVANT_MIN, score(i)),
            reverse=True,
        )
    if terms and rec["relevant_first"]:
        # Items that fit the project come first, then the rest; each part by score.
        return sorted(
            scored, key=lambda i: (i["relevance"] >= RELEVANT_MIN, score(i)), reverse=True
        )
    return sorted(scored, key=score, reverse=True)


# ---------- Search ----------

S = C["search"]
_THEME_RX = [(label, re.compile(pattern)) for label, pattern in THEMES]
_THEME_WORDS = {
    label: [w for w in re.findall(r"[a-z0-9]+", label.lower()) if w != "and"] for label, _ in THEMES
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _one_typo(a: str, b: str) -> bool:
    """At most one letter wrong, missing, extra or two swapped."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (
            len(diff) == 2
            and diff[1] == diff[0] + 1
            and a[diff[0]] == b[diff[1]]
            and a[diff[1]] == b[diff[0]]
        )
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1 :] == short for i in range(len(long_)))


TAILS = set(C["compound_tails"])


def word_stem(w: str) -> str:
    """A word without its plural or verb ending: bugs, bug; reviewing, review; fixes, fix."""
    for suf in ("ings", "ing", "ies", "es", "ed", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3 and not w.endswith(("ss", "us", "is")):
            w = w[: -len(suf)] + ("y" if suf == "ies" else "")
            break
    if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "aeiouls":
        w = w[:-1]  # "debugging" -> "debugg" -> "debug"
    return w


def word_match(q: str, w: str, min_prefix: int | None = None) -> float:
    """How well one query word matches one word: 1 exact, a stem, a prefix (or the query word
    with a compound tail: bug in bugfix), or fuzzy weight, else 0."""
    if q == w:
        return 1.0
    if len(q) >= 3 and len(w) >= 3 and word_stem(q) == word_stem(w):
        return S["stem"]
    if len(q) >= 3 and w.startswith(q) and w[len(q) :] in TAILS:
        return S["stem"]  # the word itself with a tail ("bug" in "bugfix"): as good as a form
    if len(q) >= (min_prefix or S["min_prefix"]) and w.startswith(q):
        return S["prefix"]
    if len(q) >= S["min_fuzzy"] and len(w) >= S["min_fuzzy"] - 1 and q[0] == w[0]:
        # The whole word, or its start with one letter more or less (a typo in a prefix).
        if any(_one_typo(q, w[:n]) for n in {len(w), len(q), len(q) + 1} if n <= len(w)):
            return S["fuzzy"]
    return 0.0


def _best(q: str, words: list[str], min_prefix: int | None = None) -> float:
    return max((word_match(q, w, min_prefix) for w in words), default=0.0)


def _fields(item: dict) -> dict:
    name = item.get("name", "")
    desc = item.get("description") or ""
    topics = " ".join(item.get("topics", []))
    text = f"{name} {desc} {topics}".lower()
    return {
        "name": _tokens(name),
        "description": _tokens(desc),
        "topics": _tokens(topics),
        "themes": {label for label, rx in _THEME_RX if rx.search(text)},
        "topic_list": list(item.get("topics", [])),
        "exact": " ".join(_tokens(name)),
        "text": f" {' '.join(_tokens(name))} {' '.join(_tokens(desc))} ",
    }


def search(items: list[dict], q: str) -> list[dict]:
    """The items matching a query, best first; ties keep the order they came in (the sort).
    A weak match (a copy marked `weak`) comes after every strong one: shown folded away.

    Rules: the curate-catalog skill's `search`.
    """
    words = _tokens(q)
    if not words:
        return list(items)
    fields = [_fields(i) for i in items]
    # Which themes each query word names ("review" names Code review).
    named = {w: {t for t, tw in _THEME_WORDS.items() if _best(w, tw) > 0} for w in words}
    per: list[list[float]] = []
    said: list[list[float]] = []  # each word in the name or description only
    for f in fields:
        row, own = [], []
        for w in words:
            nm = S["name"] * _best(w, f["name"], S["min_name_prefix"])
            ds = S["description"] * _best(w, f["description"])
            row.append(
                max(
                    nm,
                    S["theme"] if named[w] & f["themes"] else 0.0,
                    S["topics"] * _best(w, f["topics"]),
                    ds,
                )
            )
            own.append(max(nm, ds))
        per.append(row)
        said.append(own)
    # A word most items match ("code" in "Claude Code") only adds score; the rest must all match.
    n = len(items)
    hits = [sum(1 for row in per if row[k] > 0) for k in range(len(words))]
    common = [n >= S["common_min_items"] and h > S["common_share"] * n for h in hits]
    required = [k for k in range(len(words)) if not common[k]] or list(range(len(words)))
    phrase = " ".join(words)
    out = []
    for idx, (item, f, row, own) in enumerate(zip(items, fields, per, said, strict=True)):
        if not all(row[k] > 0 for k in required):
            continue
        score = sum(v * (S["common_weight"] if common[k] else 1) for k, v in enumerate(row))
        exact = f["exact"] == phrase
        in_text = len(words) > 1 and f" {phrase} " in f["text"]
        score += S["exact_name"] if exact else 0
        score += S["phrase"] if in_text else 0
        tier = _tier(words, f, row, exact, in_text)
        strong = _strong(words, required, own, tier)
        out.append((0 if strong else 1, -tier, -score, idx, item))
    return [
        t[-1] if t[0] == 0 else {**t[-1], "weak": True} for t in sorted(out, key=lambda t: t[:4])
    ]


def _tier(words: list[str], f: dict, row: list[float], exact: bool, said: bool) -> int:
    """Phrase and AND before OR: the exact name, the query as a phrase in the name or
    description, every word in the name, the query as one topic ("code-review"), every word
    anywhere, then the rest (only the rare words matched)."""
    if exact:
        return 5
    if said:
        return 4
    if all(_best(w, f["name"], S["min_name_prefix"]) > 0 for w in words):
        return 3
    if len(words) > 1 and " ".join(words) in {" ".join(_tokens(t)) for t in f["topic_list"]}:
        return 2
    return 1 if all(v > 0 for v in row) else 0


def _strong(words: list[str], required: list[int], own: list[float], tier: int) -> bool:
    """A match worth showing first (curate-catalog: search, strong): several words said as a
    phrase (in the name, the description or as one topic) or all in the name; one word said in
    the name or description well enough (`strong_min`). A match only by a topic tag or a theme
    ("review" names the Code review theme) is weak."""
    if len(words) > 1:
        return tier >= 2
    return all(own[k] >= S["strong_min"] for k in required)


def kinds() -> list[dict]:
    """The Library's kinds, in order, each with a line saying what it is and why you'd add one."""
    return [{"id": k, "label": v["label"], "blurb": v["blurb"]} for k, v in C["categories"].items()]


def page(
    items: list[dict],
    category: str,
    view: str,
    q: str,
    terms: set[str],
    goal: set[str] | None = None,
) -> dict:
    """What the Library shows: one kind (or "all" kinds, for search), ranked and searched, with the
    count of every kind and how many of each match the search."""
    counts = {c: 0 for c in C["categories"]}
    for i in items:
        if i["category"] in counts:
            counts[i["category"]] += 1
    pool = items if category == "all" else [i for i in items if i["category"] == category]
    ranked = rank(pool, view, terms, goal)
    if q.strip():
        ranked = search(ranked, q)
    matches = {c: 0 for c in C["categories"]}
    weak = {c: 0 for c in C["categories"]}  # of the matches, how many are weak (folded away)
    for i in ranked:
        matches[i["category"]] = matches.get(i["category"], 0) + 1
        if i.get("weak"):
            weak[i["category"]] = weak.get(i["category"], 0) + 1
    shown = ranked[:MAX_ITEMS_SHOWN]
    if category == "all":
        # Every kind keeps its best few even when one kind has most of the matches.
        per_kind: dict[str, int] = {}
        shown = []
        for i in ranked:
            k = per_kind.get(i["category"], 0)
            if k < C["search_per_kind"]:
                shown.append(i)
                per_kind[i["category"]] = k + 1
    themes: dict[str, int] = {}
    for i in shown:
        themes[i["theme"]] = themes.get(i["theme"], 0) + 1
    return {
        "items": shown,
        "themes": themes,
        "counts": counts,
        "matches": matches,
        "weak": weak,
        "kinds": kinds(),
    }


STOP = {"with", "from", "that", "this", "your", "have", "into", "about", "using", "only", "when"}


def project_terms(stack: list[str], languages: dict[str, int], use_case: str | None) -> set[str]:
    words = {s.lower().replace(".js", "").replace(" ", "-") for s in stack}
    words |= {lang.lower() for lang in languages}
    for w in re.findall(r"[a-z][a-z0-9-]{3,}", (use_case or "").lower()):
        if w not in STOP:
            words.add(w)
    return {w for w in words if len(w) >= 2 and w not in NOISE and w not in GENERIC_TERMS}


def _safe(path: str) -> PurePosixPath:
    p = PurePosixPath(path)
    if not path or p.is_absolute() or ".." in p.parts:
        raise ValueError(f"unusable path {path!r}")
    return p


def _tree(gh: GitHub, name: str) -> list[dict]:
    branch = gh.get(f"repos/{name}").get("default_branch", "main")
    return [
        t
        for t in gh.get(f"repos/{name}/git/trees/{branch}?recursive=1").get("tree", [])
        if t["type"] == "blob"
    ]


def _text(gh: GitHub, name: str, path: str) -> str:
    data = gh.get(f"repos/{name}/contents/{urllib.parse.quote(path)}")
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


def _frontmatter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def list_skills(gh: GitHub, name: str, limit: int = 40) -> list[dict]:
    """Every folder holding a SKILL.md in a repository, with its name and description."""
    paths = sorted(t["path"] for t in _tree(gh, name) if t["path"].endswith("SKILL.md"))[:limit]
    out = []
    for p in paths:
        folder = str(PurePosixPath(p).parent)
        fm = _frontmatter(_text(gh, name, p))
        out.append(
            {
                "path": folder if folder != "." else "",
                "name": str(fm.get("name") or PurePosixPath(folder).name or name.split("/")[1]),
                "description": str(fm.get("description") or "")[:300],
            }
        )
    return out


def installed_path(library: Path, name: str, folder: str) -> Path:
    """Where install_skill puts a repository's skill folder."""
    skill = PurePosixPath(folder).name or name.split("/")[1]
    return library / f"{name.replace('/', '__')}__{skill}"


def repo_parts(gh: GitHub, name: str) -> dict:
    """A harness or workflow repository as its parts and the links its own text shows.

    {"parts": [{id, kind, label, name, path, description, url}], "links": [{from, to}],
    "more": n}. Rules: the curate-catalog skill's `parts`.
    """
    rules = C["parts"]
    kinds = list(rules["kinds"].items())
    skip = re.compile(rules["skip"])
    branch = gh.get(f"repos/{name}").get("default_branch", "main")
    found: list[dict] = []
    for t in _tree(gh, name):
        path = t["path"]
        if skip.search(path):
            continue
        kind = next((k for k, v in kinds if re.search(v["match"], path)), None)
        if kind is None:
            continue
        pp = PurePosixPath(path)
        # A skill is its folder; everything else is its file.
        part = pp.parent.name if kind == "skill" else pp.stem
        found.append({"kind": kind, "name": part or name.split("/")[1], "path": path})
    order = {k: i for i, (k, _) in enumerate(kinds)}
    found.sort(key=lambda x: (order[x["kind"]], x["path"]))
    shown, more = found[: rules["max_parts"]], max(0, len(found) - rules["max_parts"])

    texts: dict[str, str] = {}
    for part in shown[: rules["max_read"]]:
        try:
            texts[part["path"]] = _text(gh, name, part["path"])
        except Exception:  # noqa: BLE001 - a part without its text still shows, undescribed
            continue
    parts = []
    for part in shown:
        fm = _frontmatter(texts.get(part["path"], ""))
        parts.append(
            part
            | {
                "id": f"{part['kind']}:{part['path']}",
                "label": rules["kinds"][part["kind"]]["label"],
                "name": str(fm.get("name") or part["name"]),
                "description": str(fm.get("description") or "")[:300],
                "url": f"https://github.com/{name}/blob/{branch}/{part['path']}",
            }
        )

    # A part uses another when its text names it as a whole word (names of 4+ characters only).
    links = []
    for a in parts:
        text = texts.get(a["path"], "").lower()
        if not text:
            continue
        for b in parts:
            n = b["name"].lower()
            if b is a or len(n) < 4 or b["kind"] == "instructions":
                continue
            if re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text):
                links.append({"from": a["id"], "to": b["id"]})
    return {"parts": parts, "links": links, "more": more}


def install_skill(gh: GitHub, name: str, folder: str, library: Path) -> Path:
    """Download one skill folder into the library and return its path."""
    if folder:
        _safe(folder)
    prefix = f"{folder}/" if folder else ""
    files = [t for t in _tree(gh, name) if t["path"].startswith(prefix)]
    if not any(t["path"] == f"{prefix}SKILL.md" for t in files):
        raise ValueError(f"{name} has no SKILL.md in {folder or 'its root'}")
    if len(files) > MAX_SKILL_FILES or sum(t.get("size", 0) for t in files) > MAX_SKILL_BYTES:
        raise ValueError("That skill folder is too large to install (over 200 files or 2 MB).")
    dest = installed_path(library, name, folder)
    tmp = dest.with_name(dest.name + ".part")
    if tmp.exists():
        import shutil

        shutil.rmtree(tmp)
    for t in files:
        rel = _safe(t["path"][len(prefix) :])
        out = tmp / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_text(gh, name, t["path"]))
    (tmp / ".source.json").write_text(json.dumps({"repo": name, "path": folder}))
    if dest.exists():
        import shutil

        shutil.rmtree(dest)
    tmp.rename(dest)
    return dest


REPO_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def readme(gh: GitHub, name: str, limit: int = 4000) -> str:
    """A repository's README as readable text: no images, badges or HTML. Empty if it has none."""
    if not REPO_NAME.match(name):
        raise ValueError(f"not a repository name: {name!r}")
    try:
        data = gh.get(f"repos/{name}/readme")
        text = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - a missing README is not an error for the caller
        return ""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)  # images and badges
    text = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)", "", text)
    text = re.sub(r"<[^>]+>", "", text)  # html
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links: keep the words
    lines = [ln.rstrip() for ln in text.splitlines()]
    text = re.sub(
        r"\n{3,}", "\n\n", "\n".join(ln for ln in lines if ln.strip() not in {"---", "***"})
    )
    text = text.strip()
    return text[:limit].rsplit("\n", 1)[0] + "\n…" if len(text) > limit else text
