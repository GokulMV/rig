"""Improve a workflow from the tasks it failed, and check the edit isn't just fitted to them.

Rules and values: the improve-from-failures skill. One model call per proposal; held-out tasks
are never shown to the model.
"""

from __future__ import annotations

import json
from pathlib import Path

from proving_ground import lab, skills
from proving_ground.generate.client import GenerationError, ModelClient
from proving_ground.generate.prompt import Prompt

V = skills.load("improve-from-failures").values
FIELDS = ("does", "name", "harness_add")
TOOL = {
    "name": "emit_improvement",
    "description": "Return a few small edits to the workflow, each with why, and a summary.",
    "input_schema": {
        "type": "object",
        "required": ["changes", "summary"],
        "properties": {
            "summary": {"type": "string"},
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["step_id", "field", "new", "why"],
                    "properties": {
                        "step_id": {"type": "string", "description": "empty for harness_add"},
                        "field": {"type": "string", "enum": list(FIELDS)},
                        "new": {"type": "string"},
                        "why": {"type": "string"},
                    },
                },
            },
        },
    },
}


def _last_text(trial: Path) -> str:
    """The agent's last message in its main session (Claude Code's jsonl logs)."""
    root = trial / "agent" / "sessions"
    files = sorted(root.rglob("*.jsonl"), key=lambda f: f.stat().st_mtime) if root.is_dir() else []
    for f in reversed(files):
        last = ""
        for line in f.read_text(errors="replace").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("type") != "assistant" or d.get("isSidechain"):
                continue
            content = (d.get("message") or {}).get("content")
            parts = [content] if isinstance(content, str) else content or []
            text = "".join(
                b.get("text", "") for b in parts if isinstance(b, dict) and b.get("type") == "text"
            ) or "".join(p for p in parts if isinstance(p, str))
            if text.strip():
                last = text.strip()
        if last:
            return last
    return ""


def evidence(trials: list, scenarios: list[dict]) -> list[dict]:
    """Failing "with" trials on visible tasks: the task, the checker's log tail, the agent's
    last words. Held-out tasks are excluded here, so nothing later can leak them."""
    visible = {s["id"]: s for s in scenarios if not s.get("held_out")}
    out, used = [], 0
    for t in trials:
        if t.arm != "with" or t.outcome != "fail" or t.scenario_id not in visible:
            continue
        trial = Path(t.transcript_uri) if t.transcript_uri else None
        log = ""
        if trial is not None and (trial / "verifier" / "check.log").is_file():
            log = (trial / "verifier" / "check.log").read_text(errors="replace")
        item = {
            "scenario": t.scenario_id,
            "instruction": str(visible[t.scenario_id].get("instruction", ""))[
                : V["instruction_chars"]
            ],
            "check_log": log.strip()[-V["log_chars"] :],
            "agent_last": (_last_text(trial) if trial is not None else "")[: V["text_chars"]],
        }
        size = sum(len(str(v)) for v in item.values())
        if len(out) >= V["max_trials"] or used + size > V["max_evidence_chars"]:
            break
        out.append(item)
        used += size
    return out


def propose(model: ModelClient, wf: lab.Workflow, items: list[dict]) -> dict:
    """{changes, summary, workflow}: valid edits only, applied to a copy of the workflow."""
    if not items:
        raise GenerationError("There are no failing visible trials to learn from.")
    harness = {k: v["name"] + ": " + v["does"] for k, v in lab.W["harness"].items()}
    text = (
        "<workflow>\n"
        + json.dumps(
            {
                "name": wf.name,
                "steps": [{"id": s.id, "name": s.name, "does": s.does} for s in wf.steps],
                "harness": wf.harness,
            },
            indent=1,
        )
        + "\n</workflow>\n<harness_rules>\n"
        + "\n".join(f"{k}: {v}" for k, v in harness.items())
        + "\n</harness_rules>\n"
        + "".join(
            f"<failure>\n<task>\n{e['instruction']}\n</task>\n<check_log>\n{e['check_log']}\n"
            f"</check_log>\n<agent_last_message>\n{e['agent_last']}\n</agent_last_message>\n"
            "</failure>\n"
            for e in items
        )
        + f"Return at most {V['max_changes']} edits with the emit_improvement tool."
    )
    call = model.call(
        Prompt(skills.section("improve-from-failures", "Prompt"), [{"type": "text", "text": text}]),
        TOOL,
        V["model"],
        V["max_tokens"],
    )
    raw = call.input if isinstance(call.input, dict) else {}
    steps = {s.id: s for s in wf.steps}
    cap = V["max_field_chars"]
    changes, harness_now = [], list(wf.harness)
    for c in raw.get("changes") if isinstance(raw.get("changes"), list) else []:
        if not isinstance(c, dict) or c.get("field") not in FIELDS:
            continue
        field, new = c["field"], str(c.get("new", "")).strip()[:cap]
        if not new:
            continue
        why = str(c.get("why", "")).strip()[:cap]
        if field == "harness_add":
            if (
                new not in lab.W["harness"]
                or new in harness_now
                or len(harness_now) >= lab.W["max_harness"]
            ):
                continue
            harness_now.append(new)
            changes.append({"step_id": "", "field": field, "old": "", "new": new, "why": why})
        else:
            step = steps.get(str(c.get("step_id")))
            old = getattr(step, field, None)
            if step is None or new == old:
                continue
            changes.append({"step_id": step.id, "field": field, "old": old, "new": new, "why": why})
        if len(changes) >= V["max_changes"]:
            break
    if not changes:
        raise GenerationError("The model proposed no usable change.")
    dump = wf.dump()
    for c in changes:
        if c["field"] == "harness_add":
            dump["harness"] = [*dump["harness"], c["new"]]
        else:
            next(s for s in dump["steps"] if s["id"] == c["step_id"])[c["field"]] = c["new"]
    dump["id"] = "i" + lab._wid(wf.id, changes)
    dump["origin"] = "custom"
    dump["name"] = wf.name if wf.name.endswith("(improved)") else f"{wf.name} (improved)"
    return {
        "changes": changes,
        "summary": str(raw.get("summary", "")).strip()[: 2 * cap],
        "workflow": lab.load_workflow(dump),
    }


def overfit(parent_row: dict, child_row: dict) -> dict:
    """Did the edit help beyond the tasks it was made from? Rows are lab results: `visible` and
    `held_out` each hold the with-minus-without change (a fraction) and its pair count."""

    def gain(key: str) -> float | None:
        a, b = parent_row.get(key) or {}, child_row.get(key) or {}
        if a.get("diff") is None or b.get("diff") is None:
            return None
        return round((b["diff"] - a["diff"]) * 100, 1)

    vis, held = gain("visible"), gain("held_out")
    if held is None:
        verdict = "unclear"
    elif vis is not None and vis >= V["overfit_visible_pts"] and held <= 0:
        verdict = "overfit"
    elif held > 0:
        verdict = "generalises"
    else:
        verdict = "unclear"
    return {"visible_gain_pts": vis, "held_out_gain_pts": held, "verdict": verdict}
