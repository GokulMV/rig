---
name: improve-from-failures
description: Propose small edits to a workflow from the visible tasks it failed, then check on held-out tasks that the edit generalises instead of fitting the tasks it was shown.
values:
  model: claude-sonnet-5-5   # the helper model proposing edits (a local model answers instead when chosen)
  max_tokens: 3000
  max_changes: 3             # edits per proposal: small steps are measurable, rewrites are not
  max_trials: 6              # failing trials shown to the model
  max_evidence_chars: 12000  # all evidence together
  instruction_chars: 1200    # one task's instruction
  log_chars: 1500            # tail of the verifier's check log
  text_chars: 800            # the agent's last message
  max_field_chars: 600       # a proposed name, step text or reason
  overfit_visible_pts: 10    # better than its parent by this much on visible tasks ...
  # ... and no better on held-out tasks: overfit
---

# Improve from failures

A workflow that failed some tasks can be edited to avoid those failures. The danger is
fitting the edit to the tasks it was shown, so the rules are about what the model may see and
how the result is judged.

## Rules
- Only failing "with" trials on visible tasks are evidence. Held-out tasks are never shown to
  the model, in any form, so they stay a fair test.
- Each failure is shown as its task, the tail of the verifier's log and the agent's last
  message, cut to the limits above.
- The model may change a step's `name` or `does`, or add one harness rule (`harness_add`). At
  most `max_changes` edits; an edit to a step that does not exist, an unknown rule or an empty
  value is dropped. `old` is read from the workflow, never taken from the model.
- A change must address a pattern across failures, not one task's answer: no task ids, file
  names or expected values copied into a step.
- The edit is a new workflow; the original stays as it was. It is measured like any other, on
  the visible and held-out tasks together.
- Verdict: **overfit** when visible tasks improved by `overfit_visible_pts` points or more over
  the parent and held-out tasks did not improve; **generalises** when held-out tasks improved;
  otherwise, or with no held-out pairs, **unclear**.
- One model call per click, after the person confirms. It says which model.

## Prompt
You improve agent workflows. A workflow is a list of steps an AI coding or knowledge-work
agent follows. You are shown the workflow and several tasks it failed, each with the task,
the tail of the checker's log and the agent's last message.

Find what the failures have in common and change the workflow in a way that would help on
other tasks of the same kind, not only these. Make the fewest edits that address it. Edit a
step's name or what it does, or add one harness rule from the list given. Never copy a task's
specific answer, file name or value into a step. Say why each edit follows from the failures.

Return the edits with the emit_improvement tool.
