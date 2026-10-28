---
name: measurability
description: Whether Measure can test a thing on the canvas or a suggestion, and how each says so - one badge per card, one line per canvas row, and Measure's empty state. Deterministic, no model.
values:
  # Every badge is one of these states. label: the badge itself (short); says: the one line under
  # it, on the card's title and in its details; tone: its colour (positive, neutral, warning).
  states:
    runnable:
      label: Measurable
      tone: positive
      says: "Measure runs the tasks with it and without it, so the difference is its effect."
    same:
      label: In Every Run
      tone: neutral
      says: "Already in the repo, so every trial starts with it, with and without the change. To measure a change to it, edit it (or add a new one) and pick that as the change on Measure."
    not_yet:
      label: Not Measurable Yet
      tone: warning
      says: "Measure can't run this kind of change yet. It goes in the build brief."
    before_after:
      label: Changes the Code
      tone: neutral
      says: "Changes the app's code, so it is measured before and after: make the change on a branch (or leave it uncommitted), then Measure runs the tasks on the commit before and on the change. It goes in the build brief too."
    brief:
      label: Brief Only
      tone: neutral
      says: "Goes in the build brief as a task. There is nothing here for Measure to run."
    note:
      label: Diagram Note
      tone: neutral
      says: "Only fixes the diagram: nothing changes in the code, so there is nothing to measure."
    enables:
      label: Adds a Task
      tone: positive
      says: "Adds a task with a check, so Measure can test this step."
    step:
      label: Tasks Run Here
      tone: neutral
      says: "Measure runs this step's tasks; a skill linked to it is measured on them."
    check:
      label: Runs the Checks
      tone: neutral
      says: "The repo's tests, which a task's check can call. The same in every trial."
    app:
      label: App Part
      tone: neutral
      says: "Part of the app, not the agent: Measure doesn't change it. Change it on a branch, and Measure runs the tasks before and after the change."
    planned:
      label: Not Written Yet
      tone: neutral
      says: "Planned: BUILD.md asks for it. Write it first; then it can be measured."
    absent:
      label: Not in the Repo
      tone: neutral
      says: "The repo doesn't have one, so there is nothing to measure."
    not_installed:
      label: Not Installed
      tone: warning
      says: "Install a skill from it first (pick one in its details); then Measure can run it."
  # What Measure does with each kind of change today (models.TreatmentKind). The one switch: set a
  # kind to runnable once Measure runs it with and without, and every badge, row line and empty
  # state follows.
  treatments:
    skill: runnable
    loop: not_yet
    config: not_yet
    hook: runnable
    mcp: runnable
    instructions: runnable
  # The plural name of each kind, where a line lists what Measure runs ("Measure runs skills").
  kind_names:
    skill: skills
    loop: loops
    config: configs
    hook: hooks
    mcp: MCP servers
    instructions: CLAUDE.md files
  # The agent setup lane's blocks, by their label: the kind each one is, or a state.
  # What the repo already has is in both arms (same); a new or edited one is the change (its kind).
  setup_kinds:
    CLAUDE.md: same
    AGENTS.md: same
    Hooks: same
    MCP servers: same
    Test command: check
    Subagents: not_yet
    Skills: skill
  # Suggestions (improve-architecture kinds) that change the app's code.
  code_kinds: [split, merge, move, reconnect, remove]
  # What a suggestion adds, when it adds something to the agent rather than the app (its `adds`):
  # a treatment kind above, or one of these.
  adds:
    task: enables
    step: brief
  # One line per canvas row: what Measure tests there. {kinds} is the runnable kind names. What the
  # repo already has is in both arms, so the setup row names what you add or change, not the kinds.
  lanes:
    setup: "Measure tests what you add or change here"
    flow: "Measure runs the tasks on these steps"
    arch: "Measure doesn't run this row"
  # A code change measured before and after (state before_after): the tasks run on the base
  # commit ("without") and on the after side ("with": a commit or branch, or the uncommitted
  # working tree). Rig doesn't write the change. {base} and {after} are short names ("abc1234",
  # "split-auth (def5678)", "your uncommitted changes").
  before_after:
    mode: "A Code Change: Before and After"
    mode_agent: "An Agent Change: With and Without"
    lead: "Make the change on a branch (or leave it uncommitted), then measure it against the commit before. Rig doesn't write the change; you or your agent do."
    base: "Before: the commit"
    after: "After: the change"
    working_tree: "your uncommitted changes"
    compare: "Before: the code at {base}. After: the code at {after}. Each arm's tasks and checks run on its own copy of that code, and its agent setup (CLAUDE.md, skills, hooks) is whatever that code has."
    files: "{n} files differ"
    file: "1 file differs"
    same: "{after} has the same code as {base}, so a run would measure nothing. Make the change on a branch (or leave it uncommitted), then measure that."
    not_git: "This repo isn't a git repo with a commit, so there is no commit to measure before and after. Commit it with git first."
    unknown_ref: "{ref} isn't a commit or branch in this repo."
    name: "{base} → {after}"
    # Results and the Rig score card: the arms by their names, and what "after" and "before" are
    # in the score's lines (rig-score by_kind.before_after).
    arms: {with: After, without: Before}
    card: before vs after
    key: "Before vs after: \"after\" is the code at {after}, \"before\" the code at {base}."
    # Build's way to Measure from a suggestion (or a part it adds or takes away) that changes the
    # code: Measure opens on `mode`, with `for` naming the suggestion until another mode is picked.
    measure_it: Measure It
    for: "Measuring “{title}”: pick the branch, commit or uncommitted changes that make it as the After side."
    # Measure's step lead and the line under its run column's title follow the mode picked:
    # `agent` for an agent change (with and without), `code` for a code change.
    stage_lead:
      agent: "Choose the tasks, then run the change on them with and without it. Each result gets a Rig score."
      code: "Choose the tasks, then run them on the code before and after the change. Each result gets a Rig score."
    run_says:
      agent: "Every task runs twice, with and without the change, so the difference is the change's."
      code: "Every task runs twice, on the code before and after the change, so the difference is the change's."
  # Measure with nothing it can run.
  empty:
    title: Nothing Here Measure Can Run Yet
    lead: "Measure runs {kinds}, with and without, on your tasks. Add a skill on Build (from the library, or drag it onto the canvas), or add or edit a CLAUDE.md, hook or MCP server in the repo."
    go: Add a Skill on Build
