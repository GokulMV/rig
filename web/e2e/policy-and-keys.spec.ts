import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// In the browser: the goal's policy reaches the workflow and BUILD.md, a missing CLAUDE.md is
// said as missing and can be planned, the (?) opens on hover and focus, the reuse box says what
// it does in its state, and the canvas's + and ? keys.
// Runs after flow.spec.ts (files go in name order): the seeded repo is attached by then.

declare const process: { env: Record<string, string | undefined> };
const TAG = process.env.PG_E2E_TAG ?? "pg-e2e";

const POLICY =
  "Answer customer support tickets from our refund policy: refund within 30 days → full refund; 30–60 days → store credit; nothing after 60; anything over $200 needs a manager.";

const TAB = { 1: "Describe", 2: "Design", 3: "Build", 4: "Measure", 5: "Ship" } as const;

async function toStep(page: Page, n: 1 | 2 | 3 | 4 | 5) {
  await page
    .getByRole("navigation", { name: /^(Steps|Workspace)$/ })
    .getByRole("button", { name: new RegExp(`^(${n}\\. |${TAB[n]}$)`) })
    .click();
}

async function open(page: Page, step: 1 | 2 | 3 | 4 | 5, space: "repo" | "lab" = "repo") {
  await page.goto("/");
  await toStep(page, 1);
  await page.getByRole("radio", { name: space === "repo" ? /^My Repo/ : /^Nothing Yet/ }).click();
  if (step > 1) await toStep(page, step);
}

/** A repo's Design folds the catalog behind "Start from a Blueprint Instead": open it (no-op in the Lab). */
async function openBlueprints(page: Page) {
  const prints = page.getByTestId("blueprints");
  await page.waitForTimeout(50);
  if ((await prints.count()) && !(await prints.evaluate((d) => (d as HTMLDetailsElement).open))) await prints.locator("summary").click();
}

const designCard = (page: Page, name: string) =>
  page.locator(".archcard").filter({ has: page.locator(".archcard__name", { hasText: new RegExp(`^${name}`) }) });

const block = (page: Page, label: string) => page.locator(`.canvas__node[aria-label="${label}"]`);

async function noA11yViolations(page: Page) {
  // Settle first: a menu caught mid fade-in fails contrast and target size for no real reason.
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity),
  );
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  await page.addInitScript((key) => localStorage.setItem(key, "1"), `pg.arch-open:${TAG}`);
});

test("the goal's policy reaches the workflow and BUILD.md: Goal & rules, every rule line, no code needed", async ({ page }) => {
  await open(page, 1, "lab");
  await page.getByLabel("What you're building").fill(POLICY);
  await page.getByRole("button", { name: /^Next: Design/ }).click();
  // Step 2 says only the words that matched, per design, not the whole sentence each time.
  const fits = page.getByRole("region", { name: "Recommended architectures" });
  await expect(fits).toContainText("Because you said 'anything over $200 needs a manager'");
  await expect(fits).not.toContainText("Because you said 'Answer customer support tickets from our refund policy: refund");
  await openBlueprints(page);
  await designCard(page, "Human-in-the-loop approvals").click();
  await page.getByRole("button", { name: "Use This Design" }).click();
  await page.getByRole("button", { name: "Fit everything" }).click();

  // The Goal & rules box: the whole goal, editable, and the rule lines the first step follows.
  const brief = page.getByLabel("Goal & rules");
  await expect(brief).toHaveValue(POLICY);
  const rules = page.getByTestId("goal-rules");
  await expect(rules.locator("li")).toHaveText([
    "refund within 30 days → full refund",
    "30–60 days → store credit",
    "nothing after 60",
    "anything over $200 needs a manager",
  ]);
  await expect(page.locator(".canvas__node", { hasText: "APPROVALS.md" })).toHaveCount(0);
  await noA11yViolations(page);

  // BUILD.md: the goal whole and its rules; no code needed to start a support agent.
  await toStep(page, 5);
  const md = page.locator("main.steppage").getByLabel("BUILD.md");
  await expect(md).toContainText("## Goal");
  await expect(md).toContainText(POLICY);
  await expect(md).toContainText("Rules to follow:");
  await expect(md).toContainText("- 30–60 days → store credit");
  await expect(md).toContainText("30 days");
  await expect(md).toContainText("No code required to start: build it in your agent platform");
  await expect(md).not.toContainText("Language: Python (suggested");
  await expect(md).toContainText("## Project layout (optional)");

  // An edited rule goes to the brief too.
  await toStep(page, 3);
  await brief.fill(`${POLICY} Never refund gift cards.`);
  await brief.blur();
  await expect(rules.locator("li").last()).toHaveText("Never refund gift cards");
  await toStep(page, 5);
  await expect(md).toContainText("- Never refund gift cards");
});

