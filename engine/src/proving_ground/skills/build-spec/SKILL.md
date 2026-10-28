---
name: build-spec
description: "Ship to any agent - turn a repo (with its accepted suggestions), a Lab workflow or a Garage design into BUILD.md and rig.json: for a repo, the changes to make in it, in its own language and with its own test commands; with nothing yet, a new project with a suggested layout."
values:
  # Words in a component's label, role or sublabel that say what part of an agent system it is.
  roles:
    planner: [planner, planning, decompos, strategist]
    executor: [executor, actor, worker, runner, coder, builder]
    orchestrator: [orchestrator, supervisor, router, coordinator, graph, workflow]
    reviewer: [reviewer, critic, judge, verifier, evaluator, checker]
    retrieval: [retrieval, retriever, rag, vector, embedding, index, search, knowledge graph, graph db, reranker]
    memory: [memory, session, history, recall, long-term]
    guardrail: [guardrail, validator, validation, policy, safety, moderation]
    approval: [approval, human-in-the-loop, human review, sign-off]
    observability: [trace, tracing, telemetry, observability, logging, metrics]
    llm: [llm, model, claude, gpt, provider, inference]
    tool: [tool, mcp, plugin, connector, integration]
  # Component types that are things the agent calls, and words that make a call sensitive.
  tool_types: [external, database, cloud, messagebus]
  write_words: [write, update, delete, send, email, pay, charge, refund, deploy, publish, post, commit, merge, drop, create]
  sensitive_words: [delete, pay, charge, refund, deploy, publish, send, email, merge, drop, transfer]
  # Defaults for what an architecture does not say. A workflow's budgets are worked out from its
  # steps with these; the numbers are starting limits to adjust, not measurements.
  default_model: claude-sonnet-5-5
  budgets:
    tokens_per_step: 40000
    usd_per_cost_unit_step: 0.03
    seconds_per_step: 90
    steps_per_run: 12
    time_s: 900
    tokens: 200000
    cost_usd: 1.5
  agent_loop: "Load context -> choose an action -> run a permitted tool -> observe the result; repeat within the budgets, or validate the final answer and return it. Approvals pause sensitive actions; a trace records every step."
  # How to measure again, in the words the app uses now. API calls go in rig.json only.
  rerun:
    repo: "In Rig, open this repo and go to step 4, Measure: run the tasks again, with and without the change. The coding agent that runs them is the one in the agent pill at the top right."
    workflow: "In Rig, choose Nothing yet in step 1, Describe; build this workflow in step 3, Build; and run it in step 4, Measure."
    design: "In Rig, choose Nothing yet in step 1, Describe; pick this design in step 2, Design; build it as a workflow in step 3, Build; and run it in step 4, Measure."
  rerun_api:
    repo: "POST /api/scenarios/{id}/prove"
    workflow: "POST /api/lab/run"
    design: "POST /api/lab/run"
  # A new project's language when there is no repo: the first whose words the use case names,
  # else the default. Always written as suggested. Each says how the layout's files are named.
  default_language: Python
  languages:
    Python: {words: [python, django, fastapi, flask, pandas, pytorch, jupyter, langgraph, llamaindex], ext: py, src: src/agent_app, manifest: pyproject.toml}
    TypeScript: {words: [typescript, node.js, nodejs, next.js, nextjs, deno, bun, vercel ai sdk], ext: ts, src: src, manifest: package.json}
    Go: {words: [golang, in go, go service, written in go], ext: go, src: internal, manifest: go.mod}
    Rust: {words: [rust, cargo, tokio], ext: rs, src: src, manifest: Cargo.toml}
    Java: {words: [java, spring, kotlin, jvm], ext: java, src: src/main/java/agentapp, manifest: pom.xml}
  # How a repo is tested, read from its own build files at the root and one folder down: the
  # file, what must be in it (if anything), and the command. A command in CLAUDE.md or AGENTS.md
  # (in backticks, with one of the test words) comes first: the team wrote it down.
  test_commands:
    - {file: go.mod, run: "go test ./..."}
    - {file: Cargo.toml, run: "cargo test"}
    - {file: package.json, script: test, run: "npm test"}
    - {file: pyproject.toml, has: pytest, run: "pytest"}
    - {file: pytest.ini, run: "pytest"}
    - {file: Makefile, has: "test:", run: "make test"}
    - {file: pom.xml, run: "mvn test"}
    - {file: build.gradle, run: "./gradlew test"}
    - {file: build.gradle.kts, run: "./gradlew test"}
  test_words: [test, pytest, vitest, jest, check]
  max_test_commands: 6
  # Words in a repo's use case that name a language or its tools. One the repo has no files in
  # is said as a warning under the goal ("Your goal mentions Java/JUnit; this repo is Python").
  stack_words:
    Java: [Java, JUnit, Maven, Gradle, Spring Boot]
    Kotlin: [Kotlin]
    Python: [Python, pytest, Django, Flask, FastAPI]
    TypeScript: [TypeScript, Vitest]
    JavaScript: [JavaScript, Jest, Node.js]
    Go: [Golang]
    Rust: [Rust, Cargo]
    Ruby: [Ruby, Rails, RSpec]
    C#: [C#, .NET, xUnit, NUnit]
    PHP: [PHP, Laravel, PHPUnit]
    Swift: [Swift, Xcode]
  # An accepted suggestion that only fixes the diagram (its kind is in `kinds`, it adds or
  # removes no part, and all it improves is in `impacts`) is a note on the diagram, not a task:
  # a coding agent has nothing to change in the code for it.
  diagram_only:
    kinds: [check]
    impacts: [clarity]
  # Steps or design parts whose words say retrieval or memory put those in a new project's
  # brief (Memory and retrieval, the layout).
  retrieval_words: [retriev, rag, vector, embedding, index, search the, sources, passages, rerank, chunk, knowledge base, citation]
  memory_words: [memory, notes file, session history, long-term]
  # Accepted suggestions become tasks in this order: effort, then title, then id.
  effort_order: [S, M, L]
  effort_words: {S: small, M: medium, L: large}
  # A new project's brief (nothing yet: a Lab workflow or a Garage design), in order. A chosen
  # design adds its own section right after the Overview.
  sections: [Overview, Components and responsibilities, Flows, Parameters, Project layout, Agent loop, Models, Tools and permissions, Budgets, Guardrails, Memory and retrieval, Evals (done when), Measured evidence]
  # A repo's brief: the changes to make in it. "Not decided yet" appears only with open
  # suggestions, the design only when one was chosen; the rest always.
  change_sections:
    goal: Goal
    current: Current setup
    changes: Changes
    diagram: Notes on the architecture diagram
    undecided: Not decided yet
    design: Design to move toward
    added: Placed on the canvas
    removed: Removed
    check: How to check it
    evidence: Measured evidence
  design_section: Design
  # A new project's goal, right after the Overview: the whole goal and its rule lines
  # (goal-rules). A repo's brief has it as its first section (change_sections.goal).
  goal_section: Goal
  # Work that isn't software (its Lab discipline isn't a code one, and the goal names no
  # language): no code is needed to start, and the layout is optional.
  layout_section: Project layout
  no_code: "No code required to start: build it in your agent platform, or ask a coding agent to scaffold it in the language your team uses ({language} suggested). Do exactly what is stated; where a value is marked default, it is a starting limit to adjust."
  layout_optional: "Optional: only if a coding agent scaffolds it. A reference layout in {language}; swap the file names for your team's language and keep the same parts."
  # What was placed on the canvas: after Flows in a new project's brief, under "Placed on the
  # canvas" in a repo's; a heading appears only when it has entries.
  added_sections:
    skills: Skills to add
    repos: Parts from GitHub repos
    planned: Planned, not written yet
    links: Links on the canvas
    notes: Notes on the canvas
  # Bounds on what the canvas may send: strings only, never read as files.
  added_limits:
    items: 200
    parts: 400
    links: 500
    name: 200
    path: 1000
    text: 2000
    design_parameters: 50
    design_value: 200
