import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// Measure's choice of change (a skill, CLAUDE.md, a hook or an MCP server) and of metric, and a
// run scored on tokens in Results. Runs last (files go in name order): the seeded repo is attached
// by flow.spec.ts, and the runs and the edited CLAUDE.md made here are seen by no other file.

declare const process: { env: Record<string, string | undefined> };
// Set to a folder to save the screenshots of the choice and the headline there (1440 × 900).
const SHOTS = process.env.PG_E2E_SHOTS;

const TAB = { 1: "Describe", 2: "Design", 3: "Build", 4: "Measure", 5: "Ship" } as const;

async function toStep(page: Page, n: 1 | 2 | 3 | 4 | 5) {
  await page
    .getByRole("navigation", { name: /^(Steps|Workspace)$/ })
    .getByRole("button", { name: new RegExp(`^(${n}\\. |${TAB[n]}$)`) })
    .click();
}

async function openMeasure(page: Page) {
  // Run on its own, the seeded repo isn't attached yet (flow.spec.ts attaches it): attach it.
  // Through the API, not a page: every page load starts the app's heavy reads (results, runs),
  // and the engine works through them after the page is gone, so the next load can wait seconds.
  const repos = (await (await page.request.get("/api/repos")).json()) as unknown[];
  if (!repos.length) {
    const origin = `http://127.0.0.1:${process.env.PG_E2E_PORT ?? 7361}`; // a write needs the app's Origin
    const r = await page.request.post("/api/repos", { headers: { origin }, data: { path: `${process.env.HOME}/.cache/${process.env.PG_E2E_TAG ?? "pg-e2e"}` } });
    expect(r.ok()).toBe(true);
  }
  await page.goto("/");
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await toStep(page, 4);
  await expect(page.getByLabel("Change to measure")).toBeVisible();
}

async function noA11yViolations(page: Page) {
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity),
  );
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target.join(" ")} (${n.failureSummary})`).join(", ")}`)).toEqual([]);
}

/** The option of the change picker whose label starts with `name`. */
async function pick(page: Page, name: string) {
  const select = page.getByLabel("Change to measure");
  const label = await select.locator("option").filter({ hasText: new RegExp(`^${name}`) }).first().textContent();
  await select.selectOption({ label: label ?? name });
}

test.describe.configure({ mode: "serial" });

