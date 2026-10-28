import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// One goal in use for every step, the design a workflow came from kept through edits, and Try it
// first for a "Nothing yet" user. Runs after flow.spec.ts, on the same seeded server.
declare const process: { env: Record<string, string | undefined> };
const TAG = process.env.PG_E2E_TAG ?? "pg-e2e";

async function noA11yViolations(page: Page) {
  // Settle first: a menu caught mid fade-in fails contrast and target size for no real reason.
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity),
  );
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

/** A repo's goal box, whatever its heading says (saved, a draft of it, or a first goal). */
const goalBox = (page: Page, repo: string) =>
  page.getByLabel(new RegExp(`^(Saved goal|Draft goal|Goal) for ${repo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}( \\(unsaved\\))?$`));

const TAB = { 1: "Describe", 2: "Design", 3: "Build", 4: "Measure", 5: "Ship" } as const;
async function toStep(page: Page, n: 1 | 2 | 3 | 4 | 5) {
  await page
    .getByRole("navigation", { name: /^(Steps|Workspace)$/ })
    .getByRole("button", { name: new RegExp(`^(${n}\\. |${TAB[n]}$)`) })
    .click();
}

/** Open the app on step 1 and pick a "Start from" card: a first visit preselects neither. */
async function start(page: Page, space: "repo" | "lab") {
  await page.goto("/");
  await toStep(page, 1);
  await page.getByRole("radio", { name: space === "repo" ? /^My Repo/ : /^Nothing Yet/ }).click();
  if (space === "repo") await page.getByRole("radio", { name: TAG, exact: true }).click();
}

/** A repo's Design folds the catalog behind "Start from a Blueprint Instead": open it (no-op in the Lab). */
async function openBlueprints(page: Page) {
  const prints = page.getByTestId("blueprints");
  await page.waitForTimeout(50);
  if ((await prints.count()) && !(await prints.evaluate((d) => (d as HTMLDetailsElement).open))) await prints.locator("summary").click();
}

const designCard = (page: Page, name: string) =>
  page.locator(".archcard").filter({ has: page.locator(".archcard__name", { hasText: new RegExp(`^${name}`) }) });

const savedGoal = async (page: Page) => {
  const repos = (await (await page.request.get("/api/repos")).json()) as { id: string; name: string }[];
  const id = repos.find((r) => r.name === TAG)!.id;
  return ((await (await page.request.get(`/api/project?repo=${id}`)).json()) as { use_case: string | null }).use_case ?? "";
};

