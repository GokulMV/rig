"""The placeholder scenario in "Add scenario", in the repo's own work (generate-scenarios)."""

from __future__ import annotations

import re

from proving_ground import skills


def scenario_example(meta: dict | None, use_case: str | None) -> dict:
    """{title, instruction, check, use_case}: the first `examples` entry the use case points at,
    else the one for the repo's main language, else the default. `use_case` is the placeholder
    for writing one (Generate scenarios), in the same work."""
    v = skills.load("generate-scenarios").values
    text = (use_case or "").lower()
    for ex in v["examples"].values():
        if any(re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", text) for w in ex["when"]):
            return {k: ex[k] for k in ("title", "instruction", "check", "use_case") if k in ex}
    langs = (meta or {}).get("languages") or {}
    for lang, _n in sorted(langs.items(), key=lambda kv: -kv[1]):
        if lang in v["languages"]:
            return dict(v["languages"][lang])
    return dict(v["default"])
