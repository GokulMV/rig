import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// A repo's run on Measure on a local model (the fake server's pretend Ollama, fake_server.py):
// picked in "Run on" beside the signed-in agent, free (no budget to set), the skill handed over,
// and the run naming the model in Results and Runs. A skill run, a before/after run and a run
// on tokens. Runs last (files go in name order): its runs and local model are seen by no other
// file, and the local model is removed at the end.

declare const process: { env: Record<string, string | undefined> };
// Set to a folder to save screenshots of the choice and the confirm there (1440 × 900).
const SHOTS = process.env.PG_E2E_SHOTS;

const TAB = { 1: "Describe", 2: "Design", 3: "Build", 4: "Measure", 5: "Ship" } as const;
const LOCAL = "qwen3:8b · ollama";

async function toStep(page: Page, n: 1 | 2 | 3 | 4 | 5) {
  await page
    .getByRole("navigation", { name: /^(Steps|Workspace)$/ })
    .getByRole("button", { name: new RegExp(`^(${n}\\. |${TAB[n]}$)`) })
    .click();
}

/** A write as the local app makes it: the engine refuses one without its Origin (playwright.config.ts's port). */
const APP = { origin: `http://127.0.0.1:${process.env.PG_E2E_PORT ?? 7361}` };

async function openMeasure(page: Page) {
  // Run on its own, the seeded repo isn't attached yet (flow.spec.ts attaches it): attach it.
  // Through the API, not a page: every page load starts the app's heavy reads (results, runs),
  // and the engine works through them after the page is gone, so the next load can wait seconds.
  const repos = (await (await page.request.get("/api/repos")).json()) as unknown[];
  if (!repos.length) {
    const r = await page.request.post("/api/repos", { headers: APP, data: { path: `${process.env.HOME}/.cache/${process.env.PG_E2E_TAG ?? "pg-e2e"}` } });
    expect(r.ok()).toBe(true);
  }
  await page.goto("/");
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await toStep(page, 4);
  // After the other files the repo has many runs, so reading it takes a while.
  await expect(page.getByLabel("Run on", { exact: true })).toBeEnabled({ timeout: 30_000 });
}

async function noA11yViolations(page: Page) {
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity),
  );
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target.join(" ")} (${n.failureSummary})`).join(", ")}`)).toEqual([]);
}

/** The option of the change picker whose label starts with `name`. */
async function pick(page: Page, name: string) {
  const select = page.getByLabel("Change to measure");
  const label = await select.locator("option").filter({ hasText: new RegExp(`^${name}`) }).first().textContent();
  await select.selectOption({ label: label ?? name });
}

test.describe.configure({ mode: "serial" });

test("measure on a local model: add one, pick it, a free run with the skill handed over, named in Results", async ({ page }) => {
  // Start with none added (the Lab's tests may have left one): the page shows how to add one.
  const got = (await (await page.request.get("/api/local-models")).json()) as { models: { id: string }[] };
  for (const m of got.models) expect((await page.request.delete(`/api/local-models/${encodeURIComponent(m.id)}`, { headers: APP })).ok()).toBe(true);
  await openMeasure(page);
  await pick(page, "refund-policy");
  const runOn = page.getByLabel("Run on", { exact: true });
  // None added yet: the signed-in agent, and how to add one.
  await expect(runOn.locator("option")).toHaveCount(1);
  await expect(runOn.locator("option").first()).toHaveText("Claude Code · your sign-in");
  await expect(page.getByTestId("run-on-none")).toContainText("No local model added yet: a run on one is free.");
  await expect(page.getByLabel("Stop at (USD)")).toBeVisible();
  await expect(page.getByTestId("run-cost")).toContainText("≈ $");

  await page.locator("summary", { hasText: /^Local Models/ }).click();
  await page.getByRole("button", { name: "Look on This Machine" }).click();
  await page.getByRole("list", { name: "Found local models" }).getByRole("button", { name: "Add" }).click();
  await expect(page.getByRole("list", { name: "Your local models" })).toContainText(LOCAL);
  await expect(page.getByTestId("run-on-none")).toHaveCount(0);
  await expect(runOn.locator("optgroup")).toHaveAttribute("label", "Local Models (Free, on This Machine)");

  await runOn.selectOption({ label: LOCAL });
  await expect(page.getByTestId("run-on-local")).toHaveText(
    `Claude Code runs in the sandbox with every model it asks for (subagents too) served by ${LOCAL}, reached as host.docker.internal, with 3× each task's time limit. Small local models often can't hold an agent loop: a run full of errors says that, not that the change is bad.`,
  );
  // Free: no budget to set, and the estimate says so (with what its pairs can tell from noise).
  await expect(page.getByLabel("Stop at (USD)")).toHaveCount(0);
  await expect(page.getByTestId("run-cost")).toHaveText(/^A local model: no API cost \(\d+ pairs?, \d+ trials?, on this machine\)\.$/);
  await expect(page.getByTestId("run-detect")).toBeVisible();
  await expect(page.getByText(/^Per pair /)).toHaveCount(0);
  // "Keep going until it's decided" has no budget to stop it here: its caps do (a pair per task a
  // look, 5 looks: 6 pairs per task).
  const tasks = Number((await page.getByText(/^\d+ runnable tasks? · /).textContent())!.split(" ")[0]);
  await expect(page.getByTestId("run-extends")).toHaveText(
    `With "Keep going until it's decided" on, it may grow to ${6 * tasks} pairs while it's undecided, its cap: a local model has no budget to stop it sooner.`,
  );
  // A small model never opens a skill it is only offered: on a local model the nudge starts on.
  const nudge = page.getByRole("checkbox", { name: /Tell the agent to open the skill/ });
  await expect(nudge).toBeChecked();
  await expect(page.getByText("Small local models rarely open a skill they are only offered, so on a local model this starts on.")).toBeVisible();
  await noA11yViolations(page);
  if (SHOTS) {
    await runOn.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${SHOTS}/measure-local.png` });
  }

  await page.getByRole("button", { name: "Review the Run" }).click();
  await expect(page.getByText(new RegExp(`× with and without, on ${LOCAL}\\.$`))).toBeVisible();
  await expect(page.getByTestId("confirm-free")).toHaveText(
    `Real agent runs in Docker sandboxes, on ${LOCAL} on this machine: free, nothing is billed, so there is no budget to set.`,
  );
  await expect(page.getByText(/billed to your sign-in/)).toHaveCount(0);
  await expect(page.getByText(/^Won't start a pair|^Capped at/)).toHaveCount(0);
  await noA11yViolations(page);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/measure-local-confirm.png` });
  await page.getByRole("button", { name: "Start, Free" }).click();

  await expect(page.getByTestId("run-status")).toHaveText("Done", { timeout: 30_000 });
  const verdict = page.locator(".verdict").first();
  await expect(verdict).toContainText(`refund-policy · ${LOCAL} (local) ·`);
  await expect(page.locator("dl.kv").filter({ hasText: "Spent" })).toContainText("Nothing: a local model");
  // The record names the model, ran Claude Code on it, handed the skill over, at no cost.
  type Row = { id: number; model: string; spent_usd: number; local_model: { id: string; label: string } | null; agent: string };
  const rows = (await (await page.request.get("/api/experiments")).json()) as Row[];
  const mine = rows.find((r) => r.local_model)!;
  expect(mine.local_model!.label).toBe(LOCAL);
  expect(mine.model).toBe(mine.local_model!.id);
  expect(mine.agent).toBe("claude-code");
  expect(mine.spent_usd).toBe(0); // the fake agent reports $0.12 a trial
  await expect(page.getByRole("list").filter({ hasText: `#${mine.id} ` }).getByText(`${LOCAL} (local) · free`)).toBeVisible();
  await noA11yViolations(page);
});

