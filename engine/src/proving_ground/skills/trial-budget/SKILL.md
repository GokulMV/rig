---
name: trial-budget
description: "How a run keeps to its \"Stop at\" budget - what the next pair is predicted to cost, when it is not started, and which agents also stop themselves inside a trial."
values:
  # A trial's cost is predicted from this run's own finished trials on that arm: their mean or
  # their max. The prediction is that times `margin`, and never below the dearest trial seen.
  predict: mean
  margin: 1.25
  # With nothing measured on this run, earlier runs on this bench with the same agent and model
  # stand in ("without": any treatment; "with": the same treatment, else any), whatever their
  # validity, leaving out errored, broken and unpriced trials. Before a run, an arm with none on
  # this model uses other models' trials scaled by relative cost, and says so. Else this prior:
  # USD per trial on the baseline model (workflow-patterns: baseline_model), scaled by the
  # model's relative cost there. Seen on Claude Code + Sonnet: a handed-over workflow ~$0.95 a trial,
  # its baseline ~$0.04. A local model costs nothing.
  prior_usd: {with: 1.00, without: 0.25}
  # Agents whose CLI stops itself at a dollar amount, and the Harbor agent option that sets it.
  # Claude Code checks its own cost between model calls, so it can pass the cap by the last call.
  in_trial_cap:
    claude-code: max_budget_usd
  # Before a run: "with N pairs, an effect smaller than about ±X pts can't be told from noise",
  # X from the 95% interval's half-width (stats.noise_half_width) at this pass rate without.
  detect_base_rate: 0.5
  # Next to it, what it takes: "To tell a ±25 pts change from noise you need about N pairs ≈ $X",
  # N the fewest pairs whose half-width is at most this (stats.pairs_for_half_width), $X those
  # pairs at the predicted cost, rounded up to the budget field's step.
  detect_target_pts: 25
  budget_step_usd: 0.5
  # Refused before a run is created: even its cheapest first step, one "with" trial (the
  # "without" may be reused), is predicted to cost more than the whole budget.
  cant_start: "A {budget} budget can't pay for one trial: a \"with\" trial is predicted at about {need} ({source}). Raise it to at least {need}."
  # When the budget stops a full run within the pilot's pairs, said plainly.
  no_better_than_pilot: "At {budget} this full run stops after {pairs}: no more conclusive than the pilot."
  # The run-size choice's "Full" label: what the budget buys for a full run. {pairs}: the pairs
  # it reaches; {pts}: the smallest change those can tell from noise (detect_target_pts sizing
  # inverted, rounded up to a whole pt). "conclusive" only when those pairs reach the sizing for
  # detect_target_pts; "like_pilot" when the budget stops it within the pilot's pairs.
  full_label:
    conclusive: "Full · {pairs} · conclusive to ±{pts} pts"
    detects: "Full · {pairs} · tells apart ±{pts} pts"
    like_pilot: "Full · the budget only covers {pairs}, as many as the pilot"
    nothing: "Full · the budget pays for no pair"
  # A run's status in words, wherever it is shown (never the raw value).
  status_words:
    pending: Waiting to start
    running: Running
    done: Done
    stopped: Stopped
    stopped_budget: Stopped at the budget
    failed_preflight: "Couldn't start: a check passed before the agent did anything"
  # A run's meta.json records `budget_cap` (how its trials were predicted) since the cap exists.
  # A run without it, made before this time, ran when only "spent >= budget" was checked.
  cap_since: "2026-10-25T17:30:09+00:00"
  # Shown after "$2.90 of $2.00" when a run's spend is over its budget.
  over_before_cap: "went over before the budget cap existed"
  over: "over by {by} (the last trial cost more than predicted)"
---

# Keep to the budget

## Rules
- The budget is a cap, not a stopping signal. Nothing starts that the budget can't pay for.
- Before a pair (a task's "with" and "without" trial in one repeat), predict both arms and start
  it only when spent + reserved + predicted fits the budget. If it doesn't fit, the run stops at
  `stopped_budget` and says why: what the next pair would cost and what is left.
- An arm already done (a reused baseline, or a resumed run) costs nothing more: only the arms
  still to run are predicted.
- Before each trial the check runs again for that trial alone, so a first arm that cost more
  than predicted can stop the pair before its second arm.
- The prediction: `predict` (mean or max) of this run's own trials on that arm, times `margin`,
  and never below the dearest one seen. With none yet, earlier runs on this bench with the same
  agent and model (for "with", the same treatment's trials, else any treatment's: a guess, which
  the in-trial cap backs up where there is one); with none of those either, `prior_usd` scaled
  by the model's relative cost. Trials that cost nothing (reused, broken, or unpriced) are not
  evidence.
- Reservations: a trial's predicted cost is reserved when its pair is started and released when
  it finishes, replaced by what it really cost. A trial can only start against what is neither
  spent nor reserved, so trials running at the same time can't spend the same dollars.
- Inside a trial: for an agent in `in_trial_cap`, the trial is given a dollar cap: its own
  reservation plus whatever is neither spent nor reserved (held by it until it ends, so a trial
  running alongside can't count on it). A trial that hits it is errored, not failed: it was cut
  short, so it measures nothing. Claude Code checks its spend between model calls, so a trial
  can pass its cap by the cost of its last call; that is the only overshoot left.
- Agents without such a cap get only the checks before each trial (and the task's time limit).
  A trial that costs more than predicted can pass the budget by up to that difference; the run
  then stops. Say so wherever the budget is promised.
- A local model costs nothing: no prediction and no cap.
- A run that spent more than its budget says why next to "spent of budget": a run whose meta
  has no `budget_cap` and that was made before `cap_since` predates the cap (`over_before_cap`);
  any other says by how much (`over`): only the last trial can take it over.
- Before a run, before any sign-in: the Measure step shows the same prediction for its first
  pair (both arms, margin included, from earlier runs or the prior), times the pairs it plans,
  and how many of them "Stop at" pays for. It is the check's own number, not a quote: reused
  baseline trials make it cost less, and auto-extend can add pairs up to the budget.
- Next to it, what the run can detect: with the pairs it will reach (the planned pairs, or as
  many as "Stop at" pays for), the 95% interval's half-width at a `detect_base_rate` pass rate.
  An effect smaller than that can't be told from noise.
- And what it would take: the pairs whose half-width is `detect_target_pts`, and the budget
  that pays for them at the same prediction (rounded up to `budget_step_usd`), with one click to
  set it. When the run plans fewer pairs than that, say so: a budget alone won't reach them.
- When "Stop at" stops a full run within the pilot's pairs, say it is no more conclusive than
  the pilot (`no_better_than_pilot`).
- A full run on one bench or repo grows with the budget: at least the fixed full
  size, plus as many pairs as "Stop at" pays for at the prediction, up to the pairs sized for
  `detect_target_pts`, in whole repeats of the tasks. The estimate and the start plan the same
  pairs (budget.full_pairs), so setting the budget the sizing offers makes it conclusive. A
  suite's and a comparison's benches keep the fixed full size their plans price.
- The run-size choice never promises a conclusive full run: its "Full" label (`full_label`) says
  the pairs the budget reaches and the smallest change they tell from noise, "conclusive" only
  when they reach the pairs sized for `detect_target_pts`, and "like the pilot" when the budget
  stops it within the pilot's pairs. Comparing a set, it is the pairs of the workflow its share
  pays for least.
- The prediction says where it came from: "measured on N earlier trials" (and the models it
  was scaled from, when it was), else "a first guess: nothing measured yet".
- A run's status is said in words (`status_words`) everywhere it is shown.
