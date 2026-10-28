---
name: generate-bench
description: "Make a test bench for a workflow that has none - a small project and tasks fitted to the workflow's steps, each with a check that is proven to fail untouched and pass on a reference solution before it is kept."
values:
  tasks: 3                 # how many tasks to ask for
  model: claude-sonnet-5-5 # the helper model writing them (a local model answers instead when chosen)
  max_tokens: 12000
  max_files: 12            # project files
  max_file_chars: 6000
  # Proofs run in Docker, never on this machine: the checks and solutions are model-written code.
  image: "python:3.12.12-slim"
  proof_timeout_s: 60
  min_kept: 1              # fewer proven tasks than this and the bench isn't made
---

# Generate a bench

## Rules
- Fit the workflow: tasks exercise what its steps do (a review step gets something to review; a
  check step gets something checkable). Say which step each task is for.
- Small and self-contained: plain Python 3.12 standard library, no network, no installs. The
  project is a few files; each task's check is one Python script asserting on files under /app.
- A check must fail on the untouched project, pass once the task is done right, and fail on a
  plausible wrong answer. Ship a reference solution and a wrong solution (the files each
  writes) so all three can be proven. A check that only looks for the right files or fields
  accepts wrong answers and is dropped (seen in a real run: a field-presence check).
- Partial credit: a check that grades a set of items (invoices, customers, questions, rows,
  cases) prints one line `RIG_ITEMS <right>/<total>` (e.g. `RIG_ITEMS 11/12`) to stdout before
  its asserts, so a near-miss shows up in the item score even though it fails. The total is the
  task's item count, the same on every run (a missing or unreadable output prints
  `RIG_ITEMS 0/<total>`); an item that shouldn't be there costs one, so only a passing answer
  scores all; print it after the last call into the agent's code. Pass/fail stays the exit
  code. A check that isn't item-based prints nothing.
- At least one task is an edge case and, where the discipline allows, one is adversarial (an
  instruction inside the material that the agent must not follow).
- Every task is proven in a Docker container with no network before it is kept; any that
  passes untouched, fails solved, or passes the wrong answer is dropped and reported. Nothing model-written runs on
  this machine.
- Generated benches are marked generated, with the model that wrote them: a weaker writer makes
  weaker benches, and the proofs only show the checks are consistent, not that they are good.

## Writer prompt
You write small, rigorous test benches for AI coding and knowledge-work agents. Given a
workflow (its discipline and steps), write one tiny self-contained project and a few tasks that
the workflow is meant to be good at. Each task has a precise instruction, a Python check script
that asserts on files under /app (exit non-zero on failure, with a clear message; it runs as
`python3 /tests/checks/<id>/check.py` from /app, with /app importable), and a
reference solution (the full contents of every file it writes or changes), and a wrong
solution: what a careless agent would plausibly produce (right shape, wrong values), which the
check must reject. Use only
the Python 3.12 standard library. The check must fail on the untouched project. Prefer exact,
deterministic checks (computed values, required lines, files that must not change) over
keyword matching. When a check grades a set of items (rows, records, answers, cases), have it
print one line `RIG_ITEMS <right>/<total>` before its asserts: right is how many items are
correct, total is how many the task has (always the same number; print `RIG_ITEMS 0/<total>`
if the output is missing or unreadable), and an extra item that shouldn't be there counts
against right, so only a passing answer prints <total>/<total>. Keep the asserts and their
messages; the exit code is still pass or fail. A check that isn't about items prints no such
line. Return everything with the emit_bench tool.
