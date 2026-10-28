import { expect, type Page, test } from "@playwright/test";

// Evidence: scores that agree with validity and the interval, Runs that fit and link, results
// scoped to what is open. The fake server seeds an old run of a GitHub skill that went over its
// $2.00 before the budget cap existed and ran a prose check, so it isn't evidence.
declare const process: { env: Record<string, string | undefined> };
const TAG = process.env.PG_E2E_TAG ?? "pg-e2e";
const PONY = "ponytail-audit (DietrichGebert/ponytail)";

test.describe.configure({ mode: "serial" });

async function runsPage(page: Page) {
  await page.goto("/");
  await page.locator(".topbar").getByRole("button", { name: "Runs", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Runs", exact: true })).toBeVisible();
  return page.getByRole("region", { name: "Every run" });
}

for (const width of [1280, 1440]) {
  test(`Runs fits at ${width}px: no sideways scroll, every key column in view`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const table = await runsPage(page);
    await expect(table.locator("tbody tr").first()).toBeVisible();
    const fit = await table.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
    expect(fit.scroll).toBeLessThanOrEqual(fit.client);
    for (const col of ["Measured", "Model", "Pairs", "Result", "Rig score", "Validity", "Spent"]) {
      const h = table.getByRole("columnheader", { name: col, exact: true });
      await expect(h).toBeInViewport();
    }
    const row = table.locator("tbody tr", { hasText: PONY });
    // The id reads as a name; the agent is in the model cell; the spend says why it went over.
    await expect(row.locator(".runs__name")).toHaveText(PONY);
    await expect(row.locator(".runs__model")).toContainText("Claude Code");
    await expect(row.locator(".runs__spent")).toContainText("$2.90 of $2.00");
    await expect(row.locator(".runs__over")).toHaveText("went over before the budget cap existed");
    await expect(row.getByTestId("runs-validity")).toHaveText("Invalid: the check is broken");
    await expect(row.getByTestId("runs-rig")).toHaveText("Not Evidence");
    // The Result column says the plain verdict and why, in a line.
    await expect(row.locator(".pill").first()).toHaveText("Stopped at the budget · can't tell yet so far");
    await expect(row.getByTestId("runs-why")).toHaveText("The task's check isn't a command, so every trial fails both ways.");
    await expect(row.getByRole("link", { name: `View ${PONY} on ${TAG}` })).toBeInViewport();
    await expect(row.getByRole("button", { name: /^Forget the run / })).toBeInViewport();
  });
}

test("a run has its own read-only link: the score is withheld, nothing switches until you confirm", async ({ page }) => {
  const [{ id: repoId, name: repoName }] = (await (await page.request.get("/api/repos")).json()) as { id: string; name: string }[];
  // Start in the Lab: viewing a repo's run must not take you out of it.
  await page.goto("/");
  await page.getByRole("navigation", { name: /^(Steps|Workspace)$/ }).getByRole("button", { name: /^(1\. |Describe$)/ }).click();
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  const table = await (async () => {
    await page.locator(".topbar").getByRole("button", { name: "Runs", exact: true }).click();
    return page.getByRole("region", { name: "Every run" });
  })();
  await table.locator("tbody tr", { hasText: PONY }).getByRole("link", { name: /^View / }).click();
  await expect(page).toHaveURL(new RegExp(`#/runs/repo/${repoId}/\\d+$`));
  const detail = page.getByTestId("run-detail");
  await expect(detail.getByRole("heading", { name: PONY })).toBeVisible();
  const card = detail.getByRole("region", { name: "Rig Score" });
  await expect(card.locator(".rig__value")).toHaveText("—");
  await expect(card.locator(".rig__label")).toHaveText("Not Evidence");
  await expect(card.locator(".rig__reason")).toContainText("Invalid: the check is broken");
  // The plain verdict is the headline: what it means, and the one thing to do next.
  await expect(card.getByTestId("rig-verdict")).toHaveText("Can't Tell Yet");
  await expect(card.getByTestId("rig-why")).toHaveText(
    "The task's check isn't a command, so every trial fails both ways. Next: give the task a real check.",
  );
  await expect(card.locator(".rig__part")).toHaveCount(0);
  // The card is the one verdict: no headline or warning box repeats it.
  await expect(detail.getByTestId("verdict-word")).toHaveCount(0);
  await expect(detail.getByTestId("validity-badge")).toHaveCount(0);
  await expect(detail.getByText("Not Evidence", { exact: true })).toHaveCount(1);
  await expect(detail.getByTestId("validity-note")).toHaveText(
    "Estimates don't count this run as a measurement of the change; its costs still price the next run.",
  );
  await expect(detail).toContainText("$2.90 of $2.00 · went over before the budget cap existed");
  await expect(detail.getByRole("region", { name: "Trials" }).locator("tbody tr")).toHaveCount(4);

  // The link works on its own: a reload comes back to the same run.
  await page.reload();
  await expect(page.getByTestId("run-detail").getByRole("heading", { name: PONY })).toBeVisible();

  // Open in Context asks first; Cancel switches nothing.
  await page.getByRole("button", { name: "Open in Context" }).click();
  const ask = page.getByRole("alertdialog", { name: "Open in Context" });
  await expect(ask).toContainText(`Switch to ${repoName}?`);
  await expect(ask).toContainText("Your canvas stays saved");
  await ask.getByRole("button", { name: "Cancel" }).click();
  await expect(page).toHaveURL(/#\/runs\/repo\//);
  await page.getByRole("link", { name: "All Runs" }).click();
  await expect(page.getByRole("region", { name: "Every run" })).toBeVisible();
  // Back in the Lab: still the Lab, never switched to the repo.
  await page.getByRole("navigation", { name: /^(Steps|Workspace)$/ }).getByRole("button", { name: /^(1\. |Describe$)/ }).click();
  await expect(page.getByRole("radio", { name: /^Nothing Yet/ })).toHaveAttribute("aria-checked", "true");

  // Confirmed, it switches to that repo's Measure step.
  await page.goto(`/#/runs/repo/${repoId}/2`);
  await page.getByRole("button", { name: "Open in Context" }).click();
  await page.getByRole("alertdialog", { name: "Open in Context" }).getByRole("button", { name: `Switch to ${repoName}` }).click();
  await expect(page.getByRole("heading", { name: "Tasks to Measure On" })).toBeVisible();
  expect(page.url()).not.toContain("#/runs");
  expect(repoName).toBe(TAG);
});

test("the Lab's Measured list and Results show this workflow's runs; others are apart, by name", async ({ page }) => {
  const valid = { status: "valid", badge: null, reason: null };
  const base = {
    bench: "qa", bench_name: "QA", model: "claude-sonnet-5-5", agent: "claude-code", status: "done", spent_usd: 1, reused: 0, saved_usd: 0,
    ci_low: -0.2, ci_high: 0.6, n_pairs: 2, adherence: null, validity: valid, verdict: "inconclusive", diff: 0.2, pass_with: 1, pass_without: 0.5,
  };
  const rig = {
    score: 22, band: "not_proven", tone: "warning", label: "Not proven — more pairs would settle it (2 so far)", reason: "No lift shown",
    provisional: true, pairs: 2, parts: [], gates: [], formula: null,
  };
  // Two other workflows' results: neither is the one open in the Lab.
  const results = [
    { ...base, id: 1, workflow: "RAG over the docs", treatment: "workflow-rag-docs", workflow_id: "rag-docs", rig },
    { ...base, id: 2, workflow: "Fix bugs from tickets", treatment: "workflow-ticket-fix", workflow_id: "ticket-fix", rig },
  ];
  await page.route("**/api/lab/results", (r) => r.fulfill({ json: results }));
  await page.route(/\/api\/lab\/matrix/, (r) =>
    r.fulfill({
      json: {
        bench: "qa", latest: null, tasks: [],
        rows: [{ experiment_id: 1, workflow: "RAG over the docs", treatment: "workflow-rag-docs", model: "claude-sonnet-5-5", agent: "claude-code",
          validity: valid, n_pairs: 2, diff: 0.2, ci_low: -0.1, ci_high: 0.5, pass_with: 1, pass_without: 0.5, cost_per_trial_usd: 0.4, mean_duration_s: 60, per_task: {} }],
      },
    }),
  );
  await page.goto("/");
  await page.getByRole("navigation", { name: /^(Steps|Workspace)$/ }).getByRole("button", { name: /^(1\. |Describe$)/ }).click();
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await page.getByRole("navigation", { name: /^(Steps|Workspace)$/ }).getByRole("button", { name: /^(4\. |Measure$)/ }).click();
  const measured = page.getByRole("region", { name: "Measured workflows" });
  await expect(measured).toContainText(/Not measured yet: .+ has no runs/);
  await expect(measured.locator(".results > .result")).toHaveCount(0);
  const others = measured.getByTestId("other-runs");
  await expect(others.locator("summary")).toHaveText("Other Runs (2)");
  await others.locator("summary").click();
  await expect(others).toContainText("RAG over the docs");
  await expect(others).toContainText("Fix bugs from tickets");

  // Results open on the bench picked in Measure, and say this workflow has nothing there.
  const bench = await page.getByLabel("Bench").inputValue();
  await page.getByLabel("Bench").selectOption("qa");
  await page.getByRole("radio", { name: "Results" }).click();
  await expect(page.getByLabel("Results from")).toHaveValue("qa");
  await expect(page.getByTestId("results-not-measured").first()).toContainText(/Not measured yet: .+ has no result on QA/);
  expect(bench.length).toBeGreaterThan(0);
});

test("Ship: the score header is for what is shipped, by name, and the estimate says what the run can detect", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation", { name: /^(Steps|Workspace)$/ }).getByRole("button", { name: /^(1\. |Describe$)/ }).click();
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await page.getByRole("navigation", { name: /^(Steps|Workspace)$/ }).getByRole("button", { name: /^(5\. |Ship$)/ }).click();
  // The repo's own skill (refund-policy) is on its canvas; the newer GitHub-skill run isn't.
  const card = page.getByRole("region", { name: "Rig score for refund-policy" });
  await expect(card.locator(".rig__kicker")).toContainText("Rig Score · refund-policy");
  await expect(page.getByRole("region", { name: /Rig score for ponytail/ })).toHaveCount(0);
  // Its band agrees with its interval (it reaches 0), and the formula rebuilds the number.
  await expect(card.locator(".rig__label")).toHaveText(/^Not Proven — /);
  await expect(card.getByTestId("rig-formula")).toContainText("weights rescaled to the measured parts");

  await page.getByRole("navigation", { name: /^(Steps|Workspace)$/ }).getByRole("button", { name: /^(4\. |Measure$)/ }).click();
  await page.getByLabel(/Stop at/).fill("0.5");
  await expect(page.getByTestId("run-cost")).toHaveText(/^Stops at \$0\.50 \(about \d+ of \d+ pairs?\)\. The full run would cost ≈ \$\d+\.\d\d\.$/);
  await expect(page.getByTestId("run-detect")).toHaveText(/^With \d+ pairs?, an effect smaller than about ±\d+ pts can't be told from noise\.$|doesn't pay for one pair/);
});

test("the estimate is measured on earlier trials, says what a ±25 pts change needs, sets that budget, and warns when full is no better", async ({ page }) => {
  // The fake server seeds an earlier bugfix run that never opened its workflow: not evidence for
  // the change, but its trials ($0.92-0.97 with, $0.03-0.04 without) are real costs.
  await page.goto("/");
  await page.getByRole("navigation", { name: /^(Steps|Workspace)$/ }).getByRole("button", { name: /^(1\. |Describe$)/ }).click();
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await page.getByRole("navigation", { name: /^(Steps|Workspace)$/ }).getByRole("button", { name: /^(4\. |Measure$)/ }).click();
  await page.getByLabel("Bench").selectOption("bugfix");
  await page.getByRole("radio", { name: /^Full/ }).click();
  await page.getByLabel(/Stop at/).fill("5");
  const est = page.locator(".runest:not([data-testid=try-price])").first();
  await expect(est).toContainText("Per pair $1.18 with + $0.04 without: measured on 3 earlier trials.");
  await expect(page.getByTestId("run-cost")).toHaveText(/^Stops at \$5\.00 \(about 4 of 20 pairs\)/);
  await expect(page.getByTestId("run-no-better")).toHaveText("At $5.00 this full run stops after 4 pairs: no more conclusive than the pilot.");
  // The Full choice says what $5 buys, never "conclusive".
  await expect(page.getByTestId("run-size-full")).toHaveText("Full · the budget only covers 4 pairs, as many as the pilot");
  await expect(page.getByTestId("run-sizing")).toContainText("To tell a ±25 pts change from noise you need about 31 pairs ≈ $38.00.");
  await page.getByRole("button", { name: "Set Budget to $38.00" }).click();
  await expect(page.getByLabel(/Stop at/)).toHaveValue("38");
  // The full run grows to the pairs that budget names: 7 whole repeats of the 5 tasks, of which
  // $38 pays for the 31 a ±25 pts change needs. Now, and only now, it is conclusive.
  await expect(page.getByTestId("run-cost")).toHaveText(/^Stops at \$38\.00 \(about 31 of 35 pairs\)\. The full run would cost ≈ \$4\d\.\d\d\.$/);
  await expect(page.getByTestId("run-no-better")).toHaveCount(0);
  await expect(page.getByTestId("run-detect")).toHaveText("With 31 pairs, an effect smaller than about ±25 pts can't be told from noise.");
  await expect(page.getByTestId("run-sizing")).toHaveCount(0);
  await expect(page.getByTestId("run-size-full")).toHaveText("Full · 31 pairs · conclusive to ±25 pts");
  // The run it starts plans those pairs (the engine's own count).
  await page.getByRole("button", { name: "Rig & Measure · 70 trials" }).click();
  const ask = page.locator(".card").filter({ hasText: "Run 70 Trials on" });
  await expect(ask).toContainText(/Every task in .+ runs 7× with this workflow and 7× without it/);
  await ask.getByRole("button", { name: "Back", exact: true }).click();
  // The pilot is the pilot: no warning about itself.
  await page.getByRole("radio", { name: /^Pilot/ }).click();
  await expect(page.getByTestId("run-cost")).toHaveText(/\(5 pairs, 10 trials\)/);
  await expect(page.getByTestId("run-no-better")).toHaveCount(0);
  // Still priced as a full run while the pilot is chosen.
  await expect(page.getByTestId("run-size-full")).toHaveText("Full · 31 pairs · conclusive to ±25 pts");
  await page.getByLabel(/Stop at/).fill("25");
  await expect(page.getByTestId("run-size-full")).toHaveText("Full · 20 pairs · tells apart ±31 pts");
  await page.getByLabel(/Stop at/).fill("5");
  await expect(page.getByTestId("run-size-full")).toHaveText("Full · the budget only covers 4 pairs, as many as the pilot");
});

test("a run's page says how it stopped in words, whether the workflow was followed, and keys the shaded band", async ({ page }) => {
  await page.goto("/#/runs/bench/bugfix/1");
  const detail = page.getByTestId("run-detail");
  await expect(detail.getByRole("heading", { name: "Seeded bug fixer" })).toBeVisible();
  await expect(detail.getByTestId("run-status")).toHaveText("Stopped at the budget");
  await expect(detail).not.toContainText("stopped_budget");
  await expect(detail.getByTestId("run-adherence")).toHaveText(
    'Followed the whole workflow in 0 of the 3 "with" trials whose logs could be read · skipped (of those 3): Fix in 3, Plan the fix in 3 · never opened the workflow in 3',
  );
  // Why it isn't evidence is said once, in the card; what the card doesn't say is one quiet line.
  await expect(detail.getByTestId("rig-score").locator(".rig__reason")).toContainText("Invalid: the workflow was never opened");
  await expect(detail.getByTestId("rig-verdict")).toHaveText("Can't Tell Yet");
  await expect(detail.getByTestId("rig-why")).toHaveText(
    'The "with" trials mostly ran without the workflow, so the difference isn\'t its. Next: check the workflow is handed to the agent, then run again.',
  );
  await expect(detail.getByText(/Invalid: the workflow was never opened/)).toHaveCount(1);
  await expect(detail.getByTestId("validity-badge")).toHaveCount(0);
  await expect(detail.getByTestId("validity-note")).toContainText("its costs still price the next run");
  // The band the sentence names is drawn, shaded, and keyed under the chart.
  const band = detail.locator(".interval__mde");
  await expect(band).toBeVisible();
  expect((await band.boundingBox())!.width).toBeGreaterThan(40);
  expect(await band.evaluate((el) => getComputedStyle(el).backgroundImage)).toContain("repeating-linear-gradient");
  await expect(detail.getByTestId("mde-key")).toHaveText(/^Shaded band: ±\d+ pts around 0 — the smallest change 3 pairs can detect\s*\?$/);
  // The Runs list says it in the same words.
  await page.getByRole("link", { name: "All Runs" }).click();
  const row = page.getByRole("region", { name: "Every run" }).locator("tbody tr", { hasText: "Seeded bug fixer" });
  await expect(row).toContainText("Stopped at the budget");
  await expect(row).not.toContainText("stopped_budget");
});

test("tasks are counted one way: approved with prose for a check is never runnable", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation", { name: /^(Steps|Workspace)$/ }).getByRole("button", { name: /^(1\. |Describe$)/ }).click();
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await page.getByRole("navigation", { name: /^(Steps|Workspace)$/ }).getByRole("button", { name: /^(4\. |Measure$)/ }).click();
  await expect(page.getByRole("heading", { name: "Tasks to Measure On" })).toBeVisible();
  await expect(page.getByTestId("task-count")).toHaveText("Tasks · 4 approved, 3 runnable — 1 check isn't a command");
  await expect(page.getByText("3 runnable tasks · ", { exact: false })).toBeVisible();

  // Only the prose one approved: the header and the run panel agree, and name what to fix.
  await page.route(/\/api\/scenarios(\?.*)?$/, async (r) => {
    if (r.request().method() !== "GET") return r.continue();
    const all = (await (await r.fetch()).json()) as { id: string; runnable: boolean }[];
    return r.fulfill({ json: all.map((s) => (s.id === "token-cost" ? s : { ...s, runnable: false, check_status: "unreviewed" })) });
  });
  await page.reload();
  await expect(page.getByTestId("task-count")).toHaveText("Tasks · 1 approved, 0 runnable — its check isn't a command");
  await expect(page.getByText("No runnable tasks: fix the check of Token cost.")).toBeVisible();
  await expect(page.getByText(/No approved (tasks|scenarios)/i)).toHaveCount(0);
});

test("a run whose checks count items says how many each arm got right, and each trial's count", async ({ page }) => {
  const [{ id: repoId }] = (await (await page.request.get("/api/repos")).json()) as { id: string }[];
  await page.goto(`/#/runs/repo/${repoId}/1`);
  const detail = page.getByTestId("run-detail");
  await expect(detail.getByTestId("items-right")).toHaveText(
    /^Items right: 141 of 144 with · 137 of 144 without \([+-]?\d+\.\d pts, 95% interval [+-]?\d+\.\d pts to [+-]?\d+\.\d pts\)$/,
  );
  const trials = detail.getByRole("region", { name: "Trials" });
  await expect(trials.getByRole("columnheader", { name: "Items" })).toBeVisible();
  await expect(trials.locator("tbody tr").last()).toContainText("12/12");
  await expect(trials.locator("tbody tr").nth(-2)).toContainText("11/12");
  // The API row carries the same counts.
  const row = (await (await page.request.get(`/api/experiments/1?repo=${repoId}`)).json()) as {
    items?: { right_with: number; total_without: number; n: number };
  };
  expect(row.items).toMatchObject({ right_with: 141, total_without: 144, n: 12 });
});
