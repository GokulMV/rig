---
name: starter-workflows
description: Ready-made agentic workflows per discipline (development, QA, product, design, data, DevOps, security, docs, support, research, marketing, leadership), and how a random workflow is built from steps, skills and models.
values:
  # think: plans, decides, reviews → the strongest model; do: produces the work → balanced;
  # check: runs checks, lists issues → fast unless it judges quality.
  model_for: {think: claude-opus-5-5, do: claude-sonnet-5-5, check: claude-haiku-5-5, judge: claude-sonnet-5-5}
  random_steps: [3, 6]          # a random workflow has this many steps
  random_skills_per_step: 1     # which skills fit a step: the match-skills skill
  drafts_kept: 8                # edited workflows kept in "Your drafts" when another one is opened
  prior: {plan: 2, check: 3, review: 3, loop: 2, judge: 1}   # starting guesses, points
  disciplines:
    development:
      label: Development
      steps:
        clarify: {name: Clarify the task, does: "Restate the task, list assumptions and open questions, and what done means.", kind: think, words: [requirements, spec, clarify]}
        spec: {name: Write a spec, does: "Write the expected behaviour with edge cases and examples.", kind: think, words: [spec, specification, requirements]}
        explore: {name: Explore the code, does: "Find the files, functions and tests the task touches.", kind: do, words: [codebase, search, explore, context]}
        plan: {name: Plan the change, does: "Plan the edits file by file and the checks that prove them.", kind: think, words: [plan, architecture]}
        test-first: {name: Write a failing test, does: "Write a test that fails until the task is done.", kind: do, words: [tdd, test, tests, testing]}
        implement: {name: Implement, does: "Make the change in small steps.", kind: do, words: [code, implement, refactor]}
        run-tests: {name: Run the tests, does: "Run the whole test suite and read every failure.", kind: check, words: [test, tests, ci, pytest]}
        review: {name: Review the diff, does: "Review the diff for correctness, scope and missing tests.", kind: think, words: [code-review, diff, pull-request, correctness]}
        document: {name: Document, does: "Update the docs and the changelog for what changed.", kind: do, words: [docs, documentation, changelog]}
        pr: {name: Write the PR, does: "Write the PR description: what, why, how it was tested.", kind: do, words: [pr, pull-request, git]}
      starters:
        - {id: feature, name: Build a feature, steps: [clarify, spec, plan, implement, run-tests, review, pr], loop: [run-tests, implement, 3]}
        - {id: bugfix, name: Fix a bug, steps: [explore, test-first, implement, run-tests, review], loop: [run-tests, implement, 3]}
        - {id: refactor, name: Refactor safely, steps: [explore, plan, implement, run-tests, review], loop: [run-tests, implement, 4], harness: [small-steps, guardrails]}
    qa:
      label: QA
      steps:
        read-spec: {name: Read the spec, does: "Read the requirements and list what must be true.", kind: think, words: [spec, requirements]}
        risks: {name: List the risks, does: "List where it is most likely to break, ranked.", kind: think, words: [risk, edge, testing]}
        cases: {name: Write test cases, does: "Write test cases for each risk: steps, data, expected result.", kind: do, words: [test, cases, qa, testing]}
        automate: {name: Automate, does: "Turn the cases into automated tests.", kind: do, words: [playwright, pytest, e2e, automation, test]}
        run: {name: Run them, does: "Run the tests and collect failures with evidence.", kind: check, words: [regression, e2e, ci, playwright]}
        explore: {name: Explore, does: "Explore the feature outside the cases, following a charter; log what's odd.", kind: do, words: [exploratory, explore, qa]}
        report: {name: Report, does: "Write the bug reports: steps to reproduce, expected, actual, severity.", kind: do, words: [bug, report, issues]}
      starters:
        - {id: test-plan, name: Test plan to automated suite, steps: [read-spec, risks, cases, automate, run, report], loop: [run, automate, 2]}
        - {id: regression, name: Regression sweep, steps: [risks, run, report]}
        - {id: exploratory, name: Exploratory session, steps: [read-spec, explore, report]}
    product:
      label: Product management
      steps:
        problem: {name: Frame the problem, does: "Write the problem, who has it, and how we know.", kind: think, words: [product, problem, discovery]}
        users: {name: Know the users, does: "Summarise the users and their jobs to be done from the evidence given.", kind: do, words: [users, research, persona]}
        feedback: {name: Cluster feedback, does: "Group the feedback into themes with counts and quotes.", kind: do, words: [feedback, research, synthesis]}
        requirements: {name: Write requirements, does: "Write the requirements as testable statements, must and should.", kind: do, words: [prd, requirements, spec]}
        metrics: {name: Define success, does: "Define success metrics with a baseline and a target.", kind: think, words: [metrics, analytics, kpi]}
        prioritise: {name: Prioritise, does: "Score the options by impact, confidence and effort; pick and say why.", kind: think, words: [prioritization, roadmap, rice]}
        review: {name: Critique it, does: "Argue the strongest case against the plan; fix what holds.", kind: judge, words: [review, critique]}
      starters:
        - {id: prd, name: Write a PRD, steps: [problem, users, requirements, metrics, review], loop: [review, requirements, 2]}
        - {id: feedback-roadmap, name: Feedback to roadmap, steps: [feedback, problem, prioritise, review]}
    design:
      label: Design
      steps:
        brief: {name: Read the brief, does: "List the goals, users and constraints.", kind: think, words: [design, brief]}
        heuristics: {name: Heuristic review, does: "Review the screens against usability heuristics; list issues with severity.", kind: judge, words: [ux, usability, heuristics, accessibility]}
        a11y: {name: Accessibility check, does: "Check contrast, targets, focus and labels; list failures with the rule.", kind: check, words: [accessibility, a11y, wcag]}
        propose: {name: Propose fixes, does: "Propose a concrete fix for each issue, smallest first.", kind: do, words: [design, ui, ux]}
        build: {name: Build it, does: "Turn the design into components that match it.", kind: do, words: [frontend, react, css, ui]}
      starters:
        - {id: ux-review, name: UX review, steps: [brief, heuristics, a11y, propose]}
        - {id: design-to-code, name: Design to code, steps: [brief, build, a11y], loop: [a11y, build, 2]}
    data:
      label: Data
      steps:
        question: {name: Sharpen the question, does: "Turn the ask into a precise question and the numbers that would answer it.", kind: think, words: [analytics, question]}
        query: {name: Query, does: "Write and run the queries.", kind: do, words: [sql, query, data, pandas]}
        validate: {name: Validate, does: "Check row counts, nulls and joins; recompute one number a second way.", kind: check, words: [data, validation, quality]}
        chart: {name: Chart, does: "Make the one chart that answers the question.", kind: do, words: [chart, visualization, plot]}
        narrative: {name: Write it up, does: "Write the answer in three sentences, then the caveats.", kind: do, words: [report, writing]}
      starters:
        - {id: analysis, name: Answer a data question, steps: [question, query, validate, chart, narrative], loop: [validate, query, 2]}
    devops:
      label: DevOps / SRE
      steps:
        triage: {name: Triage, does: "State the impact, the blast radius and the first safe action.", kind: think, words: [incident, triage, oncall]}
        mitigate: {name: Mitigate, does: "Apply the smallest safe mitigation and confirm it worked.", kind: do, words: [ops, rollback, kubernetes, deploy]}
        root-cause: {name: Find the root cause, does: "Follow the logs and changes back to the cause.", kind: think, words: [debug, logs, observability]}
        fix: {name: Fix, does: "Fix the cause and add a guard so it can't recur unnoticed.", kind: do, words: [fix, ci, infra]}
        verify: {name: Verify, does: "Check the fix with the same signal that caught the problem.", kind: check, words: [monitoring, test, verify]}
        postmortem: {name: Postmortem, does: "Write the postmortem: timeline, cause, actions, owners.", kind: do, words: [postmortem, incident]}
      starters:
        - {id: incident, name: Incident response, steps: [triage, mitigate, root-cause, fix, verify, postmortem], loop: [verify, fix, 2]}
        - {id: deploy-check, name: Pre-deploy check, steps: [triage, verify]}
    security:
      label: Security
      steps:
        model: {name: Threat model, does: "List assets, entry points and threats (STRIDE), ranked.", kind: think, words: [security, threat, stride]}
        scan: {name: Scan, does: "Run the dependency and static scans; collect findings.", kind: check, words: [security, audit, sast, dependencies]}
        triage: {name: Triage findings, does: "Separate real issues from noise, with the evidence for each.", kind: judge, words: [security, triage, vulnerability]}
        fix: {name: Fix, does: "Fix the real issues, smallest safe change first.", kind: do, words: [security, fix]}
        retest: {name: Re-test, does: "Re-run the scans and the tests.", kind: check, words: [test, audit]}
      starters:
        - {id: threat-model, name: Threat model, steps: [model, triage]}
        - {id: audit-fix, name: Audit and fix, steps: [scan, triage, fix, retest], loop: [retest, fix, 2]}
    docs:
      label: Docs
      steps:
        audience: {name: Audience, does: "Say who reads this and what they need to do after.", kind: think, words: [docs, writing]}
        outline: {name: Outline, does: "Outline the page: task first, then reference.", kind: think, words: [docs, outline]}
        draft: {name: Draft, does: "Write it plainly, with runnable examples.", kind: do, words: [docs, documentation, writing, readme]}
        verify: {name: Verify examples, does: "Run every example and command; fix what fails.", kind: check, words: [docs, test]}
        edit: {name: Edit, does: "Cut it by a third without losing a fact.", kind: judge, words: [writing, editing]}
      starters:
        - {id: how-to, name: Write a how-to, steps: [audience, outline, draft, verify, edit], loop: [verify, draft, 2]}
    support:
      label: Support
      steps:
        read: {name: Read the ticket, does: "Say what the customer wants and what they've tried.", kind: think, words: [support, ticket]}
        policy: {name: Check the policy, does: "Find the policy and limits that apply.", kind: do, words: [policy, support, refund]}
        answer: {name: Answer, does: "Write the reply: answer first, then the steps.", kind: do, words: [support, writing]}
        escalate: {name: Escalate if needed, does: "Escalate when the policy says so, with a summary.", kind: judge, words: [escalation, support]}
      starters:
        - {id: ticket, name: Handle a ticket, steps: [read, policy, answer, escalate]}
    research:
      label: Research
      steps:
        question: {name: Frame the question, does: "Write the question and what would count as an answer.", kind: think, words: [research]}
        gather: {name: Gather sources, does: "Collect sources and note what each says.", kind: do, words: [research, search, sources]}
        synthesise: {name: Synthesise, does: "Combine the findings; mark agreements and conflicts.", kind: think, words: [synthesis, research]}
        cite: {name: Check citations, does: "Check every claim against its source.", kind: check, words: [citations, research, fact-check]}
        summary: {name: Summarise, does: "Write the answer, the confidence, and what's unknown.", kind: do, words: [writing, summary]}
      starters:
        - {id: brief, name: Research brief, steps: [question, gather, synthesise, cite, summary], loop: [cite, synthesise, 2]}
    marketing:
      label: Marketing
      steps:
        audience: {name: Audience and message, does: "Say who it's for and the one thing they should take away.", kind: think, words: [marketing, positioning]}
        draft: {name: Draft, does: "Write the post or page.", kind: do, words: [copywriting, writing, content]}
        claims: {name: Check the claims, does: "Check every claim against the product facts given.", kind: check, words: [fact-check, claims]}
        critique: {name: Critique, does: "Critique as the target reader; fix what doesn't land.", kind: judge, words: [review, copy]}
      starters:
        - {id: launch, name: Launch post, steps: [audience, draft, claims, critique], loop: [critique, draft, 2]}
    leadership:
      label: Leadership
      steps:
        situation: {name: Situation, does: "Summarise the situation and the decision needed.", kind: think, words: [strategy, decision]}
        options: {name: Options, does: "List three options with costs and risks.", kind: think, words: [strategy, options]}
        decide: {name: Recommend, does: "Recommend one and the first step, with what would change the call.", kind: judge, words: [decision]}
        memo: {name: Memo, does: "Write the one-page memo.", kind: do, words: [writing, memo]}
      starters:
        - {id: decision-memo, name: Decision memo, steps: [situation, options, decide, memo]}