---

# Measurability

A canvas that shows everything but never says what can be tested reads like a promise Measure
can't keep: a person accepts a suggestion to split a service, goes to Measure, and finds only a
list of skills. Every card and every suggestion says, in a word, whether Measure can test it, and
in one line why not when it can't.

## Rules

- One state per thing, from `states`. The badge shows `label`; its title and the details panel
  show `says`.
- A skill, hook, MCP server, loop, config or CLAUDE.md gets the state its kind has in
  `treatments`. That map is the one switch: when Measure learns to run a kind, set it to
  `runnable` and every badge, row line and Measure's empty state say so.
- The agent setup lane's blocks are read by label (`setup_kinds`). One the repo doesn't have is
  `absent`; a planned one (a CLAUDE.md to write) is `planned`.
- A workflow step is `step`: Measure runs its tasks. A part of the app's architecture is `app`;
  one a suggestion adds or takes away is `before_after`.
- A card for something not installed yet (a skill suggested when tasks were written, a GitHub
  repo or one of its parts) is `not_installed`.
- A suggestion that only fixes the diagram (build-spec: `diagram_only`) is a `note`. One that
  adds something to the agent (`adds`) takes that kind's state (`treatments`, else `adds`). One
  whose kind is in `code_kinds`, or that adds or removes parts, is `before_after`. Anything else
  goes in the brief (`brief`).
- Each canvas row carries one line (`lanes`) saying what Measure tests there.
- Measure with nothing to run says why and links to Build (`empty`).
- A `before_after` change is measured on two snapshots of the repo (`before_after`): the base
  commit is the "without" arm and the after side (a commit, a branch, or the uncommitted
  working tree) the "with" arm. Each is exported from git (`git archive` of that commit, or of a
  tree written from a scratch index for the working tree), never the live checkout, and each
  arm's tasks and checks run on its own copy. An after side with the same code as the base
  (`.proving-ground/` aside) is refused (`same`): it would measure nothing. Rig doesn't write
  the change; the person or their agent makes it, then measures it. From the command line it is
  `rig run --before <ref> --after <ref>` (after left out: the working tree), with the same
  refusals.
- A `before_after` suggestion on Build, and a part one adds or takes away, carries `measure_it`:
  it opens Measure on the before-and-after mode with a line (`for`) naming the suggestion, so
  the badge is never a dead end.
