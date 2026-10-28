// GET /api/rig-score as the engine returned it (fake server, this branch): the explainer's data and
// the worked example scored by the real rig_score(). Regenerate with: curl -s 127.0.0.1:<port>/api/rig-score
import type { RigExplain } from "../lib/types";

export const RIG_EXPLAIN = {
    "intro": "One number from 0 to 100 that says whether a skill or workflow works, measured with and without it on the same tasks. It is built only from what was measured; nothing is guessed.",
    "parts": [
        {
            "id": "lift",
            "name": "Lift",
            "weight": 0.4,
            "measures": "How much the pass rate goes up with the change. It takes the lower bound of the 95% interval, not the middle, so a lucky small run can't score well.",
            "scale": "0 at a lower bound of 0 pts or below, 100 at +25 pts or above, a straight line between.",
            "needs_lift": false
        },
        {
            "id": "cost",
            "name": "Cost",
            "weight": 0.2,
            "measures": "What one task costs with the change, divided by what it costs without: per solved task when both arms solved some, else per finished task.",
            "scale": "100 at 1.2\u00d7 or less, 0 at 5.0\u00d7 or more, linear in the logarithm between. A local model costs nothing: 100.",
            "needs_lift": true
        },
        {
            "id": "followed",
            "name": "Followed",
            "weight": 0.15,
            "measures": "Whether the agent did what the change says, read from the session logs of the \"with\" trials.",
            "scale": "A workflow: 50% from the share of steps run, the rest from the share run on the step's model. A skill: the share of trials that opened it.",
            "needs_lift": false
        },
        {
            "id": "holds_up",
            "name": "Holds Up",
            "weight": 0.15,
            "measures": "Whether the gain holds on held-out tasks, ones the change was never shaped on.",
            "scale": "Generalises: 100. Overfit: 0. Unclear, or no held-out tasks: not measured.",
            "needs_lift": false
        },
        {
            "id": "reliable",
            "name": "Reliable",
            "weight": 0.1,
            "measures": "The share of trials that ran cleanly: not errored, broken, timed out or cut off by the budget cap.",
            "scale": "The clean share, 0 to 100. On a judged bench whose judge isn't calibrated, it keeps 50% of that.",
            "needs_lift": true
        }
    ],
    "missing": "A part that can't be measured is left out, and the others are scaled up to fill its share.",
    "no_credit": "Until a lift is shown (the interval's lower bound above 0), Cost and Reliable count at 0: cheap and clean at doing nothing is worth nothing.",
    "gates": [
        {
            "id": "hurts",
            "cap": 20,
            "text": "It makes results worse."
        },
        {
            "id": "not_shown",
            "cap": 49,
            "text": "Not shown to help: the interval reaches 0."
        },
        {
            "id": "provisional",
            "cap": 59,
            "text": "Fewer than 10 pairs: provisional, shown greyed with the pair count."
        },
        {
            "id": "ceiling_worse",
            "cap": 20,
            "text": "Both always pass, and it costs more or takes longer for the same result."
        }
    ],
    "min_pairs": 10,
    "bands": [
        {
            "id": "works",
            "tone": "positive",
            "label": "Works \u2014 use it",
            "min": 80,
            "when": "80 or more, with a lift shown."
        },
        {
            "id": "works_but",
            "tone": "neutral",
            "label": "Works, but \u2026 needs work",
            "min": 60,
            "when": "60 to 79, with a lift shown; names the part that costs the most points."
        },
        {
            "id": "not_proven",
            "tone": "warning",
            "label": "Not Proven \u2014 \u2026",
            "min": null,
            "when": "The interval reaches 0 but the lift could still matter, or only the pair count holds it back; says what would settle it."
        },
        {
            "id": "helps_but",
            "tone": "warning",
            "label": "Helps, but \u2026",
            "min": null,
            "when": "A lift is shown, but the score is under 60; names the biggest drag."
        },
        {
            "id": "doesnt",
            "tone": "negative",
            "label": "Doesn't Work \u2014 \u2026",
            "min": null,
            "when": "It makes results worse, or even the interval's upper bound is under +5 pts."
        }
    ],
    "verdict": [
        {
            "id": "helps",
            "word": "Helps",
            "tone": "positive"
        },
        {
            "id": "doesnt",
            "word": "Doesn't Help",
            "tone": "negative"
        },
        {
            "id": "cant",
            "word": "Can't Tell Yet",
            "tone": "neutral"
        }
    ],
    "example": {
        "title": "A five-step workflow, measured on 16 pairs",
        "note": "This bench has no held-out tasks, so Holds Up isn't measured and the other four parts share its 15%.",
        "evidence": {
            "kind": "workflow",
            "n_pairs": 16,
            "diff": 0.31,
            "ci_low": 0.12,
            "ci_high": 0.5,
            "verdict": "helps",
            "pass_with": 0.8125,
            "pass_without": 0.5,
            "costs": {
                "with": {
                    "spent_usd": 4.2,
                    "solved": 13,
                    "tasks": 16
                },
                "without": {
                    "spent_usd": 1.6,
                    "solved": 8,
                    "tasks": 16
                }
            },
            "local": false,
            "adherence": {
                "read": 15,
                "steps_run": 0.9,
                "models_ok": 0.8,
                "steps": 5
            },
            "holds_up": null,
            "ledger": {
                "total": 32,
                "with": 16,
                "without": 16,
                "pairs": 16,
                "logs_read": 15,
                "clean": 30,
                "timed_out": 1,
                "errored": 1,
                "broken": 0
            },
            "judge": null
        },
        "result": {
            "score": 67,
            "band": "works_but",
            "tone": "neutral",
            "label": "Works, but the lift needs work",
            "reason": "Lift could be as small as +12 pts",
            "provisional": false,
            "pairs": 16,
            "parts": [
                {
                    "id": "lift",
                    "name": "Lift",
                    "weight": 0.4,
                    "score": 48.0,
                    "detail": "lower bound +12 pts (target +25)",
                    "counted": true,
                    "weight_used": 0.4706
                },
                {
                    "id": "cost",
                    "name": "Cost",
                    "weight": 0.2,
                    "score": 79.2,
                    "detail": "1.6\u00d7 the plain agent's cost per solved task",
                    "counted": true,
                    "weight_used": 0.2353
                },
                {
                    "id": "followed",
                    "name": "Followed",
                    "weight": 0.15,
                    "score": 85.0,
                    "detail": "on average 4 of 5 steps run, 4 on the right model, in the 15 \"with\" trials whose logs could be read",
                    "counted": true,
                    "weight_used": 0.1765
                },
                {
                    "id": "holds_up",
                    "name": "Holds Up",
                    "weight": 0.15,
                    "score": null,
                    "detail": "This bench has no held-out tasks, so it's unknown whether this holds on unseen tasks",
                    "counted": false,
                    "weight_used": 0.0
                },
                {
                    "id": "reliable",
                    "name": "Reliable",
                    "weight": 0.1,
                    "score": 93.8,
                    "detail": "30 of 32 trials ran cleanly (16 with, 16 without)",
                    "counted": true,
                    "weight_used": 0.1176
                }
            ],
            "gates": [],
            "formula": {
                "text": "40% \u00d7 48 + 20% \u00d7 79.2 + 15% \u00d7 85 + 10% \u00d7 93.8 = 57.2; \u00f7 85% (weights rescaled to the measured parts; holds up not measured) = 67.2; rounded: 67",
                "measured_weight": 0.85,
                "raw": 67.25,
                "not_measured": [
                    "holds up"
                ]
            },
            "ledger": {
                "total": 32,
                "with": 16,
                "without": 16,
                "pairs": 16,
                "logs_read": 15,
                "clean": 30,
                "timed_out": 1,
                "errored": 1,
                "broken": 0
            },
            "ledger_text": "32 trials (16 with, 16 without) \u00b7 16 complete pairs \u00b7 30 ran cleanly, 1 timed out, 1 errored, 0 broken \u00b7 logs read for 15 of the 16 \"with\" trials",
            "verdict": {
                "id": "helps",
                "word": "Helps",
                "tone": "positive",
                "reason": "13 of 16 passed with vs 8 of 16 passed without (+31 pts, 95% interval +12 to +50).",
                "next": "Next: use it, and measure again when the model or the tasks change.",
                "facts": [
                    "Quality: 13 of 16 passed with, 8 of 16 passed without (+31 pts, 95% interval +12 to +50)"
                ]
            },
            "quality": "pass_rate"
        }
    }
} as unknown as RigExplain;
