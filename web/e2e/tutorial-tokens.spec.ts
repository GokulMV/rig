import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// The repo tutorial (fewer tokens): Home offers it under the first one, it walks the five steps
// in repo mode on its own example with what to do on your repo at each, shows the recorded run
// scored on tokens, ends on three ways on, and never writes the person's own state.

const HOME = "Swap One Part. Rerun With and Without. See What It Changed.";
const h1 = (page: Page) => page.getByRole("heading", { level: 1 });
const tourNav = (page: Page) => page.getByRole("navigation", { name: "Tutorial" });

async function noA11yViolations(page: Page) {
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity),
  );
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual([]);
}

function appState(page: Page) {
  return page.evaluate(() =>
    Object.fromEntries(
      Object.keys(localStorage)
        .filter((k) => !k.startsWith("rig-tutorial"))
        .map((k) => [k, localStorage.getItem(k)]),
    ),
  );
}

test("Home offers both tracks, the first one first; the repo tutorial walks five steps in repo mode and writes nothing of yours", async ({ page }) => {
  await page.goto("/");
  await expect(h1(page)).toHaveText(HOME);
  const tour = page.locator("[data-slot='tour']");
  const starts = tour.getByRole("button", { name: /^Start the (Repo )?Tutorial/ });
  await expect(starts).toHaveText([/^Start the Tutorial/, /^Start the Repo Tutorial/]);
  await expect(tour.getByRole("heading", { name: "Rig Your Own Repo: Fewer Tokens" })).toBeVisible();

  // The app's own start-up writes settle first (as in tutorial.spec.ts), then nothing may change.
  await expect.poll(async () => Object.keys(await appState(page)).join(",")).toContain("pg.lab.wf");
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

  await tour.getByRole("button", { name: "Start the Repo Tutorial" }).click();
  await expect(page).toHaveURL(/#\/tutorial\/tokens\/describe$/);
  const titles = [/^Describe:/, /^Design:/, /^Build:/, /^Measure:/, /^Ship:/];
  for (const [i, title] of titles.entries()) {
    await expect(h1(page)).toHaveText(title);
    await expect(page.getByText(`Repo tutorial · step ${i + 1} of 5`)).toBeVisible();
    await expect(page.getByRole("region", { name: "On Your Repo", exact: true }).getByRole("listitem").first()).toBeVisible();
    if (i === 0) {
      await expect(page.getByText("Use fewer tokens on each task in this repo", { exact: false }).first()).toBeVisible();
      await expect(page.getByText("def camel(text: str) -> str:")).toBeVisible();
    }
    if (i === 1) await expect(page.getByRole("region", { name: "On Your Repo", exact: true })).toContainText("Keep <your repo>'s Design");
    if (i === 2) {
      const places = page.getByRole("region", { name: "Where Things Go, and What Their Badges Mean" });
      for (const b of ["Measurable", "In Every Run", "Changes the Code", "Not Installed"]) await expect(places).toContainText(b);
    }
    if (i === 3) {
      await expect(page.getByRole("list", { name: "Tasks" }).getByRole("listitem")).toHaveCount(10);
      await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(10);
      await expect(page.getByTestId("metric-line").first()).toContainText("Tokens per Solved Task");
      await expect(page.getByTestId("metric-guard").first()).toContainText("Pass rate");
      await expect(page.getByRole("region", { name: "The Rig Score" })).toContainText("/100");
    }
    if (i === 4) await expect(page.getByRole("region", { name: "The Build Brief, for This Example" })).toContainText("lean-context");
    await noA11yViolations(page);
    await tourNav(page).getByRole("button", { name: i < 4 ? /^Next: / : "Finish" }).click();
  }

  await expect(page).toHaveURL(/#\/tutorial\/tokens\/done$/);
  await expect(h1(page)).toHaveText("Now Do It on Your Repo");
  const ways = page.getByRole("list", { name: "Where next" });
  await expect(ways.getByRole("button")).toHaveText([/^Rig Your Own Repo/, /^The First Tutorial/, /^Back to Home/]);
  await noA11yViolations(page);
  expect(await appState(page)).toEqual(before);
  expect(writes).toEqual([]);

  // "The first tutorial" opens the other track; Home then says Replay for this one only.
  await ways.getByRole("button", { name: /^The First Tutorial/ }).click();
  await expect(page).toHaveURL(/#\/tutorial\/describe$/);
  await expect(h1(page)).toHaveText(/^Describe: What Should the Agent Get Better At\?/);
  await page.getByRole("link", { name: "Leave the Tutorial" }).click();
  await expect(page.getByRole("button", { name: "Replay the Repo Tutorial" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start the Tutorial" })).toBeVisible();
});

test("its finish opens step 1 in repo mode, and a link straight to a step works", async ({ page }) => {
  await page.goto("/#/tutorial/tokens/build");
  await expect(h1(page)).toHaveText(/^Build:/);
  await page.goto("/#/tutorial/tokens/done");
  await page.getByRole("list", { name: "Where next" }).getByRole("button", { name: /^Rig Your Own Repo/ }).click();
  await expect(page).toHaveURL(/#\/describe$/);
  await expect(page.getByRole("radio", { name: /^My Repo/ })).toHaveAttribute("aria-checked", "true");
});
