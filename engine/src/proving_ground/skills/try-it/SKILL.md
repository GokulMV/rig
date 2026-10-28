---
name: try-it
description: "Try it: run a workflow or skill once on a few real inputs you paste, and see each answer, the steps it ran and what it cost. One sample, not a measurement."
values:
  max_inputs: 5
  max_input_chars: 8000
  max_goal_chars: 2000
  max_budget_usd: 50
  # The agent's final answer, as shown; longer ones are cut here.
  max_answer_chars: 20000
  # Seconds the agent may take on one input (the task's time limit in the sandbox).
  timeout_s: 900
  # Added under every input, so the last message is the answer itself and not a report on it.
  answer_note: "When you are done, give your final answer in full as your last message: the reply or result itself, not a summary of what you did."
  # A Lab workflow has no repo: the agent works in an empty folder holding only this README.
  empty_readme: "No files here. Work only from the task text and the workflow you were given.\n"
  # Optional grading: offered only for these disciplines, off by default, one call per answer.
  graded_disciplines: [support, research]
  judge_model: claude-haiku-5-5   # the cheapest tier: a quick look, not the measurement
  judge_call_usd: 0.01            # roughly what one grading call costs; shown before the run
  # What each input cost, kept per workflow and model (only the amounts), and priced from first:
  # a try is cheaper than a bench trial, and any workflow's trials say little about this one.
  remember_costs: 20
  placeholders:
    support: "Hi, I bought the annual plan 3 weeks ago and it's not what I expected. Can I get a refund? Order #48213. Thanks, Dana"
    research: "What changed in the EU's AI Act obligations for general-purpose models in 2025? Cite your sources."
    development: "Bug: clicking Save twice creates two invoices. Steps: open an invoice, double-click Save. Expected one invoice, got two."
    qa: "Bug: the search box returns nothing for names with an apostrophe (O'Brien)."
    default: "Paste one real input here: the kind of request this would get."
  # The example in the input box, built from the goal in use (step 1, saved or not): the kind
  # whose words the goal mentions most (ties: the first listed) gives the example; none: the
  # discipline's placeholder above. {amount} is the goal's first dollar figure pushed over it by
  # over_limit (so a support example tests the limit the policy sets), else default_amount.
  # Deterministic, no model.
  over_limit: 0.25
  default_amount: 240
  goal_examples:
    - kind: support
      words: [support, ticket, tickets, customer, customers, refund, refunds, helpdesk, help desk, complaint, complaints, billing, inbox]
      example: "Hi, I was charged ${amount} for the annual plan three weeks ago and it isn't what I expected. Can I get a full refund? Order #48213. Thanks, Dana"
    - kind: docs
      words: [docs, documentation, knowledge base, faq, faqs, q&a, question, questions, manual, handbook, wiki, guide, guides]
      example: "How do I rotate an API key without downtime? Answer from the docs and say which page you used; if the docs don't cover it, say so."
    - kind: coding
      words: [bug, bugs, code, coding, repo, test, tests, pull request, refactor, developer, developers, fix, fixes]
      example: "Bug: clicking Save twice creates two invoices. Steps: open an invoice, double-click Save. Expected one invoice, got two."
---

# Try it

Benchmarks say whether a workflow helps on average; they don't show what it does. Try it runs
the agent once per input, in the same sandbox a "with" trial uses, and shows what came back.

## Rules
- One to `max_inputs` inputs, each at most `max_input_chars`. Each input is the task
  instruction, with `answer_note` under it so the last message is the answer itself.
- The workflow or skill is handed over exactly as in a real run's "with" arm (judge-experiment:
  workflow_prompt). A repo skill runs on a snapshot of the repo; a Lab workflow runs in an empty
  folder holding only `empty_readme`. There is no check: nothing passes or fails.
- Price first. Before anything runs, show "≈ $X for N inputs (at most $Y)" from the budget
  check's own prediction for a "with" trial (trial-budget), plus `judge_call_usd` per answer when
  grading is on. Nothing runs without an explicit click with that price on screen; nothing runs
  by itself.
- A hard cap. Each input is reserved against the budget before it starts (trial-budget), and an
  agent in `in_trial_cap` stops itself at what is left. An agent with no such cap is refused
  unless the person ticks that they accept no hard cap; then only the checks before each input
  hold it. Inputs the budget can't pay for are skipped, and say so.
- One try at a time, and not while a measure run is going. Stop ends it after the input in
  progress (a running sandbox isn't killed halfway).
- Each answer shows: the final message (from Claude Code's closing result event, else the
  agent's trajectory), the workflow steps it ran ("ran 3 of 4 steps", from its session logs; for
  a plain skill, whether it opened it), its cost and time, and its status: done, capped (cut short
  at the cap), errored, broken (the sandbox didn't build), skipped (no budget) or stopped.
- Optional grading, off by default, offered only for `graded_disciplines`: one `judge_model`
  call per answer (judge-documents' judge, on a single criterion: the goal or policy written in
  the box) gives followed ✓ / not followed ✗ with a one-line reason, and its own cost.
- Nothing is kept. Inputs and answers live in the engine's memory for the job's lifetime only; the
  sandbox folders are deleted when each input finishes and the job's folder when it ends. Saving an
  input as a scenario is the only way to keep it: a draft with the input as its instruction and no
  check, which the person adds before it can be measured.
- Say it plainly on the page: one try shows what it does; Measure tells you whether it helps.
- The input box's example comes from the goal in use (`goal_examples`): a support goal gets a
  customer email that tests its limit, a docs Q&A goal a question the docs should answer, a
  coding goal a bug report. It is shown at once, before the price is in, and is only a
  placeholder: nothing is run or filled in until the person does it.
- Say what the price is in plain words: the workflow (its steps) run once per input on the
  model its working steps use, priced like a run of that model ("a first guess" until something
  is measured). It runs in an isolated test copy, never in the person's own files.