test("a repo's draft goal is the goal every step uses, kept in this browser, and saved only by Save Goal", async ({ page }) => {
  const puts: string[] = [];
  const ranked: string[] = [];
  const briefs: (string | null)[] = [];
  const generated: { use_case?: string; dry_run?: boolean }[] = [];
  page.on("request", (r) => {
    if (r.method() === "PUT" && r.url().includes("/api/usecase")) puts.push(r.postData() ?? "");
    if (r.url().includes("/api/generate")) generated.push(JSON.parse(r.postData() ?? "{}") as { use_case?: string });
    if (r.url().includes("/api/garage/recommend")) ranked.push((JSON.parse(r.postData() ?? "{}") as { use_case: string }).use_case);
    if (r.url().endsWith("/api/buildspec") || r.url().includes("/api/buildspec?"))
      briefs.push((JSON.parse(r.postData() ?? "{}") as { use_case?: string | null }).use_case ?? null);
  });
  const saved = await savedGoal(page);
  expect(saved).not.toBe("");
  const draft = "A docs Q&A agent that answers questions about the refund docs.";

  await start(page, "repo");
  const box = goalBox(page, TAG);
  await expect(box).toHaveValue(saved);
  await expect(page.getByLabel(`Saved goal for ${TAG}`, { exact: true })).toHaveValue(saved);
  await box.fill(draft);
  // The heading says it's a draft now, not the saved goal.
  await expect(page.getByLabel(`Draft goal for ${TAG} (unsaved)`, { exact: true })).toHaveValue(draft);
  await expect(page.getByLabel(`Saved goal for ${TAG}`, { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: /^Next: Design/ }).click();

  // Design ranks on the draft (once its blueprints are opened); the bar says it isn't saved.
  const bar = page.getByRole("status", { name: "Unsaved goal" });
  await expect(bar).toContainText("Unsaved goal — only in this browser.");
  await page.getByTestId("blueprints").locator("summary").click();
  await expect.poll(() => ranked.at(-1)).toBe(draft);
  await noA11yViolations(page);

  // Measure: Try it's example comes from the draft (a question the docs should answer).
  await toStep(page, 4);
  await expect(bar).toBeVisible();
  const tryBox = page.getByTestId("try-it");
  await expect(tryBox.getByRole("textbox", { name: "Input 1" })).toHaveAttribute("placeholder", /Answer from the docs/);
  // Tasks are written from the draft too: Measure says so quietly, and the estimate sends it.
  await expect(page.getByTestId("generate-goal")).toHaveText("Tasks are written from your unsaved goal.");
  await expect(page.getByText(/Save Goal first/)).toHaveCount(0);
  const gen = page.locator("details", { has: page.getByText("Generate tasks from the repo and docs") });
  if (!(await gen.evaluate((d) => (d as HTMLDetailsElement).open))) await gen.locator("summary").click();
  await gen.getByRole("button", { name: "Preview the Request" }).click();
  await expect(gen.getByText("Ready to Send")).toBeVisible();
  expect(generated.at(-1)).toMatchObject({ dry_run: true, use_case: draft });

  // Ship: BUILD.md's Goal is the draft, sent with the request, not the saved one.
  await toStep(page, 5);
  const md = page.getByLabel("BUILD.md");
  await expect(md).toContainText(draft);
  await expect(md).not.toContainText("No use case written yet");
  await expect(md).not.toContainText(saved);
  expect(briefs.at(-1)).toBe(draft);

  // A reload keeps the draft (this repo only), and still nothing was written to the repo.
  await page.reload();
  await expect(bar).toBeVisible();
  await expect(page.getByLabel("BUILD.md")).toContainText(draft);
  await toStep(page, 1);
  await expect(box).toHaveValue(draft);
  await expect(page.getByText(/^Unsaved draft, only in this browser/)).toBeVisible();
  expect(puts).toEqual([]);
  expect(await savedGoal(page)).toBe(saved);

  // Save Goal (from the bar) is the one thing that writes it; then the bar goes.
  await toStep(page, 2);
  await bar.getByRole("button", { name: "Save Goal" }).click();
  await expect(bar).toHaveCount(0);
  await expect.poll(() => savedGoal(page)).toBe(draft);
  expect(puts).toHaveLength(1);
  // Put the seeded goal back for the tests after this one (Save Goal again).
  await toStep(page, 1);
  await box.fill(saved);
  await page.getByRole("button", { name: "Save Goal" }).click();
  await expect(page.getByRole("button", { name: "Saved" })).toBeVisible();
  await expect.poll(() => savedGoal(page)).toBe(saved);
  // Typed back to the saved goal: no draft, nothing to save.
  await box.fill(`${saved} `);
  await expect(page.getByRole("button", { name: "Save Goal" })).toBeDisabled();
});

test("Design: no recommendation without a goal; a goal naming another stack is warned about", async ({ page }) => {
  await start(page, "repo");
  const box = goalBox(page, TAG);
  await expect(box).not.toHaveValue("");
  await box.fill("");
  await toStep(page, 2);
  const keep = page.getByTestId("keep-card");
  await expect(keep).toContainText(`Keep ${TAG}'s Design`);
  await expect(keep).toContainText("No goal yet, so nothing is recommended.");
  await expect(keep).not.toContainText("Recommended");
  await expect(keep).not.toContainText("how the coding agent works");
  await expect(page.getByTestId("stack-mismatch")).toHaveCount(0);

  // A goal about what the app does, not the coding agent: keeping the design isn't pushed either.
  await toStep(page, 1);
  await box.fill("Answer billing questions in three languages.");
  await toStep(page, 2);
  await expect(keep).not.toContainText("Recommended");
  await expect(keep).toContainText("reads like what the app does");

  // A goal about Java/JUnit on a repo with no Java: said on Design, from the engine's check.
  await toStep(page, 1);
  await box.fill("Write JUnit tests for the Java services and keep the build green.");
  await toStep(page, 2);
  await expect(keep).toContainText("Recommended");
  await expect(page.getByTestId("stack-mismatch")).toHaveText(/^Your goal mentions Java\/JUnit; this repo is .+\. Rig measures the agent/);
  await noA11yViolations(page);
  // Back to the saved goal: no warning.
  await toStep(page, 1);
  await box.fill(await savedGoal(page));
  await toStep(page, 2);
  await expect(page.getByTestId("stack-mismatch")).toHaveCount(0);
});

test("a workflow keeps its design through a model swap, a draft switch and a reload; only Detach drops it", async ({ page }) => {
  await start(page, "lab");
  await page.getByLabel("What you're building").fill("answer questions over our policy docs and a sales database");
  await toStep(page, 2);
  await openBlueprints(page);
  await designCard(page, "Agentic RAG").first().click();
  await page.getByLabel(/\btop_k\b/).fill("7");
  await page.getByRole("button", { name: "Use This Design" }).click();
  const banner = page.locator(".labhost__design");
  await expect(banner).toContainText("Design: Agentic RAG");

  // Swap one step's model: the workflow becomes your own copy, still linked to the design.
  await page.getByRole("button", { name: "Fit everything" }).click();
  await page.locator('.canvas__node[aria-label^="Step "] .block__body').first().click();
  await page.getByLabel("Model", { exact: true }).selectOption("claude-opus-5-5");
  await expect(page.locator(".insp__band")).toHaveText("Your workflow");
  await expect(banner).toContainText("Design: Agentic RAG");

  // Another workflow on the canvas and back from Your drafts: the link comes back with it.
  await page.getByRole("button", { name: "New blank workflow" }).click();
  await expect(banner).toHaveCount(0);
  await page.getByRole("list", { name: "Your Drafts" }).getByRole("button", { name: /^My Agentic RAG/ }).first().click();
  await expect(banner).toContainText("Design: Agentic RAG");

  // A reload: still linked; Ship has the design's parts and the parameter set in step 2.
  await page.reload();
  await expect(banner).toContainText("Design: Agentic RAG");
  await toStep(page, 5);
  const md = page.getByLabel("BUILD.md");
  await expect(md).toContainText("Vector index");
  await expect(md).toContainText("max_iterations");
  await expect(md).toContainText("sources_enabled");
  await expect(md).toContainText("| `top_k` | 7 (changed) | 5 |");

  // Detach: said plainly, and the brief no longer has the design.
  await toStep(page, 3);
  await page.getByRole("button", { name: "Detach from Design" }).click();
  await expect(banner).toHaveText(/^Detached from Agentic RAG: the workflow stays, but BUILD.md no longer has/);
  await toStep(page, 5);
  await expect(page.getByLabel("BUILD.md")).not.toContainText("top_k");
  await page.reload();
  await toStep(page, 3);
  await expect(page.getByText("Design: Agentic RAG")).toHaveCount(0);
});

test("the Lab's Measure opens on the bench choice, then Try it, which shows at once, and its example and price follow the goal", async ({ page }) => {
  // The price is slow on purpose: the box and its example must not wait for it.
  let release: () => void = () => undefined;
  const priced = new Promise<void>((r) => (release = r));
  await page.route("**/api/try/price**", async (route) => {
    await priced;
    await route.continue();
  });
  await start(page, "lab");
  await page.getByLabel("What you're building").fill("A Q&A agent that answers customers' questions about our product docs and manuals.");
  await toStep(page, 4);
  const box = page.getByTestId("try-it");
  await expect(box).toBeVisible();
  const input = box.getByRole("textbox", { name: "Input 1" });
  await expect(input).toHaveAttribute("placeholder", /^How do I rotate an API key without downtime\? Answer from the docs/);
  await expect(page.getByTestId("try-price")).toHaveText("Pricing the try…");
  // The bench choice is at the top, in view without scrolling; Try it comes before the rest of
  // the bench settings.
  const bench = page.getByLabel("Bench", { exact: true });
  await expect(bench).toBeInViewport();
  const tryTop = (await box.boundingBox())!.y;
  expect((await bench.boundingBox())!.y).toBeLessThan(tryTop);
  expect(tryTop).toBeLessThan((await page.getByText("Measure on a test bench").boundingBox())!.y);
  release();

  // The price, said plainly; no "Docker sandbox".
  await expect(page.getByTestId("try-price")).toContainText(/^≈ \$\d+\.\d\d for 1 input/);
  await expect(page.getByTestId("try-price-why")).toContainText(/^Runs your \d+-step workflow once per input, about \$\d+\.\d\d each, priced as a run on (Sonnet|Opus|Haiku) 5\.5, the model its working steps use\./);
  await expect(page.getByTestId("try-price-why")).toContainText("You pay for the model reading the task and the steps' instructions and writing its answer.");
  await expect(box).toContainText("an isolated test copy");
  await expect(box).not.toContainText("Docker");
  await box.getByRole("button", { name: "Use This Example" }).click();
  await expect(input).toHaveValue(/^How do I rotate an API key/);
  await noA11yViolations(page);

  // A support goal with a limit: a customer email that tests it ($500 -> asks for $625).
  await toStep(page, 1);
  await page.getByLabel("What you're building").fill("A support agent that answers tickets from our policy docs and hands refunds over $500 to a person.");
  await toStep(page, 4);
  await input.fill("");
  await expect(input).toHaveAttribute("placeholder", /charged \$625 .+refund/);
});
