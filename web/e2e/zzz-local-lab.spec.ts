import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// The Lab on a local model (the fake server's pretend Ollama, fake_server.py), as a repo's
// Measure has it: cost can't be the metric, and its runs are named by the model's label. Runs after the other files (name order) and before
// zzz-local-repo.spec.ts, which starts by removing every local model; this one removes its own.

const TAB = { 1: "Describe", 2: "Design", 3: "Build", 4: "Measure", 5: "Ship" } as const;
const LOCAL = "qwen3:8b · ollama";
const COST = "A local model costs nothing, so cost per solved task can't be compared. Pick tokens or time, or the pass rate.";

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

/** The Lab's Measure with the local model added (once) and picked in "Run on". */
async function labOnLocal(page: Page) {
  await page.goto("/");
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await toStep(page, 4);
  // After the other files the benches have many runs, so they take a while to load.
  const runOn = page.getByLabel("Run on", { exact: true });
  await expect(runOn).toBeVisible({ timeout: 30_000 });
  const added = (await (await page.request.get("/api/local-models")).json()).models.length;
  if (!added) {
    await page.locator("summary", { hasText: /^Local Models/ }).click();
    await page.getByRole("button", { name: "Look on This Machine" }).click();
    await page.getByRole("list", { name: "Found local models" }).getByRole("button", { name: "Add" }).click();
    await expect(page.getByRole("list", { name: "Your local models" })).toContainText(LOCAL);
  }
  await expect(runOn.locator("option", { hasText: LOCAL })).toHaveCount(1);
  await runOn.selectOption({ label: LOCAL });
}

test.describe.configure({ mode: "serial" });

test("the Lab on a local model: cost can't be the metric, on one bench or a suite", async ({ page }) => {
  await labOnLocal(page);
  const picker = page.getByTestId("metric-picker");
  const start = page.getByRole("button", { name: /Rig & Measure/ });
  await picker.getByRole("radio", { name: "Cost per Solved Task" }).click();
  await expect(page.getByTestId("cost-on-local")).toHaveText(COST);
  await expect(start).toBeDisabled();
  await noA11yViolations(page);
  await picker.getByRole("radio", { name: "Tokens per Solved Task" }).click();
  await expect(page.getByTestId("cost-on-local")).toHaveCount(0);
  await expect(start).toBeEnabled();

  // A suite never runs on a local model, and says so; on cost, that is said too.
  const bench = page.getByLabel("Bench", { exact: true });
  const single = await bench.inputValue();
  await bench.selectOption("__suite__");
  await expect(page.getByTestId("suite-local")).toHaveText("A suite runs on Claude Code, your sign-in; pick a single bench to run on a local model.");
  await expect(start).toHaveCount(0);
  await picker.getByRole("radio", { name: "Cost per Solved Task" }).click();
  await expect(page.getByTestId("cost-on-local")).toHaveText(COST);
  await noA11yViolations(page);
  await bench.selectOption(single);
  await expect(start).toBeDisabled();

  // The engine refuses it too, whatever the page sends.
  const got = await page.evaluate(async (bid) => {
    const lab = await (await fetch("/api/lab")).json();
    const local = (await (await fetch("/api/local-models")).json()).models[0].id;
    const r = await fetch("/api/lab/run", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ workflow: lab.disciplines[0].workflows[0], bench: bid, budget: 5, auto: false, local_model: local, metric: "cost" }),
    });
    return { status: r.status, detail: (await r.json()).detail };
  }, single);
  expect(got).toEqual({ status: 422, detail: COST });
});

test("the Lab on a local model: its runs are named by the model's label, not its id", async ({ page }) => {
  await labOnLocal(page);
  await page.getByRole("button", { name: /Rig & Measure/ }).click();
  await page.getByRole("button", { name: /^Start, up to/ }).click();
  // The live run names the model (a fake run can finish before it is seen: then the card below).
  const card = page.locator(".result").filter({ hasText: `${LOCAL} (local)` }).first();
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card.locator(".result__nums")).toContainText("Free (local)");
  await expect(page.locator(".results")).not.toContainText("local:");
  await noA11yViolations(page);

  // Runs names it the same way.
  await page.goto("/#/runs");
  const row = page.getByRole("region", { name: "Every run" }).locator("tr", { hasText: `${LOCAL} (local)` }).first();
  await expect(row).toBeVisible();
  await expect(row.locator(".runs__spent")).toHaveText("Free (local)");
  await expect(page.getByRole("region", { name: "Every run" })).not.toContainText("local:");
});

test("the Lab's Try it runs on the same choice: a local model, free, with no budget", async ({ page }) => {
  await labOnLocal(page);
  const box = page.getByTestId("try-it");
  await expect(page.getByTestId("try-price-local")).toHaveText(
    `Free: each input runs once on ${LOCAL} on this machine, with 3× the try's time limit. Nothing is billed, so there is no budget to set.`,
  );
  await expect(box.getByLabel("Stop this try at (USD)")).toHaveCount(0);
  await expect(box).toContainText(`Each input runs once, in an isolated test copy, never in your own files. Free, on ${LOCAL}; nothing runs until you click.`);
  await noA11yViolations(page);
  const sent: unknown[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && /\/api\/try(\?|$)/.test(r.url())) sent.push(r.postDataJSON());
  });
  await box.getByRole("textbox", { name: "Input 1" }).fill("Add a dark mode toggle to the settings page.");
  await box.getByRole("button", { name: "Run 1 Input, Free" }).click();
  await expect(page.getByTestId("try-progress")).toHaveText(`Done · free, on ${LOCAL}`, { timeout: 15_000 });
  expect(sent).toHaveLength(1);
  expect(sent[0]).toMatchObject({ agent: "claude-code", local_model: expect.stringMatching(/^local:/) });
  await box.getByRole("button", { name: "Clear the Answers and Edit the Inputs" }).click();
  // Back on the sign-in: dollars and a budget again.
  await page.getByLabel("Run on", { exact: true }).selectOption({ index: 0 });
  await expect(box.getByLabel("Stop this try at (USD)")).toBeVisible();
  await expect(box.getByRole("button", { name: /^Run 1 Input, up to \$/ })).toBeVisible();
});

test("the Lab's local model is removed again", async ({ page }) => {
  // Leave the fake server's local models as they were.
  await page.goto("/");
  await page.evaluate(async () => {
    const got = await (await fetch("/api/local-models")).json();
    for (const m of got.models) await fetch(`/api/local-models/${encodeURIComponent(m.id)}`, { method: "DELETE" });
  });
  expect((await (await page.request.get("/api/local-models")).json()).models).toEqual([]);
});
