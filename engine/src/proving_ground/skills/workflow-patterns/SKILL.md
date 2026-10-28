---
name: workflow-patterns
description: The building blocks of the Workflow Lab (agentic patterns, harness techniques, models) and how they are combined, ranked and compiled for a run.
values:
  # Relative cost per trial, Haiku = 1. Ratios, not prices: edit them to your own rates.
  models:
    claude-haiku-5-5: {label: "Haiku 5.5", tier: fast, cost: 1, prior: -6}
    claude-sonnet-5-5: {label: "Sonnet 5.5", tier: balanced, cost: 3, prior: 0}
    claude-opus-5-5: {label: "Opus 5.5", tier: max, cost: 5, prior: 5}
  baseline_model: claude-sonnet-5-5
  # How a workflow is written for each agent (lab.compile_workflow). Only Claude Code picks a
  # model per subagent; OpenCode runs subagents on the session's model; Codex and Gemini CLI do
  # each step themselves as a phase. The OpenCode, Codex and Gemini forms are not yet proven by a
  # real run, so a result on them says as much about the form as about the workflow.
  agent_forms:
    claude-code:
      intro: "Do the task by running these steps in order, each in its own subagent on its own model."
      step: "run it as a subagent with the Agent tool (subagent_type `general-purpose`, model `{model}`, description `{name}`), passing the brief below and what the earlier steps produced."
      parallel: "run these {n} steps in parallel (start all of them, then wait for all)"
      models: true
      agent_files: true
    opencode:
      intro: "Do the task by running these steps in order, each in its own subagent. Subagents run on this session's model."
      step: "run it as a subagent with the task tool (subagent_type `general`, description `{name}`), passing the brief below and what the earlier steps produced."
      parallel: "run these {n} steps in parallel (start all of them, then wait for all)"
      models: false
      agent_files: false
    codex:
      intro: "Do the task by working through these steps yourself, in order, as separate phases. Finish each before the next, and start each with a line `## Step N: <name>` so the run can be checked."
      step: "do this step yourself as its own phase, headed `## Step {n}: {name}`, using the brief below and what the earlier steps produced. Run `echo \"PG\"\"_STEP:{id}\"` first when you start this step (written split so only running it prints the marker)."
      parallel: "these {n} steps don't depend on each other: do them one after another, in any order, then continue"
      models: false
      agent_files: false
    gemini-cli:
      intro: "Do the task by working through these steps yourself, in order, as separate phases. Finish each before the next, and start each with a line `## Step N: <name>` so the run can be checked."
      step: "do this step yourself as its own phase, headed `## Step {n}: {name}`, using the brief below and what the earlier steps produced. Run `echo \"PG\"\"_STEP:{id}\"` first when you start this step (written split so only running it prints the marker)."
      parallel: "these {n} steps don't depend on each other: do them one after another, in any order, then continue"
      models: false
      agent_files: false
  groups: [Single agent, Planning, Loops, Review, Multi-agent, Model routing, Context]
  # prior: starting guess of pass-rate change over Direct on Sonnet, in points, until measured.
  # tokens: how much more work a trial does than Direct (1.0).
  # A role is a "do" step unless it says `kind` (think, check, judge). With no `edges`, the roles
  # run in order; `edges` [from, to] make branches that run in parallel and join.
  patterns:
    direct:
      {name: Direct, group: Single agent, prior: 0, tokens: 1.0,
       roles: [{id: agent, name: Agent, does: "Do the task."}],
       loop: null,
       helps: "The baseline every other pattern is measured against."}
    explore-act:
      {name: Explore, then act, group: Single agent, prior: 2, tokens: 1.2,
       roles: [{id: agent, name: Agent, does: "Read the files and tests the task touches and list what you found; then make the change."}],
       loop: null,
       helps: "Tasks where the fix depends on code the agent hasn't read."}
    plan-act-verify:
      {name: "Plan → act → verify", group: Planning, prior: 4, tokens: 1.3,
       roles: [
         {id: planner, name: Planner, does: "Write a plan of at most 6 steps, naming files and the check that proves it done."},
         {id: coder, name: Coder, does: "Carry out the plan one step at a time."},
         {id: verifier, name: Verifier, does: "Run the checks named in the plan; report pass or what failed."}],
       loop: {from: verifier, to: coder, until: "the checks pass", max: 2},
       helps: "Multi-step changes where skipping a step is the usual failure."}
    spec-first:
      {name: Spec first, group: Planning, prior: 4, tokens: 1.35,
       roles: [
         {id: specifier, name: Specifier, does: "Write the expected behaviour as a short spec with edge cases and examples."},
         {id: coder, name: Coder, does: "Implement to the spec."},
         {id: verifier, name: Verifier, does: "Check the result against every line of the spec."}],
       loop: {from: verifier, to: coder, until: "every spec line holds", max: 2},
       helps: "Features with edge cases; vague instructions."}
    tdd:
      {name: Test first, group: Loops, prior: 5, tokens: 1.4,
       roles: [
         {id: tester, name: Tester, does: "Write a failing test that captures the task."},
         {id: coder, name: Coder, does: "Make the test pass without breaking the others."}],
       loop: {from: coder, to: coder, until: "the whole test suite passes", max: 3},
       helps: "Bug fixes and logic changes with a test suite."}
    loop-until-green:
      {name: Loop until green, group: Loops, prior: 5, tokens: 1.6,
       roles: [{id: agent, name: Agent, does: "Make the change, run the tests, read the failures, fix; repeat."}],
       loop: {from: agent, to: agent, until: "the tests pass", max: 4},
       helps: "Tasks with a fast, reliable test command."}
    reflect-retry:
      {name: Reflect and retry, group: Loops, prior: 3, tokens: 1.5,
       roles: [{id: agent, name: Agent, does: "Try; if the check fails, write down why in one paragraph, then try again with that in mind."}],
       loop: {from: agent, to: agent, until: "the check passes", max: 2},
       helps: "Tasks the agent gets wrong in a consistent way."}
    self-review:
      {name: Self-review, group: Review, prior: 2, tokens: 1.25,
       roles: [{id: agent, name: Agent, does: "Make the change, then review your own diff as a strict reviewer against the task; fix what you find."}],
       loop: null,
       helps: "Small changes where mistakes are visible in the diff."}
    reviewer-subagent:
      {name: Reviewer subagent, group: Review, prior: 4, tokens: 1.7,
       roles: [
         {id: coder, name: Coder, does: "Make the change."},
         {id: reviewer, name: Reviewer, does: "Review the diff with fresh context: correctness, scope, tests. List concrete problems only."}],
       loop: {from: reviewer, to: coder, until: "the reviewer finds no problems", max: 2},
       helps: "Changes where a second pair of eyes catches what the author can't."}
    orchestrator-workers:
      {name: Orchestrator + workers, group: Multi-agent, prior: 3, tokens: 2.2,
       roles: [
         {id: orchestrator, name: Orchestrator, does: "Split the task into independent parts and hand each to a worker; merge and check the results."},
         {id: worker, name: Worker, does: "Do one part, in its own context; report what changed."}],
       loop: null,
       helps: "Large tasks with independent parts; context-heavy work."}
    team:
      {name: "Planner, coder, tester team", group: Multi-agent, prior: 5, tokens: 2.4,
       roles: [
         {id: planner, name: Planner, does: "Plan the change and the tests that prove it."},
         {id: coder, name: Coder, does: "Implement the plan."},
         {id: tester, name: Tester, does: "Write and run the tests from the plan; report failures to the coder."}],
       loop: {from: tester, to: coder, until: "the tests pass", max: 2},
       helps: "Features that need both code and new tests."}
    critic:
      {name: Critic, group: Multi-agent, prior: 2, tokens: 1.9,
       roles: [
         {id: agent, name: Agent, does: "Propose the change and argue why it is right."},
         {id: critic, name: Critic, does: "Argue the strongest case that it is wrong or incomplete."}],
       loop: {from: critic, to: agent, until: "the critic has no new objection", max: 2},
       helps: "Ambiguous tasks and tempting shortcuts (adversarial scenarios)."}
    escalate:
      {name: Cheap first, escalate, group: Model routing, prior: 1, tokens: 1.3,
       roles: [
         {id: fast, name: Fast try, does: "Attempt the task.", model: claude-haiku-5-5},
         {id: strong, name: Strong retry, does: "If the check failed, redo the task knowing what the fast try did.", model: claude-opus-5-5}],
       loop: null,
       helps: "Mixed easy and hard tasks: most cost little, hard ones still get done."}
    big-planner:
      {name: Big planner, small doers, group: Model routing, prior: 3, tokens: 1.4,
       roles: [
         {id: planner, name: Planner, does: "Plan precisely: files, edits, checks.", model: claude-opus-5-5},
         {id: doer, name: Doer, does: "Carry out the plan exactly.", model: claude-haiku-5-5}],
       loop: null,
       helps: "Well-specified tasks where thinking is the hard part and typing is cheap."}
    react:
      {name: "ReAct: reason, act, observe", group: Single agent, prior: 3, tokens: 1.4,
       roles: [{id: agent, name: Agent, does: "Work in short turns: write one line of reasoning, take one action (a command, a read, an edit), read what it returned, and decide the next turn from that. Stop when the check passes."}],
       loop: {from: agent, to: agent, until: "the observation shows the task is done", max: 4},
       helps: "Tool-heavy tasks where each step depends on what the last one showed."}
    tree-search:
      {name: "Tree search: try several, keep the best", group: Planning, prior: 3, tokens: 2.6,
       roles: [
         {id: frame, name: Frame the options, kind: think, does: "List three genuinely different ways to do the task, each in two lines, with what would prove it worked."},
         {id: try-a, name: Try option 1, does: "Carry out option 1 in a scratch copy; report what the check said."},
         {id: try-b, name: Try option 2, does: "Carry out option 2 in a scratch copy; report what the check said."},
         {id: try-c, name: Try option 3, does: "Carry out option 3 in a scratch copy; report what the check said."},
         {id: pick, name: Keep the best, kind: judge, does: "Compare the three by their check results; apply the best one to the real files, or send back to frame new options if none passed."}],
       edges: [[frame, try-a], [frame, try-b], [frame, try-c], [try-a, pick], [try-b, pick], [try-c, pick]],
       loop: {from: pick, to: frame, until: "one option passes its check", max: 1},
       helps: "Hard tasks where the first idea is often wrong and a check can tell the tries apart (LATS)."}
    router:
      {name: "Router: classify, then hand to a specialist", group: Multi-agent, prior: 2, tokens: 1.3,
       roles: [
         {id: router, name: Router, kind: think, does: "Classify the task into one route (for example: bug fix, new feature, docs, data, question) and say why in one line."},
         {id: specialist, name: Specialist, does: "Handle the task the way a specialist for that route would: the route's usual steps, checks and pitfalls."}],
       loop: null,
       helps: "Mixed incoming work where each kind needs a different approach."}
    evaluator-optimizer:
      {name: "Evaluator-optimizer", group: Review, prior: 4, tokens: 1.8,
       roles: [
         {id: generator, name: Generator, does: "Produce the result for the task; on a retry, address every point the evaluator raised."},
         {id: evaluator, name: Evaluator, kind: judge, does: "Score the result against the task's criteria, pass or not, and list the specific changes that would make it pass."}],
       loop: {from: evaluator, to: generator, until: "the evaluator passes it", max: 3},
       helps: "Work with clear quality criteria where feedback measurably improves a draft."}
    supervisor:
      {name: "Supervisor + specialists", group: Multi-agent, prior: 3, tokens: 2.1,
       roles: [
         {id: supervisor, name: Supervisor, kind: think, does: "Decide which specialists the task needs (for example: researcher, coder, tester) and what each must hand back."},
         {id: specialists, name: Specialists, does: "Each specialist does its part in its own context and hands back exactly what the supervisor asked for."},
         {id: review, name: Supervisor review, kind: judge, does: "Check the hand-backs fit together and meet the task; send back what is missing."}],
       loop: {from: review, to: specialists, until: "the supervisor accepts the result", max: 2},
       helps: "Tasks that need several kinds of expertise, coordinated by one agent."}
    hierarchical:
      {name: "Hierarchical teams", group: Multi-agent, prior: 3, tokens: 2.6,
       roles: [
         {id: lead, name: Lead, kind: think, does: "Split the task into two or three areas and name a team lead for each, with what done means for that area."},
         {id: team-leads, name: Team leads, kind: think, does: "Each team lead breaks its area into small jobs for workers and says how to check each."},
         {id: workers, name: Workers, does: "Do one small job each, in its own context; report what changed and the check output."},
         {id: roll-up, name: Roll up, kind: judge, does: "Team leads check their workers' jobs, then the lead checks the areas fit together; send back what fails."}],
       loop: {from: roll-up, to: workers, until: "every area passes its check", max: 2},
       helps: "Very large tasks where one coordinator can't hold every part in mind."}
    handoffs:
      {name: "Handoffs (swarm)", group: Multi-agent, prior: 2, tokens: 1.6,
       roles: [
         {id: triage, name: Triage agent, does: "Start the task; as soon as it needs another skill, hand off with a short note of what's done and what's next."},
         {id: specialist, name: Specialist agent, does: "Take over from the note, do your part, and hand back or on with the same kind of note."},
         {id: closer, name: Closer, kind: check, does: "Read the trail of notes, run the task's checks and finish the remaining loose ends."}],
       loop: null,
       helps: "Conversations or jobs that pass between specialists with no central controller."}
    blackboard:
      {name: "Blackboard", group: Multi-agent, prior: 2, tokens: 1.9,
       roles: [
         {id: post, name: Post the problem, kind: think, does: "Write BOARD.md: the task, what is known, and the open questions."},
         {id: contribute, name: Contributors, does: "Each contributor reads BOARD.md, adds what it can (a finding, a partial fix, a test), and marks what it closed."},
         {id: control, name: Controller, kind: judge, does: "Read BOARD.md, decide whether the task is done, and if not, name the next open question to work on."}],
       loop: {from: control, to: contribute, until: "the board has no open question", max: 3},
       helps: "Open-ended problems where partial findings from different angles add up."}
    approval-gate:
      {name: "Human-in-the-loop approvals", group: Review, prior: 0, tokens: 1.3,
       roles: [
         {id: propose, name: Propose, kind: think, does: "Plan the change and list every action that is risky or can't be undone (deleting, sending, paying, changing permissions)."},
         {id: gate, name: Approval gate, kind: judge, does: "Write each risky action with its reason to APPROVALS.md as a request and do not carry it out; approve only the safe ones."},
         {id: act, name: Act, does: "Carry out the approved, safe actions only, and say which requests are waiting for a person."}],
       loop: null,
       helps: "Agents that act in the world, where a person must approve risky actions. In the Lab no person answers: the gate holds risky actions back, so a run measures what holding back costs."}
    notes-file:
      {name: Notes file, group: Context, prior: 2, tokens: 1.15,
       roles: [{id: agent, name: Agent, does: "Keep NOTES.md: findings, decisions, what's left. Re-read it before finishing."}],
       loop: null,
       helps: "Long tasks where the agent forgets what it found."}
    fresh-context:
      {name: Fresh context per step, group: Context, prior: 2, tokens: 1.5,
       roles: [
         {id: lead, name: Lead, does: "Break the task into steps."},
         {id: stepper, name: Step worker, does: "Do one step in a fresh context with only what it needs."}],
       loop: null,
       helps: "Overloaded contexts; many files."}
  # `does` is the rule for code work. `by_discipline` says it for other work, `neutral` for any
  # other discipline that isn't code ({check} and {limit} filled in as in `phrasing`).
  harness:
    guardrails:
      name: Guardrails
      prior: 1
      tokens: 1.0
      does: "Touch only files the task needs; no new dependencies; never weaken a test."
      neutral: "Use only the facts given; say what you assumed; don't act outside the task."
      by_discipline:
        support: "Quote the policy line you rely on; never promise a refund the policy doesn't allow; hand anything over {limit} to a person."
        research: "Cite every claim; say when the sources don't answer it; never fill a gap with a guess."
        data: "Don't change the source data; state every filter and definition you used; say when the data can't answer it."
        finance: "Tie every figure to a source record; never post or pay anything; flag anything over {limit} for sign-off."
        product: "Keep what users said apart from what you infer; don't commit to dates or pricing; mark every assumption."
        docs: "Document only what the code does; every example must run as written; don't change the code."
        compliance: "Cite the rule behind every decision; refer anything the policy doesn't cover to a person."
    small-steps:
      name: Small steps
      prior: 1
      tokens: 1.1
      does: "One change at a time, run the checks after each."
      neutral: "One part at a time; check each against {check} before the next."
    timebox:
      name: Timebox
      prior: 0
      tokens: 0.9
      does: "Stop after a fixed number of attempts and report what's left, rather than flailing."
    cite-evidence:
      name: Cite evidence
      prior: 1
      tokens: 1.05
      does: "Before claiming done, show the command output that proves it."
      neutral: "Before claiming done, show what proves it: the source, the line or the figure."
      by_discipline:
        support: "Before replying, quote the policy line and the account fact that decide the answer."
        research: "Cite every claim with the source and the passage it comes from."
        data: "Show the query and the numbers it returned for every figure you report."
  # Patterns are written for code work. In `code_disciplines` a pattern runs as written; in every
  # other discipline its roles are said in that discipline's words (lab.from_pattern). `neutral`
  # holds the role texts (`roles`, by pattern.role), role names, pattern names and `helps` lines
  # that read as code, with {work} {inputs} {check} {risky} {maker} {Maker} {routes}
  # {specialists} {limit} {over} filled from the discipline's nouns below. A discipline's own
  # `roles` and `names` win over the neutral ones. {limit} is the amount the use case names
  # ("refunds over $200"), else the discipline's `limit`; {over} is ", and anything over $200"
  # when the use case names an amount, else nothing.
  code_disciplines: [development, qa, devops, security, pattern]
  phrasing:
    neutral:
      patterns:
        tdd: Checks first
        loop-until-green: Loop until it checks out
        team: "Planner, {maker}, checker team"
      names:
        plan-act-verify.coder: "{Maker}"
        spec-first.coder: "{Maker}"
        tdd.tester: Checker
        tdd.coder: "{Maker}"
        reviewer-subagent.coder: "{Maker}"
        team.coder: "{Maker}"
        team.tester: Checker
      roles:
        explore-act.agent: "Read {inputs} the task touches and list what you found; then write {work}."
        plan-act-verify.planner: "Write a plan of at most 6 steps: what to take from {inputs}, and the check that proves each step done."
        plan-act-verify.verifier: "Check {work} against {check}, as the plan says; report pass or what failed."
        spec-first.specifier: "Write what {work} must do as a short spec, with edge cases and examples."
        spec-first.coder: "Write {work} to the spec."
        spec-first.verifier: "Check {work} against every line of the spec."
        tdd.tester: "Write down the cases {work} has to get right, each with how to tell from {check} that it did."
        tdd.coder: "Write {work} so it gets every case right."
        loop-until-green.agent: "Write {work}, check it against {check}, read what's wrong, fix it; repeat."
        self-review.agent: "Write {work}, then review it as a strict reviewer against the task and {check}; fix what you find."
        reviewer-subagent.coder: "Write {work}."
        reviewer-subagent.reviewer: "Review {work} with fresh context: right by {check}, in scope, complete. List concrete problems only."
        orchestrator-workers.worker: "Do one part, in its own context; report what you found or wrote."
        team.planner: "Plan {work} and the checks that prove it right."
        team.coder: "Write {work} from the plan."
        team.tester: "Check {work} against {check} as the plan says; report what fails to the {maker}."
        critic.agent: "Propose {work} and argue why it is right."
        big-planner.planner: "Plan precisely: what to use from {inputs}, what to write, how to check it."
        react.agent: "Work in short turns: write one line of reasoning, take one action (look something up in {inputs}, or draft part of {work}), read what it returned, and decide the next turn from that. Stop when {work} is done and checked."
        tree-search.try-a: "Work option 1 out as a draft; report how it holds up against {check}."
        tree-search.try-b: "Work option 2 out as a draft; report how it holds up against {check}."
        tree-search.try-c: "Work option 3 out as a draft; report how it holds up against {check}."
        tree-search.pick: "Compare the three against {check}; keep the best, or send back to frame new options if none holds up."
        router.router: "Classify the task into one route (for example: {routes}) and say why in one line."
        supervisor.supervisor: "Decide which specialists the task needs (for example: {specialists}) and what each must hand back."
        hierarchical.workers: "Do one small job each, in its own context; report what you did and how it checked out."
        handoffs.closer: "Read the trail of notes, check {work} against {check} and finish the remaining loose ends."
        blackboard.contribute: "Each contributor reads BOARD.md, adds what it can (a finding, a fact, a draft), and marks what it closed."
        approval-gate.propose: "Plan the work and list every action in it that is risky or can't be undone ({risky})."
        approval-gate.gate: "Hold each risky action{over} back as a request for a person, with its reason, and don't carry it out; let through only the safe ones."
        approval-gate.act: "Carry out the approved, safe actions only, and say which requests are waiting for a person."
      helps:
        explore-act: "Tasks where the answer depends on material the agent hasn't read."
        tdd: "Work with cases you can write down before you start."
        loop-until-green: "Work with a quick, reliable way to check it."
        self-review: "Short pieces of work where mistakes show on a reread."
        reviewer-subagent: "Work where a second pair of eyes catches what the author can't."
        team: "Work that needs both a careful draft and a separate check."
        big-planner: "Well-specified work where thinking is the hard part and writing is cheap."
    disciplines:
      support:
        work: the reply
        inputs: the ticket, the customer's account and the policy
        check: the policy and the account
        risky: refunds, credits, account changes, promises to the customer
        maker: writer
        routes: refund, billing question, bug report, account change, complaint
        specialists: policy lookup, account history, reply writer
        limit: the policy's limit
        names:
          approval-gate.gate: Manager approval
        roles:
          approval-gate.propose: "Read the ticket and the policy, draft the reply, and list every action it would take: refunds, credits, account changes, promises to the customer."
          approval-gate.gate: "Hold any refund or credit over {limit}, and anything the policy doesn't allow, back as a request for a manager, with the amount and the policy line; don't carry it out. Let through only what is within {limit} and the policy."
          approval-gate.act: "Send the reply and do only the approved actions; tell the customer plainly which part is waiting for a manager."
      research:
        work: the answer
        inputs: the sources
        check: the sources
        risky: publishing or sending the findings, contacting people
        maker: researcher
        routes: fact lookup, comparison, explanation, open question
        specialists: searcher, reader, fact-checker, writer
        limit: the limit
      data:
        work: the analysis
        inputs: the data and its definitions
        check: the source data
        risky: changing or deleting data, sending results outside the team
        maker: analyst
        routes: metric question, data fix, new report, anomaly
        specialists: query writer, analyst, checker
        limit: the limit
      finance:
        work: the figures and the summary
        inputs: the ledgers, invoices and the policy
        check: the source records and the policy
        risky: payments, journal entries, approving spend
        maker: preparer
        routes: reconciliation, invoice question, expense review, close task
        specialists: collector, reconciler, reviewer
        limit: the approval limit
      product:
        work: the spec
        inputs: the research, the feedback and the goals
        check: the goals and the constraints
        risky: commitments to customers, dates, pricing
        maker: writer
        routes: feature request, bug report, research question, roadmap question
        specialists: researcher, writer, reviewer
        limit: the limit
      docs:
        work: the doc
        inputs: the code, the existing docs and who reads them
        check: the code and a run of every example
        risky: publishing, deleting pages
        maker: writer
        routes: how-to, reference, tutorial, correction
        specialists: researcher, writer, example tester
        limit: the limit
      design:
        work: the design
        inputs: the brief, the users' needs and the design system
        check: the brief and the design system
        risky: publishing, shipping to users
        maker: designer
        routes: new screen, fix, design system change, research question
        specialists: researcher, designer, reviewer
        limit: the limit
      marketing:
        work: the copy
        inputs: the product facts and the audience
        check: the product facts
        risky: publishing, sending to customers, claims about the product
        maker: writer
        routes: launch post, email, landing page, social post
        specialists: researcher, writer, fact-checker
        limit: the limit
      leadership:
        work: the decision memo
        inputs: the facts, the options and the constraints
        check: the facts given
        risky: announcing decisions, commitments to people
        maker: writer
        routes: decision, update, plan, people question
        specialists: analyst, writer, reviewer
        limit: the limit
      compliance:
        work: the assessment
        inputs: the evidence and the policy
        check: the policy and the evidence
        risky: approving, declining, filing with a regulator
        maker: analyst
        routes: screening, risk assessment, policy question, filing
        specialists: evidence gatherer, screener, assessor
        limit: the limit
  # Combining: a stack is one pattern + 0-2 harness techniques + a model + 0-2 skills.
  max_harness: 2
  max_skills: 2
  shuffle_count: 8
  diminishing: 0.6     # each extra harness technique or skill counts at this share of its prior
  overlap_penalty: 2   # a harness technique the pattern already does (a loop with small-steps)