---

# Starter workflows

Ready-made workflows by discipline, and a **Random** button that builds a new one. Each step
has a role, what it does, a kind (`think`, `do`, `check`, `judge`) and the words used to attach
library skills to it.

## Models per step

By kind (`model_for`): thinking and deciding on the strongest model, doing on the balanced one,
mechanical checks on the fastest, judging quality on the balanced one. Any step can be changed.

## Skills per step

Library skills are attached as the match-skills skill says: by its open-source models once
they're on this machine, else by its word rules (the step's name and words are its headline,
what it does adds evidence, and its discipline says what it is about: a development step is
about code). At most `random_skills_per_step` per step, best first, each
with the reason it was picked.

## Random

1. Pick the discipline (the one chosen, or any).
2. Take `random_steps` steps from its pool **in the pool's order** (so a plan comes before the
   work and checks after it), always keeping at least one `do` step and, when the pool has one,
   one `check` or `judge` step after the last `do` step.
3. If there is a check after a do step, loop back from the check to that do step, at most 2 times.
4. Models by kind; skills by words; 0–1 harness technique from the workflow-patterns skill.
5. Never repeat a workflow already shown.

## Discipline and drafts

The Workflows panel's **Discipline** choice filters the starters (only that discipline's group,
and the Suggested lists drawn from it) and is the discipline a Random workflow is built for; the
browser remembers it. A workflow you edited is never lost by opening another: it is kept in
**Your drafts** (newest first, at most `drafts_kept`), and the switch says where it went, with
Undo. Removing a draft asks first.

## Priors

A starting guess until measured (`prior`, in points over doing the task in one go): a plan
step, a check, a review, a loop and a judge each add their share.

## Running

A workflow compiles like a stack (see workflow-patterns): one orchestration skill plus a
subagent per step on its model. Development, QA, data, DevOps and security workflows are checked
by commands (tests, scans). Product, design, docs, support, research, marketing and leadership
workflows produce documents: their checks need a judge with a rubric, which is the next piece to
build.
