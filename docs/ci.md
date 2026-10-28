# Gating a pull request on measured results

`rig gate` runs one skill or workflow on a bench, with and without it, and exits with a code a CI job can act on.

```
uv run rig gate --treatment skills/tdd --bench bugfix --budget 2.00 --format github-md --out gate.md
```

| Option | Default | Meaning |
|---|---|---|
| `--treatment PATH` | required | Folder with a `SKILL.md` (a skill, or a compiled workflow). |
| `--bench ID` | required | Bench to measure it on (`bugfix`, `qa`, ...). |
| `--min-delta` | 0 | Least difference in percentage points. A verdict of "helps" passes regardless. |
| `--min-adherence` | 0.85 | Share of runs that must follow a workflow's steps. Checked only for a workflow folder whose session logs can be read; otherwise it warns and does not fail. |
| `--budget` | 2.00 | Stop when this many USD are spent. |
| `--agent` | claude-code | Agent that runs the tasks. |
| `--size` | pilot | `pilot` is one case per scenario; `full` is at least 20 per arm. |
| `--metric` | pass_rate | What the gate decides on: `pass_rate`, or a saving (`tokens`, `cost`, `time` per solved task) with the pass rate as its guard. See below. |
| `--local-model ID` | none | Run Claude Code on a local model added with `rig local add` (free, no API key). Cost can't be the metric there. |
| `--format` | text | `text`, `github-md` (a PR comment) or `junit` (one testcase per scenario). |
| `--out FILE` | stdout | Write the report to a file. Progress lines go to stderr either way. |

## Exit codes

- **0**: it helps, or the difference is at least `--min-delta`, and adherence is at or above `--min-adherence`.
- **1**: it hurts, or falls below a threshold.
- **2**: undecided. The budget ran out before the result was decided, or the sandbox, sign-in or bench broke.

With `--metric tokens`, `cost` or `time`, the verdict on that saving decides instead, the same one `rig run --metric` prints: **0** when it helps (the saving is clear and the pass rate's lower bound stays within the 10-point margin), **1** when it doesn't help, **2** when it can't tell yet. `--min-delta` is about the pass rate and is not used then; adherence is still checked. The guard needs more pairs than a pilot has (about 40 on a five-task bench), so a pilot usually exits 2: `--size full` plans them on a saving (as the app's full run does), with a budget that reaches it. The report leads with the metric, its verdict, the saving and the guard. An unknown metric, or cost on a local model, exits 2 before anything runs.

A judged bench (documents graded by a model) is not supported by `rig gate` yet and exits 2.

## Sign-in

Credentials come from the environment, never from a file: `ANTHROPIC_API_KEY`, or `CLAUDE_CODE_OAUTH_TOKEN` for a Claude subscription. Store it as a repository secret. The runner needs Docker, which GitHub's `ubuntu-latest` has.

## GitHub Actions

```yaml
name: rig-gate
on:
  pull_request:
    paths: ["skills/**"]

permissions:
  contents: read
  pull-requests: write

jobs:
  gate:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Gate the skill
        id: gate
        working-directory: engine
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          uv sync
          set +e
          uv run rig gate --treatment ../skills/tdd --bench bugfix --budget 2.00 \
            --format github-md --out "$RUNNER_TEMP/gate.md"
          code=$?
          cat "$RUNNER_TEMP/gate.md" >> "$GITHUB_STEP_SUMMARY" || true
          exit "$code"
      - name: Comment on the pull request
        if: always() && steps.gate.outcome != 'skipped'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require("fs");
            if (!fs.existsSync(`${process.env.RUNNER_TEMP}/gate.md`)) return;
            const body = fs.readFileSync(`${process.env.RUNNER_TEMP}/gate.md`, "utf8");
            await github.rest.issues.createComment({
              ...context.repo,
              issue_number: context.issue.number,
              body,
            });
```

To see one test per scenario in your CI's test tab, add `--format junit --out gate.xml` and upload it with your usual JUnit reporter. A job that exits 2 is red on purpose: "could not decide" should not read as a pass. To treat it as a warning, set `continue-on-error: true` on the gate step.

Use a small `--budget` on pull requests and `--size full` on a schedule. Each run spends real money; the budget is a hard stop after the trial in progress.
