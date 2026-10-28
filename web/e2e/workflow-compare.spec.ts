import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// Runs after flow.spec.ts (files run in name order on one server): its fake runs land on the
// bugfix bench and don't disturb the earlier tests' "one result" expectations.

async function noA11yViolations(page: Page) {
  // Settle first: a menu caught mid fade-in fails contrast and target size for no real reason.
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity),
  );
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(
    r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target.join(" ")} (${n.failureSummary})`).join(", ")}`),
  ).toEqual([]);
}

const TAB = { 1: "Describe", 3: "Build", 5: "Ship" } as const;

async function toStep(page: Page, n: 1 | 3 | 5) {
  await page
    .getByRole("navigation", { name: /^(Steps|Workspace)$/ })
    .getByRole("button", { name: new RegExp(`^(${n}\\. |${TAB[n]}$)`) })
    .click();
}

async function openLab(page: Page) {
  await page.goto("/");
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await toStep(page, 3);
}

/** Put a Development starter on the canvas and pin it for Compare. */
async function pinStarter(page: Page, name: string) {
  const list = page.getByRole("region", { name: "Workflows" });
  const group = list.locator(".pal-group").filter({ has: page.locator(".pal-group__title", { hasText: /^Development$/ }) });
  if (!(await group.evaluate((d) => (d as HTMLDetailsElement).open))) await group.locator("summary").click();
  await group.getByRole("button", { name: new RegExp(`^${name}`) }).click();
  await expect(page.locator(".insp__title, .insp__title-input").first()).toBeVisible();
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(page.getByRole("button", { name: "In Compare", exact: true })).toBeDisabled();
}

/** Wait for the run just started to go and then end, so what the columns show is this run's results,
 * never an earlier test's (or an earlier pass's) on the same server. */
async function untilMeasured(page: Page) {
  await expect(page.getByTestId("compare-rank")).toHaveText(/^Ranked once all \d are measured/, { timeout: 20_000 });
  await expect(page.getByRole("button", { name: "Stop", exact: true })).toHaveCount(0, { timeout: 120_000 });
}