test("measure on a local model: cost can't be the metric; tokens and a before/after run can", async ({ page }) => {
  await openMeasure(page);
  await page.getByLabel("Run on", { exact: true }).selectOption({ label: LOCAL });
  const picker = page.getByTestId("metric-picker");
  await picker.getByRole("radio", { name: "Cost per Solved Task" }).click();
  await expect(page.getByTestId("cost-on-local")).toHaveText(
    "A local model costs nothing, so cost per solved task can't be compared. Pick tokens or time, or the pass rate.",
  );
  await expect(page.getByRole("button", { name: "Review the Run" })).toBeDisabled();
  await picker.getByRole("radio", { name: "Tokens per Solved Task" }).click();
  await expect(page.getByTestId("cost-on-local")).toHaveCount(0);
  // Free, the guard's sizing is still said.
  await expect(page.getByTestId("metric-plan")).toContainText(/^Scored on tokens, the pass-rate guard needs about \d+ pairs/);

  // A code change before and after, on the local model, scored on tokens.
  await page.getByRole("radio", { name: "A Code Change: Before and After" }).click();
  await page.getByLabel("After: the change").selectOption("split-refunds");
  await expect(page.getByTestId("ba-files")).toHaveText("2 files differ");
  await expect(page.getByLabel("Run on", { exact: true })).toHaveValue(/^local:/);
  // The planned pairs only: on tokens it could keep going to 99 (the engine's tests run that).
  await page.getByRole("checkbox", { name: /Keep going until it's decided/ }).uncheck();
  await page.getByRole("button", { name: "Review the Run" }).click();
  await expect(page.getByText(new RegExp(`× before and after, on ${LOCAL}\\.$`))).toBeVisible();
  await expect(page.getByTestId("confirm-metric")).toHaveText("Scored on tokens per solved task, with the pass rate as the guard.");
  await page.getByRole("button", { name: "Start, Free" }).click();
  await expect(page.getByTestId("run-status")).toHaveText("Done", { timeout: 30_000 });
  await expect(page.getByTestId("arms-key")).toContainText("Before vs after");
  await expect(page.locator(".verdict").first()).toContainText(`${LOCAL} (local)`);
  type Row = { treatment_kind: string; metric: string; local_model: { label: string } | null; spent_usd: number };
  const rows = (await (await page.request.get("/api/experiments")).json()) as Row[];
  const ba = rows.find((r) => r.treatment_kind === "before_after" && r.local_model)!;
  expect(ba.metric).toBe("tokens");
  expect(ba.local_model!.label).toBe(LOCAL);
  expect(ba.spent_usd).toBe(0);
  await noA11yViolations(page);
});

test("runs: a run on a local model names it and reads as free", async ({ page }) => {
  await page.goto("/#/runs");
  const table = page.getByRole("region", { name: "Every run" });
  const row = table.locator("tr", { hasText: `${LOCAL} (local)` }).first();
  await expect(row).toBeVisible();
  await expect(row.locator(".runs__spent")).toHaveText("Free (local)");
  await noA11yViolations(page);

  // Leave the fake server's local models as they were.
  await openMeasure(page);
  await page.locator("summary", { hasText: /^Local Models/ }).click();
  const mine = page.getByRole("list", { name: "Your local models" });
  await mine.getByRole("button", { name: "Remove" }).click();
  await expect(mine).toHaveCount(0);
  await expect(page.getByTestId("run-on-none")).toBeVisible();
});