test("a missing CLAUDE.md says it's missing, what to put in it, and becomes a planned part in BUILD.md", async ({ page }) => {
  // The seeded repo has a CLAUDE.md: answer as if it hadn't.
  await page.route(/\/api\/project(\?|$)/, async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    body.agent = (body.agent ?? []).map((x: { id: string }) =>
      x.id === "setup:CLAUDE.md"
        ? { id: "setup:CLAUDE.md", label: "CLAUDE.md", present: false, detail: "missing: add it, so the agent knows the repo's commands and rules" }
        : x,
    );
    await route.fulfill({ response: res, json: body });
  });
  await open(page, 3);
  await page.evaluate(() => Object.keys(localStorage).forEach((k) => k.startsWith("pg.canvas") && localStorage.removeItem(k)));
  await page.reload();
  const claude = block(page, "Agent setup CLAUDE.md");
  // Missing, in the badge that also says Measure has nothing to test.
  await expect(claude.locator("[data-measure]")).toHaveText("Not in the Repo");
  await expect(claude).toContainText("missing: add it");

  // The setup lane fits the canvas at the zoom it opens at: the Test command card isn't cut off.
  const canvas = (await page.locator(".canvas").first().boundingBox())!;
  const tests = (await block(page, "Agent setup Test command").boundingBox())!;
  expect(tests.x + tests.width).toBeLessThanOrEqual(canvas.x + canvas.width);

  await claude.locator(".block__body").click();
  const insp = page.locator(".insp");
  await expect(insp.locator(".insp__band")).toHaveText("Agent setup · missing");
  await expect(insp).toContainText("Missing: not in the repo yet");
  await expect(insp).not.toContainText("Already in the repo");
  await expect(page.getByTestId("setup-missing-points")).toContainText("pytest -q");
  await expect(page.getByTestId("setup-missing-points")).toContainText("Conventions");
  await noA11yViolations(page);
  await insp.getByRole("button", { name: "Add as a Planned Part" }).click();
  await expect(block(page, "Planned CLAUDE.md")).toBeVisible();
  await expect(insp.getByRole("status")).toContainText('Planned, not written yet');

  await toStep(page, 5);
  const step = page.locator("main.steppage");
  await step.getByRole("radio", { name: "As It Is" }).click();
  const md = step.getByLabel("BUILD.md");
  await expect(md).toContainText("Planned, not written yet");
  await expect(md).toContainText("- CLAUDE.md (`setup/CLAUDE.md`): Add CLAUDE.md at the repo root");
  await expect(md).toContainText("(test: pytest -q)");
});

test("a (?) opens on hover and on keyboard focus, and closes on leaving, Esc and blur", async ({ page }) => {
  await open(page, 3, "lab");
  const q = page.getByRole("button", { name: "What is pts (pass-rate points)?" }).first();
  await expect(q).toBeVisible();
  await q.hover();
  const tip = page.getByRole("tooltip");
  await expect(tip).toContainText("pts (pass-rate points): Percentage points of tasks passed.");
  await page.mouse.move(5, 5);
  await expect(tip).toHaveCount(0);
  await q.focus();
  await expect(tip).toBeVisible();
  await expect(q).toHaveAttribute("aria-describedby", /.+/);
  await page.keyboard.press("Escape");
  await expect(tip).toHaveCount(0);
});

test("the reuse box says what it does in the state it's in", async ({ page }) => {
  await open(page, 4, "lab");
  const state = page.getByTestId("reuse-state");
  await expect(state).toHaveText(/· on: earlier baseline trials that match .* are used again/);
  await page.getByRole("checkbox", { name: /Reuse matching baseline trials/ }).uncheck();
  await expect(state).toHaveText(/· off: the baseline runs fresh/);
  await expect(state).not.toContainText("on:");
});

