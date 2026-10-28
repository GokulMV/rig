---
name: lean-context
description: "How to work on a small token budget: read only the file the task names, change it in one edit, check once, and answer in one line. Use it for every task."
---

# Lean context

Everything you read or write stays in the conversation and is sent again on every later turn,
so each extra file and each extra turn is paid for many times over. Do the task with as little
as you can.

## Rules

- **Read only what the task names.** The task says which file to change: open that file and
  nothing else. Don't list folders, search the repo, or open the README, the docs or other
  modules to get your bearings.
- **One edit.** Write the change in a single edit to that file. Don't rewrite code the task
  didn't ask about.
- **Check once.** Run `python3 -m unittest -q` from the project root once, after the edit. If
  it fails, fix only what it reports and run it again.
- **Nothing extra.** No new tests, comments, docs or files unless the task asks for them.
- **Answer in one line.** When it's done, say what you changed in one sentence. No plan before,
  no summary after.
