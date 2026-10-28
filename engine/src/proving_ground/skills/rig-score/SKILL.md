---
name: rig-score
description: "The Rig score - one number from 0 to 100 that says whether a skill or workflow works, made from five measured parts (lift, cost, followed, holds up, reliable), capped by gates and put in a band with a one-line reason."
values:
  # The five parts, in the order they are shown. Weights add up to 1; a part that can't be
  # measured is left out and the others are scaled up to fill its share.
  parts:
    lift:
      name: Lift
      weight: 0.40
      noun: the lift
      settle: more pairs
      # 0 when the 95% interval's lower bound is at or below 0, 100 at `target_pts` or above.
      target_pts: 25
    cost:
      name: Cost
      weight: 0.20
      noun: cost
      settle: a cheaper setup
      # with ÷ without, per solved task when both arms solved some, else per finished task.
      # 100 at or below `full`, 0 at or above `zero`, log-linear between.
      full: 1.2
      zero: 5.0
    followed:
      name: Followed
      weight: 0.15
      noun: following the steps
      settle: an agent that follows the steps
      # A workflow: this share of the score from steps run, the rest from steps on the right model.
      steps_share: 0.5
    holds_up:
      name: Holds Up
      weight: 0.15
      noun: held-out tasks
      settle: more held-out pairs
      # "unclear" earns nothing and costs nothing: like "no held-out tasks", it is left out
      # (not measured) and the other parts share its weight. Unknown is not half right.
      scores: {generalises: 100, overfit: 0}
    reliable:
      name: Reliable
      weight: 0.10
      noun: reliability
      settle: fixing the check
      # A judged bench whose judge isn't calibrated as trustworthy keeps this share of the part.
      untrusted_judge: 0.5
  # Applied after the weighted sum, in this order.
  gates:
    hurts_cap: 20        # verdict "hurts"
    not_shown_cap: 49    # interval lower bound at or below 0
    min_pairs: 10        # fewer pairs: provisional, and capped so it can't read as "works"
    provisional_cap: 59
    # Both always pass and the change is clearly dearer or slower (verdict.clearly): it costs
    # more for the same result, so it can't score above this.
    ceiling_worse_cap: 20
  # Which band a result is in comes from its evidence first (see Rules: Bands); only a lift
  # shown to help (lower bound above 0) is placed by its number. `tone` is the UI's colour token.
  bands:
    - {id: works, min: 80, tone: positive, label: "Works — use it"}
    - {id: works_but, min: 60, tone: neutral, label: "Works, but {noun} needs work"}
    - {id: not_proven, tone: warning, label: "Not Proven — {settle}"}
    - {id: helps_but, tone: warning, label: "Helps, but {drag}"}
    - {id: doesnt, tone: negative, label: "Doesn't Work — {drag}"}
  none: {id: none, tone: neutral, label: "Not Measured Yet", reason: "No complete pairs yet."}
  # Invalid or uninformative (evidence-validity): no score at all; the reason is the validity's.
  not_evidence: {id: not_evidence, tone: neutral, label: "Not Evidence"}
  # "Doesn't Work" for an interval that reaches 0 only when even its upper bound is under this:
  # the lift can't be big enough to matter. Otherwise it is "not proven".
  doesnt_below_pts: 5
  # Cost and Reliable earn points only once a lift is shown (lower bound above 0): being cheap
  # and clean at doing nothing is worth nothing. Until then they count at 0, weight kept.
  credit_needs_lift: [cost, reliable]
  # The reason line: the parts that cost the most points (weight × shortfall), most first, at
  # most `max_reasons`, and only those below `drag_below`.
  max_reasons: 3
  drag_below: 70
  # Holding up, for a run that wasn't made by improving another one: the same rule as
  # improve-from-failures, on the with-minus-without change itself.
  overfit_visible_pts: 10
  # Each part's detail (always shown) and drag (in the reason when it costs points).
  text:
    lift:
      detail: "lower bound {low:+.0f} pts (target +{target:.0f})"
      # The lift on partial credit: points of the share of items right.
      detail_items: "lower bound {low:+.0f} pts of items right (target +{target:.0f})"
      hurts: "does worse than the plain agent ({diff:+.0f} pts)"
      none: "no lift shown"
      low: "lift could be as small as {low:+.0f} pts"
    cost:
      detail: "{ratio:.1f}× the plain agent's cost per {basis}"
      free: "costs nothing (a local model)"
      drag: "costs {ratio:.0f}× the plain agent"
      unknown: "no priced trials on both arms"
    followed:
      # {read}: the "with" trials whose session logs could be read (the ledger's logs_read).
      workflow: "on average {run} of {steps} steps run, {models} on the right model, in the {read} \"with\" {trials} whose logs could be read"
      workflow_unsized: "on average {run_pct:.0f}% of steps run, {models_pct:.0f}% on the right model, in the {read} \"with\" {trials} whose logs could be read"
      skill: "opened the skill in {opened} of the {read} \"with\" {trials} whose logs could be read"
      drag_skipped: "the agent skipped {skipped} of {steps} steps on average"
      drag_skipped_unsized: "the agent skipped {skipped_pct:.0f}% of the steps on average"
      drag_models: "{wrong} steps ran on the wrong model on average"
      drag_skill: "the agent didn't open the skill in {missed} of the {read} \"with\" {trials} whose logs could be read"
      unknown: "no session logs to read"
      # An MCP server: the share of "with" trials whose agent called one of its tools.
      mcp: "called the MCP server in {opened} of the {read} \"with\" {trials} whose logs could be read"
      drag_mcp: "the agent didn't call the MCP server in {missed} of the {read} \"with\" {trials} whose logs could be read"
      # No signal to read: a hook runs by itself, and instructions are always loaded. Not
      # measured, never guessed.
      hook: "a hook runs by itself, so there is nothing for the agent to follow or skip"
      instructions: "the instructions are always loaded; whether the agent kept to them isn't read from the logs"
      # A code change measured before and after: the code is simply there, nothing to open.
      before_after: "the change is in the code itself, so there is nothing for the agent to follow or skip"
    holds_up:
      generalises: "Generalises: better on held-out tasks too"
      overfit: "Overfit: better on visible tasks, not on held-out"
      drag_overfit: "it's fitted to the visible tasks (overfit)"
      # Not measured, in words: what the part checks and why it can't say.
      unknown: "This bench has no held-out tasks, so it's unknown whether this holds on unseen tasks"
      unclear_no_pairs: "No held-out tasks ran, so it's unknown whether this holds on unseen tasks"
      unclear_no_gain: "No gain on the visible tasks, so there's nothing for held-out tasks to confirm"
      unclear_mixed: "Held-out tasks neither confirm nor contradict the gain on the visible ones"
    reliable:
      detail: "{clean} of {total} trials ran cleanly ({with_} with, {without} without)"
      judge: "; the judge isn't calibrated"
      drag: "{bad} of {total} trials errored, broke, timed out or were cut off"
      drag_judge: "the judge isn't calibrated as trustworthy"
      unknown: "no trials"
    # Said in a part's detail when it counts at 0 until a lift is shown (credit_needs_lift).
    no_credit: "counts once a lift is shown"
    # The band's words for a result whose interval doesn't show a lift.
    no_lift: "no lift: even the interval's upper bound is {high:+.0f} pts"
    cant_reach: "the lift can't reach +{pts:.0f} pts (the interval's upper bound is {high:+.0f})"
    settle_pairs: "about {need} pairs would settle it ({pairs} so far)"
    settle_more: "more pairs would settle it ({pairs} so far)"
    settle_none: "no lift seen in {pairs} {pairs_word} yet; more pairs would settle it"
    # The band's words when the plain agent passes every task and the change doesn't.
    baseline_ceiling: "the agent alone already passes every task"
    # The formula under the parts, so the number can be rebuilt by hand.
    formula:
      term: "{weight:.0f}% × {score}"
      term_no_credit: "{weight:.0f}% × 0 ({name}: no credit yet)"
      sum: "{terms} = {raw:.1f}"
      rescaled: "{sum}; ÷ {measured:.0f}% (weights rescaled to the measured parts; {names} not measured) = {norm:.1f}"
      capped: "capped at {cap} ({why})"
      final: "rounded: {score}"
      why: {hurts: "it makes results worse", not_shown: "not shown to help", provisional: "too few pairs", ceiling_worse: "it costs more for the same result"}
    # One count of the result's trials that every other line refers to.
    ledger: "{total} {trials_word}{arms} · {pairs} complete {pairs_word} · {clean} ran cleanly{timed}{bad}{logs}"
    ledger_timed: ", {timed_out} timed out"
    ledger_arms: " ({with_} with, {without} without)"
    ledger_bad: ", {errored} errored, {broken} broken"
    ledger_logs: " · logs read for {read} of the {with_} \"with\" trials"
    gates:
      hurts: "Capped at {cap}: it makes results worse."
      not_shown: "Capped at {cap}: not shown to help (the interval reaches 0)."
      # The pair count only limits how high the score can go: few pairs can show a change does
      # worse (an interval clear of 0), never that it works.
      provisional: "Provisional: {pairs} pairs, under {min} — it can't score above {cap} until there are more."
      provisional_doesnt: "Provisional: {pairs} pairs, under {min} — enough to show it doesn't help, not enough to show it helps."
      ceiling_worse: "Capped at {cap}: both always pass, and it costs more or takes longer for the same result."
    # Both always pass (evidence-validity both_pass) and the change is clearly cheaper or
    # faster, or clearly dearer or slower: scored on cost, time and reliability; lift can't move.
    ceiling:
      lift: "both always pass: the pass rate can't differ"
      worse: "{what} at the same pass rate"
  too_few_pairs: "Looks good on {pairs} pairs; {min} are needed to call it working"
  works_reason: "every part holds up"
  # Said after a reason with no drags in it, when some parts couldn't be measured.
  unmeasured: "not measured: {names}"

  # ---------- The metric: what a run is scored on (see Rules: Metric) ----------
  # A run's metric is chosen on Measure and kept in its meta.json (`metric`). `pass_rate` is
  # everything above, unchanged. The others score a saving, with the pass rate as a guard.
  metric:
    default: pass_rate
    ids: [pass_rate, tokens, cost, time]
    names: {pass_rate: "Pass Rate", tokens: "Tokens per Solved Task", cost: "Cost per Solved Task", time: "Time per Solved Task"}
    nouns: {tokens: "tokens", cost: "cost", time: "time"}
    # One line each, for the choice on Measure.
    describe:
      pass_rate: "Does it solve more tasks? The lift is the rise in the pass rate."
      tokens: "Does it use fewer tokens for each task it solves, without solving fewer? Tokens are in + out as the agent reports them, cached input included."
      cost: "Does each solved task cost less, without solving fewer?"
      time: "Does each solved task take less time, without solving fewer?"
    # Said under a saving metric's choice, so nobody plans a run too small to show it.
    # How many pairs that takes is said once, by the estimate beside the budget (plan.text.need).
    guard_note: "The pass rate is the guard: until its 95% interval shows it is at most {margin} pts worse, no saving is credited."
    # Per solved task: an arm's total over the complete pairs (timed-out fails included: they
    # spent it) ÷ the tasks that arm passed in them. A reused "without" trial counts at the
    # cost it ran at. The interval: a percentile bootstrap of the ratio with ÷ without,
    # resampling whole pairs (paired), with a fixed seed so the same trials give the same
    # interval. A resample in which an arm solved nothing counts against the change (an
    # infinite ratio): an undefined saving is never a saving.
    bootstrap: {resamples: 2000, seed: 0, min_pairs: 2}
    # The guard (non-inferiority): the pass rate (or items right) is "no worse" only when the
    # 95% interval of its difference (the same Newcombe interval as the lift) has its lower
    # bound above -margin_pts. 10 points is the absolute margin common in response-rate
    # non-inferiority trials; it is well under the +25 points that earn a full Lift, so a
    # saving can't buy back a drop that would matter. It needs real evidence: 20 pairs that
    # all agree reach -12 (not enough), 40 pairs with one disagreement each way reach -9.4.
    margin_pts: 10
    # The cut's Lift: 0 at a lower bound of 0% or less, 100 at `target_cut` (a halving) or more.
    target_cut: 0.5
    # "Doesn't Work" when even the interval's best cut is under this.
    doesnt_below_cut: 0.05
    # Sizing a run on Measure for a saving metric, before anything is spent: about how many pairs
    # the guard needs if the change leaves the pass rate where it is (`pass_rate`) and
    # `disagree_each_way` of the pairs come out differently each way. 80% and 1 pair in 40 each
    # way give 39 pairs; a full run on a saving metric grows to that, not to the pass-rate sizing.
    plan:
      pass_rate: 0.8
      disagree_each_way: 0.025
      text:
        need: "Scored on {noun}, the pass-rate guard needs about {need} pairs{usd} before any saving can be credited (if the pass rate stays put and 1 pair in 40 disagrees each way)."
        short: "This run plans {planned}: at best the pass rate's interval would reach about {low:+.0f} pts, past the -{margin}-pt margin, so no saving can be credited. Run Full with the budget for them, or score it on the pass rate."
        enough: "This run plans {planned}: enough for the guard if the pass rate holds."
        # A run with "Keep going until it's decided" on (judge-experiment: auto_extend), in the Lab or on a repo's Measure.
        extend: "This run plans {planned}; with \"Keep going until it's decided\" on, it adds pairs until the saving and the guard are decided, up to {max_pairs} pairs or the budget."
        extend_budget: "The budget pays for about {pairs}, short of the guard's {need}."
    # These metrics are what the Cost part measures (tokens are what cost is billed on): Lift
    # takes Cost's weight and Cost isn't scored, so one saving isn't counted twice.
    folds_cost: [tokens, cost]
    text:
      # {low} and {high} come signed ("-61%"); a bootstrap whose upper end is unbounded (some
      # resample solved nothing) says `unbounded`.
      headline: "{name}: with {with_} vs without {without} ({change}, 95% interval {low} to {high})"
      unbounded: "no upper end"
      headline_no_ci: "{name}: with {with_} vs without {without} ({change}; an interval needs {min} pairs)"
      guard: "{quality}: {with_} with vs {without} without ({diff:+.0f} pts; at worst {low:+.0f} pts, {within})"
      within: "within the {margin}-pt margin"
      past: "past the {margin}-pt margin"
      quality_pass: "Pass rate"
      quality_items: "Items right"
      # The Lift part, on the cut.
      lift_detail: "the cut in {noun} per solved task is at least {low:.0f}% (target {target:.0f}%)"
      lift_detail_none: "no cut in {noun} per solved task shown (the interval reaches {high})"
      lift_detail_no_ci: "{change} {noun} per solved task; an interval needs {min} pairs"
      # The cut earns nothing until the pass rate is shown to hold.
      lift_held: "; counts once the pass rate is shown to hold"
      drag_worse: "it uses {more:.0f}% more {noun} per solved task"
      drag_none: "no cut in {noun} per solved task shown"
      drag_low: "the cut in {noun} could be as small as {low:.0f}%"
      drag_ni: "the pass rate could be {low:.0f} pts worse (the margin is {margin})"
      cost_folded: "in Lift: {name} is what is measured"
      no_credit: "counts once a cut is shown and the pass rate holds"
      # The band's words.
      doesnt_worse: "it uses {more:.0f}% more {noun} per solved task"
      doesnt_drop: "the pass rate drops {diff:+.0f} pts, past the {margin}-pt margin"
      cant_reach: "the cut can't reach {pts:.0f}% (at best {high:.0f}%)"
      settle_ni: "about {need} pairs would show the pass rate holds ({pairs} so far)"
      settle_ni_more: "more pairs would show whether the pass rate holds ({pairs} so far)"
      settle_cut: "more pairs would settle the cut ({pairs} so far)"
      # Nothing to compare: no score.
      unsolved: "Neither arm solved a task, so {noun} per solved task can't be compared."
      unsolved_one: "The \"{arm}\" arm solved no task, so {noun} per solved task can't be compared."
      unsolved_one_next: "run more pairs, or score it on the pass rate."
      unrecorded: "No {noun} recorded on both arms, so it can't be compared."
      unrecorded_next: "a run whose trials record {mnoun} (a local model records no cost)."
      gates:
        metric_worse: "Capped at {cap}: it uses more {noun} per solved task."
        not_noninferior: "Capped at {cap}: not shown to keep the pass rate (its interval reaches {low:+.0f} pts; the margin is {margin})."
        not_cut: "Capped at {cap}: no cut in {noun} per solved task shown (the interval reaches 0)."
      formula:
        term_folded: "{weight:.0f}% × {score} (Lift takes Cost's {cost:.0f}%: the measure is {noun})"
        why: {metric_worse: "it uses more", not_noninferior: "the pass rate isn't shown to hold", not_cut: "no cut shown"}
      # The verdict.
      v_helps: "{line}, and the pass rate holds ({quality} with vs {quality_without} without; at worst {low:+.0f} pts, margin {margin})."
      v_helps_next: "use it for the saving, and measure again when the model or the tasks change."
      v_worse: "{line}: it uses more {mnoun} per solved task."
      v_worse_next: "drop {noun}, or read its \"with\" trials to see where the {mnoun} go."
      v_hurts: "It does worse on the pass rate: {quality} with vs {quality_without} without ({diff:+.0f} pts, 95% interval {qlow:+.0f} to {qhigh:+.0f}). {line}."
      v_drop: "{line}, but the pass rate drops {diff:+.0f} pts ({quality} with vs {quality_without} without), past the {margin}-pt margin."
      v_hurts_next: "drop {noun}, or read the failing \"with\" trials to see what it breaks."
      v_too_small: "{line}: even at best it cuts {mnoun} by under {pts:.0f}%."
      v_too_small_next: "drop {noun}, or measure it on tasks where it has more to cut."
      v_ni: "{line}, but the pass rate could be up to {worst:.0f} pts worse ({quality} with vs {quality_without} without; the margin is {margin})."
      v_not_settled: "{line}: the cut isn't settled."
      v_few: "{line}: it looks like a cut, but on {pairs} pairs; {min} are needed."

  # ---------- The explainer page (GET /api/rig-score): the rules above, in plain words ----------
  # Every {value} is filled in from the values above by the endpoint, so the page can't drift
  # from the score. The worked example on the page is rig_score() run on `example.evidence`.
  explain:
    intro: "One number from 0 to 100 that says whether a skill or workflow works, measured with and without it on the same tasks. It is built only from what was measured; nothing is guessed."
    parts:
      lift:
        measures: "How much the pass rate goes up with the change. It takes the lower bound of the 95% interval, not the middle, so a lucky small run can't score well."
        scale: "0 at a lower bound of 0 pts or below, 100 at +{target_pts} pts or above, a straight line between."
      cost:
        measures: "What one task costs with the change, divided by what it costs without: per solved task when both arms solved some, else per finished task."
        scale: "100 at {full}× or less, 0 at {zero}× or more, linear in the logarithm between. A local model costs nothing: 100."
      followed:
        measures: "Whether the agent did what the change says, read from the session logs of the \"with\" trials."
        scale: "A workflow: {steps_pct}% from the share of steps run, the rest from the share run on the step's model. A skill: the share of trials that opened it."
      holds_up:
        measures: "Whether the gain holds on held-out tasks, ones the change was never shaped on."
        scale: "Generalises: {generalises}. Overfit: {overfit}. Unclear, or no held-out tasks: not measured."
      reliable:
        measures: "The share of trials that ran cleanly: not errored, broken, timed out or cut off by the budget cap."
        scale: "The clean share, 0 to 100. On a judged bench whose judge isn't calibrated, it keeps {untrusted_pct}% of that."
    missing: "A part that can't be measured is left out, and the others are scaled up to fill its share."
    no_credit: "Until a lift is shown (the interval's lower bound above 0), {names} count at 0: cheap and clean at doing nothing is worth nothing."
    metric: "A run can be scored on tokens, cost or time per solved task instead of the pass rate. Then the lift is the cut in that measure: the lower bound of its 95% interval (a paired bootstrap), 0 at 0% or less and 100 at {target_pct}% or more. The pass rate becomes a guard: it must be shown to be no worse, its interval's lower bound above -{margin} pts; until it is, the cut earns nothing and the score is capped at {cap}. On tokens or cost, Lift takes Cost's {cost_pct}%, so one saving isn't counted twice. Followed, Holds Up and Reliable mean what they mean for the pass rate."
    gates:
      hurts: "It makes results worse."
      not_shown: "Not shown to help: the interval reaches 0."
      provisional: "Fewer than {min_pairs} pairs: provisional, shown greyed with the pair count."
      ceiling_worse: "Both always pass, and it costs more or takes longer for the same result."
    bands:
      works: "{min} or more, with a lift shown."
      works_but: "{min} to {top}, with a lift shown; names the part that costs the most points."
      not_proven: "The interval reaches 0 but the lift could still matter, or only the pair count holds it back; says what would settle it."
      helps_but: "A lift is shown, but the score is under {below}; names the biggest drag."
      doesnt: "It makes results worse, or even the interval's upper bound is under +{doesnt_below_pts} pts."
    example:
      title: "A five-step workflow, measured on 16 pairs"
      note: "This bench has no held-out tasks, so Holds Up isn't measured and the other four parts share its {weight}%."
      evidence:
        kind: workflow
        n_pairs: 16
        diff: 0.31
        ci_low: 0.12
        ci_high: 0.50
        verdict: helps
        pass_with: 0.8125
        pass_without: 0.5
        costs:
          with: {spent_usd: 4.2, solved: 13, tasks: 16}
          without: {spent_usd: 1.6, solved: 8, tasks: 16}
        local: false
        adherence: {read: 15, steps_run: 0.9, models_ok: 0.8, steps: 5}
        holds_up: null
        ledger: {total: 32, with: 16, without: 16, pairs: 16, logs_read: 15, clean: 30, timed_out: 1, errored: 1, broken: 0}
        judge: null

  # ---------- The verdict: one plain answer on every result (see Rules: Verdict) ----------
  verdict:
    words: {helps: "Helps", doesnt: "Doesn't Help", cant: "Can't Tell Yet"}
    tones: {helps: positive, doesnt: negative, cant: neutral}
    # "Clearly" dearer / cheaper (cost) or slower / faster (time): over at least `min_tasks`
    # tasks finished in both arms, the per-task ratio with ÷ without (each arm's mean on that
    # task) has a geometric mean of at least `ratio` (or at most 1 ÷ `ratio`) AND the 95%
    # t-interval of the mean per-task log ratio excludes 0. Size and consistency, both.
    clearly: {ratio: 1.5, min_tasks: 2}
    # Less reliable: the share of "with" trials that timed out or errored exceeds the
    # "without" share by more than this.
    unreliable_by: 0.2
    noun: {workflow: "the workflow", skill: "the skill", hook: "the hook", mcp: "the MCP server", instructions: "the instructions", before_after: "the code change", change: "the change"}
    text:
      # The facts every verdict carries, one line each: quality, cost, time, reliability.
      q_pass: "{won} of {n} passed"
      # Partial credit (items), summed over the counted pairs' trials.
      q_items: "{right} of {total} items right"
      q_items_short: "{right} of {total}"
      q_items_pct: "{pct:.0f}% of items right"
      q_items_pct_short: "{pct:.0f}%"
      fact_quality: "Quality: {with_} with, {without} without"
      fact_lift: " ({diff:+.0f} pts, 95% interval {low:+.0f} to {high:+.0f})"
      fact_cost: "Cost: {with_} vs {without} per trial ({ratio}){solved}"
      fact_cost_solved: "; {with_} vs {without} per task solved ({ratio})"
      fact_cost_free: "Cost: nothing (a local model)"
      fact_cost_unknown: "Cost: not priced on both arms"
      fact_time: "Time: {with_} vs {without} per trial ({ratio})"
      fact_time_unknown: "Time: not recorded"
      fact_reliable: "Reliability: with, {w_bad}; without, {wo_bad}"
      bad_none: "all {n} ran cleanly"
      bad_empty: "no trials"
      bad_timed: "{k} of {n} timed out"
      bad_errored: "{k} of {n} errored"
      # Pieces of the reason line.
      costs_more: "costs {ratio} more per trial"
      costs_less: "costs {ratio} less per trial"
      slower: "takes {ratio} as long"
      faster: "is {ratio} faster"
      timed_out: "timed out on {k} of {n}"
      errored: "errored on {k} of {n}"
      passes: "passes {won} of {n}"
      gets: "gets {quality}"
      and: " and "
      # Reasons and next steps, by case. {noun}: "the workflow" / "the skill".
      helps: "{quality} with vs {quality_without} without ({diff:+.0f} pts, 95% interval {low:+.0f} to {high:+.0f}){extra}."
      helps_next: "use it, and measure again when the model or the tasks change."
      helps_efficiency: "Both pass every task; with {noun} it {what} on every one of {n} tasks."
      helps_efficiency_next: "use it for the savings, and keep an eye on the pass rate on harder tasks."
      hurts: "It does worse: {quality} with vs {quality_without} without ({diff:+.0f} pts, 95% interval {low:+.0f} to {high:+.0f}){extra}."
      hurts_next: "drop {noun}, or read the failing \"with\" trials to see what it breaks."
      baseline_ceiling: "The agent alone already passes every task; with {noun} it {what}."
      baseline_ceiling_items: "The agent alone already gets every item right; with {noun} it {what}."
      baseline_ceiling_next: "a harder bench, or drop {noun}."
      too_small: "Even at best it adds under +{pts:.0f} pts ({diff:+.0f} pts, 95% interval {low:+.0f} to {high:+.0f} over {pairs} pairs){extra}."
      too_small_next: "drop {noun}, or try it on a harder bench."
      ceiling_worse: "Both pass every task, so quality is the same; with {noun} it {what}."
      ceiling_worse_next: "drop {noun}, or a harder bench where it could change the pass rate."
      ceiling_unclear: "Both pass every task, and cost and time don't clearly differ ({what} over {n} {tasks_word})."
      ceiling_unclear_next: "a harder bench, where {noun} could change the pass rate."
      ceiling_few: "Both pass every task; with {noun} it {what}, but on {n} {tasks_word}: {min} are needed to call it."
      ceiling_few_next: "run it on more tasks."
      ceiling_mixed: "Both pass every task; with {noun} it {what}: a trade-off, not a clear win."
      ceiling_mixed_next: "decide which matters more, or a harder bench."
      both_fail: "Both fail every task, so nothing could be won: the bench is too hard or the check may be wrong."
      both_fail_next: "run one task's check by hand, or an easier bench."
      each_same: "Every task passes both ways or fails both ways, so nothing could be won or lost."
      each_same_next: "a bench with tasks the agent sometimes fails."
      broken_check: "The task's check isn't a command, so every trial fails both ways."
      broken_check_next: "give the task a real check."
      not_applied: "The \"with\" trials mostly ran without {noun}, so the difference isn't its."
      not_applied_next: "check {noun} is handed to the agent, then run again."
      mcp_unused: "The \"with\" trials mostly never called the MCP server."
      mcp_unused_next: "make the tasks need the server, or check it's configured."
      not_evidence_next: "look at each bench's result on its own."
      no_pairs: "No complete pairs yet."
      no_pairs_next: "let the run finish, or start one."
      not_settled: "{quality} with vs {quality_without} without ({diff:+.0f} pts, 95% interval {low:+.0f} to {high:+.0f} over {pairs} pairs): not settled{extra}."
      settle_next: "run about {need} pairs ({pairs} so far)."
      more_next: "run more pairs ({pairs} so far)."
      few_pairs: "Looks like it helps ({quality} with vs {quality_without} without, 95% interval {low:+.0f} to {high:+.0f}), but on {pairs} pairs; {min} are needed{extra}."
      few_pairs_efficiency: "Looks cheaper or faster ({what}), but on {pairs} pairs; {min} are needed."
      few_pairs_next: "run {more} more pairs."
      next: "Next: {step}"

  # ---------- The words by kind of run (see Rules: Before and after) ----------
  # A run of this kind says its lines in these words: each key replaces the one at the same place
  # above (`text`, `verdict.text`, `metric.text`); every number, rule and other line is the same.
  by_kind:
    # A code change measured before and after: "with" is the code after the change, "without"
    # the commit before, and there is no plain agent (the same agent runs on both).
    before_after:
      text:
        lift:
          hurts: "does worse than the code before ({diff:+.0f} pts)"
        cost:
          detail: "{ratio:.1f}× the cost of the code before, per {basis}"
          drag: "costs {ratio:.0f}× the code before"
        reliable:
          detail: "{clean} of {total} trials ran cleanly ({with_} after, {without} before)"
        baseline_ceiling: "the code before already passes every task"
        ledger_arms: " ({with_} after, {without} before)"
        ledger_logs: " · logs read for {read} of the {with_} \"after\" trials"
      verdict:
        text:
          fact_quality: "Quality: {with_} after, {without} before"
          fact_cost: "Cost: {with_} after vs {without} before per trial ({ratio}){solved}"
          fact_time: "Time: {with_} after vs {without} before per trial ({ratio})"
          fact_reliable: "Reliability: after, {w_bad}; before, {wo_bad}"
          helps: "{quality} after vs {quality_without} before ({diff:+.0f} pts, 95% interval {low:+.0f} to {high:+.0f}){extra}."
          helps_next: "keep the change, and measure again when the model or the tasks change."
          helps_efficiency: "Both pass every task; after the change it {what} on every one of {n} tasks."
          hurts: "It does worse: {quality} after vs {quality_without} before ({diff:+.0f} pts, 95% interval {low:+.0f} to {high:+.0f}){extra}."
          hurts_next: "keep the code before, or read the failing \"after\" trials to see what the change breaks."
          baseline_ceiling: "The code before already passes every task; after the change it {what}."
          baseline_ceiling_items: "The code before already gets every item right; after the change it {what}."
          baseline_ceiling_next: "a harder bench, or keep the code before."
          too_small_next: "keep the code before, or try the change on a harder bench."
          ceiling_worse: "Both pass every task, so quality is the same; after the change it {what}."
          ceiling_worse_next: "keep the code before, or a harder bench where the change could move the pass rate."
          ceiling_unclear_next: "a harder bench, where the change could move the pass rate."
          ceiling_few: "Both pass every task; after the change it {what}, but on {n} {tasks_word}: {min} are needed to call it."
          ceiling_mixed: "Both pass every task; after the change it {what}: a trade-off, not a clear win."
          not_settled: "{quality} after vs {quality_without} before ({diff:+.0f} pts, 95% interval {low:+.0f} to {high:+.0f} over {pairs} pairs): not settled{extra}."
          few_pairs: "Looks like it helps ({quality} after vs {quality_without} before, 95% interval {low:+.0f} to {high:+.0f}), but on {pairs} pairs; {min} are needed{extra}."
      metric:
        text:
          headline: "{name}: after {with_} vs before {without} ({change}, 95% interval {low} to {high})"
          headline_no_ci: "{name}: after {with_} vs before {without} ({change}; an interval needs {min} pairs)"
          guard: "{quality}: {with_} after vs {without} before ({diff:+.0f} pts; at worst {low:+.0f} pts, {within})"
          # {arm}: which side solved nothing, by `arm_words`.
          unsolved_one: "The code {arm} solved no task, so {noun} per solved task can't be compared."
          arm_words: {with: after, without: before}
          v_helps: "{line}, and the pass rate holds ({quality} after vs {quality_without} before; at worst {low:+.0f} pts, margin {margin})."
          v_helps_next: "keep the change for the saving, and measure again when the model or the tasks change."
          v_worse_next: "keep the code before, or read the \"after\" trials to see where the {mnoun} go."
          v_hurts: "It does worse on the pass rate: {quality} after vs {quality_without} before ({diff:+.0f} pts, 95% interval {qlow:+.0f} to {qhigh:+.0f}). {line}."
          v_drop: "{line}, but the pass rate drops {diff:+.0f} pts ({quality} after vs {quality_without} before), past the {margin}-pt margin."
          v_hurts_next: "keep the code before, or read the failing \"after\" trials to see what the change breaks."
          v_too_small_next: "keep the code before, or measure the change on tasks where it has more to cut."
          v_ni: "{line}, but the pass rate could be up to {worst:.0f} pts worse ({quality} after vs {quality_without} before; the margin is {margin})."
