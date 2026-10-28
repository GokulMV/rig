---
name: judge-experiment
description: Run a skill with and without on the same scenarios, then say whether it helps, hurts, or
  can't tell yet.
values:
  confidence: 0.95
  power: 0.8
  z_confidence: 1.959963984540054
  z_power: 0.8416212335729143
  var_floor: 0.0475
  unreliable_error_rate: 0.1
  pilot_pairs: one per approved scenario
  full_min_pairs: 20
  interval: Newcombe method 10 (paired), Wilson for each arm
  verdict:
    helps: interval low > 0
    hurts: interval high < 0
    inconclusive: otherwise
  shared_baseline:
    reuse: true                   # reuse earlier "without" trials on the same bench version
    outcomes: [pass, fail]        # only clean trials are reused; errored and broken ones run again
    same: [bench version, model, agent, environment fingerprint]
  auto_extend:
    step_repeats: 1               # each look adds one more pair per scenario
    max_looks: 5                  # at most this many extra batches
    stop_z: 2.576                 # stop early only when the 99% interval excludes zero
    max_pairs: 60
    # A run scored on a saving (rig-score: Metric) waits for two answers at the stricter
    # interval, the saving and its pass-rate guard, and the guard needs far more pairs than a
    # pass-rate lift: at the 99% interval about 56 under rig-score's metric.plan (39 at 95%).
    # Five looks of one pair per task (12 pairs on a 2-task bench) would never get there, so a
    # look adds at least `step_pairs` pairs, up to `max_pairs` and the budget.
    metric: {step_pairs: 10, max_looks: 10, max_pairs: 100}
    text:
      # The option, as the Lab offers it. {level}: the stricter interval, in percent.
      keep_going: "adds pairs while the result is unclear, up to the budget. Stops early only when a stricter ({level}%) interval rules out zero."
      keep_going_metric: "adds pairs until the saving and the pass-rate guard are both decided, up to the budget or {max_pairs} pairs. At a stricter ({level}%) interval, the saving is decided once it rules out no change or shows the cut is under {small}%, and the guard once the pass rate's interval shows it at most {margin} pts lower. It stops at once if the pass rate is shown lower, or {name} higher."
      # What a run on a saving still waits for, after "Not decided yet at N pairs: waiting on".
      waiting: {saving: "the saving", guard: "the pass-rate guard", both: "the saving and the pass-rate guard"}
      # Why it stopped adding pairs, after "Stopped adding pairs at N:". {name}: "tokens per solved task".
      decided:
        both: "the cut in {name} and the pass-rate guard are both decided at the stricter interval"
        hurts: "the pass rate is shown lower with it at the stricter interval"
        worse: "{name} is shown higher with it at the stricter interval"
        too_small: "the cut in {name} is shown to be under {small}% at the stricter interval"
        unrecorded: "no {noun} is recorded, so more pairs can't settle it"
      # At a cap (the budget, max_pairs, max_looks) with the saving's answers still open.
      undecided: "{reason}, with {waiting} still undecided"
      # Before a run, under its estimate and on its confirm: the most pairs it may grow to while
      # undecided, every look's pairs complete (the caps above; a saving's on a saving). {pairs}:
      # "60 pairs"; {budget}: "$5.00". A local model is free: the caps alone stop it.
      grows:
        paid: "With \"Keep going until it's decided\" on, it may grow to {pairs} (≈ {usd}) while it's undecided, and still stops at {budget}."
        budget: "With \"Keep going until it's decided\" on, it may grow while it's undecided, to about {pairs} before {budget} stops it ({most} at most)."
        free: "With \"Keep going until it's decided\" on, it may grow to {pairs} while it's undecided, its cap: a local model has no budget to stop it sooner."
        none: "With \"Keep going until it's decided\" on, it can't add pairs here: {pairs} is already as many as it runs to."
        no_budget: "With \"Keep going until it's decided\" on, it can't add pairs here: {budget} stops it within the planned {pairs}."
  # One workflow across every bench that fits its discipline, one pooled verdict.
  suite:
    fits: the bench's disciplines include the workflow's discipline
    skip: [imported, generated]   # built-in benches only; a person picks those themselves
    size: pilot                   # per bench, as for a single run
    split: even                   # budget / benches left; what a bench leaves unspent carries over
    pool: pairs                   # every bench's with/without pairs, concatenated
    # A saving (rig-score: Metric) over every bench's pairs; its bootstrap resamples each bench's
    # pairs within that bench (stratified), so every resample keeps the benches' sizes as run.
    pool_metric: pairs, resampled within each bench
    scenario_key: "{bench}/{scenario}"
    # Every bench runs its planned pairs, on the pass rate as on a saving: the verdict is the
    # pool's, so a stop rule per bench would answer a question the suite doesn't ask. It would
    # also give the undecided benches the most pairs, so they would carry the pooled number, and
    # let an early bench spend the later ones' share. The estimate prices exactly these pairs.
    auto_extend: false
  # Two to four workflows on one bench, one after another, one shared baseline, one ranking.
  compare:
    min: 2
    max: 4
    split: even                   # budget / workflows, fixed: each gets the same share
    order: as pinned
    auto_extend: false            # the same planned pairs each, so they're compared on the same tasks
    reuse_baseline: true          # the first run on a model pays for "without"; the rest reuse it
    rank_by: rig score            # then the change, for ties and results with no score
    # Results on more than one session model: each lift is against its own model's baseline, so
    # lifts (and the lift-heavy Rig score) don't compare. Rank by what the workflow ends at instead.
    rank_by_models: pass rate with the workflow   # its "with" arm, Wilson interval at `confidence`
    tie_break_models: cost        # "with" spend per trial, lower first; equal pass rates only
    winner: the top interval's low end is above every other interval's high end   # whatever is ranked
    more_pairs_cap: 200           # past this, say "more than" instead of a number
    # Before a run: workflows on more than one session model each pay for a baseline. Offer to run
    # them all on one: the most common session model, the cheapest if tied (`align_to`).
    align_to: [most common, cheapest]
    text:
      winner: "{name} comes out ahead: its interval is clear of every other one's."
      winner_models: "{name} comes out ahead: its pass rate's interval is clear of every other one's."
      by_rig: "Ranked by Rig score"
      by_models: "They ran on {n} models, so each lift is against its own model's baseline; ranked by pass rate with the workflow, then cost"
      lift_vs: "vs Direct on {model}"
      other_model: "On {model}, not this one: not ranked. Measure it again to rank it."   # a result from before its model changed
      models_notice: "{n} models, so {n} baselines: +{extra}."
      align_action: "Run All on {model}"
      align_saves: "one shared baseline, ≈ {total} in total, saving {usd}."
      align_costs_more: "one shared baseline, ≈ {total} in total, {usd} more since {model} costs more per trial."
      align_level: "one shared baseline, ≈ {total} in total, about the same."
      not_proven: "Not proven yet: can't tell {a} and {b} apart yet: about {n} more {pairs} each."
      not_proven_level: "Not proven yet: can't tell {a} and {b} apart yet: they're level so far, so more pairs may never separate them."
      not_proven_many: "Not proven yet: can't tell {a} and {b} apart yet: more than {n} more pairs each."
      too_few: "Measure at least two of them on this bench to rank them."
  # A workflow is handed to the agent: its "with" arm's prompt names the workflow skill. Found in
  # real runs: a small model never opened a workflow skill it was only offered. A plain skill is
  # left for the agent to find, as in real use. {{ instruction }} is the task's own instruction.
  workflow_prompt: "{{{{ instruction }}}}\n\nThis task comes with a workflow, the skill `{skill}`: open it (its SKILL.md) before anything else and follow its steps."
