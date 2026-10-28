---
name: goal-rules
description: Find the rules in a goal (refund windows, limits, who must approve) so they reach the agent - the goal kept as a workflow's "Goal & rules" brief, its rule lines given to the first step and written into BUILD.md. Deterministic, no model.
values:
  # A goal is cut into lines at these: new lines, semicolons, a colon and a space, bullets,
  # and the end of a sentence (. ! ? followed by a space). A full stop inside a number ($1.50)
  # or a time (10:30) never cuts.
  split: '\n+|;\s*|:\s+|(?<=[.!?])\s+(?=[A-Z0-9$€£"(])|\s+•\s+'
  # A line is a rule when it has a number (30 days, $200, 60) or one of these words: what a
  # policy says, not what the work is about. Whole words, any case.
  rule_words: [must, never, only, always, not allowed, no more than, at most, at least, up to, limit, limits, within, exceed, exceeds, more than, less than, required, requires, needs, approve, approval, approved, sign-off, manager, escalate, cannot, can't, don't, do not, forbidden, mandatory, unless, except, nothing, "no"]
  # Bullet marks and leading words taken off a rule line before it is shown.
  strip: '^\s*(?:[-*•]|\d+[.)])\s*'
  max_rules: 12
  max_chars: 240
  # The words around the rules, in the workflow's compiled skill and in BUILD.md.
  heading: Goal & rules
  first_step: "Follow these rules:"
  later_steps: "Keep to the Goal & rules."
  brief_rules: Rules to follow
---

# Goal rules

A goal written in plain words often carries the policy the agent must keep: "refund within
30 days → full refund; 30–60 days → store credit; nothing after 60; anything over $200 needs a
manager". If only the amount reaches the workflow's steps, the agent never sees the windows or
the store credit, and a run measures an agent that was never told the policy.

## Rules

- The goal is kept whole as the workflow's brief (`brief`, shown in the Lab as "Goal & rules",
  editable there). A workflow built from a goal gets it: the Garage design's workflow, a pattern
  set up for a use case, and a starter opened while step 1 has a goal.
- Its rule lines are found here, not by a model: the goal is cut at `split` (new lines,
  semicolons, a colon, bullets, sentence ends); a line is a rule when it has a digit or one of
  `rule_words`. Each is trimmed of bullet marks, kept in the goal's order, at most `max_rules`,
  each at most `max_chars`. The same goal always gives the same rules.
- The compiled skill (what real runs and Try it use) starts with a "Goal & rules" section: the
  goal and its rules. The first step's brief says "Follow these rules:" with every rule; every
  later step's brief says "Keep to the Goal & rules.", so the orchestrator passes them on.
- BUILD.md's Goal section, for a repo and for a new project, holds the whole goal and a
  "Rules to follow" list of the same lines. With no goal, the brief says how to add one.
- Nothing is invented: a rule is a line of the goal as written, never reworded.