test("measure: a hook is the change, scored on tokens per solved task, and the run keeps both", async ({ page }) => {
  await openMeasure(page);
  const select = page.getByLabel("Change to measure");
  await expect(select.locator("optgroup")).toHaveCount(4);
  await expect(select.locator("optgroup").nth(0)).toHaveAttribute("label", "Skills");
  await pick(page, "format-on-edit");
  await expect(page.getByTestId("change-compare")).toHaveText(
    "With: its hooks are merged into .claude/settings.json (the repo's own hooks run first). Without: the repo's settings as they are.",
  );
  // A hook is never "opened": the nudge is for skills only.
  await expect(page.getByRole("checkbox", { name: /Tell the agent to open the / })).toHaveCount(0);
  // The metric: the pass rate until one is picked; the engine's words for each.
  const picker = page.getByTestId("metric-picker");
  await expect(picker.getByRole("radio", { name: "Pass Rate" })).toHaveAttribute("aria-checked", "true");
  await picker.getByRole("radio", { name: "Tokens per Solved Task" }).click();
  await expect(picker.getByRole("radio", { name: "Tokens per Solved Task" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("metric-describe")).toHaveText(
    "Tokens per Solved Task. Does it use fewer tokens for each task it solves, without solving fewer? Tokens are in + out as the agent reports them, cached input included. The pass rate is the guard: until its 95% interval shows it is at most 10 pts worse, no saving is credited.",
  );
  // The sizing is the guard's now. "Keep going until it's decided" is on, as in the Lab: the
  // pilot grows toward the guard, and the estimate says how far (at least 10 pairs a look, to 100 at most).
  await expect(page.getByTestId("metric-plan")).toContainText(/^Scored on tokens, the pass-rate guard needs about 39 pairs/);
  const keepGoing = page.getByRole("checkbox", { name: /Keep going until it's decided/ });
  await expect(keepGoing).toBeChecked();
  await expect(page.getByTestId("keep-going")).toContainText("adds pairs until the saving and the pass-rate guard are both decided");
  await expect(page.getByTestId("metric-plan-planned")).toHaveText(/^This run plans 3 pairs; with "Keep going until it's decided" on, it adds pairs until the saving and the guard are decided, up to 100 pairs or the budget\./);
  // At $5.00 the budget stops it first (what these runs cost so far decides where); with room, the caps.
  await expect(page.getByTestId("run-extends")).toHaveText(/^With "Keep going until it's decided" on, it (may grow while it's undecided, to about \d+ pairs before \$5\.00 stops it \(\d+ pairs at most\)|can't add pairs here: \$5\.00 stops it within the planned \d+ pairs)\.$/);
  await page.getByLabel("Stop at (USD)").fill("500");
  await expect(page.getByTestId("run-extends")).toHaveText(/^With "Keep going until it's decided" on, it may grow to (9\d|100) pairs \(≈ \$[\d.]+\) while it's undecided, and still stops at \$500\.00\.$/);
  await page.getByLabel("Stop at (USD)").fill("5");
  // Off, the pilot is all it runs, and it is told it can't be credited a saving.
  await keepGoing.uncheck();
  await expect(page.getByTestId("run-extends")).toHaveCount(0);
  await expect(page.getByTestId("metric-plan-planned")).toHaveText(/^This run plans 3 pairs: .+so no saving can be credited\. Run Full with the budget for them/);
  await expect(page.getByTestId("run-detect")).toHaveCount(0);
  await expect(page.getByTestId("run-sizing")).toHaveCount(0);
  await noA11yViolations(page);
  if (SHOTS) {
    await picker.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${SHOTS}/measure-choice.png` });
  }
  await page.getByRole("button", { name: "Review the Run" }).click();
  await expect(page.getByTestId("confirm-metric")).toHaveText("Scored on tokens per solved task, with the pass rate as the guard.");
  await expect(page.getByTestId("confirm-metric-short")).toContainText("no saving can be credited");
  await expect(page.getByTestId("confirm-extends")).toHaveCount(0);
  await page.getByRole("button", { name: /^Start, up to/ }).click();
  await expect(page.getByRole("region", { name: "Rig Score" }).locator(".rig__value")).toHaveText(/^\d{1,3}$|^—$/, { timeout: 30_000 });
  // Results leads with the metric; the run stored its choice and ran the hook in "with" only.
  await expect(page.getByTestId("metric-line")).toHaveText(/^Tokens per Solved Task: /);
  const rows = (await (await page.request.get("/api/experiments")).json()) as { id: number; metric: string; treatment_kind: string; treatment_name: string }[];
  const mine = rows.find((r) => r.treatment_name === "format-on-edit")!;
  expect(mine.metric).toBe("tokens");
  expect(mine.treatment_kind).toBe("hook");
  // Followed: a hook has nothing to follow, so it's not measured, and says why.
  const got = (await (await page.request.get(`/api/experiments/${mine.id}`)).json()) as { rig: { parts: { id: string; score: number | null; detail: string }[] } };
  const fol = got.rig.parts.find((p) => p.id === "followed")!;
  expect(fol.score).toBeNull();
  expect(fol.detail).toBe("a hook runs by itself, so there is nothing for the agent to follow or skip");
});

test("measure: the committed CLAUDE.md would measure nothing; an edited copy measures the edit", async ({ page }) => {
  await openMeasure(page);
  await pick(page, "CLAUDE.md");
  const compare = page.getByTestId("change-compare");
  await expect(compare).toHaveText(
    "This is the CLAUDE.md both arms already have, so a run would measure nothing. Edit a copy below (or edit the file without committing) to measure the edit.",
  );
  await expect(page.getByRole("button", { name: "Review the Run" })).toBeDisabled();
  const draft = page.getByTestId("instructions-draft");
  await expect(draft).toHaveAttribute("open", "");
  const box = page.getByLabel("Edited CLAUDE.md");
  await expect(box).toHaveValue("Run `pytest -q` before you finish.\n");
  await box.fill("Run `pytest -q` before you finish. Answer in as few words as you can.");
  await page.getByRole("button", { name: "Save the copy and measure it" }).click();
  // The copy is picked, and it replaces the committed file in the "with" arm only.
  await expect(page.getByLabel("Change to measure").locator("option:checked")).toHaveText("claude-md-edit · your edited copy");
  await expect(compare).toHaveText("With: this file in place of the repo's CLAUDE.md. Without: the committed CLAUDE.md. The run measures the difference.");
  await expect(page.getByRole("button", { name: "Review the Run" })).toBeEnabled();
  await noA11yViolations(page);
});

test("results: a run scored on tokens leads with the saving and the pass rate as its guard", async ({ page }) => {
  await openMeasure(page);
  const { id } = await page.evaluate(async () => (await fetch("/api/_test/token-run", { method: "POST" })).json());
  await page.reload();
  await expect(page.getByLabel("Change to measure")).toBeVisible();
  await page.getByRole("button", { name: new RegExp(`^#${id} `) }).click();
  const head = page.getByTestId("metric-headline");
  await expect(page.getByTestId("metric-line")).toHaveText("Tokens per Solved Task: with 18.0k vs without 54.0k (-67%, 95% interval -70% to -63%)");
  await expect(page.getByTestId("metric-guard")).toHaveText(
    "Pass rate: 34 of 42 passed with vs 34 of 42 passed without (+0 pts; at worst -9 pts, within the 10-pt margin)",
  );
  const rig = page.getByRole("region", { name: "Rig Score" });
  await expect(rig.locator(".rig__value")).toHaveText("100");
  await expect(rig.getByTestId("rig-verdict")).toHaveText("Helps");
  // The reason leads with the saving; the facts are the usual four.
  await expect(rig.getByTestId("rig-why")).toHaveText(/^Tokens per Solved Task: with 18\.0k vs without 54\.0k .+, and the pass rate holds /);
  await expect(rig.getByTestId("rig-facts").locator("li")).toHaveText([/^Quality: /, /^Cost: /, /^Time: /, /^Reliability: /]);
  // Cost is what Lift measures here: shown as in Lift, not counted twice.
  await expect(rig.locator(".rig__part").nth(1)).toContainText("in Lift");
  await expect(rig.getByTestId("rig-formula")).toContainText("60% × 100 (Lift takes Cost's 20%: the measure is tokens)");
  await expect(page.locator(".reveal-bar")).toContainText("Pass rate: ");
  await noA11yViolations(page);
  if (SHOTS) {
    await rig.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${SHOTS}/results-headline.png` });
    await head.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${SHOTS}/results-headline-guard.png` });
  }
});

test("Lab: a workflow is scored on tokens as a repo's change is, and its result and run page lead with the saving", async ({ page }) => {
  await page.goto("/");
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await toStep(page, 4);
  await page.getByLabel("Bench").selectOption("qa");
  const picker = page.getByTestId("metric-picker");
  await expect(picker.getByRole("radio", { name: "Pass Rate" })).toHaveAttribute("aria-checked", "true");
  await picker.getByRole("radio", { name: "Tokens per Solved Task" }).click();
  // The guard's pairs are said once, by the estimate beside the budget, not by the choice too.
  await expect(page.getByTestId("metric-describe")).toContainText("The pass rate is the guard");
  await expect(page.getByTestId("metric-describe")).not.toContainText("pairs");
  await expect(page.getByTestId("metric-plan")).toContainText(/^Scored on tokens, the pass-rate guard needs about 39 pairs/);
  // Without "Keep going", the planned pilot is all it runs: too few for the guard.
  await page.getByRole("checkbox", { name: /Keep going until it's decided/ }).uncheck();
  await expect(page.getByTestId("metric-plan-planned")).toHaveText(/^This run plans 2 pairs: .+so no saving can be credited\. Run Full with the budget for them/);
  await expect(page.getByTestId("run-sizing")).toHaveCount(0);
  await noA11yViolations(page);
  await page.getByRole("button", { name: /Rig & Measure/ }).click();
  await expect(page.getByTestId("confirm-metric")).toHaveText("Scored on tokens per solved task, with the pass rate as the guard.");
  await expect(page.getByTestId("confirm-metric-short")).toContainText("no saving can be credited");
  await page.getByRole("button", { name: /^Start, up to/ }).click();
  const results = page.getByRole("region", { name: "Measured workflows" });
  await expect(results.getByTestId("metric-line").first()).toHaveText(/^Tokens per Solved Task: /, { timeout: 30_000 });
  await expect(results.getByTestId("metric-guard").first()).toHaveText(/^Pass rate: /);
  const rows = (await (await page.request.get("/api/lab/results")).json()) as { bench: string; id: number; metric: string; rig: { metric?: { id: string } } }[];
  const mine = rows.filter((r) => r.bench === "qa" && r.metric === "tokens").pop()!;
  expect(mine.rig.metric?.id).toBe("tokens");
  // The run's own page (from Runs) reads the same as a repo run scored on tokens.
  await page.goto(`/#/runs/bench/qa/${mine.id}`);
  await expect(page.getByTestId("metric-line")).toHaveText(/^Tokens per Solved Task: /);
  await expect(page.locator(".reveal-bar")).toContainText("Pass rate: ");
  await noA11yViolations(page);
});

test("Lab: a suite is scored on tokens too, and its pooled result leads with the saving and the pooled guard", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/");
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await toStep(page, 4);
  const bench = page.getByLabel("Bench");
  const option = bench.locator("option", { hasText: /^All \d+ Matching Benches \(\d+ tasks\)$/ });
  await bench.selectOption({ label: (await option.textContent()) ?? "" });
  // The metric choice is offered for a suite as for one bench, and the guard is sized on every bench's pairs.
  const picker = page.getByTestId("metric-picker");
  await picker.getByRole("radio", { name: "Tokens per Solved Task" }).click();
  await expect(page.getByTestId("metric-plan")).toContainText(/^Scored on tokens, the pass-rate guard needs about 39 pairs/);
  await expect(page.getByTestId("metric-plan-planned")).toHaveText(/^This run plans \d+ pairs: /);
  await page.getByLabel(/Stop at \(USD, in total\)/).fill("50");
  await noA11yViolations(page);
  await page.getByRole("button", { name: /Rig & Measure/ }).click();
  await expect(page.getByText(/Run \d+ Trials on .* across \d+ Benches\?/)).toBeVisible();
  await expect(page.getByTestId("confirm-metric")).toHaveText("Scored on tokens per solved task, with the pass rate as the guard.");
  await page.getByRole("button", { name: /^Start, up to/ }).click();
  const run = page.getByRole("region", { name: "Suite run" });
  await expect(run.getByRole("button", { name: "Close" })).toBeVisible({ timeout: 150_000 });
  const pool = run.getByLabel(/^Across \d+ Benches$/);
  // Per solved task over every bench's pairs: the fake spends 44k tokens a trial either way, but solves more with the workflow.
  await expect(pool.getByTestId("metric-line")).toHaveText(/^Tokens per Solved Task: with [\d.]+k vs without [\d.]+k \([+-]\d+%, 95% interval [+-]\d+% to ([+-]\d+%|no upper end)\)$/);
  await expect(pool.getByTestId("metric-guard")).toHaveText(/^Pass rate: \d+ of \d+ passed with vs \d+ of \d+ passed without /);
  await expect(pool.locator(".result__diff")).toHaveText(/^Pass rate [+-]?\d+ pts$/);
  await expect(pool.getByText(/^[+-]\d+% tokens · [+-]?\d+ pts · \d+ pairs$/).first()).toBeVisible();
  await expect(pool.getByTestId("suite-pooling")).toContainText("resamples each bench's pairs within that bench");
  const rig = pool.getByRole("region", { name: /^Rig Score across \d+ Benches$/ });
  await expect(rig.getByTestId("rig-why")).toHaveText(/^Tokens per Solved Task: /);
  const job = (await (await page.request.get("/api/lab/results")).json()) as { metric: string }[];
  expect(job.filter((r) => r.metric === "tokens").length).toBeGreaterThan(1);
  await noA11yViolations(page);
});

test("Lab: keep going on tokens waits for the saving and its guard, and says what it waits for", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/");
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await toStep(page, 4);
  await page.getByLabel("Bench").selectOption("qa");
  const keep = page.getByRole("checkbox", { name: /Keep going until it's decided/ });
  await expect(keep).toBeChecked();
  await expect(page.getByTestId("keep-going")).toHaveText("· adds pairs while the result is unclear, up to the budget. Stops early only when a stricter (99%) interval rules out zero.");
  await page.getByTestId("metric-picker").getByRole("radio", { name: "Tokens per Solved Task" }).click();
  await expect(page.getByTestId("keep-going")).toHaveText(
    /^· adds pairs until the saving and the pass-rate guard are both decided, up to the budget or 100 pairs\. At a stricter \(99%\) interval, .+ or tokens per solved task higher\.$/,
  );
  // Short of the guard, but it grows toward it: said plainly, not as a warning.
  const planned = page.getByTestId("metric-plan-planned");
  await expect(planned).toHaveText(/^This run plans 2 pairs; with "Keep going until it's decided" on, it adds pairs until the saving and the guard are decided, up to 100 pairs or the budget\./);
  await expect(planned).not.toHaveClass(/notice--warning/);
  await keep.uncheck();
  await expect(planned).toHaveText(/so no saving can be credited/);
  await expect(planned).toHaveClass(/notice--warning/);
  await keep.check();
  await page.getByLabel("Stop at (USD)").fill("5");
  await noA11yViolations(page);
  await page.getByRole("button", { name: /Rig & Measure/ }).click();
  await expect(page.getByTestId("confirm-metric-extends")).toContainText("it adds pairs until the saving and the guard are decided");
  const earlier = (await (await page.request.get("/api/lab/results")).json()) as { id: number; bench: string }[];
  const before = Math.max(0, ...earlier.filter((r) => r.bench === "qa").map((r) => r.id));
  await page.getByRole("button", { name: /^Start, up to/ }).click();
  // The fake's outcomes are random, so the first look may extend (saying what it waits on) or already be
  // decided (the same tokens both ways and every pair passing is a cut too small to matter); the
  // "Not decided yet … waiting on …" line itself is pinned by LiveRun.test.tsx. The run's own events say
  // what it did, in the saving's terms.
  type Row = { bench: string; id: number; metric: string; n_pairs: number; status: string };
  let mine: Row | undefined;
  await expect
    .poll(
      async () => {
        const rows = (await (await page.request.get("/api/lab/results")).json()) as Row[];
        mine = rows.filter((r) => r.bench === "qa" && r.metric === "tokens" && r.id > before).pop();
        return mine && !["running", "pending"].includes(mine.status) ? mine.status : "running";
      },
      { timeout: 90_000 },
    )
    .not.toBe("running");
  expect(mine!.n_pairs).toBeGreaterThanOrEqual(2);
  const events = (await (await page.request.get(`/api/lab/runs/qa/${mine!.id}/events`)).text())
    .split("\n")
    .filter((l) => l.startsWith("data: "))
    .map((l) => JSON.parse(l.slice(6)) as { type: string; reason?: string; waiting?: string });
  const grew = events.filter((e) => e.type === "extended");
  expect(grew.map((e) => e.waiting)).toEqual(grew.map(() => expect.stringMatching(/^(the saving and the pass-rate guard|the saving|the pass-rate guard)$/)));
  await noA11yViolations(page);
  expect(events.find((e) => e.type === "settled")?.reason).toMatch(
    /^(the cut in tokens per solved task and the pass-rate guard are both decided at the stricter interval|.+, with (the saving and the pass-rate guard|the saving|the pass-rate guard) still undecided|.+ at the stricter interval)$/,
  );
});

test("measure: keep going until it's decided, as in the Lab: on by default, priced to what it may grow to, and run", async ({ page }) => {
  test.setTimeout(120_000);
  await openMeasure(page);
  await pick(page, "refund-policy");
  const keep = page.getByRole("checkbox", { name: /Keep going until it's decided/ });
  await expect(keep).toBeChecked();
  // The Lab's words, from the engine.
  await expect(page.getByTestId("keep-going")).toHaveText("· adds pairs while the result is unclear, up to the budget. Stops early only when a stricter (99%) interval rules out zero.");
  // On the pass rate a look adds a pair per task, 5 looks: 6 pairs per task at most; the budget still stops it.
  const tasks = Number((await page.getByText(/^\d+ runnable tasks? · /).textContent())!.split(" ")[0]);
  const most = 6 * tasks;
  await page.getByLabel("Stop at (USD)").fill("500");
  const grows = new RegExp(`^With "Keep going until it's decided" on, it may grow to ${most} pairs \\(≈ \\$[\\d.]+\\) while it's undecided, and still stops at \\$500\\.00\\.$`);
  await expect(page.getByTestId("run-extends")).toHaveText(grows);
  await keep.uncheck();
  await expect(page.getByTestId("run-extends")).toHaveCount(0);
  await keep.check();
  await expect(page.getByTestId("run-extends")).toHaveText(grows);
  await noA11yViolations(page);
  await page.getByRole("button", { name: "Review the Run" }).click();
  // The confirm says the same, beside the planned trials.
  await expect(page.getByText(new RegExp(`^${2 * tasks} trials: ${tasks} tasks? × 1 repeat × with and without, on `))).toBeVisible();
  await expect(page.getByTestId("confirm-extends")).toHaveText(grows);
  await noA11yViolations(page);
  const earlier = (await (await page.request.get("/api/experiments")).json()) as { id: number }[];
  const before = Math.max(0, ...earlier.map((r) => r.id));
  await page.getByRole("button", { name: /^Start, up to/ }).click();
  await expect(page.getByRole("region", { name: "Rig Score" }).locator(".rig__value")).toHaveText(/^\d{1,3}$|^—$/, { timeout: 90_000 });
  // The run kept going by the Lab's rule: decided at 99%, or at a cap (the looks or the budget).
  const rows = (await (await page.request.get("/api/experiments")).json()) as { id: number; treatment_name: string }[];
  const mine = rows.find((r) => r.id > before && r.treatment_name === "refund-policy")!;
  const events = (await (await page.request.get(`/api/experiments/${mine.id}/events`)).text())
    .split("\n")
    .filter((l) => l.startsWith("data: "))
    .map((l) => JSON.parse(l.slice(6)) as { type: string; reason?: string; pairs?: number });
  const settled = events.find((e) => e.type === "settled");
  expect(settled?.reason).toMatch(/^(decided at the stricter interval \((helps|hurts)\)|5 extra looks|the budget can't pay for another pair)$/);
  expect(settled!.pairs).toBeLessThanOrEqual(most);
});
