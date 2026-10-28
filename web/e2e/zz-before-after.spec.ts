import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// A code change measured before and after: the seeded repo's split-refunds branch (fake_server.py)
// against the commit before, as the two arms of one run. The fake executor passes the "with"
// arm's task folder (tasks-with/, here the after commit) more often, so the run has a result.

declare const process: { env: Record<string, string | undefined> };
// Set to a folder to save screenshots of the choice and the result there (1440 × 900).
const SHOTS = process.env.PG_E2E_SHOTS;

const TAB = { 1: "Describe", 2: "Design", 3: "Build", 4: "Measure", 5: "Ship" } as const;

async function toStep(page: Page, n: 1 | 2 | 3 | 4 | 5) {
  await page
    .getByRole("navigation", { name: /^(Steps|Workspace)$/ })
    .getByRole("button", { name: new RegExp(`^(${n}\\. |${TAB[n]}$)`) })
    .click();
}

async function openMeasure(page: Page) {
  await page.goto("/");
  // Run on its own, the seeded repo isn't attached yet (flow.spec.ts attaches it): attach it.
  await page.evaluate(async (root) => {
    const repos = await (await fetch("/api/repos")).json();
    if (!repos.length) await fetch("/api/repos", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ path: root }) });
  }, `${process.env.HOME}/.cache/${process.env.PG_E2E_TAG ?? "pg-e2e"}`);
  await page.goto("/");
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await toStep(page, 4);
  await expect(page.getByTestId("measure-mode")).toBeVisible();
}

async function noA11yViolations(page: Page) {
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity),
  );
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target.join(" ")} (${n.failureSummary})`).join(", ")}`)).toEqual([]);
}

test("measure: a split on a branch runs against the commit before, and Results says before vs after", async ({ page }) => {
  await openMeasure(page);
  const before = (await (await page.request.get("/api/before-after/refs")).json()) as { head: { sha: string; branch: string | null } };
  await page.getByRole("radio", { name: "A Code Change: Before and After" }).click();
  await expect(page.getByTestId("ba-lead")).toHaveText(
    "Make the change on a branch (or leave it uncommitted), then measure it against the commit before. Rig doesn't write the change; you or your agent do.",
  );
  const after = page.getByLabel("After: the change");
  await after.selectOption("split-refunds");
  const compare = page.getByTestId("ba-compare");
  await expect(compare).toContainText(/^Before: the code at HEAD \(\w{7}\)\. After: the code at split-refunds \(\w{7}\)\./);
  await expect(page.getByTestId("ba-files")).toHaveText("2 files differ");
  await page.getByTestId("ba-files").click();
  await expect(compare.locator("li")).toHaveText(["limits.py", "refunds.py"]);
  // The commit before as the after side too: the same code, so nothing to run.
  await after.selectOption("HEAD");
  await expect(compare).toHaveClass(/notice--warning/);
  await expect(compare).toContainText("has the same code as HEAD");
  await expect(page.getByRole("button", { name: "Review the Run" })).toBeDisabled();
  await after.selectOption("split-refunds");
  await expect(page.getByTestId("ba-files")).toHaveText("2 files differ");
  // The metric choice and its guard are the same as for any run.
  await expect(page.getByTestId("metric-picker").getByRole("radio", { name: "Pass Rate" })).toHaveAttribute("aria-checked", "true");
  await noA11yViolations(page);
  if (SHOTS) {
    await page.getByTestId("before-after").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${SHOTS}/before-after-choice.png` });
  }
  await page.getByRole("button", { name: "Review the Run" }).click();
  await expect(page.getByText(/^Run HEAD \(\w{7}\) → split-refunds \(\w{7}\)\?$/)).toBeVisible();
  await expect(page.getByText(/× before and after, on /)).toBeVisible();
  await page.getByRole("button", { name: /^Start, up to/ }).click();
  const rig = page.getByRole("region", { name: "Rig Score" });
  await expect(rig.locator(".rig__value")).toHaveText(/^\d{1,3}$|^—$/, { timeout: 30_000 });
  await expect(rig.getByTestId("rig-context")).toHaveText("· before vs after");
  await expect(page.getByTestId("arms-key")).toHaveText(
    /^Before vs after: "after" is the code at split-refunds \(\w{7}\), "before" the code at HEAD \(\w{7}\)\.$/,
  );
  // The score's own lines name the arms after and before, never with and without.
  await expect(rig.getByTestId("rig-facts")).toContainText(/^Quality: \d+ of \d+ passed after, \d+ of \d+ passed before/);
  await expect(rig.getByTestId("rig-facts")).toContainText("Reliability: after, ");
  await expect(rig.getByTestId("rig-ledger")).toContainText(/ after, \d+ before\)/);
  await expect(rig).not.toContainText(/\bwith(out)?\b|plain agent|agent alone/i);
  await expect(page.locator(".stats")).toContainText("After");
  await expect(page.locator(".stats")).toContainText("Before");
  if (SHOTS) {
    await rig.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${SHOTS}/before-after-result.png` });
  }
  // The run is stored as a before/after run, with both commits.
  type Row = { id: number; treatment_kind: string; before_after: { base: { sha: string }; after: { label: string; working_tree: boolean } } | null };
  const rows = (await (await page.request.get("/api/experiments")).json()) as Row[];
  const mine = rows.find((r) => r.treatment_kind === "before_after")!;
  expect(mine.before_after!.base.sha).toBe(before.head.sha);
  expect(mine.before_after!.after.label).toMatch(/^split-refunds \(/);
  expect(mine.before_after!.after.working_tree).toBe(false);
  const got = (await (await page.request.get(`/api/experiments/${mine.id}`)).json()) as { rig: { parts: { id: string; score: number | null; detail: string }[] } };
  expect(got.rig.parts.find((p) => p.id === "followed")!.score).toBeNull();
  // The checkout was never switched: still the commit and branch it was on.
  const now = (await (await page.request.get("/api/before-after/refs")).json()) as { head: { sha: string; branch: string | null } };
  expect(now.head).toMatchObject(before.head);
  await noA11yViolations(page);
});

