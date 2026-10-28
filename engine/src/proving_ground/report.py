"""Plain-text experiment reports for the CLI."""

from __future__ import annotations

from proving_ground import priors, skills
from proving_ground import rig_score as rig_mod
from proving_ground.stats import ArmPairStats, ResultSummary, summarize

# The arms by name: "With" and "Without", or a code change's "After" and "Before".
WITH = ("With", "Without")
_ARMS = skills.value("measurability", "before_after")["arms"]
BEFORE_AFTER = (_ARMS["with"], _ARMS["without"])


def arm_names(kind: str | None) -> tuple[str, str]:
    """The arms' names for a run of this treatment kind."""
    return BEFORE_AFTER if kind == "before_after" else WITH


def _pts(x: float) -> str:
    return f"{x * 100:+.1f} pts"


def _line(label: str, s: ArmPairStats, arms: tuple[str, str] = WITH) -> str:
    w, wo = (a.lower() for a in arms)
    return (
        f"{label}: {s.n_pairs} pairs, {w} {s.pass_with:.0%} vs {wo} {s.pass_without:.0%}, "
        f"{_pts(s.diff)} ({_pts(s.ci_low)} to {_pts(s.ci_high)})"
    )


def format_summary(s: ResultSummary, arms: tuple[str, str] = WITH) -> str:
    lines = [f"Verdict: {s.verdict.value.upper()}"]
    h = s.headline
    if h is None:
        lines.append("No complete real pairs yet.")
    else:
        lines.append(
            f"{arms[0]}: {h.pass_with:.1%}   {arms[1]}: {h.pass_without:.1%}   Pairs: {h.n_pairs}"
        )
        lines.append(f"Difference: {_pts(h.diff)} (95% CI {_pts(h.ci_low)} to {_pts(h.ci_high)})")
        lines.append(f"Smallest detectable difference at this size: about {s.mde * 100:.0f} pts")
        if s.required_pairs:
            lines.append(f"About {s.required_pairs} pairs would detect a difference this size.")
    for kind, st in s.by_kind.items():
        lines.append(_line(f"  {kind}", st, arms))
    if s.synthetic is not None:
        lines.append(_line("Synthetic (imaginary tasks, not in the verdict)", s.synthetic, arms))
    if s.broken:
        lines.append(f"Broken: {s.broken} trials (setup failed)")
    if s.unreliable:
        lines.append(f"Unreliable: {s.errored} of {s.total} trials errored (over 10%).")
    w, wo = (a.lower() for a in arms)
    lines.append(f"Cost: ${s.cost_with:.2f} {w}, ${s.cost_without:.2f} {wo}")
    return "\n".join(lines)


def metric_rig(trials: list, metric: str, cost_of, kind: str, local: bool = False) -> dict | None:
    """The Rig score of a run scored on tokens, cost or time (rig-score: Metric), as Results
    has it: its `metric` summary (headline, guard) and its `verdict` on the metric. None for the
    pass rate."""
    if metric == rig_mod.M["default"]:
        return None
    s = summarize(trials)
    h = s.headline
    row = {
        "n_pairs": h.n_pairs if h else 0,
        "diff": h.diff if h else None,
        "ci_low": h.ci_low if h else None,
        "ci_high": h.ci_high if h else None,
        "verdict": s.verdict.value,
        "pass_with": h.pass_with if h else None,
        "pass_without": h.pass_without if h else None,
        "arms": rig_mod.arms(trials, cost_of),
        "costs": priors.cost_per_solved(trials, cost_of),
        "ledger": rig_mod.ledger(trials),
        "local": local,
        "metric": rig_mod.metric_evidence(trials, metric, cost_of),
    }
    return rig_mod.rig_score(rig_mod.evidence_from_row(row, kind))


def format_metric(trials: list, metric: str, cost_of, kind: str, local: bool = False) -> str:
    """A run scored on tokens, cost or time, as Results says it: the metric's headline, the pass
    rate as its guard, and the verdict on the metric (rig-score: Metric). "" for the pass rate."""
    rig = metric_rig(trials, metric, cost_of, kind, local)
    if rig is None:
        return ""
    m, v = rig.get("metric") or {}, rig["verdict"]
    lines = [f"Scored on {rig_mod.M['names'][metric].lower()}:"]
    if m.get("headline"):
        lines.append(m["headline"])
    if m.get("guard"):
        lines.append(m["guard"])
    lines.append(f"Verdict on {rig_mod.M['nouns'][metric]}: {v['word']}. {v['reason']}".rstrip())
    return "\n".join(lines)


def format_event(e: dict, arms: tuple[str, str] = WITH) -> str:
    """One line of live progress for `pg run`."""
    kind = e.get("type")
    if kind == "trial":
        arm = {"with": arms[0], "without": arms[1]}.get(e["arm"], e["arm"]).lower()
        return (
            f"{e['scenario_id']}  {arm:<7}  #{e['repeat']}  {e['outcome']:<7}  "
            f"${e['spent_usd']:.2f} spent"
        )
    if kind == "broken":
        first = (e.get("log") or "").strip().splitlines()[:1]
        return f"{e['scenario_id']}: setup failed, skipped. {first[0] if first else ''}".rstrip()
    if kind == "stopped_budget":
        why = f" ({e['reason']})" if e.get("reason") else ""
        return (
            f"Stopped at budget: ${e['spent_usd']:.2f} spent{why}. "
            "Re-run with --resume to continue."
        )
    if kind == "done":
        return f"Done: ${e['spent_usd']:.2f} spent."
    # Auto-extend (`--auto`), worded as the app's live run.
    if kind == "extended":
        waiting = f"waiting on {e['waiting']}; " if e.get("waiting") else ""
        return f"Not decided yet at {e['pairs']} pairs: {waiting}added a batch ({e['look']} so far)."
    if kind == "settled":
        return f"Stopped adding pairs at {e['pairs']}: {e['reason']}."
    if kind == "reused":
        return f"Reused {e['trials']} baseline trials from earlier runs: ${e['saved_usd']:.2f} not spent again."
    return str(e)
