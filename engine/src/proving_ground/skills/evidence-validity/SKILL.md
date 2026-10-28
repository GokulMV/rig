---
name: evidence-validity
description: "When a measured result counts as evidence - the treatment was applied, a task could be won or lost, the check is a command - and when a scenario's check can be approved or run."
values:
  # A "with" trial didn't get the treatment when it wasn't seen opening the workflow (Claude Code
  # logs a Skill call) and ran none of its steps. More than this share of the "with" trials whose
  # logs could be read, and the result is invalid.
  max_not_applied_share: 0.5
  # An MCP-server run: the same share, for "with" trials that never called the server.
  max_unused_mcp_share: 0.5
  # A check is a shell command. Its first word must be a path (has a "/"), one of these, or a
  # program found on this machine's PATH. Shell words (if, for, set, export, cd, ...) count.
  check_runners: [bash, sh, zsh, python, python3, pytest, uv, uvx, pip, tox, nox, node, npm, npx,
    yarn, pnpm, bun, deno, tsc, vitest, jest, playwright, go, cargo, rustc, make, cmake, ctest,
    ruby, bundle, rake, rspec, java, mvn, gradle, dotnet, php, composer, phpunit, swift, mix,
    elixir, docker, curl, jq, grep, diff, cmp, test, "[", "[[", true, false, cd, set, export, env,
    if, for, while, until, case, timeout, git, cat, ls, echo, printf, sqlite3, psql, exit]
  # A first line made only of bare words that has one of these reads as a sentence, not a command
  # ("make sure the tests pass", "check token cost"), even when its first word is a runner.
  # Only function words: a make target or npm script may well be called "quality" or "verify".
  prose_words: [the, a, an, is, are, be, should, must, sure, that, this, it, its, of, and, than,
    when, works, correctly, properly]
---

# Evidence validity

A number is only evidence when the run could have shown a difference. Each finished result is
one of: valid, invalid (the treatment wasn't applied, or a check is broken) or uninformative (no
task could be won or lost). Only valid results feed learned priors, "learned" estimates, the
frontier and PROVEN.md. The others stay listed, with a badge that says why.

## Rules
- Treatment not applied: more than `max_not_applied_share` of the "with" trials whose session
  logs could be read were not seen opening the workflow and ran none of its steps. (Not opening
  alone isn't enough: a trial can follow every step with no Skill call in its log.) Badge: "Invalid: the workflow was never opened" when none did, else "Invalid: the
  workflow wasn't opened in X of Y trials". No logs to read: it can't be told, so it isn't held
  against the run.
- MCP server not used: the same, for "with" trials that never called the server. Badge:
  "Invalid: the MCP server was never used".
- Broken check: a scenario in the run has a check that isn't a command (see Checks). Badge:
  "Invalid: the check is broken", naming the scenarios.
- Uninformative: on every task with finished trials in both arms, both arms pass every time or
  both fail every time. Nothing could be won or lost. Badge: "Uninformative: both always pass",
  "Uninformative: both always fail", or "Uninformative: each task passes both ways or fails both
  ways".
- Broken comes before not applied, which comes before uninformative: one badge per result.
- Each result also names its cause (`broken_check`, `not_applied`, `mcp_unused`, `both_pass`,
  `both_fail`, `each_same`), so the verdict can say what to do next.
- Never call an invalid or uninformative result "learned" or "measured".
- Both always pass is still uninformative here, even when the Rig score judges it on cost and
  time (rig-score: Ceiling): it measures cost, not a change in the pass rate, so it never feeds
  learned priors, the frontier, compare rankings or PROVEN.md.

## Timeouts
- A trial whose agent ran out of the task's time limit (Harbor's AgentTimeoutError) is a fail,
  recorded with detail "timed out after N s", even when the check passed afterwards: the agent
  didn't finish the task in the time it had. It counts in the pass rate and in the shared
  baseline like any fail, against Reliable in the Rig score, and the run page labels it "timed
  out". Any other exception stays errored.
- Trials recorded as errored before this rule are read once from their Harbor `result.json`;
  an agent timeout there becomes the fail it is now.

## Checks
- A check is a bash snippet run in /app; only its exit code counts. Before a scenario can be
  approved, and before a run starts, its check must read as a command: the first line that isn't
  blank or a comment splits as shell words (shlex), and after any `VAR=value` settings its first
  word is a path, a known runner (`check_runners`), or a program on PATH.
- A first line of bare words only (no flags, paths, quotes or operators) with a `prose_words`
  word in it is a sentence ("make sure the tests pass") and is rejected, even though `make` is a
  runner. "token cost" fails earlier: `token` is not a program.
- Approving such a check is refused (HTTP 422) with what's wrong and an example; a run whose
  scenarios include one is refused, listing them. Scenarios already approved with such a check
  show a warning badge.
- A generated scenario remembers which use case it was written for. When the repo's use case
  changes, it shows "written for a different goal" until it is regenerated or rewritten.