test("build: Measure it on a suggestion that changes the code opens Measure before and after, for it", async ({ page }) => {
  const ORIGIN = { Origin: `http://127.0.0.1:${process.env.PG_E2E_PORT ?? 7361}` };
  const TAG = process.env.PG_E2E_TAG ?? "pg-e2e";
  await openMeasure(page);
  const repos = (await (await page.request.get("/api/repos")).json()) as { id: string; name: string }[];
  const id = repos.find((r) => r.name === TAG)!.id;
  type P = { id: string; title: string; state: string; measure: string; delta: { add?: { label: string }[] } };
  const all = async () => ((await (await page.request.get(`/api/suggestions?repo=${id}`)).json()) as { proposals: P[] }).proposals;
  const reopen = async () => {
    for (const p of await all()) await page.request.put(`/api/suggestions/${p.id}?repo=${id}`, { data: { state: "open" }, headers: ORIGIN });
  };
  // A split that adds a part: the fake review's (never a real agent session).
  const find = async () => (await all()).find((p) => p.measure === "before_after" && p.delta.add?.length);
  if (!(await find())) {
    await page.request.post(`/api/suggestions/review?repo=${id}`, { data: { agent: "claude-code" }, headers: ORIGIN });
    await expect.poll(async () => Boolean(await find()), { timeout: 20_000 }).toBe(true);
  }
  await reopen();
  const split = (await find())!;
  const note = `Measuring “${split.title}”: pick the branch, commit or uncommitted changes that make it as the After side.`;
  const mode = page.getByTestId("measure-mode");

  // From the suggestion's card.
  await page.addInitScript((key) => localStorage.setItem(key, "1"), `pg.arch-open:${TAG}`);
  await page.reload();
  await toStep(page, 3);
  await page.getByRole("tab", { name: "Suggestions" }).click();
  const card = page.locator(".prop", { hasText: split.title });
  await expect(card.locator("[data-measure]")).toHaveText("Changes the Code");
  // Only a change to the code gets the link: a suggestion with nothing to run has none.
  for (const p of (await all()).filter((x) => x.state === "open" && x.measure !== "before_after"))
    await expect(page.locator(`[data-prop="${p.id}"]`).getByRole("button", { name: "Measure It" })).toHaveCount(0);
  await noA11yViolations(page);
  if (SHOTS) {
    await card.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${SHOTS}/measure-it-card.png` });
  }
  await card.getByRole("button", { name: "Measure It" }).click();
  await expect(mode.getByRole("radio", { name: "A Code Change: Before and After" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("ba-for")).toHaveText(note);
  await expect(page.getByTestId("before-after")).toBeVisible();
  await noA11yViolations(page);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/measure-it-measure.png` });
  // Picking the other mode drops the note; it isn't about an agent change.
  await mode.getByRole("radio", { name: "An Agent Change: With and Without" }).click();
  await expect(page.getByTestId("ba-for")).toHaveCount(0);
  await mode.getByRole("radio", { name: "A Code Change: Before and After" }).click();
  await expect(page.getByTestId("ba-for")).toHaveCount(0);

  // From a part the accepted suggestion adds, in "With accepted": the note names the suggestion.
  await toStep(page, 3);
  await page.getByRole("tab", { name: "Suggestions" }).click();
  await card.getByRole("button", { name: "Accept" }).click();
  await expect(page.locator(".prop--accepted", { hasText: split.title })).toBeVisible();
  await page.getByRole("radio", { name: /^With Accepted/ }).click();
  await page.locator(`.canvas__node[aria-label$=" ${split.delta.add![0].label}"] .block__body`).first().click();
  await expect(page.getByTestId("measure-line")).toContainText("Changes the Code");
  await page.getByTestId("insp-measure-it").click();
  await expect(mode.getByRole("radio", { name: "A Code Change: Before and After" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("ba-for")).toHaveText(note);
  await reopen();
});

test("measure: the page's lead and the run column's line follow the mode", async ({ page }) => {
  await openMeasure(page);
  const says = page.getByTestId("measure-says");
  const lead = page.locator(".stagehead").first();
  await expect(says).toContainText("Every task runs twice, with and without the change, so the difference is the change's.");
  await expect(lead).toContainText("Choose the tasks, then run the change on them with and without it.");
  await page.getByRole("radio", { name: "A Code Change: Before and After" }).click();
  await expect(says).toContainText("Every task runs twice, on the code before and after the change, so the difference is the change's.");
  await expect(says).not.toContainText("with and without");
  await expect(lead).toContainText("Choose the tasks, then run them on the code before and after the change.");
  await noA11yViolations(page);
  await page.getByRole("radio", { name: "An Agent Change: With and Without" }).click();
  await expect(says).toContainText("with and without the change");
});