---

# Judge an experiment

## Telling the agent about the treatment
By default a workflow's "with" prompt names it (`workflow_prompt`) and a plain skill is left for
the agent to find. A small model never opened a skill it was only offered, so the choice is a
toggle (`nudge_prompt`): on hands any skill over, off leaves every treatment to be found, as in
real use. Comparing a nudged workflow against an un-nudged skill confounds content with
discovery; set both the same way when comparing them. The "without" arm is never changed, so
the baseline does not depend on it.

## Run
Each approved scenario runs in pairs: once with the skill, once without, same sandbox image,
same agent and model. **Pilot** runs `pilot_pairs`; **Full** runs at least `full_min_pairs`
pairs, repeating scenarios as needed. The budget stops the run when spent.

## Measure
- Pass rate per arm with a Wilson interval; the paired difference with Newcombe's method 10, at
  `confidence`.
- Smallest detectable difference (MDE) at `confidence` and `power`, with variance floored at
  `var_floor` so it stays meaningful near 0% or 100%.
- If more than `unreliable_error_rate` of trials errored (infrastructure, not the agent), the
  result is flagged unreliable.

## Shared baseline

"Without" means the same agent and model with no skill or workflow, so it doesn't depend on
what is being tested. On a bench, earlier "without" trials are reused when the bench version,
model and agent all match (`shared_baseline`), and only clean outcomes (`outcomes`) are reused.
The environment fingerprint hashes the base image recipe, the agent's install step, the Harbor
version and, for a local model, its server address and name; Claude Code is installed unpinned
at build time, so a changed recipe is the signal that "without" may behave differently. Runs
saved before the fingerprint existed never match. The run can also opt out of reuse and run the
baseline fresh.
Each reused trial records where it came from and costs nothing again. The comparison stays
fair: both arms ran the same tasks in the same sandbox with the same agent and model; only the
time they ran differs.

