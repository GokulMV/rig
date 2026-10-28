---
name: tutorial-tokens
description: "The tutorial's second track, Rig your own repo: fewer tokens - a tiny repo (textkit) walked through the five steps in repo mode, with a token-saving skill as the change and a real recorded run scored on tokens per solved task. Each step says what to do on your own repo."
values:
  # Home: the second entry, under the first tutorial's.
  home:
    title: "Rig Your Own Repo: Fewer Tokens"
    title_done: "The Repo Tutorial: Fewer Tokens"
    lead: "The same five steps in repo mode, on a tiny example repo: which goal to pick, where a skill or CLAUDE.md goes, what tasks to write, why a token run needs about {need} pairs, and how to read the result. Each step says what to do on yours."
    start: "Start the Repo Tutorial"
    replay: "Replay the Repo Tutorial"
  eyebrow: "Repo tutorial · step {step} of 5"
  leave: "Leave the Tutorial"
  stepper: "Repo tutorial steps"
  # Each step: what was done on the example (lead and its own fields), then `yours`: what to do
  # on your own repo, in order. {…} are filled from the example, the run and the app's own words
  # (the goal template, the badges, the metric), so they can't drift from what the app says.
  yours_title: "On Your Repo"
  steps:
    - id: describe
      title: "Describe: Pick the Goal, and Say It in Plain Words"
      lead: "In repo mode the goal is what the coding agent should get better at in your repo. Here it is the one-click goal \"{template}\": the example repo {example} stays as it is, and the agent should spend fewer tokens on it without getting fewer tasks right."
      goal_title: "Goal"
      goal: "{template_text}"
      template: "Picked from \"Start from one:\" as \"{template}\". Picking it also tells Measure to score the run on {metric_name}."
      repo: "Where it lives: the repo {example}"
      tasks_line: ".proving-ground/scenarios/ ({tasks} tasks)"
      yours:
        - "Pick \"My Repo\" and add your repo (\"Add Your Repo\": its folder on this Mac)."
        - "Under the goal box, click \"{template}\" after \"Start from one:\". It fills the box with: {template_text}"
        - "Add your own words after it if you like (\"in the billing service\", \"on bug fixes\"): the goal keeps its token metric as long as it still starts with the template's text. There is no separate use case or scenario to fill in: the goal is the use case, and the tasks (Measure) are the scenarios."
        - "Click Save Goal. Until you do, it is a draft in this browser only."
      note: "A goal typed from scratch works too, but Measure then starts on the pass rate; pick Tokens there yourself."
    - id: design
      title: "Design: Keep Your Design"
      lead: "Saving tokens is about the agent, not the app, so there is nothing to redesign: the car stays the same and the part being tested is one skill, {skill}. It tells the agent to read only what the task names, check once and answer in one line."
      car: "The Car"
      car_text: "{example} as it is, with Claude Code as the agent. Nothing in the code changes."
      part: "The Part Being Tested"
      part_text: "The skill {skill}, in .claude/skills/{skill}/. The \"with\" arm has it; the \"without\" arm never sees it."
      yours:
        - "Click \"Keep <your repo>'s Design\". A goal about tokens is about the agent, so that card is marked Recommended."
        - "Leave \"Start from a Blueprint Instead\" folded: blueprints are for what the app does, and they change the code."
        - "The part you test is a skill, a CLAUDE.md, a hook or an MCP server: something the agent reads or runs. This example uses a skill; a CLAUDE.md with the same rules is the other natural choice (it is loaded on every turn, with no skill to open)."
      note: "An agent you accepted on Design (a ranked architecture) is a blueprint: it changes the app, so it goes in the build brief rather than in a with-and-without run."
    - id: build
      title: "Build: Put the Skill on the Canvas, and Read the Badges"
      lead: "Build shows your repo's agent setup as a canvas. The skill {skill} goes in its Skills block and is marked {badge_runnable}: Measure can run the tasks with it and without it. Everything else on the canvas says, in one badge, whether Measure can test it."
      places_title: "Where Things Go, and What Their Badges Mean"
      # One row per kind of thing on your canvas: what it is, where it shows, its badge.
      places:
        - {what: "A new skill (like {skill})", where: "Agent setup · Skills. Drag it from the Library, or its + button.", badge: "{badge_runnable}", tone: positive}
        - {what: "Your CLAUDE.md, hooks and MCP servers as they are", where: "Agent setup · CLAUDE.md, Hooks, MCP servers", badge: "{badge_same}", tone: neutral}
        - {what: "A CLAUDE.md, hook or MCP server you add or edit", where: "The same blocks; picked as the change on Measure", badge: "{badge_runnable}", tone: positive}
        - {what: "A suggestion you accepted that adds a skill or a task", where: "Canvas · With Accepted", badge: "{badge_runnable} / {badge_enables}", tone: positive}
        - {what: "A suggestion you accepted that splits, merges or moves code", where: "Canvas · With Accepted", badge: "{badge_before_after}", tone: warning}
        - {what: "A skill suggested from GitHub, not installed yet", where: "Library · Picked for This Repo", badge: "{badge_not_installed}", tone: warning}
      skill_title: "The Skill, as It Goes in the Repo"
      yours:
        - "Open Library and drag your token-saving skill onto the canvas (or click its +). It lands in Agent setup · Skills with the badge {badge_runnable}."
        - "Your existing CLAUDE.md, hooks and MCP servers say {badge_same}: both arms start with them, so they aren't what is being measured. To measure a change to your CLAUDE.md, edit it (don't commit) or add a new one, then pick it as the change on Measure."
        - "Switch the canvas to \"With Accepted\" to see the suggestions you accepted. Only the ones marked {badge_runnable} or {badge_enables} can go in this run; {badge_before_after} and {badge_brief} go in the build brief on Ship."
      note: "A hook or an MCP server that saves tokens (one that trims tool output, say) is measured exactly the same way: it is the change, the rest is the same."
    - id: measure
      title: "Measure: Tasks with Checks, Then a Run Scored on Tokens"
      lead: "Each task ran {repeats} times with the skill and {repeats} times without, each in its own Docker sandbox: {n} pairs. Scored on {metric_name}, a saving only counts once the pass rate is shown to be at most {margin} pts worse, and that takes about {need} pairs."
      # Tasks live on Measure in the app ("Tasks to Measure On"), so they come first here.
      tasks_heading: "First, the Tasks"
      tasks_lead: "Tokens per solved task only counts tasks that pass, so every task needs a check: a command that exits 0 when the job is done right. Each of these {tasks} tasks asks for one small helper in a named file, and its check runs the tests and calls the new function."
      tasks_title: "Tasks"
      check_title: "One Task's Check"
      tasks_yours:
        - "Under \"Tasks to Measure On\": \"+ Add Task\" for one you write, or \"Generate tasks from the repo and docs\" to have Rig draft them from your code."
        - "Write the jobs you hand the agent every day: fix this bug, add this endpoint, rename this field. A token saving on tasks you never give it saves nothing."
        - "A real check runs your own tests, then asserts the new behaviour, like the one shown here. On your repo: `pytest tests/test_invoice.py -q`, `npm test -- billing`, `go test ./billing/...`, followed by a line that calls the new code and compares its answer."
        - "Click \"Approve Check\" on each one. A check that already passes on the untouched repo measures nothing: Rig runs it first and says so."
        - "Keep them small and sure: a task the agent fails at random makes the pass-rate guard hard to clear."
      run_heading: "Then, the Run"
      task: "Task"
      without: "Without"
      with: "With"
      passed: "passed"
      tokens: "tokens"
      per_trial: "median tokens per trial"
      tokens_note: "Tokens: the median per trial, in + out as the agent reported them. The score counts them per solved task, over all the pairs."
      total: "Passed"
      metric_title: "{metric_name}"
      guard_title: "The Guard: The Pass Rate"
      score_title: "The Rig Score"
      yours:
        - "\"Change to measure\": pick your skill (or the CLAUDE.md, hook or MCP server you edited)."
        - "\"Run on\": your signed-in agent, or a local model you added under Local Models (free: no budget to set, and the skill nudge starts on). This run was on one."
        - "\"Score the run on\": Tokens. A goal from the template has picked it already (\"Picked from your goal.\")."
        - "Size: Full. A pilot is a few pairs, far short of the about {need} the guard needs, so it can never credit a saving. With 10 tasks, about 4 runs of each."
        - "\"Tell the agent to open the skill in the prompt\": off is real use (the agent has to find the skill); on makes sure it reads it, at the price of a turn spent opening it. This run had it on, as a small model never opens a skill it is only offered."
        - "Review the Run: on your agent it shows the price and how many pairs the budget buys before anything starts; on a local model it says the run is free."
      note: "Tokens are in + out as the agent reports them, cached input included: every turn sends the whole conversation again, so fewer turns is most of a saving."
    - id: ship
      title: "Ship: Read the Result, Then Keep Only What Earned It"
      lead: "The skill scored {score} out of 100: {label}. The verdict: {verdict}. {reason}"
      result_title: "What It Rests On"
      without_arm: "Without the skill"
      with_arm: "With the skill"
      brief_title: "The Build Brief, for This Example"
      # The brief follows the verdict: only a change that helps goes in it as one to make.
      brief_helps:
        - "Add the skill {skill} to the agent's skills (.claude/skills/{skill}/)."
        - "Measured on {n} pairs with {model}: {tok_with} tokens per solved task with it, {tok_without} without ({change}); {with_} of {n} passed with it, {without} of {n} without."
        - "Rig score {score}/100: {label}."
        - "Measure again when the model or the tasks change."
      brief_not:
        - "Leave the skill {skill} out: it hasn't earned its place."
        - "Measured on {n} pairs with {model}: {tok_with} tokens per solved task with it, {tok_without} without ({change}); {with_} of {n} passed with it, {without} of {n} without."
        - "Rig score {score}/100: {label}."
        - "To try again: change the skill (or put its rules in CLAUDE.md, which costs no turn to open) and measure that."
      yours:
        - "Read the verdict line first, then the guard: a cut in tokens with the guard \"past the margin\" is not a saving yet, it's \"Can't Tell Yet\". Run more pairs, or make the tasks surer."
        - "\"Which design\": As It Is, or With the Accepted Suggestions. Pick the second only if you accepted any on Build."
        - "\"Save to the Repo\" writes BUILD.md (the brief, with the evidence beside each change) and rig.json (the same as data). Hand BUILD.md to any coding agent."
        - "A change that didn't earn its place stays out of the brief. A \"Not Proven\" is an answer too: it says what would settle it."
      note: "{next}"
  finish:
    eyebrow: "Repo tutorial · Done"
    title: "Now Do It on Your Repo"
    lead: "Goal from the template, keep your design, the change on the canvas, tasks with checks, Tokens and Full on Measure, then Ship what earned it."
    options:
      - {id: repo, label: "Rig Your Own Repo", text: "Step 1 in repo mode: add your repo and pick the goal.", to: repo}
      - {id: first, label: "The First Tutorial", text: "One skill measured on the pass rate, on a price-tags example.", to: first}
      - {id: home, label: "Back to Home", text: "The start page, with your runs.", to: home}
  stale: "The example changed after this run was recorded, so these numbers are from the earlier version."
  not_recorded: "No run has been recorded for this example yet, so there are no numbers to show. Record one with `python -m proving_ground.tutorial.record --track tokens` on a local model."
  recorded_note: "Recorded on {date} with {model}, in {took}. This page only reads that record; it runs nothing."
  settings_title: "How It Was Run"
  settings:
    - "Model: {model_file}, served by {server}"
    - "Agent: Claude Code in a Docker sandbox, pointed at the local server; the \"with\" arm told to open the skill"
    - "Run through the same engine as a repo run, scored on {metric_name} (prepare_experiment with the run's metric set to tokens). In the app, pick a local model in Measure's \"Run on\" to run yours the same way, for free."
    - "Time limit: {timeout_factor}× each task's own, as for any local model"