test("keys: + opens Add step in the Lab and the library search on a repo; ? lists the shortcuts; Undo follows Cmd/Ctrl+Z", async ({ page }) => {
  await open(page, 3, "lab");
  await page.getByRole("button", { name: "Fit everything" }).click();
  await page.locator(".canvas").first().click({ position: { x: 20, y: 300 } });
  await page.keyboard.press("+");
  const menu = page.getByRole("group", { name: "Steps to add" });
  await expect(menu).toBeVisible();
  await expect(menu.locator(".labadd__item").first()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);

  // Undo is enabled after an edit, and disabled again once Cmd/Ctrl+Z took it back.
  const undo = page.getByRole("group", { name: "Workflow edits" }).getByRole("button", { name: "Undo" });
  await expect(undo).toBeDisabled();
  await page.getByRole("button", { name: /Add Step/ }).click();
  await menu.locator(".labadd__item").first().click();
  await expect(undo).toBeEnabled();
  await page.locator(".canvas").first().click({ position: { x: 20, y: 300 } });
  await page.keyboard.press("ControlOrMeta+z");
  await expect(undo).toBeDisabled();

  await page.keyboard.press("?");
  const sheet = page.getByRole("dialog", { name: "Keyboard Shortcuts" });
  await expect(sheet).toBeVisible();
  await expect(sheet).toContainText("Add a step");
  await expect(sheet).toContainText("Undo the last change");
  await expect(sheet).toContainText("Remove the selected step");
  await noA11yViolations(page);
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);

  // On a repo's canvas, + puts the cursor in the library search.
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await toStep(page, 3);
  await page.locator(".canvas").first().click({ position: { x: 20, y: 300 } });
  await page.keyboard.press("+");
  await expect(page.getByRole("region", { name: "Library" }).getByRole("searchbox")).toBeFocused();
  await page.locator(".canvas").first().click({ position: { x: 20, y: 300 } });
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog", { name: "Keyboard Shortcuts" })).toContainText("Search the library");
  await page.keyboard.press("Escape");

  // The repo canvas's Undo follows Cmd/Ctrl+Z too, and Delete takes the selected card off.
  await page.evaluate(() => Object.keys(localStorage).forEach((k) => k.startsWith("pg.canvas") && localStorage.removeItem(k)));
  await page.reload();
  const edits = page.getByRole("group", { name: "Canvas edits" });
  await expect(edits.getByRole("button", { name: "Undo" })).toBeDisabled();
  const palette = page.getByRole("region", { name: "Library" });
  await palette.getByRole("button", { name: /^Skills/ }).click();
  await palette.getByRole("button", { name: "Add tdd to the canvas" }).click();
  const card = page.locator('.canvas__node[aria-label="Skill tdd"]');
  await expect(card).toHaveCount(1);
  await expect(edits.getByRole("button", { name: "Undo" })).toBeEnabled();
  await page.locator(".canvas").first().click({ position: { x: 20, y: 300 } });
  await page.keyboard.press("ControlOrMeta+z");
  await expect(card).toHaveCount(0);
  await expect(edits.getByRole("button", { name: "Undo" })).toBeDisabled();
  await palette.getByRole("button", { name: "Add tdd to the canvas" }).click();
  await card.locator(".block__body").click();
  await page.keyboard.press("Delete");
  await expect(card).toHaveCount(0);
});

test("Measure's workflow map is read-only: no Undo or Reset there, and the bench choice is in view without scrolling", async ({ page }) => {
  await open(page, 3, "lab");
  await expect(page.getByRole("group", { name: "Workflow edits" }).getByRole("button", { name: "Undo" })).toBeVisible();
  await toStep(page, 4);
  await expect(page.getByText("Workflow map, read-only here.")).toBeVisible();
  await expect(page.getByRole("group", { name: "Workflow edits" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Undo" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reset" })).toHaveCount(0);
  const where = page.getByRole("group", { name: "Where it's measured" });
  await expect(where.getByLabel("Bench", { exact: true })).toBeInViewport();
  // The choice drives the settings below it: the same select, not a copy.
  await expect(page.getByLabel("Bench", { exact: true })).toHaveCount(1);
  await noA11yViolations(page);
});
