---
name: failure-forensics
description: Explain, without any model call, why a trial failed and where the with-skill and without-skill runs of the same task parted ways.
values:
  max_files_touched: 4          # more distinct files edited than this is over-engineering
  timeline_cap: 40              # tool calls shown per trial
  final_text_chars: 300
  command_chars: 120
  test_words: [pytest, unittest, npm test, node --test, bash tests/test.sh, go test, cargo test, jest, vitest, make test]
  edit_tools: [Edit, Write, MultiEdit, NotebookEdit]
---

# Failure forensics

When the with-skill and without-skill trials of the same task and repeat end differently (a
discordant pair), the number alone does not say why. This step reads the trial's folder
(session logs, `verifier/check.log`, `result.json`) and puts each trial in one bucket. Nothing
here calls a model: it only reads files and applies the rules below.

## Buckets
Passing trials are `solved`. The rest take the first rule that matches:

1. `timeout`: its `result.json` exception mentions a timeout (an agent timeout is recorded as a
   fail, "timed out after N s"), or it errored and the agent never wrote a final message.
2. `errored`: it errored or broke for any other reason (nothing to read the agent's work from).
3. `unknown`: it failed and there are no session logs to read.
4. `loop_thrash`: a workflow was given and a loop's target step was launched more than 1 + max times.
5. `premature_stop`: no Bash call ran a test or check command (any of `test_words`, or the
   scenario's own check command) after the last edit. An agent that never edited ends up here too.
6. `regression`: `check.log` shows more than one distinct failing test or assertion. The check was
   written to fail on the one bug, so several failures suggest the agent broke something else.
   This is an approximation.
7. `over_engineering`: it edited more distinct files than `max_files_touched`.
8. `wrong_fix`: none of the above. It ran the check, and the check still failed.

## Where two runs diverge
`diverged_at` is the first position where the two timelines' tool names differ, or where one
ends early. It is null when the two used the same tools in the same order.
