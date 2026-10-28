import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// The tutorial: it starts only from Home's button, walks the five steps on the recorded example,
// ends on three ways on, says "Replay" once finished, leaves the top bar as it is, and never
// writes the person's own state.

const HOME = "Swap One Part. Rerun With and Without. See What It Changed.";
const h1 = (page: Page) => page.getByRole("heading", { level: 1 });
const bar = (page: Page) => page.getByRole("navigation", { name: /^(Steps|Workspace)$/ });
const tourNav = (page: Page) => page.getByRole("navigation", { name: "Tutorial" });

async function noA11yViolations(page: Page) {
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity),
  );
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual([]);
}

/** The top bar as a person sees it: every link and button, with its name and where it goes. */
async function barShape(page: Page) {
  return bar(page).evaluate((nav) =>
    Array.from(nav.querySelectorAll("a, button")).map((el) => ({
      text: (el.textContent ?? "").trim(),
      href: el.getAttribute("href"),
      label: el.getAttribute("aria-label"),
    })),
  );
}

function appState(page: Page) {
  return page.evaluate(() => Object.fromEntries(Object.keys(localStorage).filter((k) => k !== "rig-tutorial.done").map((k) => [k, localStorage.getItem(k)])));
}

test("nothing starts on a first visit: Home offers the tutorial, and shows the recorded run in place of the illustration", async ({ page }) => {
  await page.goto("/");
  await expect(h1(page)).toHaveText(HOME);
  await expect(page).toHaveURL(/#\/home$/);
  const tour = page.locator("[data-slot='tour']");
  await expect(tour.getByRole("button", { name: "Start the Tutorial" })).toBeVisible();
  await expect(page.locator(".tour")).toHaveCount(0);
  const proof = page.getByTestId("recorded-proof");
  await expect(proof).toContainText("Real Run");
  await expect(proof).toContainText(/\d+ of \d+ passed/);
  await expect(page.getByText("Illustration, Not a Real Run")).toHaveCount(0);
  await page.reload();
  await expect(h1(page)).toHaveText(HOME);
  await noA11yViolations(page);
});

test("Start walks the five steps on the example, the top bar never changes, and Finish offers three ways on", async ({ page }) => {
  await page.goto("/");
  await expect(h1(page)).toHaveText(HOME);
  const home = bar(page).getByRole("link", { name: "Home" });
  await expect(home).toHaveAttribute("href", "#/home");
  const shape = await barShape(page);
  // The app's own start-up writes come first (the Lab, mounted behind every page, remembers its
  // workflow within a second or so of loading, tutorial or not): snapshot once they settled.
  await expect.poll(async () => Object.keys(await appState(page)).sort().join(",")).toContain("pg.lab.wf");
  let before = await appState(page);
  await expect.poll(async () => {
    const now = await appState(page);
    const same = JSON.stringify(now) === JSON.stringify(before);
    before = now;
    return same;
  }, { intervals: [500] }).toBe(true);
  const writes: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/") && r.method() !== "GET") writes.push(`${r.method()} ${r.url()}`);
  });

  await page.getByRole("button", { name: "Start the Tutorial" }).click();
  await expect(page).toHaveURL(/#\/tutorial\/describe$/);
  const titles = [/^Describe:/, /^Design:/, /^Build:/, /^Measure:/, /^Ship:/];
  for (const [i, title] of titles.entries()) {
    await expect(h1(page)).toHaveText(title);
    await expect(page.getByRole("list", { name: "Tutorial steps" }).getByRole("button", { name: new RegExp(`^${i + 1}\\. `) })).toHaveAttribute("aria-current", "step");
    // The top bar is the app's own: the same links and buttons, Home among them, no step marked.
    expect(await barShape(page)).toEqual(shape);
    await expect(home).toHaveText("Home");
    await expect(home).not.toHaveAttribute("aria-current");
    await expect(bar(page).locator("[aria-current]")).toHaveCount(0);
    if (i === 0) await expect(page.getByText("def price(cents: int) -> str:")).toBeVisible();
    if (i === 2) await expect(page.getByRole("list", { name: "Tasks" }).getByRole("listitem")).toHaveCount(10);
    if (i === 3) {
      await expect(page.getByRole("table").getByRole("row")).toHaveCount(12);
      await expect(page.getByRole("region", { name: "The Rig Score" })).toContainText("/100");
      for (const part of ["Lift", "Cost", "Followed", "Holds Up", "Reliable"]) await expect(page.getByRole("region", { name: "The Rig Score" })).toContainText(part);
    }
    await noA11yViolations(page);
    await tourNav(page).getByRole("button", { name: i < 4 ? /^Next: / : "Finish" }).click();
  }

  await expect(page).toHaveURL(/#\/tutorial\/done$/);
  await expect(h1(page)).toHaveText("That's Rig, End to End");
  const ways = page.getByRole("list", { name: "Where next" });
  await expect(ways.getByRole("button")).toHaveText([/^Rig Your Own Repo/, /^Rig a Workflow/, /^Back to Home/]);
  expect(await barShape(page)).toEqual(shape);
  await noA11yViolations(page);
  // Isolation: the whole way through, nothing of yours was written, here or on the engine.
  expect(await appState(page)).toEqual(before);
  expect(writes).toEqual([]);

  // Back in the browser's history retraces the steps.
  await page.goBack();
  await expect(h1(page)).toHaveText(/^Ship:/);
  await page.goForward();
  await ways.getByRole("button", { name: /^Back to Home/ }).click();
  await expect(page).toHaveURL(/#\/home$/);
  await expect(page.getByRole("button", { name: "Replay the Tutorial" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start the Tutorial" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("button", { name: "Replay the Tutorial" })).toBeVisible();
  expect(await barShape(page)).toEqual(shape);
});

test("the finish screen's ways on open step 1 in a repo or in the Lab; leaving early keeps Start", async ({ page }) => {
  await page.goto("/#/home");
  await page.getByRole("button", { name: "Start the Tutorial" }).click();
  await page.getByRole("link", { name: "Leave the Tutorial" }).click();
  await expect(h1(page)).toHaveText(HOME);
  await expect(page.getByRole("button", { name: "Start the Tutorial" })).toBeVisible();

  await page.goto("/#/tutorial/done");
  await page.getByRole("list", { name: "Where next" }).getByRole("button", { name: /^Rig Your Own Repo/ }).click();
  await expect(page).toHaveURL(/#\/describe$/);
  await expect(page.getByRole("radio", { name: /^My Repo/ })).toHaveAttribute("aria-checked", "true");

  await page.goto("/#/tutorial/done");
  await page.getByRole("list", { name: "Where next" }).getByRole("button", { name: /^Rig a Workflow/ }).click();
  await expect(page).toHaveURL(/#\/describe$/);
  await expect(h1(page)).toHaveText("What Are You Building?");
  await expect(page.getByRole("radio", { name: /^Nothing Yet/ })).toHaveAttribute("aria-checked", "true");
});
