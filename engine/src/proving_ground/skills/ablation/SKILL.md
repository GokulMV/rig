---
name: ablation
description: "Slim this workflow - run the workflow again with one part taken out at a time, and say which steps earn their cost, which are dead weight and which hurt."
values:
  # At most this many variants are run. Drop-one-step variants come first, then loops, then
  # cheaper models.
  max_variants: 8
  # A step is essential, or harmful, when taking it out moves the result by at least this many
  # points. Below that, with a cheaper variant, it is dead weight.
  min_points: 5
  # A variant counts as cheaper when it saves at least this share of the workflow's cost per task.
  min_saving: 0.05
  # When the 95% intervals of the workflow and the variant overlap by more than this share of the
  # narrower one, a difference is called unclear, never essential or harmful.
  unclear_overlap: 0.5
  # A cheaper model for a step: Opus to Sonnet for any step, Sonnet to Haiku only for steps
  # that check or judge.
  downgrade:
    claude-opus-5-5: {to: claude-sonnet-5-5, kinds: [think, do, check, judge]}
    claude-sonnet-5-5: {to: claude-haiku-5-5, kinds: [check, judge]}
---

# Slim this workflow

## Rules
- Only a workflow measured to help is worth slimming. Each variant is the same workflow with one
  change; it runs on the same bench, agent and size as the measured run.
- A variant never pays for the baseline again: its "without" trials are the measured run's
  (judge-experiment: shared_baseline), so a variant costs only its "with" arm.
- Variants, in this order: drop one step (everything that led into it now leads to what followed
  it; loops through it go), drop one loop, run one step on the next cheaper model. A workflow's
  only "do" step is never dropped.
- The budget is a total for the job. Each variant gets an equal share of what is left; when the
  budget is gone, the rest are skipped and the result says so.
- Contribution of a part is the workflow's difference minus the variant's, in points. Essential:
  at least `min_points` and the intervals clearly apart. Harmful: at most minus `min_points`, the
  same. Dead weight: under `min_points` either way and the variant is cheaper. Where the intervals
  overlap by more than `unclear_overlap`, it is unclear: say so rather than guess.
- Slim runs are small. A wide interval is the usual answer; the result shows the interval.
- The job can be stopped: the run in progress stops after its trial and the rest are skipped.
