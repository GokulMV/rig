import { expect, type Page, test } from "@playwright/test";

// Rig a Repo tells one story: what was accepted shows on Build and in the brief, every card says
// whether Measure can test it, Measure and Build always have a way back, and the goal shapes
// Design and the tasks. Runs last (zz-), on the server the other files have used, so it puts the
// suggestions it needs back to open first.
declare const process: { env: Record<string, string | undefined> };
const TAG = process.env.PG_E2E_TAG ?? "pg-e2e";
const ORIGIN = { Origin: `http://127.0.0.1:${process.env.PG_E2E_PORT ?? 7361}` };

const TAB = { 1: "Describe", 2: "Design", 3: "Build", 4: "Measure", 5: "Ship" } as const;
async function toStep(page: Page, n: 1 | 2 | 3 | 4 | 5) {
  await page
    .getByRole("navigation", { name: /^(Steps|Workspace)$/ })
    .getByRole("button", { name: new RegExp(`^(${n}\\. |${TAB[n]}$)`) })
    .click();
}

async function repoId(page: Page): Promise<string> {
  const repos = (await (await page.request.get("/api/repos")).json()) as { id: string; name: string }[];
  return repos.find((r) => r.name === TAG)!.id;
}

/** Every suggestion open again, so this file starts from nothing accepted. */
async function reopenAll(page: Page, id: string) {
  const got = (await (await page.request.get(`/api/suggestions?repo=${id}`)).json()) as { proposals: { id: string }[] };
  for (const p of got.proposals) await page.request.put(`/api/suggestions/${p.id}?repo=${id}`, { data: { state: "open" }, headers: ORIGIN });
}

async function openRepo(page: Page, step: 1 | 2 | 3 | 4 | 5) {
  await page.addInitScript((key) => localStorage.setItem(key, "1"), `pg.arch-open:${TAG}`);
  await page.goto("/");
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await page.getByRole("radio", { name: TAG, exact: true }).click();
  if (step > 1) await toStep(page, step);
}

test.describe.configure({ mode: "serial" });

test("accepted suggestions are what Build draws, each card says if Measure can test it, and Ship says what “with” adds", async ({ page }) => {
  const id = await repoId(page);
  await reopenAll(page, id);
  // A suggestion that changes the app's code, and adds a part: the fake review's split.
  type P = { id: string; title: string; measure: string; delta: { add?: { label: string }[] } };
  const find = async () =>
    ((await (await page.request.get(`/api/suggestions?repo=${id}`)).json()) as { proposals: P[] }).proposals.find(
      (p) => p.measure === "before_after" && p.delta.add?.length,
    );
  if (!(await find())) {
    await page.request.post(`/api/suggestions/review?repo=${id}`, { data: { agent: "claude-code" }, headers: ORIGIN });
    await expect.poll(async () => Boolean(await find()), { timeout: 20_000 }).toBe(true);
  }
  const code = (await find())!;
  const part = code.delta.add![0].label;
  await openRepo(page, 3);
  // Nothing accepted: the view says so, and open suggestions aren't drawn.
  await expect(page.getByTestId("suggested-count")).toHaveText("With Accepted · 0");
  // Each canvas row says what Measure tests there; each card has a badge.
  await expect(page.locator(".lane__measure").first()).toHaveText("Measure tests what you add or change here");
  await expect(page.locator('.canvas__node[aria-label*="CLAUDE.md"] [data-measure]')).toHaveText("In Every Run");
  await expect(page.locator('.canvas__node[aria-label^="Skill in repo"] .est--verdict, .canvas__node[aria-label^="Skill in repo"] [data-measure]').first()).toBeVisible();
  // A measured skill reads as Measure reads it, never as an estimate's "Measured +N pts".
  await expect(page.locator(".canvas .est--measured")).toHaveCount(0);

  await page.getByRole("tab", { name: "Suggestions" }).click();
  const hot = page.locator(".prop", { hasText: code.title });
  await expect(hot.locator("[data-measure]")).toHaveText("Changes the Code");
  await expect(hot.getByTestId("prop-measure")).toContainText("make the change on a branch (or leave it uncommitted), then Measure runs the tasks on the commit before and on the change");
  // Previewing draws one open suggestion, marked as a preview.
  await hot.getByRole("button", { name: "Preview" }).click();
  await expect(page.locator(".block__flag--new").first()).toHaveText("Preview");
  await hot.getByRole("button", { name: "Accept" }).click();
  await expect(page.locator(".prop--accepted", { hasText: code.title }).locator(".prop__state")).toHaveText("Accepted");
  await page.getByRole("radio", { name: "As It Is" }).click();
  await page.getByRole("radio", { name: /^With Accepted/ }).click();
  await expect(page.getByTestId("suggested-count")).toHaveText("With Accepted · 1");
  await expect(page.locator(".difflegend")).toContainText("1 accepted suggestion applied");
  await expect(page.locator(".block__flag--new").first()).toHaveText("New");
  // A new part names the suggestion it came from.
  await page.locator(`.canvas__node[aria-label$=" ${part}"] .block__body`).first().click();
  await expect(page.getByTestId("part-origin")).toContainText(`${code.title} · accepted`);
  await expect(page.getByTestId("measure-line")).toContainText("Changes the Code");

  // Ship: "with" adds exactly that change, listed by name.
  await toStep(page, 5);
  const ship = page.getByTestId("ship-difference");
  await expect(ship).toHaveAttribute("data-same", "false");
  await expect(ship).toContainText(code.title);
  // Marked as Build marks it: a change to the code, measured before and after.
  await expect(ship.locator("li", { hasText: code.title }).locator("[data-measure]")).toHaveText("Changes the Code");
  await expect(page.locator(".rig__kicker").first()).toContainText("the Last Skill Measured");
  await reopenAll(page, id);
});