test("compare: pin three, see what differs, price and measure them together, a ranking that never overclaims, ship one", async ({ page }) => {
  test.setTimeout(150_000);
  await openLab(page);
  for (const n of ["Fix a bug", "Refactor safely", "Build a feature"]) await pinStarter(page, n);
  // The Lab keeps a short summary, not a table, and opens the full view.
  const summary = page.getByRole("region", { name: "Compared workflows" });
  await expect(summary.locator("li")).toHaveCount(3);
  await page.getByRole("button", { name: "Open the Comparison" }).click();
  await expect(page).toHaveURL(/#\/compare$/);
  await expect(page.getByRole("heading", { name: "Compare Workflows" })).toBeVisible();

  // One column per workflow, each with its diagram, provenance, value in plain units and actions.
  const side = page.getByRole("region", { name: "Workflows side by side" });
  await expect(side.locator("thead th[scope=col]")).toHaveCount(4); // the label column + 3
  await expect(side.getByRole("img", { name: /^Fix a bug: Explore the code, then Write a failing test/ })).toBeVisible();
  await expect(side.getByTestId("compare-provenance")).toHaveCount(3);
  await expect(side.getByRole("rowheader", { name: /Value pts per 1× cost/ })).toBeVisible();
  for (const n of ["Fix a bug", "Refactor safely", "Build a feature"]) {
    await expect(side.getByRole("button", { name: `Open in Build: ${n}` })).toBeVisible();
    await expect(side.getByRole("button", { name: `Remove from Compare: ${n}` })).toBeVisible();
  }

  // Only what differs, aligned by step: a step one has and the others don't, a rule, a loop.
  const diffs = page.getByRole("region", { name: "Differences" }).getByTestId("compare-diff");
  await expect(diffs.filter({ hasText: /^Step: Write a failing test/ })).toHaveCount(1);
  await expect(diffs.filter({ hasText: /^Step: Write a failing test/ }).locator("td")).toHaveText(["Write a failing test", "–", "–"]);
  await expect(diffs.filter({ hasText: /^Rule: / }).first()).toBeVisible();
  await expect(diffs.filter({ hasText: /^Loop: Run the tests back to Implement/ }).locator("td")).toHaveText(["at most 3×", "at most 4×", "at most 3×"]);
  // Steps all three share, the same in each, are never listed.
  await expect(diffs.filter({ hasText: /^Step: Implement/ })).toHaveCount(0);
  await noA11yViolations(page);

  // Priced before sign-in; measuring needs one.
  await page.locator(".agent-pill").click();
  await page.getByRole("radio", { name: /Codex/ }).click();
  await page.getByRole("dialog", { name: "Agent" }).getByRole("button", { name: "Close" }).click();
  await expect(page.getByTestId("compare-price")).toHaveText(
    /^(≈ \$\d+\.\d\d for all 3 \(\d+ pairs each\), split evenly: \$6\.67 each\.|Stops at \$20\.00, split evenly: \$6\.67 each, which pays for about \d+ of \d+ pairs\. All 3 in full would cost ≈ \$\d+\.\d\d \(\d+ pairs each\)\.) (One shared baseline\.|\d baselines: one per session model\.)$/,
  );
  await page.getByRole("button", { name: "Sign In to Measure" }).click();
  await expect(page.getByRole("dialog", { name: "Agent" })).toBeVisible();
  await page.getByRole("radio", { name: /Claude Code/ }).click();
  await page.getByRole("dialog", { name: "Agent" }).getByRole("button", { name: "Close" }).click();

  // An explicit confirm with the total, the even split and the shared baseline.
  await page.getByLabel("Bench").selectOption("bugfix");
  await page.getByLabel("Stop at (USD, in total)").fill("15");
  // $15 split three ways stops a full run within the pilot's pairs: the Full choice says so.
  await expect(page.getByTestId("run-size-full")).toHaveText(/^Full · (the budget only covers \d+ pairs?, as many as the pilot|\d+ pairs · tells apart ±\d+ pts)$/);
  await expect(page.getByTestId("run-size-full")).not.toContainText("conclusive");
  await page.getByRole("button", { name: /^Measure All 3 on / }).click();
  const ask = page.getByRole("group", { name: "Confirm the comparison run" });
  await expect(ask).toContainText("Measure All 3 on");
  await expect(ask.getByTestId("compare-total")).toHaveText(/^≈ \$\d+\.\d\d in total, predicted by the budget check\. \$15\.00 is split evenly: \$5\.00 for each workflow/);
  await expect(ask.locator("li").nth(0)).toContainText("pays for its baseline");
  await expect(ask.locator("li").nth(1)).toContainText(/reuses \d+ baseline pairs?/);
  await noA11yViolations(page);
  await ask.getByRole("button", { name: "Start, up to $15.00" }).click();
  await untilMeasured(page);

  // The columns fill in as each run finishes; then one line ranks them, never past the intervals.
  const results = side.getByTestId("compare-result");
  await expect(results.filter({ hasText: /95% interval/ })).toHaveCount(3, { timeout: 120_000 });
  const rank = page.getByTestId("compare-rank");
  await expect(rank).toHaveText(/(comes out ahead: its interval is clear of every other one's\.|Not proven yet: can't tell .+ and .+ apart yet: .+)/, {
    timeout: 20_000,
  });
  const won = /comes out ahead/.test((await rank.textContent()) ?? "");
  await expect(page.getByRole("button", { name: "Ship the Winner" })).toHaveCount(won ? 1 : 0);
  await expect(side.locator(".cmp-tag--win")).toHaveCount(won ? 1 : 0);
  await noA11yViolations(page);

  // Make one the working workflow: the Lab's canvas has it, and the column says so.
  await side.getByRole("button", { name: "Make This the Working Workflow: Refactor safely" }).click();
  await expect(page.getByText("Refactor safely is the working workflow now")).toBeVisible();
  await expect(side.locator("thead th", { hasText: "Refactor safely" }).getByText("Working Workflow", { exact: true })).toBeVisible();

  // On a phone the columns scroll inside their box, never the page.
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.setViewportSize({ width: 1440, height: 900 });

  // The set survives a reload on its own link.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Compare Workflows" })).toBeVisible();
  await expect(side.locator("thead th[scope=col]")).toHaveCount(4);
  await expect(results.filter({ hasText: /95% interval/ })).toHaveCount(3);

  // Ship the selected one: step 5 with that workflow's brief.
  await side.getByRole("button", { name: "Ship This One: Build a feature" }).click();
  const step = page.locator("main.steppage");
  await expect(step.getByRole("heading", { name: "Ship It to Any Agent" })).toBeVisible();
  await expect(step.getByLabel("BUILD.md")).toContainText("Build a feature");
  await expect(page).not.toHaveURL(/#\/compare/);

  // Remove one from the Lab's summary; the Compare page has two left.
  await toStep(page, 3);
  await page.getByRole("button", { name: "Stop comparing Fix a bug" }).click();
  await expect(summary.locator("li")).toHaveCount(2);
  await page.getByRole("button", { name: "Open the Comparison" }).click();
  await expect(side.locator("thead th[scope=col]")).toHaveCount(3);
});

test("compare on two models: the extra baseline priced, one click onto one model, ranked by the pass rate with it", async ({ page }) => {
  test.setTimeout(150_000);
  await openLab(page);
  for (const n of ["Fix a bug", "Refactor safely", "Build a feature"]) await pinStarter(page, n);
  await page.getByRole("button", { name: "Open the Comparison" }).click();
  // Build a feature's main steps on Haiku: its runs are recorded under another session model.
  await page.evaluate(() => {
    const set = JSON.parse(localStorage.getItem("pg.lab.compare") ?? "[]");
    for (const p of set) {
      if (p.wf.name === "Build a feature") for (const s of p.wf.steps) if (s.kind === "do") s.model = "claude-haiku-5-5";
    }
    localStorage.setItem("pg.lab.compare", JSON.stringify(set));
  });
  await page.reload();
  // A bench the other tests leave alone: Build a feature is only ever measured on Haiku here.
  await page.getByLabel("Bench").selectOption("refactor");
  await page.getByLabel("Stop at (USD, in total)").fill("30");

  // Said plainly before a run: two models, two baselines, what the second costs, and the way out.
  const notice = page.getByTestId("compare-models");
  await expect(notice).toContainText(/^2 models, so 2 baselines: \+\$\d+\.\d\d\. A baseline on one model says nothing about another/);
  // Its with arm moves to Sonnet too, so all on Sonnet can cost more than the baseline it saves: said either way.
  await expect(notice).toContainText(
    /Run All on Sonnet 5\.5: one shared baseline, ≈ \$\d+\.\d\d in total, (saving \$\d+\.\d\d|\$\d+\.\d\d more since Sonnet 5\.5 costs more per trial|about the same)\./,
  );
  await expect(page.getByTestId("compare-price")).toContainText("2 baselines: one per session model.");
  await noA11yViolations(page);

  // Measured as they are: ranked by what each ends at with its workflow, each lift against its own model.
  await page.getByRole("button", { name: /^Measure All 3 on / }).click();
  const ask = page.getByRole("group", { name: "Confirm the comparison run" });
  await expect(ask.locator("li").nth(2)).toContainText("pays for its baseline");
  await ask.getByRole("button", { name: "Start, up to $30.00" }).click();
  await untilMeasured(page);
  const side = page.getByRole("region", { name: "Workflows side by side" });
  const results = side.getByTestId("compare-result");
  await expect(results.filter({ hasText: /95% interval/ })).toHaveCount(3, { timeout: 120_000 });
  const rank = page.getByTestId("compare-rank");
  await expect(rank).toContainText("They ran on 2 models, so each lift is against its own model's baseline; ranked by pass rate with the workflow, then cost:", {
    timeout: 20_000,
  });
  await expect(rank).toHaveText(/(its pass rate's interval is clear of every other one's\.|Not proven yet: can't tell .+ and .+ apart yet: .+)/);
  await expect(results.nth(2)).toContainText(/\d+% pass with it · 95% interval \d+% to \d+%/);
  await expect(results.nth(2)).toContainText(/[+-]?\d+ pts vs Direct on Haiku 5\.5 · 95% interval/);
  await expect(results.nth(0)).toContainText(/[+-]?\d+ pts vs Direct on Sonnet 5\.5 · 95% interval/);
  await noA11yViolations(page);

  // One click puts them all on Sonnet: one baseline, priced again, and it can be undone.
  await notice.getByRole("button", { name: "Run All on Sonnet 5.5" }).click();
  await expect(page.getByRole("status").filter({ hasText: "All 3 run on Sonnet 5.5 now" })).toBeVisible();
  await expect(notice).toHaveCount(0);
  await expect(page.getByTestId("compare-price")).toContainText("One shared baseline.");
  // Its Haiku result is not its result on Sonnet: marked, left out of the ranking, and no longer read
  // as current; the other two, on Sonnet all along, are ranked by Rig score as on one model.
  await expect(results.nth(2).getByTestId("compare-other-model")).toHaveText("On Haiku 5.5, not this one: not ranked. Measure it again to rank it.");
  await expect(results.nth(2)).toContainText(/On Haiku 5\.5: [+-]?\d+ pts vs Direct there/);
  await expect(results.nth(2)).not.toContainText("pass with it");
  await expect(rank).not.toContainText("Build a feature");
  await expect(rank).not.toContainText("They ran on 2 models");
  await expect(results.nth(0)).not.toContainText("vs Direct on");
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(notice).toBeVisible();
  await notice.getByRole("button", { name: "Run All on Sonnet 5.5" }).click();
  await expect(page.getByTestId("compare-price")).toContainText("One shared baseline.");
  // The confirm agrees: the first pays for the one baseline, the other two reuse it.
  await page.getByRole("button", { name: /^Measure All 3 on / }).click();
  await expect(ask.locator("li").nth(0)).toContainText("pays for its baseline");
  await expect(ask.locator("li").nth(1)).toContainText(/reuses \d+ baseline pairs?/);
  await expect(ask.locator("li").nth(2)).toContainText(/reuses \d+ baseline pairs?/);
  // The choice survives a reload: it is the pinned set itself.
  await page.reload();
  await page.getByLabel("Bench").selectOption("refactor");
  await expect(page.getByTestId("compare-price")).toContainText("One shared baseline.");
  await expect(results.nth(2).getByTestId("compare-other-model")).toHaveText("On Haiku 5.5, not this one: not ranked. Measure it again to rank it.");
});
