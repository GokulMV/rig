---
name: improve-architecture
description: Propose concrete changes to a repo's architecture (split, merge, add, reconnect, move off the hot path), each with why, what it does, what it improves and the evidence in the code.
values:
  hub_fan_out: 5              # a block calling this many internal blocks directly is a hub
  shared_targets_min: 3       # two ways in calling this many of the same blocks share a flow
  store_writers: 3            # this many blocks writing one store need one owner
  big_lines: 4000             # a block over this many lines of code is worth splitting
  big_files: 40               # ... or over this many code files
  big_file_lines: 900         # a single file over this many lines is worth splitting
  max_split_parts: 4
  max_proposals: 12
  server_words: [fastapi, flask, django, express, fastify, spring, nestjs, websocket, ws, http, api, rails, gin]
  model_words: [anthropic, claude, openai, gpt, openrouter, groq, gemini, bedrock, llm, mistral, ollama]
  impact_order: [reliability, speed, agent, clarity]
  review_model_tier: "the person's chosen agent, read-only (one session)"
---

# Improve the architecture

Suggestions are only worth showing if they are concrete, grounded in this repo, and say plainly
what changes and why. Every proposal has:

- **title**: the change, in a few words ("Move model calls off the request path").
- **kind**: `split`, `merge`, `add`, `reconnect`, `move`, `remove` or `check`.
- **targets**: the blocks it is about.
- **why**: what in this repo makes it worth doing, with numbers.
- **what**: what the change does, step by step, in plain words.
- **impact**: which of reliability, speed, agent success and clarity it improves, and how.
- **effort**: S (an afternoon), M (a few days) or L (a week or more).
- **evidence**: the files, counts or lines it rests on.
- **delta**: the blocks and lines it adds, removes or reconnects, so the canvas can draw the result.

Nothing is applied to the code. Accepting a proposal puts it in the *proposed* architecture
(Build's "With accepted" view, exportable as an Archify spec) and in BUILD.md, as a task or, when
it only fixes the diagram, a note. An open proposal is drawn only while it is previewed, so the
proposed architecture always shows exactly what was accepted. Each new or taken-away part names
the proposal it came from. Every proposal also says whether Measure can test it (the
measurability skill): a change to the app's code is measured before and after, not with and
without.

## Rules (no model)

1. **Hub.** A block that calls `hub_fan_out` or more internal blocks directly is doing
   orchestration and its own work at once. Propose a service layer between it and them.
   For a way in (UI, CLI), the layer is where the flow lives so every way in shares it.
2. **Shared flow.** Two ways in that each call `shared_targets_min` or more of the same blocks
   repeat the same orchestration. Propose one service both call.
3. **Cycle.** Two internal blocks that call each other can't be changed or tested alone. Propose
   moving what both need into a small shared contracts block, so the lines go one way.
4. **Model calls on the request path.** A server block (any of `server_words`) calling a model
   API (any of `model_words`) directly makes requests wait on the slowest call and fail with it.
   Propose a job queue and a worker that makes the call, with a timeout and a retry. Only a direct
   line from the server counts: a model API reached through a queue and a worker is already off
   the request path.
5. **One store, many writers.** A store written by `store_writers` or more blocks needs one owner.
   For SQLite: write-ahead logging and a single writer. Otherwise: a data-access block in front.
6. **Big block.** Over `big_lines` lines or `big_files` files: propose a split along its largest
   sub-folders (up to `max_split_parts`), named after them.
7. **Big file.** A file over `big_file_lines` lines: propose splitting it, naming the file.
8. **Isolated block.** A block with no lines at all is either dead or missing a connection:
   check which.
9. **Unverified block.** A block that checking against the code found weak or missing: confirm it
   or take it off the diagram.
10. **Agent readiness.** No `CLAUDE.md` or `AGENTS.md`: propose one with the build, test and
    run commands. A workflow step with no approved scenario can't be measured: propose one. No
    test step: propose a verify step.

At most `max_proposals`, ordered by impact (`impact_order`), then effort (smaller first).

## Deeper review (one agent session)

The chosen agent reads the repo with read-only tools and returns more proposals in the same
shape. They are checked like everything else: targets must be blocks on the canvas and evidence
must be files in the repo, or the proposal is dropped.

## Review prompt

You are reviewing the architecture of the repository in the current directory, to propose
changes that would make it more reliable, faster, clearer, or easier for a coding agent to work
in. You are given the current architecture as JSON (components with ids, connections).

Read the code first. Then reply with ONE JSON object and nothing else:
{"proposals": [{"title": "...", "kind": "split|merge|add|reconnect|move|remove|check",
"targets": ["<component id>"], "why": "...", "what": "...", "impact": {"reliability": "...",
"speed": "...", "agent": "...", "clarity": "..."}, "effort": "S|M|L",
"evidence": ["<repo-relative path>"], "delta": {"add": [{"id": "...", "type": "backend",
"label": "...", "sublabel": "..."}], "remove": ["<id>"], "connect": [["<from>", "<to>", "<label>"]],
"disconnect": [["<from>", "<to>"]]}}]}

Rules:
- 3 to 8 proposals, each grounded in files you read; cite them in "evidence".
- "targets" and every id in "delta" refer to components in the given architecture, or to ones
  added in the same proposal's "delta.add".
- Only impacts you can justify; leave the others out.
- "why" names what you saw (counts, file names). "what" says the change step by step.
- No generic advice ("add tests", "improve docs") unless you point at the exact gap.