## Auto-extend

A pilot rarely settles it. With auto-extend on, after each batch the run checks the result at a
stricter interval (`stop_z`): if it excludes zero, it stops; otherwise it adds `step_repeats`
more pairs per scenario, up to `max_looks` batches, `max_pairs` pairs and the budget. Checking
again and again makes a lucky result likelier, which is why the stop rule is stricter than the
95% interval the result is reported with.

A run scored on tokens, cost or time per solved task (rig-score: Metric) is decided by the
saving and its guard, not by the pass rate excluding zero: a pass rate that settles says nothing
about the saving, and a change meant to save rarely moves the pass rate at all. After each batch
both are checked at the same stricter interval (`stop_z`: the bootstrap's 99% percentiles for
the ratio, the 99% Newcombe interval, or the 99% paired t on partial credit, for the guard):
- The saving is decided when its interval rules out no change either way (a cut, or the
  measure higher with it), or shows the best cut is under rig-score's `doesnt_below_cut` (5%):
  too small to matter, the same line the verdict calls "Doesn't Help". No separate equivalence
  margin: that line is the one the score already uses, so the stop and the verdict agree.
- The guard is decided when the pass rate's lower bound is above `-margin_pts` (it holds).
- It stops when both are decided as a cut and a guard met, or at once when an answer is
  "Doesn't Help" whatever the other says: the pass rate shown lower (upper bound below 0), the
  measure shown higher, or the cut shown too small. It also stops when the measure isn't
  recorded at all (no pairs can settle that).
- Otherwise it adds a batch, saying what it waits for (`text.waiting`). A guard needs about 56
  pairs at the 99% interval, so a look adds at least `metric.step_pairs` pairs (whole repeats of
  every task), up to `metric.max_looks` batches, `metric.max_pairs` pairs and the budget. At a
  cap it says what was still undecided (`text.undecided`).
A run on the pass rate keeps the rule above, unchanged.

The Lab and a repo's Measure offer it the same way ("Keep going until it's decided", on by
default), for a change with and without and for a code change before and after: one rule, one set
of caps. Before the run, the estimate and the confirm say the most pairs it may grow to while
undecided, every look's pairs complete (`text.grows`), with what they cost or the pairs the budget
stops it at first. The budget stays the hard stop. A run on a local model is free, so no budget
stops it: the caps (`max_pairs` and `max_looks`, or `metric`'s on a saving) do.

## Suite runs
A suite runs one workflow on each built-in bench that fits its discipline (`suite.fits`; imported
and generated benches are skipped unless a person picks them), one after another, at pilot size.
One total budget is split evenly over the benches still to run (`suite.split`): each bench gets
what is left divided by the benches left, so what an earlier bench didn't spend carries over to
the later ones. Stopping ends the bench in progress and skips the rest.

The pooled verdict concatenates every bench's pairs (a pair is the with and without trial of one
task and repeat) and judges the union exactly as a single run is judged: the same interval, the
same verdict rule. Task ids are made unique per bench (`suite.scenario_key`) so two benches never
merge a pair. Pooling weights benches by their number of pairs: a bench with 6 pairs counts for
three times a bench with 2, so one big bench can carry the pooled number. Each bench's own change
is shown beside it so that can be seen. A pooled "helps" says the workflow helps across these
tasks, not that it helps on every bench.

