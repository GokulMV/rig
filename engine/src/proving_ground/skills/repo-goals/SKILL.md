---
name: repo-goals
description: What a repo's goal is about (how the coding agent works, or what the app does), and the one-click goals Describe offers, each naming the metric it is about. Deterministic, no model.
values:
  # A goal is about the coding agent when it has one of these, as whole words in any case.
  # Otherwise it reads like what the app does, and Design says a blueprint may fit better.
  agent_words: [agent, agents, coding agent, coding, claude.md, agents.md, skill, skills, hook, hooks, mcp, prompt, prompts, bug, bugs, bugfix, bug fix, bug fixes, fix, fixes, fixing, fixed, review, reviews, reviewing, test, tests, testing, refactor, refactors, refactoring, pull request, pull requests, pr, prs, lint, linting, convention, conventions, token, tokens, cost, costs, cheaper, spend, spending, context, context window, latency, speed, faster, slower, turns, pass rate]
  # One-click goals for a repo, in Describe. id: kept with the saved goal; label: the button;
  # text: what fills the goal box; metric: what the goal is about, one of pass_rate, tokens,
  # cost, time (kept with the saved goal as its metric hint, for Measure to read).
  templates:
    - id: fewer-tokens
      label: Fewer Tokens at the Same Pass Rate
      text: "Use fewer tokens on each task in this repo, without lowering how many tasks the agent gets right."
      metric: tokens
    - id: lower-cost
      label: Lower Cost per Task
      text: "Spend less per task in this repo, at the same pass rate."
      metric: cost
    - id: fewer-wrong-fixes
      label: Fewer Wrong Bug Fixes
      text: "Fix bugs in this repo right the first time: fewer fixes that look done but break something else."
      metric: pass_rate
    - id: runs-tests
      label: Always Runs the Tests
      text: "Always run this repo's tests before finishing, and show their output."
      metric: pass_rate
    - id: conventions
      label: Follows Our Conventions
      text: "Follow this repo's conventions: code style, where things go, naming, and what not to touch."
      metric: pass_rate
    - id: faster
      label: Finishes Faster
      text: "Finish tasks in this repo faster, at the same pass rate."
      metric: time
  metrics: [pass_rate, tokens, cost, time]
---

# Repo goals

A repo's goal says what the coding agent should get better at. Design reads it to choose between
keeping the repo's design (a goal about the agent: its instructions, skills, checks, spend) and
starting from a blueprint (a goal about what the app does).

## Rules

- A goal is about the agent when it has any of `agent_words` as a whole word, any case. "Reduce
  the token usage" is about the agent; "Answer billing questions in three languages" is not.
- Describe offers `templates` as one-click goals for a repo. Picking one fills the goal box with
  its `text`; it is a draft like any typed goal until Save Goal.
- Saving a goal picked from a template keeps the template's `id` and its `metric` with it, while
  the box still starts with the template's text (adding words keeps it; rewriting it drops it).
  The project says them back as `goal_template` and `goal_metric`, for Measure to choose what to
  compare. A goal typed from scratch has neither.
