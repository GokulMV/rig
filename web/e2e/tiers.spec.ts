import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// Bench difficulty in the browser: a bench's hard tier is picked and labelled; a baseline check
// is priced first, runs only the agent alone, and its result says the bench is too easy (the
// fake server's agent alone passes every rag-qa task); Measure then warns before Rig & Measure,
// and the Runs page lists the check. Runs after flow.spec.ts (files go in name order).

const TAB = { 1: "Describe", 2: "Design", 3: "Build", 4: "Measure", 5: "Ship" } as const;

async function toStep(page: Page, n: 1 | 2 | 3 | 4 | 5) {
  await page
    .getByRole("navigation", { name: /^(Steps|Workspace)$/ })
    .getByRole("button", { name: new RegExp(`^(${n}\\. |${TAB[n]}$)`) })
    .click();
}

async function openLab(page: Page) {
  await page.goto("/");
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await toStep(page, 4);
}

async function noA11yViolations(page: Page) {
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity),
  );
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

test.describe.configure({ mode: "serial" });

test("hard tier: picked per run, its tasks labelled, priced on its own tasks", async ({ page }) => {
  await openLab(page);
  const bench = page.getByLabel("Bench");
  await expect(bench.locator("option", { hasText: /^Questions answered from a company's documents · 6 tasks \+ \d+ hard/ })).toHaveCount(1);
  await bench.selectOption("rag-qa");
  const tiers = page.getByRole("radiogroup", { name: "Tasks" });
  await expect(tiers.getByRole("radio", { name: /^Standard · 6$/ })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText(/Tasks: Single-document factual questions;/)).toBeVisible();
  await tiers.getByRole("radio", { name: /^Hard · \d+$/ }).click();
  await expect(page.getByText(/Tasks: [^.]*\(hard\)/)).toBeVisible();
  await expect(page.getByText(/Single-document factual questions/)).toBeHidden();
  const hardN = Number((await tiers.getByRole("radio", { name: /^Hard/ }).innerText()).match(/(\d+)$/)![1]);
  // A pilot runs each hard task once per arm.
  await expect(page.getByRole("button", { name: new RegExp(`Rig & Measure · ${2 * hardN} trials`) })).toBeVisible();
  await tiers.getByRole("radio", { name: /^Standard and hard/ }).click();
  await expect(page.getByRole("button", { name: new RegExp(`Rig & Measure · ${2 * (6 + hardN)} trials`) })).toBeVisible();
  // A bench without a hard tier has no choice to make.
  await bench.selectOption("qa");
  await expect(page.getByRole("radiogroup", { name: "Tasks" })).toHaveCount(0);
  await noA11yViolations(page);
});

test("baseline check: priced first, the agent alone only, then too easy and a warning before measuring", async ({ page }) => {
  await openLab(page);
  await page.getByLabel("Bench").selectOption("rag-qa");
  await expect(page.getByTestId("too-easy-warn")).toHaveCount(0);
  await page.getByRole("button", { name: "Check the Bench First" }).click();
  const ask = page.getByTestId("probe-ask");
  await expect(ask).toContainText(/Check the bench first: run the agent alone on each task once, about \$\d+\.\d\d for 6 trials/);
  await expect(ask).toContainText("costs nothing extra overall");
  await noA11yViolations(page);
  await ask.getByRole("button", { name: /^Run the Check, up to \$\d+\.\d\d$/ }).click();
  await expect(page.getByRole("heading", { name: /^Checking the bench: the agent alone/ })).toBeVisible();
  // Done: the list, the bench line and Measure all say it.
  await expect(page.getByTestId("baseline-text")).toHaveText(/^Too easy for .+: the agent alone passed 6 of 6\.$/, { timeout: 60_000 });
  await expect(page.getByTestId("too-easy-warn")).toHaveText(
    "A workflow can't show a lift on quality here; it can only show cost or speed. Try the hard tier.",
  );
  await expect(page.getByLabel("Bench").locator("option", { hasText: /^Questions answered .* · too easy for / })).toHaveCount(1);
  await page.getByRole("button", { name: /Rig & Measure/ }).click();
  const confirm = page.locator(".card", { hasText: /^Run \d+ Trials/ });
  await expect(confirm).toContainText("Try the hard tier.");
  await confirm.getByRole("button", { name: "Back" }).click();
  // The hard tier knows nothing yet.
  await page.getByRole("radiogroup", { name: "Tasks" }).getByRole("radio", { name: /^Hard/ }).click();
  await expect(page.getByTestId("too-easy-warn")).toHaveCount(0);
  await expect(page.getByTestId("baseline-text")).toHaveCount(0);

  // The Runs page lists it as a baseline check, with what it found.
  await page.locator(".topbar").getByRole("button", { name: "Runs", exact: true }).click();
  const row = page.getByRole("region", { name: "Every run" }).locator("tbody tr", { hasText: "Baseline check" }).first();
  await expect(row).toContainText("The agent alone passed 6 of 6");
  await expect(row).toContainText("bench Questions answered from a company's documents");
});