---

# Workflow patterns

The Workflow Lab tests agentic setups directly, on built-in test benches, without the person's own
repo. Everything here is a starting point: priors are guesses until a run measures them, and
relative costs are ratios to edit to your own rates.

## Building blocks

- **Patterns** (`patterns`): how the work is split into roles and loops, grouped by `groups`. Each
  role says what it does and its kind (a "do" step unless it says think, check or judge); a role
  may pin a model. The roles run in order, or as a graph when the pattern lists `edges`
  (branches run in parallel and join). A loop goes back from one role to another until a
  condition holds, at most `max` times.
- **Harness techniques** (`harness`): rules layered on any pattern.
- **Models** (`models`): each with a relative cost and a prior against `baseline_model`.
- **Skills**: anything in the library.

## Said in the discipline's words

Patterns are written for code work, and run as written in `code_disciplines` (development,
QA, DevOps, security). A pattern set up for any other discipline (support, research, data,
finance, product, docs …) says its roles in that discipline's words: `phrasing.neutral` holds
each role that reads as code, with placeholders filled from the discipline's nouns (support's
work is "the reply", checked against "the policy and the account"), and a discipline's own
`roles` win where a pattern needs saying differently. Human-in-the-loop for Support proposes a
reply and its actions, sends any refund over the limit to a manager, and replies saying what is
waiting; it never asks to "plan the change". An amount the use case names ("refunds over
$200 need a manager") goes into the wording as {limit}.

Harness rules are said the same way: `does` for code ("never weaken a test"), `by_discipline`
for the rest (support: quote the policy line you rely on, never promise a refund the policy
doesn't allow, hand anything over the limit to a person; research: cite every claim, say when
the sources don't answer it), else `neutral`.

## Stacks

A stack is one pattern, up to `max_harness` harness techniques, a model, and up to `max_skills`
skills. The Lab offers:

1. **One per group**: the strongest pattern of each group on the baseline model.
2. **Cheap and fast / max quality**: the same patterns on the fastest and the strongest model.
3. **Shuffled**: `shuffle_count` random stacks, never repeating one already shown.

Each stack gets a **prior** (pattern + model + harness and skills at `diminishing` share, minus
`overlap_penalty` per technique the pattern already does) and a **relative cost** (model cost ×
pattern tokens × harness tokens). Ranked two ways: best expected result, and best value
(prior per unit of cost). A run replaces the prior with a measured pass rate.

## Running a stack

A stack compiles into what the agent runs in the sandbox:
- an orchestration skill: the pattern's roles in order, its loops with their stop rules, the
  harness rules, and the chosen skills' instructions;
- one subagent file per role (`.claude/agents/<role>.md`) with its instructions and its model,
  so roles run in their own context on their own model.
Loops and limits are carried out by the agent following the protocol; they are instructions,
not hard limits enforced from outside.

Stacks are measured on the same bench, same scenarios, against Direct on the same model, so
every stack's number is a change against one baseline.