---

# Tutorial: fewer tokens on your repo

The first tutorial shows what Rig does on one skill and the pass rate. This one answers what a
person asks next, on their own repo: "my goal is fewer tokens; where does the change go, what do
I pick, what tasks do I write?" Each step does it on a tiny example and then says what to do on
yours, in the app's own words.

## Rules
- Same isolation as the first tutorial: it reads only `proving_ground/tutorial/tokens/` and the
  app's skills, never the person's repos, runs, step, space or goal. The browser keeps one flag
  of its own: whether this track was finished.
- The numbers are a real run's: `tokens/recorded.json`, written by
  `python -m proving_ground.tutorial.record --track tokens` on a local model (free). The Rig
  score is the one the app computed. Whatever the run shows (a saving, none, or "Can't Tell
  Yet") is what the pages say; no number is ever typed in by hand. With no run recorded, the
  Measure and Ship steps say so (`not_recorded`).
- Labels the app shows elsewhere (the goal template, the badges, the metric's name, the guard's
  pairs and margin) are filled from their own skills, never repeated here.
- The steps are the app's five. Tasks are part of Measure, as in the app ("Tasks to Measure
  On"), and come first on it.

## The example
`textkit`: three small modules of text helpers, tests, a README and design notes. Each task
names the file to change and asks for one helper. The skill `lean-context` tells the agent to
read only that file, edit once, check once and answer in one line. The question is whether that
spends fewer tokens per solved task without solving fewer.
