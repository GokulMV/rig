import { expect, type Page, test } from "@playwright/test";

// Home, Build and Measure as two pages, the browser's Back across the hash routes, the Rig score
// explainer, and the page transition (with and without reduced motion).

const HOME = "Swap One Part. Rerun With and Without. See What It Changed.";
const steps = (page: Page) => page.getByRole("navigation", { name: /^(Steps|Workspace)$/ });
const h1 = (page: Page) => page.getByRole("heading", { level: 1 });

test("Home is the landing page: its two ways in open step 1 in that mode, and the logo comes back", async ({ page }) => {
  await page.goto("/");
  await expect(h1(page)).toHaveText(HOME);
  await expect(page).toHaveURL(/#\/home$/);
  await expect(steps(page).getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "Rig a Repo" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Rig a Workflow" })).toBeVisible();
  // A first visit has nothing to continue.
  await expect(page.getByRole("button", { name: /^Continue:/ })).toHaveCount(0);
  // Recent runs are the Runs page's own lists, newest first.
  await expect(page.getByRole("region", { name: "Recent Runs" }).getByRole("link").first()).toBeVisible();

  await page.getByRole("button", { name: /^(Rig a Repo|Add a Repo)$/ }).click();
  await expect(page).toHaveURL(/#\/describe$/);
  await expect(h1(page)).toHaveText("What Should Your Agent Get Better At?");
  await expect(page.getByRole("radio", { name: /^My Repo/ })).toHaveAttribute("aria-checked", "true");

  await page.getByRole("link", { name: "Rig, home" }).click();
  await expect(h1(page)).toHaveText(HOME);
  // Back from a step: Home offers to continue there.
  await expect(page.getByRole("button", { name: "Continue: Step 1 · Describe" })).toBeVisible();
  await page.getByRole("button", { name: "Rig a Workflow" }).click();
  await expect(h1(page)).toHaveText("What Are You Building?");
  await expect(page.getByRole("radio", { name: /^Nothing Yet/ })).toHaveAttribute("aria-checked", "true");
});

test("a returning visit lands on Home with Continue; a step's own link reopens that step", async ({ page }) => {
  await page.addInitScript(() => {
    if (localStorage.getItem("pg.step")) return;
    localStorage.setItem("pg.step", "3");
    localStorage.setItem("pg.reached", "3");
    localStorage.setItem("pg.space", "lab");
  });
  await page.goto("/");
  await expect(h1(page)).toHaveText(HOME);
  await page.getByRole("button", { name: "Continue: Step 3 · Build" }).click();
  await expect(page).toHaveURL(/#\/build$/);
  await expect(h1(page)).toHaveText("Build the Workflow");
  await page.reload();
  await expect(h1(page)).toHaveText("Build the Workflow");
});

test("Build and Measure are two pages with their own heading and action, in a repo and in the Lab", async ({ page }) => {
  await page.goto("/#/describe");
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await steps(page).getByRole("button", { name: /^3\. Build/ }).click();
  await expect(h1(page)).toHaveText(/^Change .+'s Parts$/);
  await expect(page.locator(".stagehead")).toContainText("Step 3 of 5 · Build");
  await expect(page.getByRole("heading", { name: "Tasks to Measure On" })).toHaveCount(0);
  await page.getByRole("button", { name: "Next: Measure" }).click();
  await expect(page).toHaveURL(/#\/measure$/);
  await expect(h1(page)).toHaveText("Measure What It Changed");
  await expect(page.getByRole("heading", { name: "Tasks to Measure On" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Canvas" })).toHaveCount(0);

  await steps(page).getByRole("button", { name: /^1\. Describe/ }).click();
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await steps(page).getByRole("button", { name: /^3\. Build/ }).click();
  await expect(h1(page)).toHaveText("Build the Workflow");
  await expect(page.getByRole("region", { name: "Workflows", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Add Step/ })).toBeVisible();
  const name = await page.locator(".insp__title").textContent();
  await expect(page.locator(".insp__band")).not.toHaveText("Measuring");
  await page.getByRole("button", { name: "Next: Measure" }).click();
  await expect(h1(page)).toHaveText("Measure the Workflow");
  // Measure's own layout: the run is the main column, the workflow a read-only map beside it.
  await expect(page.locator(".insp__band")).toHaveText("Measuring");
  await expect(page.getByRole("button", { name: /^Add Step/ })).toBeHidden();
  await expect(page.getByRole("button", { name: /^Remove the step / })).toHaveCount(0);
  await expect(page.locator(".insp__label", { hasText: /^Goal & rules$/ })).toHaveCount(0);
  await expect(page.getByTestId("try-it")).toBeVisible();
  await expect(page.getByLabel("Bench")).toBeVisible();
  const run = (await page.getByRole("region", { name: "Measure", exact: true }).boundingBox())!;
  const map = (await page.getByRole("region", { name: "Workflow", exact: true }).boundingBox())!;
  expect(run.x).toBeLessThan(map.x);
  expect(run.width).toBeGreaterThan(map.width);
  // The same workflow: the Lab kept it across the move.
  await expect(page.locator(".insp__title")).toHaveText(name!);
  await page.getByRole("button", { name: "Change It on Build" }).click();
  await expect(h1(page)).toHaveText("Build the Workflow");
  await expect(page.getByRole("button", { name: /^Remove the step / }).first()).toBeVisible();
  // Exactly one page heading at a time.
  await expect(h1(page)).toHaveCount(1);
});

test("the browser's Back and Forward retrace Home, the steps, Runs and the Rig score", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Rig a Workflow" }).click();
  await page.getByRole("button", { name: "Next: Design" }).click();
  await expect(page).toHaveURL(/#\/design$/);
  await page.getByRole("button", { name: "Next: Build" }).click();
  await expect(page).toHaveURL(/#\/build$/);
  await page.locator(".topbar").getByRole("button", { name: "Runs", exact: true }).click();
  await expect(page).toHaveURL(/#\/runs$/);
  await expect(h1(page)).toHaveText("Runs");

  await page.goBack();
  await expect(h1(page)).toHaveText("Build the Workflow");
  await page.goBack();
  await expect(page).toHaveURL(/#\/design$/);
  await expect(steps(page).getByRole("button", { name: /^2\. Design/ })).toHaveAttribute("aria-current", "step");
  await page.goBack();
  await expect(h1(page)).toHaveText("What Are You Building?");
  await page.goBack();
  await expect(h1(page)).toHaveText(HOME);
  await page.goForward();
  await expect(h1(page)).toHaveText("What Are You Building?");

  await steps(page).getByRole("link", { name: "Home" }).click();
  await page.getByRole("link", { name: /How the Rig Score Works/ }).click();
  await expect(page).toHaveURL(/#\/rig-score$/);
  await page.goBack();
  await expect(h1(page)).toHaveText(HOME);
});

test("the Rig score page: five parts whose weights add up to 100%, gates, bands and the engine's worked example", async ({ page }) => {
  await page.goto("/#/rig-score");
  await expect(h1(page)).toHaveText("How the Rig Score Works");
  const parts = page.getByTestId("rigx-part");
  await expect(parts).toHaveCount(5);
  await expect(parts.locator("b")).toHaveText(["Lift", "Cost", "Followed", "Holds Up", "Reliable"]);
  const weights = (await parts.locator(".rigx__weight").allTextContents()).map((t) => Number(t.replace("%", "")));
  expect(weights).toEqual([40, 20, 15, 15, 10]);
  expect(weights.reduce((a, b) => a + b, 0)).toBe(100);
  const bar = page.getByTestId("weight-bar");
  expect((await bar.locator("[data-weight]").evaluateAll((els) => els.map((e) => Number(e.getAttribute("data-weight"))))).reduce((a, b) => a + b, 0)).toBeCloseTo(1);
  // Two gates share the cap of 20: one row, two reasons.
  await expect(page.locator(".rigx__gates li")).toHaveCount(3);
  await expect(page.locator(".rigx__gates li").first()).toContainText("≤20");
  await expect(page.getByText("Illustrative Inputs, Not a Real Run")).toBeVisible();
  await expect(page.locator(".rigx__bands li")).toHaveCount(5);
  const example = page.getByRole("region", { name: "Worked Example" });
  await expect(example.locator(".rig__value")).toHaveText("67");
  await expect(example.getByTestId("rig-formula")).toContainText("÷ 85%");
  // Not a link to itself.
  await expect(example.getByRole("link", { name: "How Is This Scored?" })).toHaveCount(0);
});

test("every Rig score card and the Measure step link to the explainer", async ({ page }) => {
  await page.goto("/#/runs/bench/bugfix/1");
  const card = page.getByTestId("rig-score").first();
  await expect(card).toBeVisible();
  await card.getByRole("link", { name: "How Is This Scored?" }).click();
  await expect(h1(page)).toHaveText("How the Rig Score Works");
  await page.goBack();
  await expect(page.getByTestId("rig-score").first()).toBeVisible();

  await page.goto("/#/describe");
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await steps(page).getByRole("button", { name: /^4\. Measure/ }).click();
  await page.locator(".stagehead").getByRole("link", { name: "How Is This Scored?" }).click();
  await expect(h1(page)).toHaveText("How the Rig Score Works");
});

test("a page change slides in the way you went and moves focus to its heading; reduced motion has no movement", async ({ page }) => {
  await page.goto("/");
  const app = page.locator(".app");
  await page.getByRole("button", { name: "Rig a Workflow" }).click();
  await expect(app).toHaveAttribute("data-transition", "forward");
  // Describe puts you in its goal box; every other page focuses its heading.
  await expect(page.getByLabel("What you're building")).toBeFocused();
  await page.getByRole("button", { name: "Next: Design" }).click();
  await expect(h1(page)).toBeFocused();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(app).toHaveAttribute("data-transition", "back");
  // Fast clicks never queue: each part of the page has one transition at most, and it ends on the last page.
  for (let i = 0; i < 4; i++) await steps(page).getByRole("button", { name: new RegExp(`^${(i % 2) + 2}\\. `) }).click();
  const running = await page.evaluate(() => {
    const targets = document.getAnimations().filter((a) => a.id === "page-transition").map((a) => (a.effect as KeyframeEffect).target);
    return { n: targets.length, distinct: new Set(targets).size };
  });
  expect(running.n).toBe(running.distinct);
  await expect(page).toHaveURL(/#\/build$/);
  await page.waitForFunction(() => document.getAnimations().every((a) => a.id !== "page-transition" || a.playState !== "running"));
  const main = page.locator(".app > :not(.topbar)").first();
  expect(await main.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");

  await page.emulateMedia({ reducedMotion: "reduce" });
  await steps(page).getByRole("link", { name: "Home" }).click();
  await expect(h1(page)).toHaveText(HOME);
  await expect(app).toHaveAttribute("data-transition", "none");
  expect(await page.evaluate(() => document.getAnimations().filter((a) => a.id === "page-transition").length)).toBe(0);
  await expect(h1(page)).toBeFocused();
});
