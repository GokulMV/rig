import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// Try it on a repo's Measure follows the run's "Run on" choice: on a local model (the fake
// server's pretend Ollama, fake_server.py) it is free and needs no sign-in. Runs after
// zzz-local-repo.spec.ts (name order); it adds its own local model and removes it at the end.

declare const process: { env: Record<string, string | undefined> };

const TAB = { 1: "Describe", 2: "Design", 3: "Build", 4: "Measure", 5: "Ship" } as const;
const LOCAL = "qwen3:8b · ollama";

async function toStep(page: Page, n: 1 | 2 | 3 | 4 | 5) {
  await page
    .getByRole("navigation", { name: /^(Steps|Workspace)$/ })
    .getByRole("button", { name: new RegExp(`^(${n}\\. |${TAB[n]}$)`) })
    .click();
}

async function noA11yViolations(page: Page) {
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity),
  );
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target.join(" ")} (${n.failureSummary})`).join(", ")}`)).toEqual([]);
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
  // After the other files the repo has many runs, so reading it takes a while.
  await expect(page.getByLabel("Run on", { exact: true })).toBeEnabled({ timeout: 30_000 });
}

test.describe.configure({ mode: "serial" });

test("Try it on Measure runs on the run's choice: a local model, free, with no sign-in", async ({ page }) => {
  await openMeasure(page);
  const select = page.getByLabel("Change to measure");
  const label = await select.locator("option").filter({ hasText: /^refund-policy/ }).first().textContent();
  await select.selectOption({ label: label ?? "refund-policy" });
  const box = page.getByTestId("try-it");
  // On the signed-in agent first: priced in dollars, with a budget to stop at.
  await expect(box.getByLabel("Stop this try at (USD)")).toBeVisible();
  await expect(page.getByTestId("try-price")).toContainText(/^≈ \$\d+\.\d\d for 1 input/);

  await page.locator("summary", { hasText: /^Local Models/ }).click();
  await page.getByRole("button", { name: "Look on This Machine" }).click();
  await page.getByRole("list", { name: "Found local models" }).getByRole("button", { name: "Add" }).click();
  await page.getByLabel("Run on", { exact: true }).selectOption({ label: LOCAL });

  // Free: no budget, the price says where it runs, and the button says free.
  await expect(box.getByLabel("Stop this try at (USD)")).toHaveCount(0);
  await expect(page.getByTestId("try-price-local")).toHaveText(
    `Free: each input runs once on ${LOCAL} on this machine, with 3× the try's time limit. Nothing is billed, so there is no budget to set.`,
  );
  await expect(box).toContainText(`Free, on ${LOCAL}; nothing runs until you click.`);
  await expect(box).not.toContainText("Billed to your sign-in");
  await noA11yViolations(page);

  const sent: unknown[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && /\/api\/try(\?|$)/.test(r.url())) sent.push(r.postDataJSON());
  });
  await box.getByRole("textbox", { name: "Input 1" }).fill("Refund ticket T-12: charged twice for the pro plan.");
  await box.getByRole("button", { name: "Run 1 Input, Free" }).click();
  await expect(box.getByTestId("try-result")).toContainText("issued a full refund", { timeout: 15_000 });
  await expect(page.getByTestId("try-progress")).toHaveText(`Done · free, on ${LOCAL}`);
  expect(sent).toHaveLength(1);
  const body = sent[0] as { agent: string; local_model: string };
  expect(body.agent).toBe("claude-code");
  expect(body.local_model).toMatch(/^local:/);
  await noA11yViolations(page);

  // Back on the signed-in agent: dollars again.
  await box.getByRole("button", { name: "Clear the Answers and Edit the Inputs" }).click();
  await page.getByLabel("Run on", { exact: true }).selectOption({ index: 0 });
  await expect(box.getByLabel("Stop this try at (USD)")).toBeVisible();
  await expect(box.getByRole("button", { name: /^Run 1 Input, up to \$/ })).toBeVisible();

  // Leave the fake server's local models as they were.
  await page.evaluate(async () => {
    const got = await (await fetch("/api/local-models")).json();
    for (const m of got.models) await fetch(`/api/local-models/${encodeURIComponent(m.id)}`, { method: "DELETE" });
  });
});