test("Build and Measure keep a way back; Measure says what it can't run; the task form explains a check", async ({ page }) => {
  await openRepo(page, 4);
  const head = page.locator(".stagehead");
  // Guided or workspace, Measure always has a way back to Build.
  await expect(head.getByRole("button", { name: /^Back/ })).toBeVisible();
  await page.getByRole("button", { name: "Change What's Measured on Build" }).click();
  await expect(page.getByRole("heading", { level: 1, name: new RegExp(`^Change ${TAG}'s Parts$`) })).toBeVisible();
  await expect(page.locator(".stagehead").getByRole("button", { name: /^Back/ })).toBeVisible();
  await toStep(page, 4);
  await page.getByRole("button", { name: "+ Add Task" }).click();
  await expect(page.getByTestId("check-help")).toContainText("exit code 0 is a pass");
  await expect(page.locator("#sc-step-hint")).toContainText("A skill linked to that step on Build is measured on it");
  // The task generator shows Describe's goal, read only, with the way to edit it.
  await page.getByText("Generate tasks from the repo and docs").click();
  await expect(page.getByTestId("generate-goal-copy")).toBeVisible();
  await expect(page.getByLabel("Use case")).toHaveCount(0);
  await page.getByRole("button", { name: "Edit in Describe" }).click();
  await expect(page.getByRole("heading", { name: "What Should Your Agent Get Better At?" })).toBeVisible();
});

test("a goal from a template is about the agent: Design keeps the repo's design, the catalog folded, and the metric is saved", async ({ page }) => {
  await openRepo(page, 1);
  const before = await repoId(page);
  const was = ((await (await page.request.get(`/api/project?repo=${before}`)).json()) as { use_case: string | null }).use_case;
  await page.getByRole("button", { name: "Fewer Tokens at the Same Pass Rate" }).click();
  await expect(page.getByRole("button", { name: "Fewer Tokens at the Same Pass Rate" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Save Goal" }).click();
  await expect(page.getByRole("button", { name: "Saved" })).toBeVisible();
  const id = await repoId(page);
  const p = (await (await page.request.get(`/api/project?repo=${id}`)).json()) as { goal_template: string; goal_metric: string };
  expect([p.goal_template, p.goal_metric]).toEqual(["fewer-tokens", "tokens"]);
  await toStep(page, 2);
  const keep = page.getByTestId("keep-card");
  await expect(keep).toContainText("Recommended");
  await expect(keep).not.toContainText("reads like what the app does");
  // The catalog is behind one line until opened.
  const prints = page.getByTestId("blueprints");
  await expect(prints).not.toHaveAttribute("open", "");
  await expect(page.locator(".archcard")).toHaveCount(0);
  await prints.locator("summary").click();
  await expect(page.locator(".archcard").first()).toBeVisible();
  // Leave the shared fake repo's goal as it was: later specs expect no metric hint.
  const back = await page.request.put(`/api/usecase?repo=${id}`, { data: { text: was ?? "" }, headers: ORIGIN });
  expect(back.ok()).toBe(true);
});
