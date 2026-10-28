"""PROVEN.md: what a workflow's measured Lab runs say, kept in its own folder.

The folder gets a short table, a `proven_results:` YAML block (one entry per finished run) and a
compact `proven:` line in SKILL.md's frontmatter, so the claim travels with the skill.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

FILE = "PROVEN.md"
RANK = {"helps": 2, "inconclusive": 1, "hurts": 0}
_FRONT = re.compile(r"\A---\n(.*?)\n---(?=\n|\Z)", re.S)


def entry(row: dict) -> dict | None:
    """One measured run as a PROVEN.md entry; None for a run that is not finished, has no pairs,
    or isn't evidence (evidence-validity: invalid or uninformative)."""
    if (
        row.get("status") in ("running", "pending")
        or not row.get("n_pairs")
        or row.get("diff") is None
        or (row.get("validity") or {}).get("status", "valid") != "valid"
    ):
        return None
    ad = row.get("adherence") or {}
    rig = row.get("rig") or {}
    return {
        "experiment": row.get("id"),
        "bench": row.get("bench"),
        "bench_version": row.get("bench_version"),
        "agent": row.get("agent"),
        "model": row.get("model"),
        "verdict": row.get("verdict"),
        "diff": round(row["diff"], 4),
        "ci_low": None if row.get("ci_low") is None else round(row["ci_low"], 4),
        "ci_high": None if row.get("ci_high") is None else round(row["ci_high"], 4),
        "n_pairs": row["n_pairs"],
        "adherence": {"followed": ad.get("followed"), "read": ad.get("read")} if ad else None,
        "per_extra_solved_usd": (row.get("costs") or {}).get("per_extra_solved_usd"),
        "rig": {k: rig.get(k) for k in ("score", "band", "tone", "label", "provisional")}
        if rig.get("score") is not None
        else None,
        "date": row.get("date"),
    }


def best(entries: list[dict]) -> dict | None:
    """The compact claim: the best verdict, then the biggest difference."""
    if not entries:
        return None
    e = max(entries, key=lambda x: (RANK.get(x["verdict"], 0), x["diff"], x["n_pairs"]))
    claim = {
        "verdict": e["verdict"],
        "diff_pts": round(e["diff"] * 100, 1),
        "pairs": e["n_pairs"],
        "bench": e["bench"],
    }
    rig = e.get("rig")
    if rig:  # the same run's Rig score, for the badge
        claim |= {"rig": rig["score"], "rig_band": rig["band"], "rig_tone": rig.get("tone")}
        if rig.get("provisional"):
            claim["rig_provisional"] = True
    return claim


def _cell(v) -> str:
    return "" if v is None else str(v).replace("|", "/")


def rig_cell(rig: dict | None) -> str | None:
    if not rig:
        return None
    return f"{rig['score']} {rig['label']}" + (" (provisional)" if rig.get("provisional") else "")


def render(name: str, entries: list[dict]) -> str:
    lines = [
        f"# Proven results: {name}",
        "",
        "Measured with Rig: the same tasks with and without this workflow.",
        "",
        "| Bench | Agent | Model | Verdict | Difference | 95% interval | Pairs | Followed | $ per extra solved | Rig score | Date |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for e in entries:
        ad = e["adherence"]
        lines.append(
            "| "
            + " | ".join(
                _cell(x)
                for x in (
                    e["bench"],
                    e["agent"],
                    e["model"],
                    e["verdict"],
                    f"{e['diff'] * 100:+.1f} pts",
                    f"{e['ci_low'] * 100:+.1f} to {e['ci_high'] * 100:+.1f}"
                    if e["ci_low"] is not None and e["ci_high"] is not None
                    else None,
                    e["n_pairs"],
                    f"{ad['followed']}/{ad['read']}" if ad and ad.get("read") else None,
                    e["per_extra_solved_usd"],
                    rig_cell(e.get("rig")),
                    e["date"],
                )
            )
            + " |"
        )
    block = yaml.safe_dump(
        {"proven_results": entries}, sort_keys=False, width=100, allow_unicode=True
    ).rstrip()
    return "\n".join(lines) + f"\n\n```yaml\n{block}\n```\n"


def _set_frontmatter(skill_md: Path, claim: dict | None) -> None:
    """Put (or remove) the `proven:` line in the frontmatter; every other byte stays."""
    text = skill_md.read_text(encoding="utf-8")
    m = _FRONT.match(text)
    if not m:
        return
    kept: list[str] = []
    skipping = False
    for line in m.group(1).split("\n"):
        if line.startswith("proven:"):
            skipping = True
            continue
        if skipping and (line.startswith((" ", "\t")) or not line.strip()):
            continue
        skipping = False
        kept.append(line)
    if claim:
        flow = yaml.safe_dump(claim, default_flow_style=True, sort_keys=False, width=10**6).strip()
        kept.append(f"proven: {flow}")
    out = "---\n" + "\n".join(kept) + "\n---" + text[m.end() :]
    if out != text:
        skill_md.write_text(out, encoding="utf-8")


def refresh(folder: Path, name: str, rows: list[dict]) -> dict | None:
    """Rewrite PROVEN.md and the frontmatter line from measured rows. Returns the claim, or None
    (and clears both) when nothing finished has pairs."""
    entries = [e for e in map(entry, rows) if e]
    entries.sort(key=lambda e: e["experiment"] or 0)
    claim = best(entries)
    if not (folder / "SKILL.md").is_file():
        return claim
    if entries:
        (folder / FILE).write_text(render(name, entries), encoding="utf-8")
    elif (folder / FILE).is_file():
        (folder / FILE).unlink()
    _set_frontmatter(folder / "SKILL.md", claim)
    return claim


def read(folder: Path) -> dict | None:
    """The compact claim kept in a skill folder: the frontmatter's `proven:`, else PROVEN.md."""
    try:
        text = (folder / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        m = _FRONT.match(text)
        # Just our own line: a compiled workflow's description is not always valid YAML.
        line = next(
            (x for x in (m.group(1).split("\n") if m else []) if x.startswith("proven:")), ""
        )
        got = (yaml.safe_load(line) or {}).get("proven") if line else None
        if isinstance(got, dict) and got.get("verdict"):
            return got
        f = folder / FILE
        if f.is_file():
            block = re.search(r"```yaml\n(.*?)\n```", f.read_text(errors="replace"), re.S)
            data = yaml.safe_load(block.group(1)) if block else None
            return best((data or {}).get("proven_results") or [])
    except (OSError, yaml.YAMLError, AttributeError, KeyError, TypeError):
        return None
    return None