A suite can be scored on tokens, cost or time per solved task, as a single run can (rig-score:
Metric, Suites). Every bench's run is scored on it, and the pooled saving is over the same pairs
the pooled pass rate counts (`suite.pool_metric`): each arm's total over every bench's pairs ÷
the tasks it solved in them, so it reads as one run over all these tasks would. Its bootstrap
draws each bench's pairs from that bench alone: the benches' sizes are fixed by how the suite
ran, so a resample that moved pairs between benches would add a spread the suite never had. The
pass-rate guard is the pooled pass-rate interval above, judged as a single run's guard is.

The benches don't auto-extend (`suite.auto_extend`), on the pass rate or on a saving: each runs
its planned pairs, so the estimate before the run prices what runs. The verdict is decided on
the pool, not per bench. A stop rule per bench would add pairs exactly where a bench's own
interval is unclear, so the benches hardest to read would carry the pooled number by weight,
and an early bench that kept going would spend the share the later ones were split.

## Comparing workflows
Two to four workflows (`compare.min`, `compare.max`) run on one bench one after another, in the
order they were pinned. The total budget is split evenly and fixed (`compare.split`): each gets
the same share. Auto-extend is off (`compare.auto_extend`), so each runs the same planned pairs on
the same tasks. Reuse is on: the first workflow on a session model pays for the "without" trials
and the later ones on that model reuse them (the shared baseline above), so a later workflow
costs about its "with" arm alone. Workflows on different session models can't share a baseline
(the model is one of the keys that must match), and each such group pays for its own. That is
right, not a gap to paper over: a baseline on one model says nothing about another. The
prediction before the run is the trial-budget one, per workflow, with reused trials at zero.
Stopping ends the workflow in progress and skips the rest.

When the set is on more than one session model, the page says so before the run with what the
extra baselines cost (`text.models_notice`: the "without" trials paid by every workflow not on the
model offered) and offers one click to run them all on one model (`compare.align_to`): the most
common session model in the set, the cheapest in total when tied. It sets each workflow's main
steps (the "do" steps, the ones the session model is read from) to that model and leaves
planning and checking steps as they were, then prices the set again. The offer states the new
total and the difference: usually a saving, but moving a workflow off a cheaper model raises its
"with" arm, and then it says it costs more. It changes only the copies pinned for Compare, and
can be undone.

A workflow's result on the bench is its latest valid one on the session model it is on now. After
it moves model, an earlier result on another model is not its result: it is shown marked
(`text.other_model`) with its numbers kept apart, and left out of the ranking until it is measured
again. A finished run whose workflows have since moved model gives way to that standing too.

Ranking: valid results only (evidence-validity). On one session model: by Rig score, then by the
change. On more than one (`compare.rank_by_models`), each change is against its own model's
baseline, so neither the changes nor the lift-heavy Rig score compare: a weak model lifted from
10% to 50% would outrank a strong one that went from 90% to 95%. Then they are ranked by the pass
rate with the workflow (the "with" arm, with its Wilson interval at `confidence`), ties broken by
the "with" arm's spend per trial, lower first (`compare.tie_break_models`). Each one's Rig score
and change are still shown, labelled with what the change is against (`text.lift_vs`).

Whatever is ranked, a winner is named only when the top one's 95% interval sits wholly above
every other one's (`compare.winner`). Otherwise it says the two closest can't be told apart yet
and roughly how many more pairs each would need: an interval narrows with the square root of the
pairs, so with half-widths h1 and h2 at n pairs and a gap d between the two, the intervals stop
overlapping at about n·((h1+h2)/d)² pairs. With no gap at all, more pairs may never separate them.
Comparing two intervals against the same baseline is conservative (a paired test between the two
would need fewer pairs), which is the side to err on before calling a winner; across models the
pass-rate intervals are independent samples, so the same rule holds without that caveat.

## Verdict
- **Helps** when the interval's low end is above 0.
- **Hurts** when its high end is below 0.
- **Inconclusive** otherwise, with how many pairs would be needed to tell.
An estimate is never a verdict.

## Per-protocol
The headline change counts every pair, whether or not the "with" trial followed the workflow
(intention to treat). "When followed" repeats the comparison on pairs whose "with" trial
followed it (session logs read, workflow opened, no step skipped). It is selection-biased: it
leaves out trials that ignored the workflow, and those may be the harder ones. It is shown only
when logs can be read and some, but not all, pairs followed. The headline stays the verdict.