---

# Build spec

## Rules
- Two kinds of brief. A repo ("As it is", "With the accepted suggestions") gets a change brief:
  the changes to make in that repo, in its own languages, layout and test commands, read from
  the repo scan. It never scaffolds a new project and never names a language the repo doesn't
  use. Only with nothing yet (a Lab workflow or a Garage design) is there a new project with a
  file layout, and its language is a suggestion: the one the use case names, else the default.
- A change brief says the goal (the goal in use in the browser, an unsaved draft included, sent
  with the request; else the repo's saved use case), the current agent setup (CLAUDE.md or
  AGENTS.md, skills, hooks, MCP servers, whether each is there), the changes, what was placed on
  the canvas, what was removed, how to check it (the repo's own test commands, then the Rig
  tasks) and the measured evidence.
- With the accepted suggestions, every accepted suggestion that changes code or config is a
  task: title, why, what to do, the files to touch and the effort, in effort-then-title order.
  One that only fixes the diagram (`diagram_only`: "Show where X gets its input") is not a task
  for a coding agent: it is listed under "Notes on the architecture diagram".
- When the use case names a language or its tools (`stack_words`) that the repo has no files in,
  the brief says so under the goal: "Your goal mentions Java/JUnit; this repo is Python/TypeScript."
  The Design step says the same, as soon as the goal in use says it (`/api/goal/check`). Dismissed ones are left out;
  open ones are listed under "Not decided yet". As it is, no suggestion is a task, and the
  brief says how many accepted ones it leaves out.
