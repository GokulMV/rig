---
name: learned-priors
description: "How measured runs replace the Lab's starting guesses - which workflows count as similar, how much a measurement weighs against the guess, and what a solved task really cost."
values:
  # The starting guess counts as this many measured pairs. More pairs of evidence outweigh it.
  guess_weight_pairs: 10
  # Workflows share features (plans, checks, judges, reviews, loops, parallel steps, harness
  # rules, the model tier). Below this overlap (Jaccard) a measured run says nothing about another.
  min_similarity: 0.5
  # Only results that ran to an answer count: not ones still running or with no pairs.
  min_pairs: 2
  # Fewer valid pairs than this, over every run it would learn from, and the number stays the
  # guess from shape: a couple of pairs can't move it honestly.
  min_learned_pairs: 6
  # A run on a different model tier (local, cloud_fast, cloud_frontier) weighs this much against
  # one on the target's tier (1.0). Local and cloud are never pooled.
  tier_factor_fast_vs_frontier: 0.5
  tier_factor_local_vs_cloud: 0.0
  # A run on a bench of another discipline than the target workflow's weighs this much more.
  discipline_factor: 0.75
  # The shape guess counts the steps' models: each step's model prior (workflow-patterns:
  # models.prior, points against Sonnet), averaged with these weights by kind of step. Thinking
  # and judging lean on the model most, a check (a command) least. A guess, not a measurement.
  model_weight_by_kind: {think: 1.5, judge: 1.5, do: 1.0, check: 0.5}
---

# Learned priors

## Rules
- A workflow's number starts as a guess from its shape (workflow-patterns). Each measured run of
  a similar workflow moves it towards what was measured, weighted by pairs and similarity.
- The same workflow, measured, is similarity 1: its own measurement dominates as pairs grow.
- Similar is about shape, not name: the same kinds of steps, loops, parallel steps, rules and
  model tier. Measurements on any bench count; the result says how many runs it learned from.
- Only valid results count (evidence-validity): a run where the workflow was never opened, a
  check was broken, or both arms always passed (or always failed) teaches nothing and is skipped.
- Below `min_learned_pairs` valid pairs in all, the number is the guess and says so.
- One provenance badge, the same words everywhere: "measured n=<pairs>" (this workflow, measured),
  "estimated from N valid runs" (similar runs moved the guess), or "guess from shape".
- Say what it learned from. "Estimated from 3 valid runs (41 pairs)" is honest; a bare number isn't.
- Cost per solved task is what was spent on an arm divided by the tasks it solved. Cost per
  extra solved task is the extra spend with the workflow divided by the extra tasks it solved;
  when it solves no more, there is no such number, and it says so.
- Reused baseline trials count at what they cost when they ran, not at zero.
- Tiers stay apart. Model tier is local (id starts "local:"), cloud_fast (haiku, mini or flash
  in the id) or cloud_frontier (the rest). Fast and frontier cloud runs count half as much for
  each other; local and cloud runs never count for each other. Lab estimates are for cloud runs.
- A run on a bench of another discipline than the workflow's counts three quarters as much.
- The guess from shape includes the models: each step's model prior averaged with
  `model_weight_by_kind`, so moving a planning or judging step from Opus to Haiku lowers it more
  than moving a check. The workflow's "why" says what the models added. It is a guess like the
  rest: a measured run replaces it.
- The same workflow always gets the same guess: pricing it again (a reload, the Lab's list, a
  saved draft) gives the same number, ties between models go to the earliest step, and an
  unedited pattern keeps its pattern's prior. It changes only when the workflow is edited or a
  new valid run is learned from; the Lab then says which ("updated: learned from 1 new run").
