---
name: tutorial
description: "The tutorial - one tiny example (price tags for a corner shop) walked through Rig's five steps, with a real recorded run: the same ten tasks with and without one skill, on a free local model, and the Rig score it got."
values:
  # Home: the entry (Home's tour slot) and the recorded run beside the headline (its proof slot).
  home:
    title: "New Here? See One Real Run, Start to Finish"
    title_done: "The Tutorial: One Real Run, Start to Finish"
    lead: "{tasks} tiny coding tasks, run with and without one skill on a free local model. Five steps, about two minutes to read. Nothing in it touches your repos or runs."
    start: "Start the Tutorial"
    replay: "Replay the Tutorial"
  proof:
    pill: "Real Run"
    caption: "{example}: {n} tasks with and without the skill {skill}, on {model}, local and free"
    without: "Without the skill"
    with: "With the skill"
  # The page itself.
  eyebrow: "Tutorial · step {step} of 5"
  leave: "Leave the Tutorial"
  stepper: "Tutorial steps"
  # One entry per step of the guided path, in its order. {…} are filled from the example and the
  # recorded run, so the words can't drift from the numbers.
  steps:
    - id: describe
      title: "Describe: What Should the Agent Get Better At?"
      lead: "Every Rig run starts from a goal and the place the work lives. Here the goal is plain: write the labels on a corner shop's shelves in the shop's house style. The work lives in a tiny Python repo, {example}."
      goal_title: "Goal"
      goal: "Shelf labels for a corner shop, written in the shop's house style."
      repo: "Where it lives: the repo {example}"
      tasks_line: ".proving-ground/scenarios/ ({tasks} tasks)"
      note: "In your own run, this is your repo (Rig a Repo) or a workflow you describe (Rig a Workflow)."
    - id: design
      title: "Design: The Agent, and One Part to Test"
      lead: "Your architecture is the car; the change you want to judge is a part. Here the car is Claude Code running on {model}, a free local model, and the part is one skill, {skill}: the house rules, written down. The code alone doesn't say them."
      car: "The Car"
      car_text: "Claude Code, on {model} served by llama.cpp on this Mac. Nothing leaves the machine, and it costs nothing."
      part: "The Part Being Tested"
      part_text: "The skill {skill}. The \"with\" arm is told to open it; the \"without\" arm never sees it."
      note: "In your own run, Design ranks whole architectures for your goal; you can also keep the one you have."
    - id: build
      title: "Build: Tasks, Each with a Check"
      lead: "Rig judges a change on tasks, never on a feeling. Each of these {tasks} tasks asks for one new label, and each has a check: a command that passes or fails by calling the new function and comparing its text. Nothing is graded by eye."
      tasks_title: "Tasks"
      check_title: "One Task's Check"
      note: "In your own run, Rig writes tasks like these for your repo, and you approve each check before anything runs."
    - id: measure
      title: "Measure: The Same Tasks, with and without the Skill"
      lead: "Each task ran twice, each time in its own Docker sandbox: once with the skill and once without. With it, {with_} of {n} passed; without it, {without} of {n}. The Rig score turns that into one number, and shows how it was made."
      task: "Task"
      without: "Without"
      with: "With"
      passed: "passed"
      failed: "failed"
      timed_out: "timed out"
      errored: "errored"
      total: "Passed"
      # Per task, in its rows: which way the skill moved it. Read the rows, not only the total.
      rows: "Task by task, with the skill: {helped} went from fail to pass, {hurt} from pass to fail, and {same} came out the same both ways."
      interval_title: "What the Skill Changed"
      interval: "{diff} pts, 95% interval {low} to {high}"
      score_title: "The Rig Score"
      note: "In your own run, you pick the tasks and the size, see the price first, and watch it live."
    - id: ship
      title: "Ship: Keep What Earned Its Place"
      lead: "The skill scored {score} out of 100: {label}. Ship turns what you measured into a build brief any coding agent can follow, with the evidence beside each change."
      result_title: "What It Rests On"
      brief_title: "The Build Brief, for This Example"
      brief:
        - "Add the skill {skill} to the agent's skills (.claude/skills/{skill}/)."
        - "Measured on {n} pairs with {model}: {with_} of {n} passed with it, {without} of {n} without."
        - "Rig score {score}/100: {label}."
        - "Measure again when the model or the tasks change."
      note: "In your own run, Ship writes BUILD.md and rig.json for the changes you accepted."
  # The finish screen: where to go next. `to` says what each option opens.
  finish:
    eyebrow: "Tutorial · Done"
    title: "That's Rig, End to End"
    lead: "Describe, design, build, measure, ship, on one real run. Now try it on something of yours."
    options:
      - {id: repo, label: "Rig Your Own Repo", text: "Attach a repo: Rig maps it, suggests parts, writes tasks and measures each change.", to: repo}
      - {id: lab, label: "Rig a Workflow", text: "No repo needed: build or pick a workflow and measure it on a bench.", to: lab}
      - {id: home, label: "Back to Home", text: "The start page, with your runs.", to: home}
  # When the recorded run doesn't match the example as it is now (a task or the skill changed
  # since): the numbers are still shown, said plainly.
  stale: "The example changed after this run was recorded, so these numbers are from the earlier version."
  # What the tutorial can't do from here, said once on the Measure step.
  recorded_note: "Recorded on {date} with {model}. This page only reads that record; it runs nothing."
  settings_title: "How It Was Run"
  settings:
    - "Model: {model_file}, served by {server}"
    - "Agent: Claude Code in a Docker sandbox, pointed at the local server; the \"with\" arm told to open the skill"
    - "Time limit: {timeout_factor}× each task's own, as for any local model"
---

# Tutorial

One small, plain example walked through the five steps, so a first visit sees what Rig does and
what a skill changes before touching anything of its own.

## Rules
- It starts only when the person clicks "Start the Tutorial" on Home. Nothing starts on its own,
  on a first visit or any other. Once finished, the button reads "Replay the Tutorial".
- It runs in its own space: it reads only the example shipped with the engine
  (`proving_ground/tutorial/`) and its recorded run. It never reads or writes the person's repos,
  runs, step, space or goal, in the engine or in the browser. The browser keeps one flag of its
  own: whether the tutorial was finished.
- The numbers are a real run's, never made up: `recorded.json`, written by
  `python -m proving_ground.tutorial.record` on a local model (free). The Rig score shown is the
  one the app computed for that run. If the example changed after the run, `stale` says so.
- The top bar is the app's own throughout: the tutorial adds no step to it and changes no label
  in it.
- It ends on a finish screen with three ways on: Rig your own repo (step 1, in a repo), Rig a
  workflow (step 1, in the Lab), Back to Home.

## The example
`pricetags`: a shop's shelf labels in Python. `price(cents)` already writes one price the house
way (`€1.234,56`). Each task asks for one more label (per unit, refunds, discounts, ranges,
sales, free items, per 100 g, reading a label back, prices with tax). The skill
`price-tags-style` holds the house rules for them. Some tasks the agent can get right from the
code alone (a total is just `price()` of a sum); the rest need rules only the skill says. That is
what skills are for: knowledge the agent doesn't have.