- A chosen Garage design is stated with its parts, connections and parameters, each with the
  value chosen and the default (a Lab workflow built from a design included: its parameters go
  in the Parameters table, and its retrieval and memory parts, with the workflow's steps,
  decide the Memory and retrieval section and the layout): for a new project as the design to build, for a repo as the
  design to move toward. Only names the design has are taken; values are text, never run.
- Parameters are only what can be tuned: a design's parameters, a step's model, a loop's
  limit. What Rig found about a part (its source file, whether the code check found it, its
  type) is a fact about the part, never a parameter.
- The brief's words are the app's words today (steps by name, the agent pill). API calls
  belong in rig.json, never in BUILD.md.
- Every brief says the goal whole and its rules ("Rules to follow": the lines of the goal with
  a number, a limit or a must/never/only, found by the goal-rules skill), so a policy such as
  "30–60 days → store credit" reaches the agent, not only its amount. The goal is the one step 1
  sends, else a workflow's own Goal & rules, else the saved use case.
- With nothing yet, work that isn't software (a support, finance or research agent: the Lab
  discipline isn't a code one, and the goal names no language) needs no code to start: the
  brief says to build it in an agent platform or have a coding agent scaffold it in the
  team's language (Python suggested), and the project layout is marked optional.
- A build spec is made from what the repo, architecture, workflow or design already says.
  Nothing is invented that the source does not support, except a new project's skeleton and
  the default limits above, and the spec says which values are defaults or suggestions.
- A new project's layout is the reference layout (agents, orchestration, llm, prompts, tools,
  guardrails, observability, api, configs, evals, tests, infra) in its language, adapted:
  `retrieval/` only when a component is retrieval, vector or graph; `memory/` only when a
  component is memory; `guardrails/approvals` only when a tool is sensitive or a component is
  an approval; one `agents/` file per real role, never a made-up one. A Lab workflow becomes
  one agent file per step, an orchestration graph from its edges and loops, and its harness
  rules as guardrails.
- Budgets, guardrails, tools with permissions, and the evals that say "done" are always stated
  in a new project's brief, never left for the builder to guess. Measured results are quoted
  only when a run produced them.
- What was placed on the canvas is part of the plan: skills (with where to get each: a path
  relative to the repo when it is inside it, else its GitHub folder, else the local folder),
  GitHub repos with their parts, suggestions still to be written (planned, not written yet), the
  links drawn between blocks and any notes. These come from the canvas as text; no file is read
  from the paths they name. The repo's own build files and agent setup are read for its test
  commands, hooks and MCP servers; nothing else.
- BUILD.md and rig.json hold the same facts; both are deterministic and make no model call.
