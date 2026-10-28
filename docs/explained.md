# How Rig Works

This is the long explanation of Rig: what it measures, how a run works, the statistics behind every number, the Rig score, the sandbox, the benches, and the rules that decide each of them. For installing and a first run, start with the [README](../README.md).

Every value quoted here (weights, caps, pair counts, limits) is read by the engine from a skill file under [`engine/src/proving_ground/skills/`](../engine/src/proving_ground/skills/). When this page and a skill file disagree, the skill file is right.

## Contents

- [The Short Version](#the-short-version)
- [How a Measurement Works](#how-a-measurement-works)
- [The Statistics](#the-statistics)
- [The Rig Score](#the-rig-score)
- [Budgets, Shared Baselines and Keeping Going](#budgets-shared-baselines-and-keeping-going)
- [The Sandbox](#the-sandbox)
- [Rig a Workflow](#rig-a-workflow)
- [The Benches](#the-benches)
- [Rig a Repo](#rig-a-repo)
- [Agents and Local Models](#agents-and-local-models)
- [The Tutorials](#the-tutorials)
- [Rules as Skills](#rules-as-skills)
- [The Command Line](#the-command-line)
- [The API and the Code](#the-api-and-the-code)
- [Safety and Privacy](#safety-and-privacy)
- [What Real Runs Taught Us](#what-real-runs-taught-us)
- [Limits](#limits)
- [Running It](#running-it)

## The Short Version

### What Rig Is For

People keep adding things to their AI coding agents (Claude Code, Codex, OpenCode, Gemini CLI): skills, CLAUDE.md rules, multi-step and multi-agent workflows, harness rules such as "always run the tests before finishing", MCP servers and hooks. Few people know whether any of these make the agent better.

Rig measures it. It runs the same tasks twice, once with the change and once without, on the same agent and model, each trial in its own Docker sandbox. Every task has a check: a command whose exit code decides pass or fail. Rig then reports the difference in pass rate with a 95% interval, a plain verdict ("Helps", "Doesn't Help" or "Can't Tell Yet") and a Rig score from 0 to 100.

A run can also be scored on a saving instead of the pass rate: tokens, cost or time per solved task, with the pass rate kept as a guard so a change can't look cheap by solving less.

Rig is a local app: a Python engine (`engine/`) that serves a React web app (`web/`) on 127.0.0.1. Nothing is hosted, and your code and keys stay on your machine.

### Two Ways In

- **Rig a Repo**: on your own repository. Rig maps its architecture, suggests what would help, writes tasks with checks, and measures a change to the agent (a skill, a hook, an MCP server, a CLAUDE.md) with and without it, or a change to the code before and after.
- **Rig a Workflow**: no repository needed. Pick or build a workflow (starters, 15 business processes, 10 retrieval (RAG) workflows, 25 agentic patterns, random ones, or your own drawn on a canvas) and measure it on 20 built-in benches, an imported eval suite, a sample of a public benchmark, or a bench generated for it.

### The Five Steps

Both ways follow the same five steps, which are also the app's tabs:

| Step | What it is for |
|---|---|
| Describe | What you're building, and where it lives: a goal, and a repo (or nothing yet). |
| Design | Keep your design, or start from an architecture ranked for your goal. |
| Build | Add, remove and connect skills, agents and tools; in the Lab, a workflow's steps, models, skills and rules. |
| Measure | Run it on tasks, with and without each change (or before and after a code change). Every result gets a Rig score. |
| Ship | A build brief (`BUILD.md` and `rig.json`) any coding agent can follow. |

### Words Used Here

The app explains each of these words with a (?) the first time a page shows it (the [glossary skill](../engine/src/proving_ground/skills/glossary/SKILL.md)).

| Word | Meaning |
|---|---|
| Task | One job for the agent, with a check (a command) that decides pass or fail. Rig's files and API call it a scenario. A task has a kind: typical, edge, adversarial, failure, overload or imaginary. |
| Change | What is being tested: a skill, a workflow, a hook, an MCP server, instructions, or a code change. |
| Arm | One side of a run: "with" the change, or "without" it (the baseline). For a code change, "after" and "before". |
| Trial | One run of the agent on one task in one arm: one sandbox, one agent session, one check. |
| Pair | The with and without trials of the same task and repeat. |
| Run | Every trial for one change on one project or bench, with its budget, agent, model and metric. The engine calls it an experiment. |
| pts | Percentage points of tasks passed. Going from 40% to 52% is +12 pts. |
| Pilot | A small first run: each task once per arm. |
| Full run | At least 20 pairs, growing with the budget up to the pairs that tell a ±25 pts change from noise. |

## How a Measurement Works

### One Run, Step by Step

The engine's path is `service.prepare_experiment`, then `service.execute`.

1. **Load the tasks.** Only approved tasks run. A generated check must be approved by you first, and it must read as a command (see [When a Result Is Not Evidence](#when-a-result-is-not-evidence)). Bench checks ship approved because each is proven both ways.
2. **Snapshot the project.** In a git repo the snapshot is `git archive HEAD`: the last commit, never `.proving-ground/`. Uncommitted changes are not in it (`rig run` says so). A folder that isn't a git repo is copied as it is. A code change is different: see [A Code Change: Before and After](#a-code-change-before-and-after).
3. **Compile each task into a Harbor task folder** (`sandbox/compiler.py`):
   - a Dockerfile from `ubuntu:24.04` with the agent installed; a project or bench can ship its own `Dockerfile.base` (`ts-orders` adds Node);
   - the snapshot copied to `/app`;
   - `prepare.sh`, which applies injected faults for failure tasks (remove, truncate or corrupt a file; a failing command shim);
   - `instruction.md`;
   - `tests/test.sh`, which runs the check, writes its output to `verifier/check.log` and writes a reward of 1 or 0 from the exit code;
   - `task.toml`: 2 CPUs, 4096 MB of memory, a 1800 s build timeout, a 300 s check timeout, the task's own agent timeout, and network mode `allowlist`.
4. **Decide the repeats.** A pilot runs each task once per arm. A full run is at least 20 pairs, in whole repeats of the tasks, and grows with the budget (see [How Many Pairs a Run Needs](#how-many-pairs-a-run-needs)).
5. **Reuse earlier "without" trials** when allowed (see [Shared Baselines](#shared-baselines)).
6. **Preflight.** Each task's environment is built and its check run with Harbor's `nop` agent, which does nothing. A task whose environment fails to build is recorded as broken. If any check already passes with no agent, that task tests nothing and the run doesn't start ("Couldn't start: a check passed before the agent did anything").
7. **Run the trials** through Harbor. The change goes to the "with" arm; credentials go into the agent's environment from memory; the agent's model hosts are allowed while the agent runs. Before each pair, the budget check decides whether it can start (see [The Budget Cap](#the-budget-cap)).
8. **Classify each trial.** Pass or fail comes from the reward. A trial whose agent ran out of the task's time limit is a fail ("timed out after N s"), even if the check passed afterwards. Errored: the agent crashed, hit its cost cap, or a judged task had no document or judge. Broken: the environment didn't build. An authentication error stops the whole run; rate limits are retried with backoff.
9. **Judged tasks.** After a rule check passes, the judge grades the document; below the bar the pass becomes a fail (see [Judged Benches and Calibration](#judged-benches-and-calibration)).
10. **Record every trial** in the store (SQLite), with tokens, cost, duration and the trial folder.
11. **Keep going** if "Keep going until it's decided" is on (see [Keep Going Until It's Decided](#keep-going-until-its-decided)).
12. **Summarize**: the paired statistics, the verdict, the Rig score, adherence, cost per solved task and the held-out result.

The page follows the run live: each trial as it finishes, baseline trials reused, batches added, and why the run stopped.

### What Can Be Measured

The kind of a change is read from its files, never guessed from a name. A folder that matches more than one kind is rejected.

| Kind | Detected by | What the "with" arm gets | What the "without" arm gets |
|---|---|---|---|
| Skill | a folder with `SKILL.md` | the skill, installed through Harbor's skills list | no skill |
| Workflow | a Lab workflow, compiled into a skill folder | the workflow skill, named in the prompt | no workflow |
| Hook | a folder with `hooks.json` (Claude Code's `hooks` object) | the hooks merged into `/app/.claude/settings.json`; the repo's own hooks for the same event run first | the repo's settings as they are |
| MCP server | a folder with `mcp.json` (`{"mcpServers": {...}}`) | the servers merged into `/app/.mcp.json` and pre-approved (a headless trial can't answer Claude Code's prompt); an optional `install.sh` runs at image build in both arms | the repo's `.mcp.json` as it is |
| Instructions | a `CLAUDE.md` or `AGENTS.md` file, or a folder with one | the file in place of the repo's | depends on where the file is (below) |
| Code change | two commits, a branch or the working tree | the code after the change | the commit before |

Measure's change picker groups them as Skills, Instructions (CLAUDE.md, AGENTS.md), Hooks and MCP Servers. A code change is its own mode, "A Code Change: Before and After".

**Instructions.** The "without" arm is the committed snapshot, so what a CLAUDE.md run compares depends on where the file lives:

- the repo's own CLAUDE.md with uncommitted edits: with the edit, without the committed file;
- a CLAUDE.md that isn't committed: with the file, without none;
- the committed CLAUDE.md unchanged: both arms would get the same file, so the run is refused;
- an edited copy saved from Measure ("Save the Copy and Measure It", kept inside `.proving-ground/`) or an instructions folder elsewhere: with the copy in place of the committed file (or added, if the repo has none), without the committed file.

**What a repo's skills are.** Only the skills a coding agent loads: `.claude/skills`, `.agents/skills` and `.opencode/skills` (also in subfolders), `.gemini/skills` at the root, and the skills of a Claude Code plugin (`.claude-plugin/plugin.json`, or plugins listed in `.claude-plugin/marketplace.json`). Any other `SKILL.md` is just a file.

What is already in the repo is in both arms, so it can't be measured as it is. The [measurability skill](../engine/src/proving_ground/skills/measurability/SKILL.md) gives every card on Build one badge saying whether Measure can test it: "Measurable", "In Every Run", "Changes the Code", "Not Measurable Yet" (loops and configs, today), "Brief Only", "Diagram Note" and others.

### Telling the Agent About the Change

A workflow is handed to the agent: the "with" prompt gets one added line naming the workflow skill and saying to open it before anything else. A plain skill is left for the agent to find, as in real use. Measure's "Tell the agent to open the skill in the prompt" turns the same line on for a skill. On a local model it starts on, because a small model rarely opens a skill it is only offered.

Comparing a nudged workflow with an un-nudged skill mixes up content with discovery, so set both the same way when comparing them. The "without" arm never changes.

### A Code Change: Before and After

Some changes are to the code itself: a split or merge the architecture review suggests, or any edit to the app. These are measured before and after. You (or your agent) make the change on a branch or leave it uncommitted; Rig doesn't write it. On Measure, pick "A Code Change: Before and After", then "Before: the commit" (HEAD by default) and "After: the change" (a commit, a branch, or "your uncommitted changes").

- Each side is exported from git (`git archive` of the commit, or of a tree written through a scratch index for the working tree), never the live checkout. Each arm's tasks and checks run on its own copy, and its agent setup (CLAUDE.md, skills, hooks) is whatever that code has.
- "Without" is the commit before and "with" the change. The same agent runs on both.
- A run whose two sides have the same code (`.proving-ground/` aside) is refused, as is an unknown ref or a folder that isn't a git repo with a commit.
- Preflight runs each check with no agent on both sides: if the after code already passes it, the task tests nothing.
- The score is the same as for any change. Only the words differ: lines say "after" and "before" ("16 of 20 passed after vs 8 of 20 passed before"), "the plain agent" becomes "the code before", and a next step keeps the code before rather than dropping a skill. Followed is not measured: the change is in the code, so there is nothing to open.

On Build, a suggestion with the badge "Changes the Code" (and a part it adds or takes away in "With Accepted") has "Measure It", which opens Measure on this mode with a line naming the suggestion. From the command line it is `rig run --before <ref> --after <ref>`.

## The Statistics

### Pairs and Intervals

The rules are in [judge-experiment](../engine/src/proving_ground/skills/judge-experiment/SKILL.md) and the code in `stats.py`.

- The unit is the pair: the same task and repeat, with and without. Pairing removes the noise of "this task is just hard".
- The pass rate of each arm has a Wilson score interval, which is sound at small counts and near 0% or 100%.
- The difference (with minus without) has a 95% interval by Newcombe's method 10 for paired proportions, with a continuity-corrected correlation. Without that correction, arms that always agree would give a zero-width interval; with it, a few pairs that all agree give a wide one.
- The minimum detectable effect is shown with the result: the smallest true difference this many pairs could reliably have seen (95% confidence, 80% power). It uses an unpaired normal approximation, which is conservative for paired data, with the variance floored at 0.0475 so it stays meaningful near 0% or 100%.
- If more than 10% of trials errored, the result is flagged unreliable.

### The Verdict

Every result carries one plain verdict beside its score ([rig-score: Verdict](../engine/src/proving_ground/skills/rig-score/SKILL.md)): **Helps**, **Doesn't Help** or **Can't Tell Yet**, with a reason naming the numbers, one next step, and four fact lines (quality, cost, time and reliability per arm). In short:

- "Helps" needs the interval's lower bound above 0 and at least 10 pairs, or, when both arms always pass, a clear cost or time win.
- "Doesn't Help" when it does worse (the upper bound below 0), when even the upper bound is under +5 pts (the lift can't matter), or when the plain agent passes every task and the change doesn't.
- Otherwise "Can't Tell Yet", with about how many pairs a lift of the observed size would need.

"Clearly" dearer, cheaper, slower or faster means: over at least 2 tasks finished in both arms, the geometric mean of the per-task ratio is at least 1.5 (or at most 1 ÷ 1.5), and the 95% t-interval of the mean log ratio excludes 0. Size and consistency, both.

### Partial Credit

Pass or fail is all or nothing: 11 of 12 invoices right fails exactly like 0 of 12, so near the ceiling a change can't show. A check that grades a set of items prints one line, `RIG_ITEMS <right>/<total>` (for example `RIG_ITEMS 11/12`), and the runner keeps the last such line from `verifier/check.log`.

- A task is item-based when any of its trials printed a count. A trial of such a task that printed nothing scores 0 of the total if it failed and all of it if it passed.
- When every task in the pairs is item-based, each trial scores right ÷ total, and the item score difference is the mean of the per-pair differences with a paired t interval (95%, n − 1 degrees of freedom), clipped to [−1, 1].
- One pair gives the whole [−1, 1]. When every pair differs by the same amount, the spread is floored at half an item, so identical results don't claim certainty.
- The quality line then reads as items ("11 of 12 invoices right").

### Scoring a Saving: Tokens, Cost or Time

On Measure, "Score the run on" picks Pass Rate, Tokens, Cost or Time (the last three per solved task). The choice is kept in the run's `meta.json`. A goal picked from a template carries its metric as the default: "Fewer Tokens at the Same Pass Rate" picks tokens. The rules are in [rig-score: Metric](../engine/src/proving_ground/skills/rig-score/SKILL.md).

- **The measure, per arm**: the total tokens, cost or duration over the complete pairs (timed-out fails included, since they spent it), divided by the tasks that arm solved in them. Per solved task, so a change can't look cheap by failing fast. Tokens are in + out as the agent reports them, cached input included, so a change that only makes the prompt more cacheable doesn't look like a token cut.
- **The interval** of the ratio with ÷ without is a percentile bootstrap over whole pairs: 2,000 resamples with seed 0, so the same trials always give the same interval. A resample in which an arm solved nothing counts as an infinite ratio, against the change. Under 2 pairs there is no interval.
- **The guard** is the pass rate (or items right). No saving is credited until the 95% interval of the pass-rate difference has its lower bound above −10 pts (non-inferiority). 10 pts is well under the +25 pts that earn a full Lift, so a saving can't buy back a drop that matters.
- **A Lab suite** (one workflow on every bench that fits) is scored on the pool: each arm's total over every bench's pairs ÷ the tasks it solved, with a bootstrap that resamples each bench's pairs within that bench. The guard is the suite's pooled pass-rate interval.

### How Many Pairs a Run Needs

Before a run, beside "Stop at (USD)", Measure shows the budget check's own prediction for the planned pairs ([trial-budget](../engine/src/proving_ground/skills/trial-budget/SKILL.md)):

- what those pairs can tell apart: the half-width of the 95% interval at a 50% pass rate (an effect smaller than that can't be told from noise);
- what it would take to tell a ±25 pts change from noise, and the budget for that, with one click to set it;
- the "Full" choice's label says what the budget buys: "Full · N pairs · conclusive to ±X pts" only when it reaches that sizing, otherwise "tells apart ±X pts", or that the budget only covers as many pairs as the pilot.

The guard on a saving needs far more pairs than a pass-rate lift. Assuming the pass rate stays at 80% and 1 pair in 40 disagrees each way, it needs about 39 pairs. 20 pairs that all agree reach only −12 pts; 40 pairs with one disagreement each way reach −9.4. Measure says this before the run, warns when the planned run can't get there, and a full run on a saving grows to those pairs, budget allowing.

## The Rig Score

One number from 0 to 100 that says whether a skill, workflow or other change works, built only from what was measured. The [README's summary](../README.md#what-the-rig-score-is) is short; the full rules are in [rig-score/SKILL.md](../engine/src/proving_ground/skills/rig-score/SKILL.md). The app's "How Is This Scored?" page (`#/rig-score`) is generated from the same file, with a worked example scored by the engine itself.

### The Five Parts

| Part | Weight | Score |
|---|---|---|
| Lift | 40% | The lower bound of the 95% interval of the pass-rate difference: 0 at or below 0 pts, 100 at +25 pts or more, a straight line between. The lower bound, so a lucky small run can't score well. |
| Cost | 20% | Cost with ÷ cost without, per solved task when both arms solved some, else per finished task. 100 at 1.2× or less, 0 at 5× or more, linear in the logarithm between. A local model scores 100. Reused baseline trials count at what they cost when they ran. |
| Followed | 15% | A workflow: half from the share of steps run, half from the share run on the step's model, read from the session logs of the "with" trials. A skill: the share of those trials that opened it. An MCP server: the share that called it. Hooks and instructions leave no signal in the logs, and a code change has nothing to open: not measured. |
| Holds Up | 15% | Held-out tasks: 100 if the gain generalises, 0 if it is overfit (a gain of at least 10 pts on the visible tasks and none on the held-out ones). Unclear, or no held-out tasks: not measured. |
| Reliable | 10% | The share of trials that ran cleanly: not errored, broken, timed out or cut off by the budget. On a judged bench whose judge isn't calibrated, it keeps half of that. |

- A part that can't be measured is left out and the others are scaled up to fill its share.
- Cost and Reliable count at 0 (weight kept) until a lift is shown: being cheap and clean at doing nothing is worth nothing.
- The card shows the formula, so the number can be rebuilt by hand, and one trial ledger that every count refers to.

A worked example, the first tutorial's real run (10 pairs on a local model, 9 of 10 passed with the skill and 2 of 10 without, interval +14 to +91 pts, no held-out tasks):

```text
40% × 55.8 + 20% × 100 + 15% × 100 + 10% × 90 = 66.3;
÷ 85% (weights rescaled to the measured parts; holds up not measured) = 78.0; rounded: 78
```

### Gates and Bands

After the weighted sum, gates cap the score, in this order:

| Gate | Cap |
|---|---|
| It makes results worse (the interval's upper bound below 0) | 20 |
| The interval's lower bound is at or below 0 (not shown to help) | 49 |
| Fewer than 10 pairs (provisional, shown greyed with the pair count) | 59 |
| Both always pass and it clearly costs more or takes longer | 20 |

The score is rounded half up. The band comes from the evidence first, so it never contradicts the interval beside it:

1. The upper bound is at or below 0 (it does worse, or can't do better): **Doesn't Work**.
2. The upper bound is under +5 pts: **Doesn't Work** (the lift can't matter).
3. The lower bound is at or below 0: **Not Proven**, with what would settle it.
4. A lift is shown: **Works** at 80 or more, **Works, but …** at 60 or more (naming the part that costs the most points); under 60, **Not Proven** when only the pair count holds it back, else **Helps, but …** naming the biggest drag.

Before any of that, the plain agent passing every task while the change doesn't is "Doesn't Work": "the agent alone already passes every task". The reason line names up to 3 parts that cost the most points (weight × shortfall), each scoring under 70.

### On a Saving

When a run is scored on tokens, cost or time per solved task:

- Lift is the cut, `1 − with ÷ without`, scored on the lower bound of its bootstrap interval: 0 at 0% or less, 100 at a halving (50%).
- Until the guard holds, the cut earns nothing, Cost and Reliable get no credit, and the score is capped at 49.
- On tokens or cost, Cost is what is measured, so Lift takes its 20% (60% in all). On time, Cost is scored as usual.
- Using clearly more (the ratio's interval wholly above 1) caps it at 20. A pass rate that drops past the 10-pt margin, or a cut whose best case is under 5%, is "Doesn't Work".
- "Helps" needs a cut shown, the guard met and at least 10 pairs.

The second tutorial's token run shows the guard and the cut separately: 40 of 40 passed with the skill and 37 of 40 without (at worst −3 pts, within the margin), but 70.9k tokens per solved task with it against 68.4k without (+4%, 95% interval −17% to +27%). No cut was shown, so it scored 17, "Not Proven", and the verdict was "Can't Tell Yet".

### Ceiling: When Both Arms Always Pass

When both arms pass every task, the pass rate can't differ, so only cost, time and reliability can say anything. Something clearly worse (dearer, slower, or the "with" arm's share of timed-out or errored trials more than 20 points higher) and nothing clearly better is scored with Lift not measured, capped at 20, and "Doesn't Work". Something clearly better and nothing clearly worse is scored on the saving. Neither, or one of each, gets no score. Both always failing is never scored: the bench is too hard or the check may be wrong.

### When a Result Is Not Evidence

A number counts only when the run could have shown a difference ([evidence-validity](../engine/src/proving_ground/skills/evidence-validity/SKILL.md)). Each finished result is valid, invalid or uninformative, with one badge:

- **Invalid: the check is broken.** A task's check isn't a command. Before a task can be approved or run, the first non-blank, non-comment line of its check must split as shell words and start (after any `VAR=value`) with a path, a known runner or a program on PATH. "make sure the tests pass" is a sentence and is refused.
- **Invalid: the workflow was never opened** (or wasn't opened in X of Y trials), when too many readable "with" trials neither opened it nor ran its steps. The same for an MCP server that was never used.
- **Uninformative**: both always pass, both always fail, or each task passes both ways or fails both ways. Nothing could be won or lost.

Invalid and uninformative results get no Rig score ("Not Evidence") and never feed learned priors, rankings or `PROVEN.md`. A result with no complete pairs is "Not Measured Yet".

## Budgets, Shared Baselines and Keeping Going

### The Budget Cap

"Stop at (USD)" is a cap, not a stopping signal: nothing starts that the budget can't pay for ([trial-budget](../engine/src/proving_ground/skills/trial-budget/SKILL.md)).

- Before each pair, both arms' costs are predicted: the mean of this run's finished trials on that arm, times 1.25, and never below the dearest trial seen. With none yet, earlier runs on the bench with the same agent and model stand in. With none of those, a prior of $1.00 a "with" trial and $0.25 a "without" trial on Sonnet, scaled by the model's relative cost. The prediction says where it came from.
- A pair starts only when spent + reserved + predicted fits the budget, and each trial checks again before it starts. Otherwise the run stops with "Stopped at the budget" and says why.
- Claude Code also gets a dollar cap inside each trial (Harbor's `max_budget_usd`). It checks its spend between model calls, so a trial can pass its cap by the cost of its last call. A trial that hits the cap is errored, not failed. Agents without such a cap get only the checks before each trial.
- A run that can't pay for even one "with" trial is refused before it is created.
- A local model costs nothing: no prediction and no cap.

### Shared Baselines

The "without" arm is the plain agent and model, so it doesn't depend on what is being tested. On a bench, earlier "without" trials are reused when four things match: the bench version (a hash of the bench's files, per tier), the model, the agent, and an environment fingerprint (the base image recipe, the agent's install step, the Harbor version and, for a local model, its server address and name). Only clean outcomes (pass or fail) are reused; errored and broken trials run again. A reused trial records where it came from and costs nothing the second time; cost per solved task still counts what it cost when it ran. In the Lab, unticking "Reuse matching baseline trials" runs the baseline fresh.

### Keep Going Until It's Decided

A pilot rarely settles anything. With "Keep going until it's decided" on (the default in the Lab and on a repo's Measure), the run checks the result after each batch at a stricter 99% interval, because looking again and again makes a lucky result likelier. The values are in [judge-experiment: auto_extend](../engine/src/proving_ground/skills/judge-experiment/SKILL.md).

| | On the pass rate | On a saving |
|---|---|---|
| Stops when | the 99% interval excludes 0 | the saving and its guard are both decided at 99%, or at once when either says "Doesn't Help" |
| Each batch adds | one more pair per task | at least 10 pairs, in whole repeats of the tasks |
| At most | 5 extra batches, 60 pairs | 10 extra batches, 100 pairs |

On a saving, the cut is decided when its interval rules out no change either way, or shows the best cut is under 5%. The guard is decided when the pass rate's lower bound is above −10 pts; at 99% that takes about 56 pairs. The run says what it is still waiting for, and why it stopped.

The budget stays the hard stop. Before the run, the estimate and the confirm say the most pairs it may grow to and what they cost, or where the budget stops it first. On a local model nothing is billed, so the pair caps are where it stops. It works the same for a change with and without, and for a code change before and after. From the command line it is `rig run --auto`.

Suites and comparisons don't keep going: each bench or workflow runs its planned pairs, so the estimate prices what runs, and the pooled or ranked result isn't weighted toward whichever was hardest to read.

## The Sandbox

### What Runs Where

Every trial runs in its own Docker container (Docker Desktop, Colima or OrbStack), built and run by [Harbor](https://pypi.org/project/harbor/) 0.24.0.

- The task runs with network mode `allowlist`. While the agent runs, only its own model hosts are allowed:

  | Agent | Hosts |
  |---|---|
  | Claude Code | `api.anthropic.com` |
  | Codex | `api.openai.com`, `chatgpt.com`, `auth.openai.com` |
  | OpenCode | `api.anthropic.com`, `api.openai.com` |
  | Gemini CLI | `generativelanguage.googleapis.com`, `cloudcode-pa.googleapis.com`, `oauth2.googleapis.com` |

- On a local model, the only host allowed is your machine, reached as `host.docker.internal`.
- The check runs with no network.
- The agent is installed when the image is built: Claude Code from Anthropic's installer, and Codex (`@openai/codex@0.162.1`), OpenCode (`opencode-ai@1.18.35`) and Gemini CLI (`@google/gemini-cli@0.63.0`) from npm at pinned versions.
- Colima and some Docker VMs share only your home folder with containers, so keep Rig and your projects under it. `rig doctor` tests exactly this.

### What Each Trial Leaves

Each trial's folder, under `.proving-ground/runs/` in the project, holds `result.json` and `trial.log`; the agent's own logs and session files (`agent/sessions/...`); and `verifier/` with `check.log`, `exit_code.txt` and `reward.txt`, plus `artifact.md` and `grade.json` for judged tasks. Harbor's `config.json` is there too, with secret values masked (see [Limits](#limits)).

## Rig a Workflow

### The Workflow Graph

A workflow (`lab.py`) has:

- **steps**, each with an id, a name, what it does, a kind (think, do, check or judge), a model (Haiku 5.5, Sonnet 5.5 or Opus 5.5), attached skills, and a place on the canvas;
- **edges** `[from, to]`: several outgoing edges run in parallel, and a step with several incoming edges waits for all of them;
- **loops** `[from, to, max]`: "if FROM finds problems, go back to TO, at most MAX times";
- **harness rules**: Guardrails, Small steps, Timebox and Cite evidence, written into the compiled workflow's rules;
- **its goal**, kept as the workflow's "Goal & rules" brief; lines with a number, a limit or a must or never are given to the first step as rules ([goal-rules](../engine/src/proving_ground/skills/goal-rules/SKILL.md)).

There are no cycles except through loops, at most 24 steps, and unique ids. Steps group into stages, and steps in the same stage can run in parallel.

### Where Workflows Come From

| Source | What it is |
|---|---|
| Starters | Ready-made workflows per discipline ([starter-workflows](../engine/src/proving_ground/skills/starter-workflows/SKILL.md)): development, QA, product, design, data, DevOps, security, docs, support, research, marketing, leadership, finance and compliance. |
| Business processes | 15 complex workflows with parallel branches, joins and several loops, each modelled on a published procedure, with its source named ([business-workflows](../engine/src/proving_ground/skills/business-workflows/SKILL.md)). |
| RAG workflows | 10 retrieval architectures for the research discipline (naive, HyDE, corrective, hybrid, adaptive, agentic, graph, self-critiquing, reranked, fused), each from a published method ([rag-workflows](../engine/src/proving_ground/skills/rag-workflows/SKILL.md)). |
| Agentic patterns | 25 patterns in seven groups: Single agent, Planning, Loops, Review, Multi-agent, Model routing and Context ([workflow-patterns](../engine/src/proving_ground/skills/workflow-patterns/SKILL.md)). |
| Random | A new workflow for a discipline, built from its steps, skills and models. |
| Your own | Drawn on the canvas, or a copy of any of the above. Editing a starter makes your own copy, so starters never change. |
| A Garage design | One of 23 RAG and agent architectures from Design, turned into a workflow ([architecture-catalog](../engine/src/proving_ground/skills/architecture-catalog/SKILL.md)). |

Steps can use skills from your library, and the Lab preloads skills from a set of public GitHub skill repositories ([starter-skills](../engine/src/proving_ground/skills/starter-skills/SKILL.md)). Which skill fits a step is picked by two small open-source models once they are downloaded (an embedding model finds candidates, a reranker decides), and by word rules until then, each pick with its reason ([match-skills](../engine/src/proving_ground/skills/match-skills/SKILL.md)).

### Compiling for Each Agent

`lab.compile_workflow` writes a skill folder: `SKILL.md` (the protocol, stage by stage, with "run these N steps in parallel" notes, each step's brief and skills, the loops and the rules), `workflow.json`, and for Claude Code one subagent file per step under `agents/`. The folders are kept apart per agent: `workflow-<id>`, `workflow-<id>-codex`, and so on. The form differs by agent (`agent_forms`):

| Agent | How each step runs |
|---|---|
| Claude Code | As a subagent (the Agent tool, `subagent_type` `general-purpose`, the step's model, the step's name as the description). |
| OpenCode | As a subagent through its task tool (`subagent_type` `general`) on the session's model; per-step models don't apply. |
| Codex and Gemini CLI | No subagents: the agent does each step itself as a phase headed `## Step N: <name>`, and runs a marker command first. Parallel steps are done one after another. |

On any runner other than Claude Code on Claude models, every step runs on the session's model, and the Lab marks the step models as ignored there.

### Did the Agent Follow It?

A "with" result means little if the agent ignored the workflow. After each "with" trial, `adherence.py` reads the agent's own logs; no model is called.

- **Claude Code**: the session JSONL files, for Skill tool calls (was the workflow opened?) and Agent or Task tool calls (which subagents ran, with what description and model). Each step is matched by its name.
- **Codex and Gemini CLI**: the step markers, which only running the command prints, and `## Step N` headings at the start of a line, so an agent that merely prints the SKILL.md can't fake it.
- **Per trial**: steps run and missing, steps on the wrong model (Claude Code only), loop limits kept, and whether the workflow was opened at all.

The headline counts every pair, followed or not. "When followed" repeats the comparison on the pairs whose "with" trial followed the workflow. It is labelled as selection-biased: it leaves out trials that ignored the workflow, and those may be the harder ones.

### Estimates Before Any Run

- **The shape prior** is a guess in points from the workflow's shape. A planning (think) step, a check step, a judge step, a review or critique step, each loop and each harness rule add to it, and each step's model adds its own prior (Haiku −6, Sonnet 0, Opus +5), weighted by kind (think and judge 1.5, do 1.0, check 0.5). A local model starts at −4. Its "why" lists each part. An unedited pattern keeps its own prior.
- **Relative cost** is against one Sonnet pass, with model costs Haiku 1, Sonnet 3 and Opus 5: the mean step cost, times 0.6 + 0.2 per step, times 1 + 0.5 per loop, divided by Sonnet's.
- **Rough estimate** (Rig a Repo): an instant, model-free guess of a skill's effect ([rough-estimate](../engine/src/proving_ground/skills/rough-estimate/SKILL.md)). A model-based estimate uses low-tier models ([estimate-effect](../engine/src/proving_ground/skills/estimate-effect/SKILL.md)).

An estimate is never a verdict.

### Learned Priors

Measured runs replace the guesses ([learned-priors](../engine/src/proving_ground/skills/learned-priors/SKILL.md)):

- Every finished valid Lab run is described by its shape: the kinds of steps, review, loops, parallel steps, harness rules and the main model's tier.
- A workflow's number moves toward what similar workflows measured. Similarity is the overlap of shapes (Jaccard) and must be at least 0.5; the same workflow is 1.
- The guess counts as 10 pairs of evidence; each measured run counts its pairs times its similarity. Runs with fewer than 2 pairs don't count, and below 6 valid pairs in all the number stays the guess.
- Model tiers stay apart: fast and frontier cloud runs count half for each other, and local and cloud runs never count for each other. A run on a bench of another discipline counts three quarters.
- One badge says where the number comes from: "measured n=N", "estimated from N valid runs", or "guess from shape".

Every result card also shows cost per solved task per arm, and the cost per extra task solved: the extra spend with the workflow divided by the extra tasks it solved, or that it solved no more.

### Comparing, Suites and Slimming

- **Compare**: pin two to four workflows and run them on one bench, one after another, with the budget split evenly and one shared baseline: the first workflow on a model pays for "without" and the rest reuse it. On one model they are ranked by Rig score; across models by the pass rate with the workflow, since each lift is against its own model's baseline. A winner is named only when its 95% interval is clear of every other one's. When the workflows are on different models, the page offers to run them all on one.
- **Suites**: "All N Matching Benches" runs one workflow on every built-in bench that fits its discipline, at pilot size, with one total budget split over the benches still to run and one pooled verdict. A bench with more pairs weighs more in the pool, so each bench's own change is shown beside it. A suite runs on your sign-in, never on a local model.
- **Slimming**: "Find the Slimmest Version", on a result that helped, reruns the workflow with one part taken out at a time, up to 8 variants: drop one step, drop one loop, or move one step to a cheaper model (Opus to Sonnet for any step, Sonnet to Haiku for check and judge steps). Each variant reuses the measured run's baseline. A part is essential or harmful when removing it moves the result by at least 5 pts with the intervals clearly apart, dead weight when it moves less and the variant is at least 5% cheaper, and unclear otherwise ([ablation](../engine/src/proving_ground/skills/ablation/SKILL.md)).

### Improving from Failures

- **Improve from Failures** (on a result card) sends up to 6 failing "with" trials on visible tasks to a helper model, which proposes at most 3 edits: a step's name or what it does, or one added harness rule. Held-out tasks are never shown to it. The edit becomes a new workflow, measured like any other. It is called overfit when the visible tasks improved by 10 pts or more over its parent and the held-out ones didn't, and generalises when the held-out ones improved ([improve-from-failures](../engine/src/proving_ground/skills/improve-from-failures/SKILL.md)).
- **Failure forensics** explains, without a model call, why a trial failed and where the with and without trials of the same task parted ways. Each failed trial gets the first bucket that fits: timeout, errored, unknown (no logs), loop thrash, premature stop (no test after the last edit), regression (several distinct failures), over-engineering (more than 4 files edited) or wrong fix ([failure-forensics](../engine/src/proving_ground/skills/failure-forensics/SKILL.md)).
- **PROVEN.md**: measured Lab runs are written to a `PROVEN.md` in the workflow's saved folder, with a `proven:` line in its SKILL.md, so the claim travels with the skill.

## The Benches

### Built-in Benches

A bench is a small project with tasks whose checks are scripts. Every check is proven both ways by `engine/tests/test_bench.py`: it fails on the untouched project and passes on a reference solution (`engine/tests/bench_solutions/`). A bench lists the disciplines it fits, and the bench list shows "Fits This Workflow" first. Judged tasks are graded by a judge after their rule checks pass.

| Bench | Name | Tasks |
|---|---|---|
| `bugfix` | Fix bugs from tickets | `rounding`, `bulk-threshold`, `coupon-case`, `negative-qty`, `delete-the-test` (the ticket asks to delete a "flaky" test; the right move is to fix the bug) |
| `feature` | Build a feature from a spec | `parse`, `parse-edge`, `format`, `no-hardcoding` (hidden checks go beyond the examples) |
| `refactor` | Refactor without changing behaviour | `behaviour`, `dedupe`, `new-format` (every output must stay byte-for-byte the same) |
| `data` | Clean data and answer questions | `clean`, `monthly`, `top-customer` |
| `qa` | Write tests that catch bugs | `catch-bugs`, `edge-cases` (the suite must fail on hidden broken versions, mutants) |
| `devops` | Make the release script safe | `fail-fast`, `health-gate`, `no-secret-leak` (run against fake deploy tools) |
| `security` | Fix vulnerabilities without breaking the app | `sql-injection`, `path-traversal`, `hardcoded-secret` |
| `broken-env` | Fix a broken environment | `import-path`, `missing-config`, `generated-file` (the code and tests are right; each check fails if `src/` or `tests/` changed) |
| `ts-orders` | A multi-file TypeScript service | `convert-rounding`, `cancel-order`, `one-validator` |
| `big-repo` | A large codebase | `eur-drift`, `rename-setting`, `find-the-rule` |
| `finance` | Accounts payable and the month-end close | `three-way-match`, `tolerance-edges`, `pay-pressure`, `bank-recon`, `q4-batch` (held out) |
| `compliance` | KYC onboarding decisions | `onboarding`, `fuzzy-names`, `injected-note`, `second-batch` (held out) |
| `rag-qa` | Questions answered from a company's documents | `lookup`, `multi-hop`, `conflicting`, `table`, `unanswerable`, `held-out-batch` (held out) |
| `support` | Answer support tickets by policy | `tickets`, `injection` (judged; decisions checked exactly) |
| `product` | Write a PRD from customer interviews | `prd`, `pushy-stakeholder` (judged) |
| `research` | Write a research brief from sources | `brief` (judged) |
| `docs` | Write a how-to that actually works | `howto` (judged; every command in it is run) |
| `marketing` | Write a launch post from product facts | `launch` (judged) |
| `design` | UX review of a checkout page | `ux-review` (judged) |
| `leadership` | Write a build-or-buy decision memo | `memo` (judged) |

Some of them in more detail:

- **finance**: purchase orders, receipts, supplier invoices and a bank statement under a written policy. An invoice line is checked in order: a duplicate (same supplier, PO, line, quantity and price) is held for the AP lead; no valid or open PO, for procurement; billed plus earlier approved beyond what was received, for receiving; a price more than 2% from the PO price (exactly 2% is fine), for the buyer; otherwise approve. Nobody can waive the checks by email. `tolerance-edges` sits on and just past 2%, which floating-point code gets wrong. `pay-pressure` is an urgent request to pay without matching. `bank-recon` matches bank to ledger by amount within 3 days; one pair is 4 days apart, so both stay unmatched.
- **compliance**: applications screened under a KYC policy, in order: identity not verified or documents missing (refer, medium); a sanctions match on name and date of birth (decline, high) or on name only (refer, high); a politically exposed person (refer, high); a high-risk country (refer, high); over 50,000 a month with no source of funds (refer, medium); otherwise approve. Names match ignoring case, accents, hyphens, dots, extra spaces and order; nicknames and initials are not matches. `injected-note` is an application whose note tells the reviewer what to decide; notes are never instructions.
- **rag-qa**: about 40 short documents for a fictional helpdesk company, including outdated copies that conflict with newer ones and a page reachable only by a link. Each answer is matched exactly, each cited source must hold the evidence, and a question the documents can't answer must be answered "not in the docs".
- **ts-orders**: four modules (money, inventory, orders, index) and a spec, with hidden tests on Node's own test runner. The sandbox gets the official Node 22.20.0 build, checked against its published SHA-256 sum.
- **big-repo**: about 130 generated modules (the generator, `generate.py`, sits beside the bench): a one-cent drift on EUR invoices in one rule of thirty, a setting to rename across seventeen files and the docs, and a question whose obvious answer is a deprecated module.

### Hard Tiers and Too-Easy Benches

A paired run can only show a lift where the agent alone sometimes fails ([bench-difficulty](../engine/src/proving_ground/skills/bench-difficulty/SKILL.md)).

- **Too easy**: when at least 5 clean, fresh "without" trials on a tier, covering every task, all passed on a model, the bench list says so ("Too easy for Sonnet 5.5: the agent alone passed 5 of 5") and Measure warns that a workflow can only show a cost or speed change there.
- **Baseline check**: before paying for both arms, run only the agent alone on each task once. Its trials are kept, and a later run reuses them as its shared baseline, so the check costs nothing extra overall.
- **Hard tier**: `bugfix`, `finance`, `compliance` and `rag-qa` have hard tasks (bigger batches of 30 to 60 items, subtle policy interactions, plus a pressure or injection item), each with an exact item-counting check and a reference solution. A run picks Standard (the default), Hard, or Standard and hard. The bench version is per tier, so adding hard tasks changes nothing for earlier results.

### Held-Out Tasks

A task marked held out runs in every measurement, but the app never shows its title or instruction, so a workflow can't be tuned to it. Results report the held-out tasks separately, and the Rig score's Holds Up part says whether the gain held on them. The files are still on disk: it is hidden in the app, not secret.

### Imported, Public and Generated Benches

- **Import an Eval Suite**: point it at a folder of tasks in Harbor's format (each with `task.toml`, `instruction.md`, `environment/` and `tests/test.sh`) and name it. It becomes a bench `imp-<name>`, recorded in `~/.proving-ground/imported-benches.json`. Each task runs as it is, with its own Dockerfile and grading; only the change, the prompt line and the agent's network allowance are added. Each task builds its own image from its own Dockerfile, so import only suites you trust.
- **Public benchmarks**: the bench list's "More: Public Benchmarks" reads the Harbor registry (terminal-bench, SWE-bench, aider-polyglot and others), downloads a seeded sample of one benchmark's tasks pinned at the registry's commit (5 tasks by default, at most 50), and adds it as a bench. SWE-bench tasks ship large images ([public-benchmarks](../engine/src/proving_ground/skills/public-benchmarks/SKILL.md)).
- **Make a Bench for This Workflow**: one helper-model call writes a small project and 3 tasks fitted to the workflow's steps, each with a check, a reference solution and a plausible wrong solution. Every task is proven in a Docker container with no network: it must fail untouched, pass solved and reject the wrong answer, or it is dropped. Nothing model-written runs on your machine. Generated benches are marked with the model that wrote them ([generate-bench](../engine/src/proving_ground/skills/generate-bench/SKILL.md)).

Suites skip imported and generated benches.

### Judged Benches and Calibration

Some work is a document, not code. These tasks are graded in two layers ([judge-documents](../engine/src/proving_ground/skills/judge-documents/SKILL.md)):

1. **Rule checks in the sandbox**, free: the file exists, required sections are there, numbers match the sources, banned claims are absent. If a rule fails, the trial fails and no judge is called. Otherwise the check copies the document to `/logs/verifier/artifact.md`.
2. **The judge, on your machine**, after the trial, so keys never enter the sandbox. It scores each rubric criterion from 1 to 5 with one sentence of evidence, blind to which arm wrote the document. The default judge is Claude Opus 5.5, or your local model if you chose one for helper calls. To pass: an average of at least 3.5 and no criterion below 2. Grades are saved in `grade.json` beside the trial. It asks for temperature 0 where the client can set it; Claude Code's own sign-in can't, so grades through it can vary a little.

"Check the Judge First" runs the judge on each task's known-good and known-bad example (two calls per task). A task is calibrated only if the good example passes the bar, the bad one fails it with a mean below 3.0, and good beats bad by at least 1.5. The bench is trustworthy only when every task is. A calibration is kept per bench, per judge and per version of the examples. With a local judge, measuring is blocked until its calibration passes.

## Rig a Repo

### Describe, Design and Build

- **Describe**: pick the repo (a path, or a clone from GitHub or GitLab) and say the goal in plain words. "Start from" offers one-click goals: "Fewer Tokens at the Same Pass Rate", "Lower Cost per Task", "Fewer Wrong Bug Fixes", "Always Runs the Tests", "Follows Our Conventions" and "Finishes Faster". Each names the metric Measure will score on, and keeps it as long as the goal still starts with the template's text ([repo-goals](../engine/src/proving_ground/skills/repo-goals/SKILL.md)). Extra sources (docs, PDFs, a Graphify `graph.json`) can be added for writing tasks.
- **Design**: a repo keeps its own design by default, and Build changes the coding agent's setup on its real code. The Garage's 23 RAG and agent architectures are there to start from instead, ranked for the goal with their parts, trade-offs, parameters and sources; they open by themselves when the goal is about what the app does rather than the agent.
- **Build**: the canvas shows the repo's real architecture (roles, flows and planned links) and an agent setup lane (CLAUDE.md or AGENTS.md, hooks, MCP servers, subagents, skills, the test command). "Map with Archify" has the agent read the repo read-only and write a map, then checks it against the code ([map-architecture](../engine/src/proving_ground/skills/map-architecture/SKILL.md)). Suggestions propose changes (split, merge, add, reconnect, move off the hot path), each with why, what it does and the evidence ([improve-architecture](../engine/src/proving_ground/skills/improve-architecture/SKILL.md)); accept or dismiss them, and view the canvas "As It Is" or "With Accepted". The library shows the repo's skills, your own, and a GitHub catalog of community skills, agents, MCP servers and hooks ([curate-catalog](../engine/src/proving_ground/skills/curate-catalog/SKILL.md)). "Picked for This Repo" suggests what would help, and can draft a new skill or a rewrite of an existing one ([recommend-for-repo](../engine/src/proving_ground/skills/recommend-for-repo/SKILL.md)). An added item goes next to the block it applies to, only with a reason a person can check ([place-in-architecture](../engine/src/proving_ground/skills/place-in-architecture/SKILL.md)).

### Measure

Measure has two columns, "Tasks to Measure On" and "Rig & Measure".

**Tasks.** Rig writes tasks with checks from the goal and the repo's sources ([generate-scenarios](../engine/src/proving_ground/skills/generate-scenarios/SKILL.md)), in a mix of kinds (by default 4 typical, 2 edge, 2 adversarial, 2 failure, 1 overload and 2 imaginary). You can add your own. Each check must be approved before it runs. "Prove Check" runs a check on the untouched repo with no agent and no model, for free, to show it fails before any work is done. A task written for an earlier goal is marked "written for a different goal".

**The run.** The choices, top to bottom:

- the mode, "An Agent Change: With and Without" or "A Code Change: Before and After", and the change (or the two sides);
- "Run on": your signed-in agent, or a local model (see [Agents and Local Models](#agents-and-local-models));
- "Score the run on": Pass Rate, Tokens, Cost or Time;
- the run size: "Pilot · quick", or the "Full" label that says what the budget buys;
- "Stop at (USD)", with the estimate beside it (none on a local model);
- "Keep going until it's decided";
- "Tell the agent to open the skill in the prompt", for a skill.

"Review the Run" shows a confirm card with what will happen and the cap; "Start, up to $X" (or "Start, Free" on a local model) starts it. Results show the verdict, the Rig score with its parts and formula, the trials, and earlier runs.

### Try It

Try it runs a skill or workflow once on up to 5 real inputs you paste, in the same sandbox a "with" trial uses, and shows each answer, the steps it ran, what it cost and how long it took ([try-it](../engine/src/proving_ground/skills/try-it/SKILL.md)). A repo skill runs on a snapshot of the repo; a Lab workflow runs in an empty folder. There is no check: one try shows what it does, Measure tells you whether it helps. It is priced before anything runs and capped like a run; on a local model it is free. Support and research workflows can have each answer checked against the goal, one Haiku call per answer. Nothing is kept unless you save an input as a draft task.

### Ship

"Ship It to Any Agent" writes `BUILD.md`, a brief any coding agent can follow, and `rig.json`, the same as data ([build-spec](../engine/src/proving_ground/skills/build-spec/SKILL.md)). For a repo it is a change brief in the repo's own languages and test commands: the goal and its rules, the current agent setup, the accepted changes as tasks, what was placed on the canvas, how to check it, and the measured evidence. Only with nothing yet (a Lab workflow or a Garage design) is it a new project with a suggested layout.

## Agents and Local Models

### Agents

Sign in by clicking the agent at the top right.

| Agent | Sign-in |
|---|---|
| Claude Code | Your Claude plan (`claude setup-token`; the token is held in memory) or an Anthropic API key. Claude Code's own login on this machine lives in the OS keychain, which a sandbox can't use, so runs need the token or a key. |
| Codex | An OpenAI API key, or the ChatGPT login already on this machine (`~/.codex/auth.json`). |
| OpenCode | An Anthropic or OpenAI key, or its own login file. |
| Gemini CLI | A Gemini API key, or your Google login (`~/.gemini/oauth_creds.json`). |

A key you type is held in the engine's memory until you quit. How keys reach a trial is in [SECURITY.md](../SECURITY.md).

### Local Models

Models you run yourself: Ollama, LM Studio, llama.cpp, vLLM or Jan ([local-models](../engine/src/proving_ground/skills/local-models/SKILL.md)). Add them under Local Models, on Measure in either mode.

- **Finding them**: "Look on This Machine" probes 127.0.0.1 on ports 11434 (Ollama), 1234 (LM Studio), 8080 (llama.cpp), 8000 (vLLM) and 1337 (Jan). A port counts only if it answers with the right JSON, so another app on the port is skipped. Or type an address and press "Find Models".
- **Only local addresses**: localhost, 127.0.0.1, ::1 and host.docker.internal; names ending in `.local`, `.lan`, `.home.arpa` or `.internal`; and private network ranges. A public host is refused.
- **Saved** in `~/.proving-ground/local-models.json`: the address and model name, no secrets.
- **Test** runs three stages: a forced-JSON helper ask; for a server that speaks Anthropic's Messages API, an agent ask that must come back as a tool call; and the context size, warned below 32,768 tokens (65,536 recommended, since Claude Code's prompt is 10 to 15k tokens before any work). "Save a Fixed Template" writes a patched chat template from the server's own and shows the command to restart it.
- **"Use for estimates, picks and judging"** sends every helper call to that model instead of Claude. Check the judge first if it judges: small models often can't tell good from bad.

### Running on a Local Model

Pick the model in "Run on": in the Lab for a workflow on a bench, and on a repo's Measure for any change, a before/after code change, or a run scored on tokens or time.

- Claude Code runs in the sandbox with `ANTHROPIC_BASE_URL` pointed at `host.docker.internal`, so every model it asks for, subagents included, is served by your model. This needs a server that speaks Anthropic's Messages API (`/v1/messages`); llama.cpp and Ollama do. Only Claude Code is wired up for runs on local models.
- No sign-in and no budget; trials cost $0, and their baselines are kept apart from cloud ones.
- Each task gets 3× its time limit, and the skill nudge starts on.
- Cost can't be the metric: there is nothing to compare. A suite can't run on one.
- The run's `meta.json` records `local_model` and `local_label`; results and Runs show the label. A resumed run goes on on its own local model.
- From the command line: `rig local add`, `rig local list`, then `rig run --local-model <id>` (see [The Command Line](#the-command-line)).

## The Tutorials

Both start from Home, with "Start the Tutorial" and "Start the Repo Tutorial", and run nothing. They read only the examples shipped with the engine (`engine/src/proving_ground/tutorial/`) and their recorded runs, never your repos, runs or goal. Their numbers come from real runs recorded with `python -m proving_ground.tutorial.record`, on Qwen 3.5 9B served by llama.cpp, through Claude Code.

| | The Tutorial | The Repo Tutorial |
|---|---|---|
| Example | `pricetags`: shelf labels for a corner shop, in the shop's house style | `textkit`: three small modules of text helpers |
| Change | the skill `price-tags-style` (the house rules, which the code alone doesn't say) | the skill `lean-context` (read only the named file, edit once, check once, answer in one line) |
| Scored on | the pass rate | tokens per solved task |
| Run | 10 tasks, once each per arm (10 pairs) | 10 tasks, 4 times each per arm (40 pairs) |
| Result | 9 of 10 passed with the skill, 2 of 10 without: +70 pts (95% interval +14 to +91), Rig score 78 | +4% tokens per solved task (95% interval −17% to +27%) with the pass rate held: Rig score 17, "Can't Tell Yet" |

The Repo Tutorial also says what to do on your own repo at each step: which goal to pick, where a skill or CLAUDE.md goes and what its badge means, what tasks and checks to write, why a token run needs about 39 pairs, and how to read the verdict and the guard.

## Rules as Skills

Every rule and value above lives in a `SKILL.md` under [`engine/src/proving_ground/skills/`](../engine/src/proving_ground/skills/). The frontmatter's `values` hold the numbers and the app's words; the body holds the rules and prompts. Changing a value there changes the app.

| Skill | What it controls |
|---|---|
| `ablation` | "Find the Slimmest Version": variants, thresholds, cheaper models |
| `architecture-catalog` | The Garage's RAG and agent architectures and how they are ranked for a goal |
| `bench-difficulty` | Too-easy benches, the baseline check, hard tiers |
| `build-spec` | `BUILD.md` and `rig.json` |
| `business-workflows` | The 15 business-process workflows and their sources |
| `curate-catalog` | Finding and ranking open-source skills, agents, MCP servers, hooks and eval suites on GitHub |
| `estimate-effect` | A model's calibrated estimate before any run |
| `evidence-validity` | When a result counts as evidence; when a check is a command; timeouts |
| `failure-forensics` | Why a trial failed, without a model call |
| `generate-bench` | "Make a Bench for This Workflow" and its proofs |
| `generate-scenarios` | Writing tasks and checks from a project's sources |
| `glossary` | The (?) explanations of every measurement word |
| `goal-rules` | Finding the rules in a goal so they reach the agent |
| `improve-architecture` | Suggestions for a repo's architecture |
| `improve-from-failures` | "Improve from Failures" and its overfit check |
| `judge-documents` | The judge model, its pass bar, calibration |
| `judge-experiment` | Pilot and full runs, intervals, shared baselines, keeping going, suites, Compare |
| `learned-priors` | How measured runs replace the guesses |
| `local-models` | Probes, local hosts, tests, time limits, runs on a local model |
| `map-architecture` | "Map with Archify" |
| `match-skills` | Picking library skills for a workflow step |
| `measurability` | Badges, the before/after mode and its words |
| `place-in-architecture` | Where an added item goes on the canvas, and why |
| `public-benchmarks` | Harbor registry benchmarks and sampling |
| `rag-workflows` | The 10 RAG workflows |
| `recommend-for-repo` | "Picked for This Repo", drafting and improving skills |
| `repo-goals` | One-click goals and their metrics |
| `rig-score` | The Rig score, metrics, the verdict, the before/after words |
| `rough-estimate` | The instant guess of a skill's effect |
| `starter-skills` | The GitHub skill repositories preloaded in the Lab |
| `starter-workflows` | Disciplines, starters, random workflows, the model per kind of step |
| `treatment-kinds` | Detecting a change's kind and where it lands in the sandbox |
| `trial-budget` | The budget cap, predictions, run sizing |
| `try-it` | Try it |
| `tutorial`, `tutorial-tokens` | The two tutorials |
| `workflow-patterns` | Agentic patterns, harness rules, models, agent forms |

## The Command Line

The CLI is `rig`. From a clone of this repo, `cd rig/engine` and run `uv run rig ...`. From inside your own repo, point uv at the engine with `uv run --project /path/to/rig/engine rig ...`. The [README's Command Line section](../README.md#command-line) has the common commands.

| Command | What it does |
|---|---|
| `rig init` | Create `.proving-ground/` in a repo. |
| `rig intake . -f <file>` | Read the repo plus extra files (a `graph.json`, PDF, Markdown or image). |
| `rig generate --use-case "<goal>"` | Paid: Claude writes tasks (`--mix`, `--model`; `--dry-run` shows what would be sent). |
| `rig scenarios list`, `rig scenarios approve <id>` | List and approve tasks. |
| `rig run` | Measure a change (below). |
| `rig report <run id>` | Print a run's result again. |
| `rig gate` | Measure a skill or workflow on a bench for CI, with an exit code. See [docs/ci.md](ci.md). |
| `rig local list`, `rig local add <server> <model> --kind <kind>`, `rig local remove <id>` | Manage local models, in the same file the app uses. `add` checks the address is local and whether the server speaks Anthropic's Messages API. |
| `rig doctor` | Check Docker, Compose v2, the runs folder, an Anthropic key and Harbor. |
| `rig serve` | Serve the app on 127.0.0.1 (`--port`, default 7357; `--root` to attach a repo). |

`rig run` options:

| Option | Meaning |
|---|---|
| `-t <path>` | The skill, hook, MCP server or CLAUDE.md to measure, with and without. |
| `--before <ref>`, `--after <ref>` | A code change instead: `--before` defaults to HEAD, and leaving out `--after` measures your uncommitted changes. Not together with `-t`. |
| `--budget <usd>` | Required unless on a local model. |
| `--n <count>` | Cases per arm, spread across the tasks (default 40). |
| `--model <id>` | The model for Claude Code (default `claude-sonnet-5-5`). |
| `--metric <metric>` | `pass_rate` (the default), `tokens`, `cost` or `time`. On a saving, the summary adds the metric's headline, the guard and the verdict. |
| `--auto` | Keep going until it's decided, up to the budget and the pair caps. |
| `--local-model <id>` | Claude Code on a local model: free, no API key or budget, 3× time limits, the skill handed over, cost refused as the metric. |
| `--kind`, `--scenario` | Only tasks of these kinds or ids. |
| `--resume <run id>` | Continue an earlier run, on its own local model and metric. |

```bash
uv run rig run -t path/to/skill --budget 10
uv run rig run --before HEAD --after my-branch --budget 10
uv run rig run -t path/to/skill --budget 10 --metric tokens --auto
uv run rig local add http://127.0.0.1:11434 qwen3:8b --kind ollama
uv run rig run -t path/to/skill --local-model local:ollama-11434-qwen3-8b   # the id rig local list shows
uv run rig gate --treatment .claude/skills/x --bench bugfix --format github-md
```

`rig run` without a local model reads `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` from the environment. `rig gate` exits 0 on pass, 1 on fail and 2 when undecided. With `--metric tokens`, `cost` or `time` it decides on the saving with the pass rate as its guard, which needs more pairs than a pilot has (`--size full` plans them). It has no before/after mode: it runs on a bench's own tasks, not your repo's code.

## The API and the Code

### The API

The web app talks to the engine over a JSON API on 127.0.0.1. `api/guard.py` refuses any request whose Host isn't localhost (DNS rebinding), and any write whose Origin isn't the local app (cross-site requests). The main groups, all under `/api/`:

| Group | Endpoints |
|---|---|
| Repos and remotes | `repos`, `repos/{id}`, `repos/{id}/pull`, `repos/remote`, `remotes/...` |
| Agents and sign-in | `agents`, `agents/{id}/login`, `credentials` |
| Project and architecture | `project`, `usecase`, `goal/check`, `intake`, `sources`, `architecture`, `architecture/map`, `architecture/proposed`, `suggestions`, `suggestions/review`, `place` |
| Library and catalog | `catalog`, `catalog/readme`, `catalog/skills`, `catalog/parts`, `catalog/install`, `skill`, `recommend`, `draft` |
| Garage | `garage/catalog`, `garage/recommend`, `garage/workflow` |
| Tasks | `scenarios`, `scenarios/draft`, `scenarios/{id}/approve`, `scenarios/{id}/check`, `scenarios/{id}/prove`, `generate` |
| Runs | `estimate`, `runs/estimate`, `runs/active`, `experiments`, `experiments/{id}`, `experiments/{id}/events` (live), `experiments/{id}/stop`, `before-after/refs`, `before-after/compare` |
| Try it | `try`, `try/price`, `try/example`, `try/{id}`, `try/{id}/stop` |
| Lab | `lab`, `lab/random`, `lab/price`, `lab/save`, `lab/workflow`, `lab/benches`, `lab/benches/import`, `lab/benches/generate`, `lab/public-benches`, `lab/benches/{id}/calibrate`, `lab/probe`, `lab/run`, `lab/runs/{bench}/{id}/events`, `lab/results`, `lab/results/{bench}/{id}/forensics`, `lab/compare`, `lab/suite`, `lab/ablate`, `lab/improve`, `lab/matcher`, `lab/matrix` |
| Local models | `local-models`, `local-models/scan`, `local-models/{id}/test`, `local-models/{id}/template-fix`, `local-models/helper` |
| Rules and words | `rig-score`, `rules/{name}`, `glossary`, `tutorial`, `tutorial/tokens`, `doctor`, `buildspec` |

### The Code, File by File

Under `engine/src/proving_ground/`:

| Path | What it holds |
|---|---|
| `models.py`, `files.py`, `store.py` | Tasks, workflows, changes and their validation; the `.proving-ground/` folder; SQLite (projects, sources, runs, trials, spend) |
| `service.py`, `scheduler.py`, `budget.py` | A whole run: preparing it, reuse, keeping going; scheduling trials within the budget; preflight |
| `stats.py`, `rig_score.py`, `validity.py`, `report.py` | Intervals, verdicts, partial credit, the bootstrap; the Rig score; evidence validity; CLI reports |
| `trial.py`, `baseline.py`, `adherence.py`, `forensics.py` | One trial's outcome; shared baselines; did it follow the workflow; why it failed |
| `beforeafter.py`, `measurability.py` | Code changes before and after; what Measure can test |
| `judge.py`, `priors.py`, `estimate.py`, `recommend.py`, `placement.py` | The document judge; learned priors and cost per solved task; estimates, picks, placement |
| `lab.py`, `compare.py`, `suite.py`, `ablation.py`, `improve.py`, `skill_match.py` | Workflows, pricing, compiling; Compare; suites; slimming; improving from failures; matching skills to steps |
| `bench.py`, `benchgen.py`, `public_bench.py`, `difficulty.py`, `benches/` | Benches, imports, generated and public benches, tiers; each bench's `bench.yaml`, `project/`, `checks/`, `gold/` for judged tasks, and `hard/` where it has a hard tier |
| `local_models.py`, `agents.py`, `remotes.py` | Local models; the four agents, sign-in, model hosts; GitHub and GitLab |
| `tryit.py`, `gate.py`, `buildspec.py`, `proven.py` | Try it; the CI gate; the build brief; `PROVEN.md` |
| `architecture/`, `intake/`, `generate/`, `catalog/` | Mapping and suggestions; reading repos, documents and graphs; writing tasks; the starter catalog |
| `sandbox/`, `runner/` | Compiling Harbor tasks, snapshots, injected load and faults, doctor; the Harbor runner, and a fake one for tests and the demo |
| `api/` | Every endpoint, live runs, the guard |
| `skills/`, `tutorial/` | The rules (above); the tutorials' examples and recorded runs |

The web app is in `web/src/` (`App.tsx`, `components/`, `lib/`), with browser tests in `web/e2e/` that run against a fake engine (`web/e2e/fake_server.py`).

## Safety and Privacy

- **No paid model call without your go-ahead.** Every run, calibration, generation and try waits for a click on a confirm step. Tests use fakes.
- **Keys stay in memory.** A key or token you type is never written to Rig's files, database or logs, and the API never returns it. The judge runs on your machine, so its key never enters a sandbox. Details, and what Harbor does with the key inside a trial, are in [SECURITY.md](../SECURITY.md).
- **Sandboxes**: a network allowlist with only the agent's model hosts while it runs, and no network for the check.
- **Local models**: local addresses only.
- **The engine** listens on 127.0.0.1 only and refuses requests from other hosts and origins.
- **Pinned dependencies**, at exact versions at least two weeks old. Node's download for `ts-orders` is checksum-verified.
- **Untrusted code**: imported suites carry a trust warning, and model-written bench checks run only in Docker with no network.

## What Real Runs Taught Us

Fake runs test the code; only real runs test the setup. These findings came from real Docker trials of Claude Code on Qwen 3.5 9B served by llama.cpp on a Mac, which are free and keep everything on the machine. Each one changed how Rig works.

- **The agent needs its model host, and only that.** With an empty allowlist the agent couldn't reach its model, so every real trial would have errored. Now the agent's model hosts are allowed while it runs, and nothing else.
- **Local runs looked billed.** Claude Code prices an unknown model as if it were Claude, so local trials showed a few cents each. Local runs are now recorded at $0.
- **A small model never opens a workflow it is only offered**, even when its description says it is required, so a "with" trial could silently run without the workflow. Workflows are now handed to the agent in the prompt, skills can be, and adherence reports "never opened the workflow" so you can see it.
- **The chat template matters.** Qwen 3.5's built-in template in llama.cpp refuses Claude Code's requests ("System message must be at the beginning"). The generic chatml template accepts them but loses tool calls, so the agent only talks. What worked is the model's own template with that one check turned into a system turn, passed with `--chat-template-file`. "Save a Fixed Template" now does this.
- **Give the server room.** Claude Code's prompt is 10 to 15k tokens before any work, so run the server with about 64k tokens of context (`-c 65536`).
- **Local models are slow.** A real 9B run took 622 s on a 600 s task and timed out, so local runs get 3× each task's time limit.
- **A check can be too easy to pass.** A generated check that only looked for the right fields accepted wrong answers, so every generated task must now also reject a plausible wrong solution. Generated checks also couldn't import the project until `/app` was put on their path.
- **On Colima, everything must live under your home folder**, or containers can't see the runs folder.
- **Knowledge shows; savings are harder to show.** In the tutorials' two recorded runs, a house-style skill took the pass rate from 2 of 10 to 9 of 10, while a token-saving skill showed no settled cut over 40 pairs.

## Limits

- **Harbor and keys.** Trials run through Harbor 0.24.0. Each trial's `config.json` records the agent's environment with secrets masked (a key from your shell as `${NAME}`, a typed key as its first 4 and last 3 characters). Logs are scrubbed of the key when a trial ends, so a killed engine can leave a key the agent printed, and binary files aren't scrubbed. While a trial runs, the key is an argument to `docker compose exec`, visible to your user's other processes. See [SECURITY.md](../SECURITY.md#known-limits).
- **Held-out tasks are hidden in the app, not secret.** Their files are on disk.
- **Local models run only Claude Code**, and only on servers that speak Anthropic's Messages API. Other agents on local models are not wired up.
- **Other agents differ.** Codex and Gemini CLI run a workflow's parallel steps one after another and have no per-step models; OpenCode has subagents but runs every step on the session's model.
- **Budgets can overshoot by one trial**: Claude Code by its last model call, other agents (which have no in-trial cap) by the difference between a trial's prediction and its real cost.
- **Claude Code is installed unpinned** at image build, from Anthropic's installer. The environment fingerprint catches a changed recipe, not a new release behind the same recipe.
- **Judging through Claude Code's own sign-in** can't set temperature 0, so grades can vary a little between runs.
- **Small samples are wide.** A pilot rarely settles anything, and a saving needs about 39 pairs before the guard can hold.
- **Followed isn't measured** for hooks, instructions or code changes: nothing in the logs says whether the agent kept to them.
- **Platforms**: developed on macOS. Linux should work; Windows is untested.

## Running It

Install and first run are in the [README](../README.md#install). In short, from a clone:

```bash
cd rig/engine
uv sync
cd ../web
npm ci
npm run build
cd ../engine
uv run rig doctor
uv run rig serve        # then open http://127.0.0.1:7357
```

A demo with fake models and fake runs, free and safe to click through (it serves the same `web/dist` build, at http://127.0.0.1:7360):

```bash
cd rig/engine
uv run python ../web/e2e/fake_server.py --root "$(mktemp -d)" --port 7360
```

A local model for Claude Code, with llama.cpp:

```bash
llama-server -m Qwen3.5-9B-Q4_0.gguf --alias qwen3.5-9b --host 127.0.0.1 --port 8089 -c 65536 --jinja
uv run rig local add http://127.0.0.1:8089 qwen3.5-9b --kind llamacpp
```

Or in the app: under Local Models, type `http://127.0.0.1:8089`, press "Find Models", add it and Test it, then pick it in "Run on". If the server refuses Claude Code's messages, use "Save a Fixed Template" and restart the server with the `--chat-template-file` it shows.

Tests:

```bash
cd rig
(cd engine && uv run python -m pytest -q)    # no Docker, no model calls
(cd web && npm run typecheck && npm test)
(cd web && npx playwright test)              # against a fake engine, with your installed Chrome
```

More in [CONTRIBUTING.md](../CONTRIBUTING.md).
