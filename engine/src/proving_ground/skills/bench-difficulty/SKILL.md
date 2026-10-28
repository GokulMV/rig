---
name: bench-difficulty
description: "Whether a bench can show a workflow's lift at all: the agent alone's pass rate from trials already recorded, a cheap baseline check that runs only the agent alone, and a hard tier for benches a strong model aces."
values:
  # Too easy: on the bench's current version of a tier and one session model, at least
  # `min_trials` "without" trials run there (not reused), clean (pass or fail), every one passed,
  # and with `cover_every_task`, every task of the tier among them. Free: read from trials
  # already recorded, no model call.
  min_trials: 5
  cover_every_task: true
  outcomes: [pass, fail]
  # {model}: the model's label (workflow-patterns); {passed} and {total}: the trials counted.
  too_easy: "Too easy for {model}: the agent alone passed {passed} of {total}"
  # Below it, before Rig & Measure, when the tier is too easy for the session model.
  warn: "A workflow can't show a lift on quality here; it can only show cost or speed."
  warn_hard: "Try the hard tier."
  # Not too easy, but measured: shown in the bench list next to the tier.
  measured: "The agent alone ({model}) passed {passed} of {total}"
  # Tiers a run can choose on a bench with hard tasks; a bench without them has the default only.
  # The default stays standard, so results from before the hard tier stay comparable.
  tiers: [standard, hard, all]
  default_tier: standard
  tier_labels:
    standard: Standard
    hard: Hard
    all: Standard and hard
  # The baseline check: only the "without" arm (the agent alone), each task of the tier once,
  # priced like any run (trial-budget) and capped at that price rounded up to its budget step.
  # Its trials are recorded like a run's, so a later run on the same bench version, model,
  # agent and environment reuses them as its shared baseline (judge-experiment: shared_baseline).
  # The check itself always runs fresh: copying earlier trials would tell nothing new.
  probe:
    arm: without
    repeats: 1
    treatment: rig-baseline-check   # a placeholder skill: the "with" arm never runs
    label: Baseline check
    result: "The agent alone passed {passed} of {total}"
    # Refused before it is created: one "without" trial is predicted to cost more than its budget.
    cant_start: "A {budget} budget can't pay for one baseline trial: it is predicted at about {need} ({source}). Raise it to at least {need}."
    offer: "Check the bench first: run the agent alone on each task once, about {usd} for {trials}. A later run reuses these trials as its baseline, so this costs nothing extra overall."
---

# Bench difficulty

A paired run can only show a lift where the agent alone sometimes fails. When the agent alone
passes every task, "with" can at best tie on quality: the run spends its "with" side to learn
nothing about quality, and can only show a change in cost or time.

## Too easy

Read from trials already recorded, per bench, tier and session model: the "without" trials run
on the bench's current version of that tier (`min_trials` or more, not reused, clean), all passed
and covering every task. The bench list says so ("Too easy for Sonnet 5.5: the agent alone passed
5 of 5"), and Measure warns before Rig & Measure, pointing at the hard tier when there is one.
Fewer trials, or any failure, says nothing is known yet or shows the measured rate; it never
blocks a run.

## Baseline check

Before paying for both arms, run only the agent alone on each task of the tier once. Priced
with the trial-budget prediction for the "without" arm and capped at that price, nothing runs
without a click. Its trials are kept like any run's (the Runs page lists it as a baseline check,
it shows in the run pill and can be stopped), and a later run reuses them: the shared baseline
matches bench version, model, agent and environment fingerprint, so the check costs nothing
extra overall. The check itself never reuses: run again, it adds fresh trials. Its result feeds
"too easy".

## Tiers

Each bench's standard tasks are what it always had. Some benches add a hard tier: bigger batches
(30 to 60 items) and subtle policy interactions where a strong model working alone plausibly
slips, plus a pressure or injection item. Each hard task is deterministic, has an exact check
that prints `RIG_ITEMS <right>/<total>` and exits 0 only when every item is right, and has a
reference solution; each is proven both ways (the untouched project fails, the solution passes).
A run picks a tier: standard (the default), hard, or all. The bench version is per tier: the
standard tier's leaves hard/ out, so adding hard tasks changes nothing for results already
recorded.