---

# Rig score

One number that says whether the rig works: a skill or a Lab workflow, measured with and
without on the same tasks. It is built only from what was measured; nothing is guessed.

## Rules
- Only evidence is scored. A result that evidence-validity calls invalid or uninformative gets
  no score at all: the card reads "— Not Evidence" with the validity's badge and reason. With
  no complete pairs there is no score either ("—", "Not Measured Yet"). One exception: both
  always pass and cost or time clearly differ (see Ceiling).
- The score is a weighted sum of five parts, each from 0 to 100, then capped by the gates.
  Weights are in `parts`. A part that couldn't be measured (no logs to read, no held-out tasks,
  no priced trials) is left out, its weight shared out over the others in proportion, and the
  part is shown as "not measured".
- No credit for value nobody measured: until a lift is shown (the interval's lower bound above
  0) the parts in `credit_needs_lift` (Cost, Reliable) count at 0 with their weight kept. Their
  detail is still shown, greyed, with `no_credit`. Their drags still count in the reason.
- The card shows the formula (`text.formula`): each counted part as weight × score, the parts
  given no credit, the measured share the sum is divided by ("weights rescaled to the measured
  parts (85%)") when parts were left out, a cap that bound, and the rounding.
- Lift: the lower bound of the 95% interval of the pass-rate difference, in points. 0 at or
  below 0; 100 at `target_pts` or above; a straight line between. The lower bound, not the
  middle, so a lucky small run can't score well.
- Cost: what one task costs with the rig divided by what it costs without. When both arms
  solved at least one task the cost is per solved task (spend ÷ tasks solved); otherwise per
  finished task. Reused "without" trials count at what they cost when they ran. 100 at a ratio
  of `full` or less, 0 at `zero` or more, and between them linear in the logarithm of the
  ratio. A local model costs nothing: 100. Without priced trials on both arms: not measured.
- Followed: for a workflow, from the session logs of the "with" trials: `steps_share` from the
  share of steps actually run, the rest from the share run on the step's model, averaged over
  the "with" trials whose logs could be read (and the detail says so). For a single skill: the
  share of those trials whose agent opened the skill. No logs to read: not measured.
- Holds Up: from the held-out tasks. Only "generalises" (100) and "overfit" (0) score;
  "unclear" is not measured, like no held-out tasks, and its detail says why in words (none ran,
  no visible gain to confirm, or held-out neither confirms nor contradicts it).
- Holds Up, the verdicts: a run made by improving another one uses that comparison
  (improve-from-failures). Any other run compares the held-out change with the visible one: it
  generalises when the held-out change is above 0; it is overfit when the visible change is at
  least `overfit_visible_pts` and the held-out change is 0 or less; otherwise (or with held-out
  tasks but no held-out pairs yet) unclear. No held-out tasks: not measured.
- Reliable: the share of trials that ran cleanly: not errored, not broken, not timed out, not cut
  off by the budget cap (those are errored). A timed-out trial is a fail (the agent didn't finish
  in the task's time limit) and counts in the pass rate; here it counts against Reliable too.
  On a judged bench whose judge isn't calibrated as trustworthy, the part keeps only `untrusted_judge` of its score.
- One trial ledger per result (`ledger`): trials total, with, without, complete pairs (as the
  interval counts them), clean, errored, broken, and the "with" trials whose logs could be
  read. Every line that cites a count takes it from the ledger and says which subset it is.
- Gates, after the sum: a "hurts" verdict caps the score at `hurts_cap`; a lower bound at or
  below 0 caps it at `not_shown_cap`; fewer than `min_pairs` pairs marks it provisional: still
  scored, shown greyed, with the pair count, and capped at `provisional_cap`. The cap only
  limits how high the score goes: a provisional result can still be "Doesn't Work" when its
  interval shows that (the gate then reads `provisional_doesnt`), never "Works". A gate whose cap
  is above the sum is listed but doesn't bind.
- The score is rounded half up to a whole number.
- Bands, decided in this order, so the band never contradicts the interval beside it:
  1. verdict "hurts", or the interval's upper bound at or below 0: `doesnt` ("Doesn't Work — …").
  2. the upper bound under `doesnt_below_pts`: `doesnt` (the lift can't reach that).
  3. the lower bound at or below 0 (it reaches 0 but could still matter): `not_proven`, with
     what would settle it: the pairs a lift of the observed size needs (stats.required_pairs),
     or "more pairs" — never "Doesn't Work".
  4. a lift shown: by the number: `works` at 80+, `works_but` at 60+ (naming the part that
     costs the most points); under 60, `not_proven` when only the pair count holds it back,
     else `helps_but` naming the biggest drag.
  The tone is always the band's.
- The reason line names the biggest drags concretely, most points lost first, joined by "; ".
  A part loses `weight × (100 − its own score)` points; ties go in part order.
- A reason with no drags in it ("every part holds up") also says which parts weren't measured.
- Same evidence, same score: the function is pure and reads nothing else.
- The plain agent passes every task and the change doesn't: band `doesnt`, "the agent alone
  already passes every task", before the interval rules (no lift is possible on that bench).

## Ceiling: both always pass
When evidence-validity says both always pass (cause `both_pass`), the pass rate can't differ,
so only cost, time and reliability can say anything. They are compared with `verdict.clearly`:
- Per task finished in both arms, take each arm's mean cost (and, separately, mean duration) and
  the ratio with ÷ without. "Clearly more" needs at least `min_tasks` such tasks, a geometric mean
  ratio of at least `ratio`, and a 95% Student-t interval of the mean log ratio whose lower end
  is above 0 (ratio above 1). "Clearly less" is the mirror. Size and consistency both: a big
  average driven by one task doesn't count, nor does a small consistent difference.
- Less reliable: the "with" arm's share of timed-out or errored trials exceeds the "without"
  arm's by more than `unreliable_by`.
- Something clearly worse (dearer, slower or less reliable) and nothing clearly better: scored,
  Lift shown as not measured ("the pass rate can't differ"), Cost and Reliable without credit,
  capped at `gates.ceiling_worse_cap`, band `doesnt` ("costs 26× more per trial … at the same
  pass rate").
- Something clearly better and nothing clearly worse: scored with Lift not measured and Cost and
  Reliable given credit (the saving is the value shown); band by the number as for a shown lift,
  and the usual provisional cap under `min_pairs`.
- Neither, or one of each: no score, "Not Evidence", as before.
Both always fail stays unscored: the bench is too hard or the check may be wrong.

## Metric: tokens, cost or time per solved task
A run is scored on one metric, chosen on Measure and kept in its meta.json. `pass_rate` (the
default, and a run made before the choice existed) is every rule above, unchanged. The others
ask "is it cheaper, without solving fewer?":
- The measure, per arm: its total tokens, cost or duration over the complete pairs,
  divided by the tasks it solved in them. Per solved task, so a change can't look cheap by
  failing fast. A reused "without" trial counts at the cost it ran at. Tokens are a trial's
  `tokens_in + tokens_out` as Harbor records them; its input count includes cached input tokens
  (cache reads and writes), so a change that only makes the prompt more cacheable doesn't look
  like a token cut. Cost is `cost_usd`; time is `duration_s`.
- Sizing, on Measure before anything is spent (`metric.plan`): the pairs the guard needs under
  the plan's assumptions; a planned run with fewer is told it can't be credited a saving, and a
  full run grows to that many pairs (budget allowing) instead of the pass-rate sizing.
- The interval: a percentile bootstrap of the ratio with ÷ without, resampling whole pairs
  (`metric.bootstrap`), with a fixed seed: the same trials always give the same interval. A
  resample where an arm solved nothing counts as an infinite ratio, against the change. Under
  `bootstrap.min_pairs` pairs there is no interval and nothing is shown.
- The guard, non-inferiority: the pass rate (items right, on partial credit) is "no worse" when
  the 95% interval of its difference has its lower bound above `-margin_pts`. Until then the cut
  earns nothing (Lift counts 0 with `lift_held`), Cost and Reliable get no credit, and the
  score is capped at `gates.not_shown_cap`. The margin's reason is beside its value.
- Lift: the lower bound of the cut (1 − the ratio interval's upper end). 0 at 0% or less, 100
  at `target_cut`, a straight line between. A cut is shown when that lower bound is above 0.
- Cost: on `folds_cost` metrics (tokens, cost) Cost is what is measured, so it isn't scored and
  Lift takes its weight (60%). On time, Cost is scored as usual.
- Followed, Holds Up and Reliable: as above. Cost and Reliable count only once a cut is shown
  and the pass rate holds (`credit_needs_lift`, with `metric.text.no_credit`).
- Gates, after the sum: pass-rate verdict "hurts" caps at `hurts_cap`; a ratio interval wholly
  above 1 (it clearly uses more) caps at `hurts_cap` (`metric_worse`); the guard not met, or no
  cut shown, caps at `not_shown_cap`; fewer than `min_pairs` pairs, `provisional_cap`.
- Bands, in this order: pass rate "hurts", it clearly uses more, or the pass rate's point
  estimate past the margin: `doesnt`. The cut's upper bound under `doesnt_below_cut`: `doesnt`.
  Guard not met: `not_proven`, with the pairs that would show it holds (the run's pairs scaled
  by the square of how much narrower the interval must get). No cut shown: `not_proven`, more
  pairs. Otherwise by the number, as for a shown lift.
  The plain agent passing every task isn't a "Doesn't Work" of its own here: the guard decides.
- Both always pass is evidence here: the pass rate can't differ, which is what the guard asks;
  the Ceiling rules are for the pass-rate metric. Both always fail has nothing solved: no score.
- Verdict: `helps` only with a cut shown, the guard met and at least `min_pairs` pairs. Every
  reason leads with the metric's headline (`metric.text.headline`); the facts are the usual four.
- Never a token cut without pass-rate evidence: no pairs, no interval or no guard, no credit.
- Suites (one workflow on several benches, judge-experiment: Suite runs): every bench's run is
  scored on the metric, and so is the pool. The pooled measure is each arm's total over every
  bench's complete pairs ÷ the tasks it solved in them: the figure one run over all these tasks
  would give, so a bench weighs by its pairs and by how much each of its tasks spends (a bench of
  heavy tasks moves the ratio more, as a heavy task does within one run; each bench's own saving
  is shown beside it). The interval is the same bootstrap, stratified: each resample draws every
  bench's own number of pairs from that bench alone, since the suite fixed how many pairs each
  bench ran; with one bench it is the single run's interval, draw for draw. A bench that recorded
  nothing on an arm makes the pool "unrecorded". The guard is the suite's pooled pass-rate
  interval (the same Newcombe interval over every bench's pairs that the pooled verdict uses),
  and the pool is scored, gated and banded exactly as one run on the metric. A pooled saving says
  it saves across these tasks, not on every bench.

## Verdict
Every result carries one plain verdict beside the score, the card's headline: `helps` ("Helps"),
`doesnt` ("Doesn't Help") or `cant` ("Can't Tell Yet"), with a reason naming the numbers, one
next step ("Next: …") and four fact lines: quality (pass rate, or partial credit), cost (mean
per trial and per task solved, with ÷ without), time (mean duration per trial) and reliability
(timed out / errored per arm). Same evidence, same verdict. Decided in this order:
1. Invalid (evidence-validity): `cant`, with the fix for its cause: a broken check ("give the
   task a real check"), a workflow not applied, an MCP server unused.
2. Both always pass: the Ceiling rules: clearly worse → `doesnt`; clearly better → `helps` on at
   least `gates.min_pairs` pairs (else `cant`, with how many more); a trade-off, too few tasks, or
   nothing clear → `cant`.
3. Both always fail, or every task the same both ways: `cant` ("the bench is too hard or the
   check may be wrong").
4. No complete pairs: `cant`.
5. The plain agent passes everything and the change doesn't: `doesnt` ("The agent alone already
   passes every task; with the workflow it costs 22× more per trial and timed out on 3 of 5").
6. Worse (upper bound below 0, or verdict "hurts"): `doesnt`.
7. Upper bound under `doesnt_below_pts`: `doesnt` (the lift can't matter).
8. Lower bound above 0: `helps` on at least `gates.min_pairs` pairs, else `cant` with how many
   more pairs.
9. Otherwise `cant`, with the pairs a lift of this size needs (stats.required_pairs).
"Helps" is never said without a lift whose 95% lower bound is above 0 or a clear cost or time
win at equal quality. Cost, time and timeouts that differ by at least `clearly.ratio` (or any
timeouts) are named in the reason whatever the verdict.

Quality is partial credit when the result row has `items` ({with, without, diff, ci_low,
ci_high, n}, fractions; optional `of` items per trial and their `noun`, e.g. 12 invoices): "11 of
12 invoices right". Without `items`, the pass rate over complete pairs. Partial credit that
differs keeps a both-always-pass result out of the Ceiling rules: quality did differ.

## Before and after
A code change measured before and after (measurability: `before_after`) is scored by every rule
above: the "with" arm is the code after the change, the "without" arm the commit before, and the
same agent runs on both. Only the words differ: each line that names an arm says "after" and
"before", "the plain agent" is "the code before", and a next step keeps the code before rather
than dropping a skill (`by_kind.before_after`, keyed as the lines it replaces). Followed is not
measured (`text.followed.before_after`).
