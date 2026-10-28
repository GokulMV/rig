import AxeBuilder from "@axe-core/playwright";
import { expect, type Locator, type Page, test } from "@playwright/test";

// The seeded repos are named after their cache folders, which the environment's tag sets (see playwright.config.ts).
declare const process: { env: Record<string, string | undefined> };
const TAG = process.env.PG_E2E_TAG ?? "pg-e2e";


/** Any of the Rig score's bands, as its label reads (engine: rig-score skill). */
const RIG_LABEL = /^(Works — use it|Works, but .+ needs work|Not Proven — .+|Helps, but .+|Doesn't Work — .+)$/;

/** A Rig score card: the plain verdict and why, a number, a band label and five parts, each scored or "not measured". */
async function expectRigCard(card: Locator) {
  await expect(card.getByTestId("rig-verdict")).toHaveText(/^(Helps|Doesn't Help|Can't Tell Yet)$/);
  await expect(card.getByTestId("rig-why")).toHaveText(/\. Next: .+\.$/);
  // The full card lists quality, cost, time and reliability; a compact one (a list row) doesn't.
  if (!(await card.evaluate((el) => el.classList.contains("rig--compact"))))
    await expect(card.getByTestId("rig-facts").locator("li")).toHaveText([/^Quality: /, /^Cost: /, /^Time: /, /^Reliability: /]);
  await expect(card.locator(".rig__value")).toHaveText(/^\d{1,3}$/);
  await expect(card.locator(".rig__label")).toHaveText(RIG_LABEL);
  await expect(card.locator(".rig__part")).toHaveCount(5);
  await expect(card.locator(".rig__name")).toHaveText([/^Lift/, /^Cost/, /^Followed/, /^Holds Up/, /^Reliable/]);
  for (const sc of await card.locator(".rig__score").allTextContents()) expect(sc).toMatch(/^(\d{1,3}|not measured|no credit)$/);
}

async function noA11yViolations(page: Page) {
  // Settle first: a menu caught mid fade-in fails contrast and target size for no real reason.
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity),
  );
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(
    r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target.join(" ")} (${n.failureSummary})`).join(", ")}`),
  ).toEqual([]);
}

/** Pointer drag, the way a person does it: press, move in steps, release. */
async function drag(page: Page, from: Locator, to: { x: number; y: number }) {
  await from.scrollIntoViewIfNeeded();
  const b = (await from.boundingBox())!;

  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 12 });
  await page.mouse.up();
}

const block = (page: Page, label: string) => page.locator(`.canvas__node[aria-label="${label}"]`);

async function center(l: Locator) {
  const b = (await l.boundingBox())!;
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
}

/** Open one kind of the Library from its home, the kinds overview (going back to it first). */
async function libraryKind(palette: Locator, kind: string) {
  const back = palette.getByRole("button", { name: "Library: all kinds" });
  if (await back.isVisible()) await back.click();
  await palette.getByRole("button", { name: new RegExp(`^${kind}`) }).click();
  await expect(palette.getByRole("heading", { level: 2 })).toHaveText(new RegExp(kind));
}

/** Sort the kind on show, from its small Sort menu. */
async function sortBy(palette: Locator, label: string) {
  await palette.getByRole("button", { name: /^Sort:/ }).click();
  await palette.getByRole("menuitemradio", { name: label }).click();
  await expect(palette.getByRole("button", { name: `Sort: ${label}` })).toBeVisible();
}


// Once the guide has been through (or skipped), the steps are tabs with these names.
/** A repo's goal box, whatever its heading says (saved, a draft of it, or a first goal). */
const goalBox = (page: Page, repo: string) =>
  page.getByLabel(new RegExp(`^(Saved goal|Draft goal|Goal) for ${repo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}( \\(unsaved\\))?$`));

const TAB = { 1: "Describe", 2: "Design", 3: "Build", 4: "Measure", 5: "Ship" } as const;

/** Go to a step from the step bar: a numbered step while guided, its tab in the workspace. */
async function toStep(page: Page, n: 1 | 2 | 3 | 4 | 5) {
  await page
    .getByRole("navigation", { name: /^(Steps|Workspace)$/ })
    .getByRole("button", { name: new RegExp(`^(${n}\\. |${TAB[n]}$)`) })
    .click();
}

/** A design's card in step 2, by its name. */
/** A repo's Design folds the catalog behind "Start from a Blueprint Instead": open it (no-op in the Lab). */
async function openBlueprints(page: Page) {
  const prints = page.getByTestId("blueprints");
  await page.waitForTimeout(50);
  if ((await prints.count()) && !(await prints.evaluate((d) => (d as HTMLDetailsElement).open))) await prints.locator("summary").click();
}

const designCard = (page: Page, name: string) =>
  page.locator(".archcard").filter({ has: page.locator(".archcard__name", { hasText: new RegExp(`^${name.replace(/[()]/g, "\\$&")}`) }) });

/** Detach a repo from its chip's ⋯ menu, through the confirm. */
async function detach(page: Page, name: string) {
  await page.getByRole("button", { name: `More for ${name}` }).click();
  await page.getByRole("button", { name: "Detach…" }).click();
  await expect(page.getByText(/Rig stops showing it; nothing in/)).toBeVisible();
  await page.getByRole("button", { name: "Detach", exact: true }).click();
}

/** Open the app on a step: with a repo, or with "lab" starting from nothing (workflows). */
async function open(page: Page, step: 1 | 2 | 3 | 4 | 5, space: "repo" | "lab" = "repo") {
  await page.goto("/");
  await toStep(page, 1);
  await page.getByRole("radio", { name: space === "repo" ? /^My Repo/ : /^Nothing Yet/ }).click();
  if (step > 1) await toStep(page, step);
}

test.describe.configure({ mode: "serial" });

// The repo's goal is about the coding agent, so its architecture starts folded away; the first
// test checks that, and the rest open it, as a person who unfolded it once would have it.
test.beforeEach(async ({ page }, info) => {
  if (info.title.startsWith("no repo: attach one")) return;
  await page.addInitScript((key) => localStorage.setItem(key, "1"), `pg.arch-open:${TAG}`);
});

// The seeded repo's folder, read from the server in the first test.
let ROOT = "";

test("no repo: attach one, then the canvas shows its architecture, setup and workflow", async ({ page }) => {
  await page.goto("/");
  // A first visit lands on Home, with nothing to continue; Describe is one click away.
  await expect(page.getByRole("heading", { level: 1, name: "Swap One Part. Rerun With and Without. See What It Changed." })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Continue:/ })).toHaveCount(0);
  await toStep(page, 1);
  // A first visit chooses nothing: a neutral question, both "Start from" cards, no goal box yet,
  // and Next waits for a choice.
  await expect(page.getByRole("heading", { name: "What Are You Working On?" })).toBeVisible();
  await expect(page.getByRole("radio", { name: /^My Repo — 1 attached/ })).toHaveAttribute("aria-checked", "false");
  await expect(page.getByRole("radio", { name: /^Nothing Yet/ })).toHaveAttribute("aria-checked", "false");
  await expect(page.getByRole("textbox")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Next: Design/ })).toBeDisabled();
  await noA11yViolations(page);
  // Choosing reveals the goal box; the choice is remembered.
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await expect(page.getByRole("heading", { name: "What Are You Building?" })).toBeVisible();
  await expect(page.getByLabel("What you're building")).toHaveValue("");
  await page.reload();
  await expect(page.getByRole("radio", { name: /^Nothing Yet/ })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  // With a repo, it's about the agent.
  await expect(page.getByRole("heading", { name: "What Should Your Agent Get Better At?" })).toBeVisible();
  await expect(page.getByRole("radio", { name: TAG, exact: true })).toBeVisible();
  const [{ root }] = (await (await page.request.get("/api/repos")).json()) as { root: string }[];
  ROOT = root;
  // Each chip shows its folder, so two repos of one name can be told apart.
  await expect(page.getByRole("radio", { name: TAG, exact: true })).toContainText(`/${TAG}`);
  await detach(page, TAG);

  await expect(page.getByLabel("Folder of the repo on this machine")).toBeVisible();
  await noA11yViolations(page);
  await page.getByLabel("Folder of the repo on this machine").fill(ROOT);
  await page.getByRole("button", { name: "Attach" }).click();
  await expect(page.getByRole("radio", { name: TAG, exact: true })).toBeChecked();
  await goalBox(page, TAG).fill("Fix refund bugs without breaking the plan limits.");
  // The same as the repo's saved goal: nothing to save, and no unsaved-goal bar later.
  await expect(page.getByRole("button", { name: "Save Goal" })).toBeDisabled();
  await page.getByRole("button", { name: /^Next: Design/ }).click();
  await expect(page.getByRole("heading", { name: /^(Choose a Design|Keep .+'s Design, or Start from Another)$/ })).toBeVisible();
  await expect(page.getByRole("status", { name: "Unsaved goal" })).toHaveCount(0);
  await page.getByRole("button", { name: /^Next: Build/ }).click();

  // The agent's setup leads; the goal is about the agent, so the app's architecture is folded.
  const archToggle = page.getByRole("button", { name: /^Architecture of .+ · \d+ parts?/ });
  await expect(archToggle).toHaveAttribute("aria-expanded", "false");
  await expect(block(page, "Frontend web")).toHaveCount(0);
  const setupLane = page.locator(".lane", { hasText: "Agent setup" });
  expect((await setupLane.boundingBox())!.y).toBeLessThan((await archToggle.boundingBox())!.y);
  await expect(block(page, "Agent setup Hooks")).toContainText("none yet");
  await expect(block(page, "Agent setup Test command")).toBeVisible();
  await archToggle.click();
  await expect(archToggle).toHaveAttribute("aria-expanded", "true");
  // Read from the code: compose services become blocks of the right kind.
  for (const label of ["Frontend web", "Backend api", "Backend worker", "Message bus queue", "Data store db", "Data store cache"]) {
    await expect(block(page, label)).toBeVisible();
  }
  await expect(page.getByText(/Architecture of .+ · read from the code/)).toBeVisible();
  await expect(block(page, "Agent setup CLAUDE.md")).toBeVisible();
  // Measured: its last run, in the words Measure shows it (Rig score and verdict), not an estimate.
  await expect(block(page, "Skill in repo refund-policy")).toContainText(/Rig \d+ · (Helps|Doesn't Help|Can't Tell Yet)/);
  await expect(block(page, "Step 3: verify")).toBeVisible();
  // Edges flow: each one carries a moving dot.
  expect(await page.locator(".canvas__dot").count()).toBeGreaterThan(4);
  await noA11yViolations(page);

  // Selecting a block explains it on the right.
  await block(page, "Message bus queue").locator(".block__body").click();
  await expect(page.getByRole("heading", { name: "queue" })).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.locator(".insp__title")).not.toHaveText("queue");
});

test("more repos: add a second one and switch between them", async ({ page }) => {
  await open(page, 1);
  await page.getByText("Add Another Repo").click();
  await page.getByLabel("Folder of the repo on this machine").fill(`${ROOT}-blog`);
  await page.getByRole("button", { name: "Attach" }).click();
  await expect(page.getByRole("radio", { name: `${TAG}-blog`, exact: true })).toBeChecked();
  // The same folder by another spelling is the same repo: still one chip.
  await page.getByLabel("Folder of the repo on this machine").fill(`${ROOT}-blog/`);
  await page.getByRole("button", { name: "Attach" }).click();
  await expect(page.getByRole("radio", { name: `${TAG}-blog`, exact: true })).toHaveCount(1);
  await page.getByRole("radio", { name: TAG, exact: true }).click();
  await toStep(page, 3);
  await expect(block(page, "Backend api")).toBeVisible();
});

test("remote repo: clone by owner/name, show its GitHub mark, pull it, detach it", async ({ page }) => {
  await open(page, 1);
  await page.getByText("Add Another Repo").click();
  await page.getByRole("radio", { name: "From GitHub or GitLab" }).click();
  await expect(page.getByLabel("GitHub token (only needed for private repos)")).toBeVisible();
  await noA11yViolations(page);
  await page.getByLabel("Repo address or owner/name").fill("octo/widgets");
  await page.getByRole("button", { name: "Clone" }).click();
  const chip = page.getByRole("radio", { name: "widgets", exact: true });
  await expect(chip).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Pull widgets" }).click();
  await expect(page.getByText("Pulled widgets: now at abc1234.")).toBeVisible();
  // Detach asks first: Cancel keeps it.
  await page.getByRole("button", { name: "More for widgets" }).click();
  await page.getByRole("button", { name: "Detach…" }).click();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(chip).toBeVisible();
  await noA11yViolations(page);
  await detach(page, "widgets");
  await expect(chip).toHaveCount(0);
});

test("library: drag skills onto the canvas, see an estimate, wire them to any block", async ({ page }) => {
  await open(page, 3);
  await page.evaluate(() => Object.keys(localStorage).forEach((k) => k.startsWith("pg.canvas") && localStorage.removeItem(k)));
  await page.reload();
  const palette = page.getByRole("region", { name: "Library" });
  const surface = page.locator(".canvas__surface");
  await expect(block(page, "Step 2: fix")).toBeVisible();
  await libraryKind(palette, "Skills");

  // Onto a step: a new card beside it, linked to it, with an estimate at once.
  await drag(page, palette.locator(".pal-item__main", { hasText: "tdd" }), await center(block(page, "Step 2: fix")));
  const tdd = block(page, "Skill tdd");
  await expect(tdd).toBeVisible();
  // The rough estimate: a model is asked only from "Sharpen with the model".
  await expect(tdd.locator(".est")).toHaveText(/^Rough [+-]?\d+ pts$/);
  await expect(page.locator(".estbox")).toContainText(/a run makes it conclusive/i);
  await expect(page.getByRole("button", { name: "Remove the link to fix" })).toBeVisible();
  const [fix, card] = [(await block(page, "Step 2: fix").boundingBox())!, (await tdd.boundingBox())!];
  expect(card.y >= fix.y + fix.height || card.y + card.height <= fix.y || card.x >= fix.x + fix.width || card.x + card.width <= fix.x).toBe(true);

  // Into open space: a free card.
  const sb = (await surface.boundingBox())!;
  await drag(page, palette.locator(".pal-item__main", { hasText: "careful-review" }), { x: sb.x + sb.width - 160, y: sb.y + 400 });
  const review = block(page, "Skill careful-review");
  await expect(review).toBeVisible();
  await expect(page.getByText("None of yours yet.")).toBeVisible();

  // Handles: out of careful-review into two different blocks: many outputs.
  await review.hover();
  await drag(page, review.locator(".handle--out"), await center(block(page, "Step 3: verify")));
  await review.hover();
  await drag(page, review.locator(".handle--out"), await center(block(page, "Backend api")));
  await review.locator(".block__body").click();
  await expect(page.getByRole("button", { name: "Remove the link to verify" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove the link to api" })).toBeVisible();

  // And any block to any block, dragging from the in-handle too: worker <- db.
  const worker = block(page, "Backend worker");
  await worker.hover();
  await drag(page, worker.locator(".handle--in"), await center(block(page, "Data store db")));
  await worker.locator(".block__body").click();
  await expect(page.getByRole("button", { name: "Remove the link from db" })).toBeVisible();

  // Kept across reloads.
  await page.reload();
  await expect(block(page, "Skill careful-review")).toBeVisible();
  await expect(page.locator(".layer")).toContainText("2 changes on the canvas");
  await noA11yViolations(page);

  // Unwire from the panel.
  await block(page, "Skill careful-review").locator(".block__body").click();
  await page.getByRole("button", { name: "Remove the link to api" }).click();
  await expect(page.getByRole("button", { name: "Remove the link to api" })).toHaveCount(0);
});

test("GitHub catalog: sort, add a repo, pick one of its skills to install", async ({ page }) => {
  await open(page, 3);
  const palette = page.getByRole("region", { name: "Library" });
  await libraryKind(palette, "Skills");
  await expect(palette.getByText("refund-skills", { exact: true })).toBeVisible({ timeout: 20_000 });
  await sortBy(palette, "Most Starred");
  // The sort changes what comes first: a top list in that order.
  await expect(palette.locator(".pal-top__title")).toHaveText("Most starred");
  const starsShown = await palette.locator(".pal-top .pal-item__meta .num").allInnerTexts();
  const n = starsShown.map((t) => parseFloat(t) * (t.includes("k") ? 1000 : 1));
  expect(n).toEqual([...n].sort((a, b) => b - a));
  await palette.getByRole("button", { name: "Add refund-skills to the canvas" }).click();
  const card = block(page, "GitHub repo refund-skills");
  await expect(card).toBeVisible();
  await page.getByRole("button", { name: "Use This" }).first().click();
  await expect(block(page, "Skill escalation")).toBeVisible();
  await expect(palette.getByText("Installed from GitHub")).toBeVisible();

  // Clicking an item explains it in detail, README included.
  await palette.getByRole("button", { name: /^refund-skills/ }).first().click();
  await expect(page.locator(".insp__band")).toHaveText("From GitHub · Skill");
  await expect(page.getByRole("region", { name: "README" }).or(page.getByLabel("README"))).toContainText("Skills for refund desks.");
  await expect(page.getByLabel("README")).not.toContainText("img.shields.io");
  // The Add above brought its card into view at the canvas's left; fit it all back first, so
  // the zoom buttons don't sit on a block's own button.
  await page.getByRole("button", { name: "Fit everything" }).click();
  await noA11yViolations(page);

  // More kinds than skills, each a tile on the Library's home.
  for (const kind of ["Agents & Subagents", "MCP Servers", "Hooks & Commands", "Eval Suites"]) await libraryKind(palette, kind);
  await libraryKind(palette, "Workflows");
  await expect(palette.getByText("spec-first", { exact: true })).toBeVisible();
});

test("library home: kinds to drill into and back, search across kinds, / and Esc", async ({ page }) => {
  await open(page, 3);
  const palette = page.getByRole("region", { name: "Library" });
  const kinds = palette.getByRole("list", { name: "Kinds" });
  // The home is the kinds, each with its count and a plain line on what it's for; no Sort here.
  await expect(kinds.getByRole("button", { name: /^Harness Techniques, 1$/ })).toBeVisible({ timeout: 20_000 });
  await expect(kinds.getByRole("button")).toHaveText([/^Skills/, /^Agents & Subagents/, /^MCP Servers/, /^Hooks & Commands/, /^Harness Techniques/, /^Workflows/, /^Eval Suites/]);
  await expect(kinds.getByRole("button", { name: /^Skills, \d+$/ })).toBeVisible();
  await expect(kinds.getByRole("button", { name: "Agents & Subagents, 0" })).toBeVisible();
  await expect(kinds.getByRole("button", { name: /^MCP Servers/ })).toHaveAccessibleDescription(/^Gives your agent a new tool/);
  await expect(palette.getByRole("button", { name: /^Sort:/ })).toHaveCount(0);
  await noA11yViolations(page);

  // Into a kind: a back button, its title (focused), its list, and a small Sort menu.
  await kinds.getByRole("button", { name: /^Harness Techniques/ }).click();
  await expect(palette.getByRole("heading", { level: 2 })).toHaveText("Harness Techniques");
  await expect(palette.getByRole("heading", { level: 2 })).toBeFocused();
  await expect(palette.getByText("ralph", { exact: true })).toBeVisible();
  const sort = palette.getByRole("button", { name: "Sort: Recommended" });
  await sort.press("Enter");
  await expect(palette.getByRole("menuitemradio", { name: "Recommended" })).toBeFocused();
  await noA11yViolations(page);
  await page.keyboard.press("ArrowDown");
  await expect(palette.getByRole("menuitemradio", { name: "Most Starred" })).toBeFocused();
  await page.keyboard.press("Escape"); // closes the menu only
  await expect(palette.getByRole("menu")).toHaveCount(0);
  await expect(palette.getByRole("heading", { level: 2 })).toHaveText("Harness Techniques");
  await sort.click();
  await palette.getByRole("menuitemradio", { name: "Most Starred" }).click();
  await expect(palette.getByRole("button", { name: "Sort: Most Starred" })).toBeFocused();

  // Back with the button: the tile you came from has the focus.
  await palette.getByRole("button", { name: "Library: all kinds" }).click();
  await expect(kinds.getByRole("button", { name: /^Harness Techniques/ })).toBeFocused();
  // Back with Esc.
  await kinds.getByRole("button", { name: /^Workflows/ }).click();
  await expect(palette.getByText("spec-first", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(kinds.getByRole("button", { name: /^Workflows/ })).toBeFocused();

  // "/" puts the cursor in the search; from the home it searches every kind, grouped by kind.
  await page.keyboard.press("/");
  const search = palette.getByRole("searchbox", { name: "Search the library" });
  await expect(search).toBeFocused();
  await page.keyboard.type("agent");
  await expect(palette.getByRole("region", { name: "Matches in Skills" })).toContainText("refund-skills");
  await expect(palette.getByRole("region", { name: "Matches in Harness Techniques" })).toContainText("ralph");
  await expect(palette.getByRole("region", { name: "Matches in Workflows" })).toContainText("spec-first");
  await expect(kinds).toHaveCount(0);
  await noA11yViolations(page);
  // Words, not a substring: every word must match, in any order and any field.
  await search.fill("harness agent");
  await expect(palette.getByRole("region", { name: /^Matches in/ })).toHaveCount(1);
  await expect(palette.getByRole("region", { name: "Matches in Harness Techniques" })).toContainText("ralph");
  await search.fill("nothing-like-this");
  await expect(palette.getByText("Nothing matches “nothing-like-this” in any kind.")).toBeVisible();
  // Esc on the home clears the search and shows the kinds again.
  await search.press("Escape");
  await expect(search).toHaveValue("");
  await expect(kinds.getByRole("button")).toHaveCount(7);

  // Within a kind, the search is that kind's only.
  await kinds.getByRole("button", { name: /^Skills/ }).click();
  await expect(palette.getByRole("searchbox", { name: "Search Skills" })).toBeVisible();
  await palette.getByRole("searchbox", { name: "Search Skills" }).fill("refund");
  await expect(palette.locator(".pal-top__title")).toHaveText("Best matches");
  await expect(palette.locator(".pal-top .pal-item__name")).toHaveText(["refund-skills"]);
});

test("scenarios: add your own; agent: pick one and sign in", async ({ page }) => {
  await open(page, 4);
  await page.getByRole("button", { name: "+ Add Task" }).click();
  await page.getByLabel("What should the agent do?").fill("Refund in yen");
  await page.getByLabel("Instruction the agent gets").fill("A customer asks for a refund in yen.");
  await page.getByLabel("Check: a shell command").fill("pytest -q");
  await page.getByRole("button", { name: "Add Task", exact: true }).click();
  await expect(page.getByText("Refund in yen")).toBeVisible();

  // A generated check can be proven for free: run with no agent, it should fail.
  await page.getByRole("button", { name: /The limits file is gone/ }).click();
  await page.getByRole("button", { name: "Prove Check", exact: true }).click();
  await expect(page.getByText("Fails Untouched (Proven)")).toBeVisible({ timeout: 30_000 });

  // Generating from the repo and its docs: what was found, the sources, a free preview.
  await page.getByText("Generate tasks from the repo and docs").click();
  // The goal is Describe's, shown here read only: one place to write it.
  await expect(page.getByTestId("generate-goal-copy")).toContainText("Fix refund bugs without breaking the plan limits.");
  await expect(page.getByRole("region", { name: "Add sources" })).toBeVisible();
  // The page itself never scrolls: long panels scroll inside their pane.
  expect(await page.evaluate(() => document.documentElement.scrollHeight - innerHeight)).toBeLessThanOrEqual(0);
  await page.getByLabel("Typical").fill("2");
  await page.getByRole("button", { name: "Preview the Request" }).click();
  await expect(page.getByRole("heading", { name: "Ready to Send" })).toBeVisible();
  await noA11yViolations(page);

  // The agent is chosen from the pill at the top, on any step.
  await page.locator(".agent-pill").click();
  await expect(page.getByRole("dialog", { name: "Agent" })).toBeVisible();
  await page.getByRole("radio", { name: /Codex/ }).click();
  await expect(page.getByRole("radio", { name: /Codex/ })).toContainText("Not signed in");
  // One-click sign-in runs the agent's own CLI; here it isn't installed, and says how to get it.
  await page.getByRole("button", { name: "Sign In with ChatGPT" }).click();
  await expect(page.getByText(/npm install -g @openai\/codex@0\.162\.1/)).toBeVisible();
  // Or a key, kept in memory only.
  await page.getByText("Use an API Key Instead").click();
  await page.locator("#cred-value").fill("sk-test-not-a-real-key");
  await page.getByRole("button", { name: "Use This Key" }).click();
  await expect(page.locator(".agent-pill")).toContainText("Codex · signed in");
  await expect(page.getByText("Codex is ready to run")).toBeVisible();
  await noA11yViolations(page);
  await page.getByRole("button", { name: "Sign Out" }).click();
  await expect(page.locator(".agent-pill")).toContainText("Codex · sign in");
  await page.getByRole("radio", { name: /Claude Code/ }).click();
  await expect(page.locator(".agent-pill")).toContainText("Claude Code · signed in");
});

test("run: a full run on the repo grows to the pairs the sizing names when its budget is set", async ({ page }) => {
  await open(page, 3);
  await libraryKind(page.getByRole("region", { name: "Library" }), "Skills");
  await page.getByRole("button", { name: "Add tdd to the canvas" }).click();
  await page.getByRole("button", { name: "Confirm with a run" }).click();
  await page.getByRole("radio", { name: /^Full/ }).click();
  await page.getByLabel("Stop at (USD)").fill("1");
  const full = page.getByTestId("run-size-full");
  await expect(full).not.toContainText("conclusive");
  await expect(page.getByTestId("run-sizing")).toContainText("To tell a ±25 pts change from noise you need about 31 pairs");
  await page.getByRole("button", { name: /^Set Budget to \$/ }).click();
  await expect(full).toHaveText(/^Full · \d+ pairs · conclusive to ±\d+ pts$/);
  await expect(page.getByTestId("run-sizing")).toHaveCount(0);
  // The run it starts plans at least those 31 pairs: the engine's count, in whole repeats.
  const said = (await page.getByText(/ runnable tasks? · \d+ trials$/).textContent()) ?? "";
  const [, tasks, trials] = said.match(/^(\d+) runnable tasks? · (\d+) trials$/) ?? [];
  expect(Number(trials) / 2).toBeGreaterThanOrEqual(31);
  expect((Number(trials) / 2) % Number(tasks)).toBe(0);
  await page.getByRole("button", { name: "Review the Run" }).click();
  await expect(page.getByText(new RegExp(`^${trials} trials: `))).toBeVisible();
});

test("run: confirm an estimate with a real (faked) run", async ({ page }) => {
  await open(page, 3);
  // Each test has its own browser storage: add the skill here (the click path, not a drag).
  await libraryKind(page.getByRole("region", { name: "Library" }), "Skills");
  await page.getByRole("button", { name: "Add tdd to the canvas" }).click();
  await expect(block(page, "Skill tdd").locator(".est")).toHaveText(/pts/);
  await page.getByRole("button", { name: "Confirm with a run" }).click();
  await expect(page.getByLabel("Change to measure")).toHaveValue(/tdd/);
  await page.getByRole("button", { name: "Review the Run" }).click();
  // Claude Code stops itself mid-trial, so the confirm can promise a cap (engine: trial-budget).
  await expect(page.getByText(/^Capped at \$\d+\.\d\d: a pair starts only if its predicted cost fits, and Claude Code stops itself mid-trial/)).toBeVisible();
  await page.getByRole("button", { name: /^Start, up to/ }).click();
  await expect(page.getByRole("progressbar", { name: "Trials done" })).toBeVisible();
  // The finished run leads with its Rig score; the earlier-runs list carries the small form.
  const rig = page.getByRole("region", { name: "Rig Score" });
  await expect(rig.locator(".rig__value")).toHaveText(/^\d{1,3}$/, { timeout: 30_000 });
  // The card is the verdict: no second headline repeats its label.
  await expect(page.locator(".verdict__word")).toHaveCount(0);
  await expectRigCard(rig);
  await expect(rig.locator(".rig__kicker")).toHaveText(/^Rig Score( · provisional: \d+ pairs?)?$/);
  await expect(page.getByTestId("rig-badge").first()).toHaveText(/^Rig \d{1,3}/);
  // A (?) explains a measurement word in plain words, from the glossary skill; Esc closes it.
  const what = page.getByRole("button", { name: "What is pts (pass-rate points)?" }).first();
  await what.click();
  await expect(page.getByRole("tooltip")).toContainText("Percentage points of tasks passed");
  await noA11yViolations(page);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await noA11yViolations(page);
});

test("Map with Archify: confirm, the agent maps the repo, the canvas redraws", async ({ page }) => {
  await open(page, 3);
  await expect(page.getByText(/Architecture of .+ · read from the code/)).toBeVisible();
  await page.getByRole("button", { name: "Map with Archify" }).click();
  await expect(page.getByText("read-only tools (no shell, no edits, no web)", { exact: false })).toBeVisible();
  await noA11yViolations(page);
  await page.getByRole("button", { name: "Map It" }).click();
  await expect(page.getByText("Mapping with Archify", { exact: true })).toBeVisible();
  await expect(page.getByText("usually 1–3 min", { exact: false })).toBeVisible();
  await expect(block(page, "Edge / proxy Gateway")).toBeVisible({ timeout: 15_000 });
  await expect(block(page, "Backend Refund API")).toBeVisible();
  await expect(page.getByText(/Architecture of .+ · mapped with Archify/)).toBeVisible();
  const again = page.getByRole("button", { name: /^Map Again/ });
  await expect(again).toBeVisible();
  // Checked against the code, with a score on the button; a part with no evidence is flagged.
  await expect(again).toContainText(/\d+\/9 found/);
  await expect(again).toHaveAttribute("title", /Checked against the code: \d+ of 9 parts found/);
  await expect(page.getByText(/checked: \d+ of 9 found in the code/)).toBeVisible();
  // What flows on each line is explained with the block.
  // Nine parts don't fit at 70%: "Fit everything" brings the store on the right into view.
  await page.getByRole("button", { name: "Fit everything" }).click();
  await block(page, "Database Ledger").or(block(page, "Data store Ledger")).locator(".block__body").click();
  await expect(page.getByText("← Refund worker")).toBeVisible();
  await expect(page.locator(".insp")).toContainText("SQL");
});

test("real roles, flows and planned links; suggested architecture with why and what", async ({ page }) => {
  await open(page, 3);
  // The mapped spec (from the test above): roles, not just "Frontend/Backend".
  await expect(block(page, "Backend Refund worker")).toContainText("Job worker");
  // A planned link is a short tag; what's planned is its title.
  await expect(page.locator('.canvas__label--planned[title*="nightly export"]')).toBeVisible();

  // A flow, step by step.
  await page.getByLabel("Show a flow").selectOption("Refund a ticket");
  await expect(page.locator(".flowcard li")).toHaveCount(6);
  await expect(page.locator(".flowcard")).toContainText("writes the refund to the ledger");
  await expect(page.locator(".canvas__step")).toHaveCount(6);
  await noA11yViolations(page);
  await page.locator(".flowcard").getByRole("button", { name: "Close" }).click();

  // Suggestions: each says why, what it does and what it improves.
  await page.getByRole("tab", { name: "Suggestions" }).click();
  const hot = page.locator(".prop", { hasText: "Move model calls off the request path" });
  await expect(hot).toBeVisible();
  await expect(hot).toContainText("Refund API answers requests and calls Anthropic API itself");
  await expect(page.locator(".prop", { hasText: "Build the link from Ledger to Audit export" })).toBeVisible();
  await hot.getByRole("button", { name: "Why, What It Does, and the Evidence" }).click();
  await expect(hot).toContainText("What it does");
  await expect(hot).toContainText("Speed:");

  // Preview draws it; accepting keeps it in the proposed architecture, exportable as Archify.
  await hot.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("radio", { name: /^With Accepted/ })).toHaveAttribute("aria-checked", "true");
  // A preview, not yet accepted: its parts say so.
  await expect(page.locator(".block__flag--new").first()).toHaveText("Preview");
  await expect(page.locator('.canvas__node[aria-label*="Model worker"]')).toBeVisible();
  await hot.getByRole("button", { name: "Accept" }).click();
  await expect(page.locator(".prop--accepted", { hasText: "Move model calls off the request path" })).toBeVisible();
  await page.getByRole("button", { name: "Export as an Archify Spec" }).click();
  await expect(page.getByLabel("Proposed architecture, Archify JSON")).toHaveValue(/"diagram_type": "architecture"/);
  await expect(page.getByLabel("Proposed architecture, Archify JSON")).toHaveValue(/Model worker/);
  // Check from the list's resting position: axe counts a card half-scrolled under the sticky tabs
  // as an obscured target, which any scrolled list with a sticky header shows mid-scroll.
  await page.locator('section.pane[aria-label="Details"]').evaluate((el) => el.scrollTo(0, 0));
  await noA11yViolations(page);
  // The legend says what changes; the As it is view says how many are waiting.
  await expect(page.locator(".difflegend")).toContainText(/accepted( suggestions? applied| · \d+ drawn here)/);
  await expect(page.locator(".difflegend")).toContainText(/New \d+ parts?/);
  if (process.env.PG_SHOT) await page.screenshot({ path: process.env.PG_SHOT });
  await page.getByRole("radio", { name: "As It Is" }).click();
  await expect(page.locator('.canvas__node[aria-label*="Model worker"]')).toHaveCount(0);
  // Counted as accepted suggestions (only those are drawn); what the brief gets, and the open ones, in its title.
  await expect(page.getByRole("radio", { name: /^With Accepted · \d+$/ })).toBeVisible();
  await expect(page.getByTestId("suggested-count")).toHaveAttribute("title", /not drawn until accepted|from accepted suggestions/);
});

test("Add puts an item next to what it serves; picked for this repo; create a skill", async ({ page }) => {
  await open(page, 3);
  await page.evaluate(() => Object.keys(localStorage).forEach((k) => k.startsWith("pg.canvas") && localStorage.removeItem(k)));
  await page.reload();
  // Add places beside a block on the canvas: wait for the canvas to be drawn before adding.
  await expect(block(page, "Frontend Support desk")).toBeVisible();
  const palette = page.getByRole("region", { name: "Library" });
  await libraryKind(palette, "Skills");
  await expect(palette.getByText("refund-skills", { exact: true })).toBeVisible({ timeout: 20_000 });
  await palette.getByRole("button", { name: "Add refund-skills to the canvas" }).click();
  const card = block(page, "GitHub repo refund-skills");
  await expect(card).toBeVisible();
  await expect(page.locator(".insp")).toContainText("Why it's here");
  await expect(page.locator(".insp")).toContainText(/Applies to Support desk: because the \w[\w ]* mentions /);

  // Picked from what the repo needs, each pick naming the need.
  await sortBy(palette, "Picked for This Repo");
  await expect(palette.getByText("What this repo needs")).toBeVisible();
  // Rough picks first; the model picks only when asked.
  await palette.getByRole("button", { name: /^Ask the model to pick/ }).click();
  await expect(palette.getByText("Picked by the cheapest model from the repo's needs.")).toBeVisible();
  await expect(palette.locator(".need-tag").first()).toContainText("for:");
  await palette.getByRole("button", { name: /^refund-limits-here/ }).click();
  await expect(page.locator(".insp__band")).toHaveText("A new skill for this repo");
  await page.getByRole("button", { name: "Write a Draft" }).click();
  await expect(page.getByLabel("Draft SKILL.md")).toHaveValue(/Refund limits/);
  await noA11yViolations(page);
  await page.getByRole("button", { name: "Save to My Library" }).click();
  await expect(page.getByText(/Saved to your library as refund-limits-here/)).toBeVisible();
  await sortBy(palette, "Recommended");
  await expect(palette.locator(".pal-group__title", { hasText: "Created here" })).toBeVisible();
  await expect(palette.getByRole("button", { name: /^refund-limits-here created here/ })).toBeVisible();
});

test("Add: a Go skill on a Python repo goes with the agent setup and says so; a testing skill goes where the tests run", async ({ page }) => {
  await open(page, 3);
  await page.evaluate(() => Object.keys(localStorage).forEach((k) => k.startsWith("pg.canvas") && localStorage.removeItem(k)));
  await page.reload();
  await expect(block(page, "Frontend Support desk")).toBeVisible();
  const palette = page.getByRole("region", { name: "Library" });
  await libraryKind(palette, "Skills");
  // Still in the library, last in its group, and saying it isn't for this repo.
  const mine = palette.locator(".pal-group").filter({ has: page.locator(".pal-group__title", { hasText: "Your skills" }) });
  await expect(mine.locator(".pal-item").last()).toContainText("go-naming");
  await expect(mine.locator(".pal-item").last().getByTestId("fit-note")).toHaveText("For Go; this repo has none.");
  await expect(mine.getByTestId("fit-note")).toHaveCount(1);

  const links = page.locator(".canvas__label", { hasText: "applies to" });
  await palette.getByRole("button", { name: "Add go-naming to the canvas" }).click();
  const go = block(page, "Skill go-naming");
  await expect(go.locator(".block__sub")).toHaveText("Applies to the whole repo: because it is about conventions & style, so it goes with CLAUDE.md.");
  await expect(go.locator(".block__flag")).toHaveText("For Go; this repo has none.");
  await expect(links).toHaveCount(1);
  await expect(page.locator(".insp")).toContainText("To CLAUDE.md");
  // Beside the agent setup it goes with, not in among other cards.
  const [g, md] = [await go.boundingBox(), await block(page, "Agent setup CLAUDE.md").boundingBox()];
  expect(Math.abs(g!.x - md!.x) + Math.abs(g!.y - md!.y)).toBeLessThan(400);

  await palette.getByRole("button", { name: "Add tdd to the canvas" }).click();
  const tdd = block(page, "Skill tdd");
  await expect(tdd.locator(".block__sub")).toHaveText(/^Applies to (Test command|verify): because /);
  await expect(tdd.locator(".block__flag")).toHaveCount(0);
  await expect(links).toHaveCount(2);
});

test("side panels resize by drag or keys, and remember it", async ({ page }) => {
  await open(page, 3);
  const lib = page.getByRole("separator", { name: "Library width" });
  await lib.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Shift+ArrowRight");
  await expect(lib).toHaveAttribute("aria-valuenow", "350");
  const box = (await lib.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 200);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 60, box.y + 200, { steps: 6 });
  await page.mouse.up();
  await expect(lib).toHaveAttribute("aria-valuenow", "410");
  await page.reload();
  await expect(page.getByRole("separator", { name: "Library width" })).toHaveAttribute("aria-valuenow", "410");
  const w = await page.getByRole("region", { name: "Library" }).evaluate((e) => e.getBoundingClientRect().width);
  expect(Math.round(w)).toBe(410);
  await page.getByRole("separator", { name: "Details panel width" }).dblclick();
  await expect(page.getByRole("separator", { name: "Details panel width" })).toHaveAttribute("aria-valuenow", "360");
});

test("Workflow Lab: starters by discipline, random workflows, edit, compare, save, no repo needed", async ({ page }) => {
  await open(page, 3, "lab");
  const list = page.getByRole("region", { name: "Workflows" });
  for (const d of ["Development", "QA", "Product management", "Design", "Data", "DevOps / SRE", "Security"]) {
    await expect(list.locator(".pal-group__title", { hasText: d }).first()).toBeVisible();
  }
  await expect(list.locator(".pal-group__title", { hasText: "Multi-agent" })).toBeVisible();
  await expect(list.locator(".pal-group__title", { hasText: "Best expected result" })).toBeVisible();
  await noA11yViolations(page);

  // RAG architectures are workflows too, measured on the document Q&A bench.
  await list.locator(".pal-group").filter({ has: page.locator(".pal-group__title", { hasText: "RAG architectures" }) }).locator("summary").click();
  await list.getByRole("button", { name: /^Corrective RAG/ }).last().click();
  await expect(page.locator(".insp__band")).toHaveText("RAG architecture");

  // A business process: parallel screening that the risk rating waits for, with its source.
  await list.locator(".pal-group").filter({ has: page.locator(".pal-group__title", { hasText: "Real procedures" }) }).locator("summary").click();
  await list.getByRole("button", { name: /^KYC onboarding/ }).last().click();
  await expect(page.locator(".insp__band")).toHaveText("Business process");
  await page.getByRole("button", { name: "Fit everything" }).click();
  await expect(page.locator(".canvas__node", { hasText: "Sanctions screening" })).toBeVisible();
  await expect(page.locator(".canvas__node", { hasText: "PEP screening" })).toBeVisible();
  await expect(page.getByText(/Modelled on: KYC\/AML onboarding/)).toBeVisible();

  // Skills come preloaded from GitHub as well as your own, each marked with where it's from.
  await expect(list.getByText(/Built from the discipline's steps, \d+ skills \(\d+ from GitHub, \d+ yours\) and \d+ models\./)).toBeVisible({
    timeout: 15_000,
  });
  await list.locator(".pal-group").filter({ has: page.locator(".pal-group__title", { hasText: /^Development$/ }) }).locator("summary").click();
  await list.getByRole("button", { name: /^Fix a bug/ }).last().click();
  await page.getByRole("button", { name: "Fit everything" }).click();
  await expect(page.locator('.canvas__node[aria-label="Step 2: Write a failing test"]')).toBeVisible();
  await page.locator('.canvas__node[aria-label="Step 2: Write a failing test"] .block__body').click();
  // A searchable picker, grouped by where each skill is from.
  await page.getByRole("combobox", { name: "Add a skill" }).click();
  await expect(page.getByRole("group", { name: "GitHub · obra/superpowers" }).getByRole("option")).toHaveText([/^test-driven-development/]);
  // Type to filter; down and Enter choose.
  const pick = page.getByRole("combobox", { name: "Add a skill" });
  await pick.fill("driven");
  await expect(page.getByRole("listbox", { name: "Skills" }).getByRole("option").first()).toHaveText(/^test-driven-development/);
  await noA11yViolations(page);
  await pick.press("Enter");
  await expect(page.getByRole("link", { name: "View test-driven-development on GitHub (obra/superpowers)" })).toHaveAttribute(
    "href",
    "https://github.com/obra/superpowers/tree/HEAD/skills/test-driven-development",
  );
  await expect(page.getByRole("button", { name: "Remove tdd from this step" })).toBeVisible();
  await expect(page.locator(".labskills li", { hasText: "tdd" })).toContainText("yours");
  // Each skill the Lab attached says why: the step's words it matched.
  await expect(page.locator(".labskills li", { hasText: "tdd" }).locator(".labskills__why")).toHaveText(/^matched: failing test/);
  await page.getByRole("button", { name: "Fit everything" }).click();
  await expect(page.locator('.canvas__node[aria-label="Step 4: Run the tests"] .labloop')).toHaveText("↺ back to Implement until it passes, at most 3×");
  await expect(page.locator('.canvas__node[aria-label="Step 5: Review the diff"]')).toContainText("Opus 5.5");

  await page.locator('.canvas__node[aria-label="Step 5: Review the diff"] .block__body').click();
  const before = await page.locator(".labnums b").nth(1).innerText();
  await page.getByLabel("Model", { exact: true }).selectOption("claude-haiku-5-5");
  await expect(page.locator(".labnums b").nth(1)).not.toHaveText(before);
  await expect(page.locator(".insp__band")).toHaveText("Your workflow");
  await page.getByRole("button", { name: "Compare" }).click();

  await page.getByLabel("Discipline", { exact: true }).selectOption("qa");
  await page.getByRole("button", { name: "Random" }).click();
  await expect(page.locator(".insp__band")).toHaveText("Random workflow");
  await expect(page.locator(".insp__subtitle")).toContainText("QA");
  await page.getByRole("button", { name: "Compare" }).click();
  await expect(page.getByRole("region", { name: "Compared workflows" }).locator("li")).toHaveCount(2);

  await page.getByRole("button", { name: "Save to My Library" }).click();
  await expect(page.getByText(/Saved as a runnable skill/)).toBeVisible();

  // Measure it on a built-in bench: with against without, live, then on the board.
  await toStep(page, 4);
  await page.getByLabel("Bench").selectOption("qa");
  await expect(page.getByRole("button", { name: /Rig & Measure · 4 trials/ })).toBeVisible();
  await page.getByRole("button", { name: /Rig & Measure/ }).click();
  await expect(page.getByText(/Run 4 Trials on Claude Code\?/)).toBeVisible();
  await expect(page.getByText(/^Capped at \$5\.00: a pair starts only if/)).toBeVisible();
  await page.getByRole("button", { name: /^Start, up to/ }).click();
  await expect(page.getByRole("region", { name: "Measured workflows" }).locator(".result")).toHaveCount(1, { timeout: 30_000 });
  await expect(page.getByRole("region", { name: "Measured workflows" })).toContainText("Write tests that catch bugs");
  await expect(page.getByRole("region", { name: "Measured workflows" })).toContainText(/per solved task with/);
  // Every measured result says in one number whether it works, and why. The run keeps adding pairs while
  // undecided, so it may or may not reach the minimum for a firm score.
  const card = page.getByRole("region", { name: /^Rig score for .+ on Write tests that catch bugs$/ });
  await expectRigCard(card);
  await expect(card.locator(".rig__kicker")).toHaveText(/^Rig Score( · provisional: \d+ pairs?)?$/);
  // Measure is its own page, without the Workflows list: the saved workflow is listed back on Build.
  await expect(page.getByRole("region", { name: "Workflows", exact: true })).toBeHidden();
  await toStep(page, 3);
  await expect(list.getByText("Saved in Your Library")).toBeVisible();
  // Measured, a saved workflow shows what the run found (kept in its PROVEN.md), not a guess.
  await page.reload();
  const savedRow = list.locator(".pal-section", { hasText: "Saved in Your Library" }).locator(".pal-item").first();
  await expect(savedRow.getByTestId("proven-badge")).toHaveText(/^([+-]\d+ pts(, hurts)?|no effect) · measured n=\d+$/);
  await expect(savedRow.getByTestId("rig-badge")).toContainText(/^Rig \d{1,3}/);
  await expect(savedRow).not.toContainText("≈");
  await noA11yViolations(page);
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await toStep(page, 3);
  await expect(page.getByRole("region", { name: "Library" })).toBeVisible();
});

test("Lab builder: a blank workflow, steps from the palette, parallel branches, a loop, edit, save", async ({ page }) => {
  await open(page, 3, "lab");
  const list = page.getByRole("region", { name: "Workflows" });
  await list.getByRole("button", { name: "New blank workflow" }).click();
  await expect(page.locator(".insp__band")).toHaveText("Your workflow");
  await expect(page.locator('.canvas__node[aria-label="Step 1: New step"]')).toBeVisible();

  // Name it and the first step.
  await page.getByLabel("Workflow name").fill("Contract review");
  await page.getByLabel("Workflow name").blur();
  await page.getByLabel("Name", { exact: true }).fill("Read the contract");
  await page.getByLabel("What it does").fill("Read the contract and list every obligation and date.");
  await page.getByLabel("What it does").blur();
  await expect(page.locator(".canvas__node", { hasText: "Read the contract" })).toBeVisible();

  // Two steps after it: they run in parallel.
  await list.getByRole("button", { name: "Add the step Review" }).first().click();
  await page.locator(".canvas__node", { hasText: "Read the contract" }).locator(".block__body").click();
  await list.getByRole("button", { name: "Add the step Check" }).first().click();
  await expect(page.locator(".insp__subtitle")).toContainText("runs steps in parallel");

  // Connect Review to Check, then Check back to the first step: a loop.
  await page.getByRole("button", { name: "Fit everything" }).click();
  await page.locator(".canvas__node", { hasText: "Review" }).locator(".block__body").click();
  await page.getByLabel("Connect to").selectOption({ label: "Check" });
  await page.locator(".canvas__node", { hasText: /Check/ }).locator(".block__body").click();
  await page.getByLabel("Connect to").selectOption({ label: "Read the contract" });
  await expect(page.locator(".labloop")).toContainText("back to Read the contract");
  await expect(page.locator(".insp")).toContainText("Loops back from Check to Read the contract");
  await noA11yViolations(page);

  await page.getByRole("button", { name: "Save to My Library" }).click();
  await expect(page.getByText(/Saved as a runnable skill/)).toBeVisible();
  await expect(list.locator(".pal-item__name", { hasText: "Contract review" }).first()).toBeVisible();
});

test("Workflow Lab: + Add step works on a phone; a local runner says its step models are ignored", async ({ page }) => {
  // Phone: one pane at a time, and the step menu adds a step to the canvas.
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, 3, "lab");
  const view = page.getByRole("tablist", { name: "View" });
  await expect(view).toBeVisible();
  await view.getByRole("tab", { name: "Canvas" }).click();
  await expect(page.getByRole("region", { name: "Workflow", exact: true })).toBeVisible();
  const steps = page.locator('.canvas__node[aria-label^="Step "]');
  const before = await steps.count();
  const add = page.getByRole("button", { name: "Add Step" });
  await expect(add).toHaveAttribute("aria-expanded", "false");
  await add.click();
  await expect(add).toHaveAttribute("aria-expanded", "true");
  const menu = page.locator("#lab-add-menu");
  await expect(menu.getByRole("button").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  await expect(add).toHaveAttribute("aria-expanded", "false");
  await expect(add).toBeFocused();
  await add.click();
  await menu.locator(".labadd__item").first().click();
  await expect(menu).toBeHidden();
  await expect(steps).toHaveCount(before + 1);
  await noA11yViolations(page);

  // Desktop: a local model as the runner ignores the per-step models, and says so.
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, 4, "lab");
  await page.locator("summary", { hasText: /^Local Models/ }).click();
  await page.getByRole("button", { name: "Look on This Machine" }).click();
  await page.getByRole("list", { name: "Found local models" }).getByRole("button", { name: "Add" }).click();
  const mine = page.getByRole("list", { name: "Your local models" });
  await expect(mine).toContainText("qwen3:8b · ollama");
  await page.getByLabel("Run on", { exact: true }).selectOption({ label: "qwen3:8b · ollama" });
  // Steps are edited on Build (Measure has no step editor); the runner chosen on Measure is kept.
  await toStep(page, 3);
  await page.getByRole("button", { name: "Fit everything" }).click();
  await page.locator('.canvas__node[aria-label^="Step "] .block__body').first().click();
  await expect(page.getByText("Runs on qwen3:8b · ollama: every step uses that one model, so this choice is ignored there.")).toBeVisible();
  await expect(page.getByLabel("Model", { exact: true })).toHaveAttribute("aria-describedby", "lab-model-note");
  await expect(page.locator(".labchip--model.chip--ignored").first()).toHaveAttribute("title", /Ignored on qwen3:8b · ollama/);
  await noA11yViolations(page);
  // Leave the fake server's local models as they were, for the test after this one.
  await toStep(page, 4);
  await page.locator("summary", { hasText: /^Local Models/ }).click();
  await mine.getByRole("button", { name: "Remove" }).click();
  await expect(mine).toHaveCount(0);
});

test("local models: find one on this machine, add it, test it, run a bench on it", async ({ page }) => {
  await open(page, 4, "lab");
  await page.locator("summary", { hasText: /^Local Models/ }).click();
  await page.getByRole("button", { name: "Look on This Machine" }).click();
  const found = page.getByRole("list", { name: "Found local models" });
  await expect(found).toContainText("qwen3:8b");
  await expect(found).toContainText("can run Claude Code");
  await found.getByRole("button", { name: "Add" }).click();
  const mine = page.getByRole("list", { name: "Your local models" });
  await expect(mine).toContainText("qwen3:8b · ollama");
  await mine.getByRole("button", { name: "Test" }).click();
  const status = mine.getByRole("status");
  await expect(status).toContainText("Helper ready");
  await expect(status).toContainText("Claude Code ready");
  await expect(status).toContainText("context: passed, 65536 tokens.");
  await mine.getByLabel("Use for estimates, picks and judging").check();
  await expect(page.getByRole("button", { name: "Use Claude for Estimates and Judging Again" })).toBeVisible();
  // A public address is refused.
  await page.getByLabel("Server address").fill("https://api.example.com");
  await page.getByRole("button", { name: "Find Models" }).click();
  await expect(page.getByText(/isn't on this machine or your network/)).toBeVisible();
  await noA11yViolations(page);

  await page.getByLabel("Run on", { exact: true }).selectOption({ label: "qwen3:8b · ollama" });
  await expect(page.getByText(/served by qwen3:8b · ollama, reached as host.docker.internal/)).toBeVisible();
  await page.getByRole("button", { name: /Rig & Measure/ }).click();
  await expect(page.getByText(/Run \d+ Trials on qwen3:8b · ollama\?/)).toBeVisible();
  await expect(page.getByText(/on your local model \(no API cost\)/)).toBeVisible();
  await expect(page.getByText("Stops at $5.00; a local model costs nothing.")).toBeVisible();
  // Put estimates and judging back on Claude for the tests after this one (the model stays added).
  await page.getByRole("button", { name: "Use Claude for Estimates and Judging Again" }).click();
  await expect(page.getByRole("button", { name: "Use Claude for Estimates and Judging Again" })).toBeHidden();
});

test("Lab results: the frontier plots the measured workflow, and the by-task grid lists the bench's tasks", async ({ page }) => {
  await open(page, 3, "lab");
  // The measure from the test above is on the qa bench, so Results is offered now.
  await page.getByRole("radio", { name: "Results" }).click();
  await page.getByLabel("Results from").selectOption("qa");

  const chart = page.getByRole("region", { name: "Cost against lift for each workflow" });
  await expect(chart.locator(".matrix__dot").first()).toBeVisible();
  // The workflow measured above is a random QA one, so only its prefix is known.
  await expect(chart.getByRole("button", { name: /^QA: / }).first()).toBeVisible();
  await noA11yViolations(page);

  await page.getByRole("tab", { name: "By Task" }).click();
  const grid = page.getByRole("region", { name: "Pass rate by task" });
  await expect(grid.locator("tbody tr")).toHaveCount(2);
  await expect(grid.locator("tbody th", { hasText: "A suite that catches broken carts" })).toBeVisible();
  await expect(grid.locator("tbody th", { hasText: "Edge cases the obvious tests miss" })).toBeVisible();
  await expect(grid.locator("thead th", { hasText: "Without (baseline)" })).toBeVisible();
  await expect(grid.locator("thead th", { hasText: /^QA: / }).first()).toBeVisible();
  await noA11yViolations(page);

  await page.getByRole("radio", { name: "Canvas" }).click();
  await expect(page.locator(".canvas__node").first()).toBeVisible();
});

test("benches: held-out tasks stay hidden; an existing Harbor suite imports as a bench", async ({ page }) => {
  const suite = "~/.cache/pg-e2e-suite"; // laid out by the fake server
  await open(page, 4, "lab");
  await page.getByLabel("Bench").selectOption("finance");
  await expect(page.getByText(/Plus 1 held-out task: run, but not shown here/)).toBeVisible();
  await expect(page.getByText(/Tasks: Match a batch of invoices; .*Reconcile the bank to the ledger\./)).toBeVisible();

  await page.locator("summary", { hasText: "Import an Eval Suite" }).click();
  await page.getByLabel("Folder").fill(suite);
  await page.getByLabel("Name", { exact: true }).fill("Team suite");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByLabel("Bench")).toHaveValue("imp-team-suite");
  await expect(page.getByText(/Imported from .*pg-e2e-suite: 2 Harbor tasks/)).toBeVisible();
  await noA11yViolations(page);
});

test("public benchmarks: listed from the Harbor registry, a sample downloads and is selected", async ({ page }) => {
  await open(page, 4, "lab");
  const main = page.getByLabel("Bench", { exact: true });
  // Behind one entry in the Bench list; chosen, they get a list of their own.
  await main.selectOption({ label: (await main.locator("option", { hasText: /^More: Public Benchmarks/ }).textContent()) ?? "" });
  const bench = page.getByLabel("Public benchmark");
  // Listed, with their size: one task is "1 task", not "1 tasks"; the excluded one isn't offered.
  await expect(bench.locator("optgroup[label='Public Benchmarks for This Workflow'] option", { hasText: "terminal-bench 2.0 · 89 tasks · public" })).toHaveCount(1);
  await expect(bench.locator("option", { hasText: "hello-world 1.0 · 1 task · public" })).toHaveCount(1);
  await expect(bench.locator("option", { hasText: /seta-env/ })).toHaveCount(0);
  await expect(bench.locator("option", { hasText: / 1 tasks/ })).toHaveCount(0);

  await bench.selectOption({ label: "swebench-verified 1.0 · 500 tasks · public" });
  await expect(page.getByText(/Large Docker images/)).toBeVisible();

  await bench.selectOption({ label: "terminal-bench 2.0 · 89 tasks · public" });
  await expect(page.getByLabel("Tasks to download")).toHaveValue("5");
  await expect(page.getByText(/each one costs money: start small/)).toBeVisible();
  await page.getByLabel("Tasks to download").fill("3");
  await page.getByRole("button", { name: "Download 3 Tasks" }).click();
  await expect(main).toHaveValue("imp-terminal-bench-2-0");
  await expect(main.locator("option:checked")).toHaveText("terminal-bench 2.0 · 3 tasks · public");
  await expect(page.getByText(/3 tasks sampled from its 89, run as they are/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Source" })).toHaveAttribute("href", "https://github.com/laude-institute/terminal-bench-2");
  // Added: no longer offered for download, and it can be removed like an imported suite.
  await expect(bench).toHaveCount(0);
  await expect(main.locator("option", { hasText: "terminal-bench 2.0 · 89 tasks · public" })).toHaveCount(0);
  await noA11yViolations(page);
  await page.getByRole("button", { name: "Remove This Public Benchmark" }).click();
  await page.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(main.locator("option", { hasText: "terminal-bench 2.0 · 3 tasks · public" })).toHaveCount(0);
  await main.selectOption({ label: (await main.locator("option", { hasText: /^More: Public Benchmarks/ }).textContent()) ?? "" });
  await expect(bench.locator("option", { hasText: "terminal-bench 2.0 · 89 tasks · public" })).toHaveCount(1);
});

test("suite: one option runs every fitting bench; the confirm names them and the split", async ({ page }) => {
  await open(page, 4, "lab");
  const bench = page.getByLabel("Bench");
  const option = bench.locator("option", { hasText: /^All \d+ Matching Benches \(\d+ tasks\)$/ });
  await expect(option).toHaveCount(1);
  await bench.selectOption({ label: (await option.textContent()) ?? "" });
  await expect(page.getByText(/split evenly over [^;]+; .+, with one pooled verdict/)).toBeVisible();
  await page.getByLabel(/Stop at \(USD, in total\)/).fill("20");
  await page.getByRole("button", { name: /Rig & Measure/ }).click();
  await expect(page.getByText(/Run \d+ Trials on .* across \d+ Benches\?/)).toBeVisible();
  await expect(page.getByText(/\$20\.00 in total is split evenly: \$\d+\.\d\d per bench/)).toBeVisible();
  await noA11yViolations(page);
});

test("make a bench for a workflow: confirm, proofs, only proven tasks kept", async ({ page }) => {
  await open(page, 4, "lab");
  await page.getByRole("button", { name: "Make a Bench for This Workflow" }).click();
  await expect(page.getByText(/proven in a Docker container with no network/)).toBeVisible();
  await page.getByRole("button", { name: "Make It" }).click();
  await expect(page.getByText(/Made "Checks for a release": 1 task proven both ways\. Dropped always \(the check passes on the untouched project\)/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByLabel("Bench")).toHaveValue(/^gen-/);
  await expect(page.getByLabel("Bench").locator("option:checked")).toContainText("generated");
  await noA11yViolations(page);
});

test("undo, reset and remove: in the Lab and on the repo canvas", async ({ page }) => {
  await open(page, 3, "lab");
  const list = page.getByRole("region", { name: "Workflows" });
  await list.locator(".pal-group").filter({ has: page.locator(".pal-group__title", { hasText: /^Development$/ }) }).locator("summary").click();
  await list.getByRole("button", { name: /^Fix a bug/ }).last().click();
  await page.getByRole("button", { name: "Fit everything" }).click();
  const steps = page.locator(".canvas__node");
  const before = await steps.count();
  await expect(page.getByRole("button", { name: "Undo" })).toBeDisabled();

  // Remove a step from its card; undo brings it back; reset returns to the starter.
  await page.getByRole("button", { name: "Remove the step Review the diff" }).click();
  await expect(steps).toHaveCount(before - 1);
  await expect(page.locator(".insp__band")).toHaveText("Your workflow");
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(steps).toHaveCount(before);
  await page.getByRole("button", { name: "Fit everything" }).click();
  await page.getByRole("button", { name: "Remove the step Review the diff" }).click();
  await page.getByRole("button", { name: "Fit everything" }).click();
  await page.getByRole("button", { name: "Remove the step Run the tests" }).click();
  await expect(steps).toHaveCount(before - 2);
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(steps).toHaveCount(before);
  await expect(page.locator(".insp__band")).toHaveText("Starter workflow");

  // Random workflows can be removed again; clearing the compare set hides its summary.
  await page.getByRole("button", { name: "Random" }).click();
  const rnd = list.locator(".pal-section", { hasText: "Random" });
  await expect(rnd.locator(".pal-item")).toHaveCount(1);
  await page.getByRole("button", { name: "Compare" }).click();
  await expect(page.getByRole("region", { name: "Compared workflows" })).toBeVisible();
  await page.getByRole("button", { name: "Clear the pinned set" }).click();
  await expect(page.getByRole("region", { name: "Compared workflows" })).toHaveCount(0);
  await rnd.getByRole("button", { name: /^Remove .* from this list$/ }).click();
  await expect(list.locator(".pal-section", { hasText: "Random" })).toHaveCount(0);
  await noA11yViolations(page);

  // The repo canvas: add a card, undo it, add again, reset.
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await toStep(page, 3);
  const palette = page.getByRole("region", { name: "Library" });
  await libraryKind(palette, "Skills");
  await palette.getByRole("button", { name: "Add tdd to the canvas" }).click();
  const card = page.locator('.canvas__node[aria-label*="tdd"]');
  await expect(card).toHaveCount(1);
  await page.getByRole("group", { name: "Canvas edits" }).getByRole("button", { name: "Undo" }).click();
  await expect(card).toHaveCount(0);
  await palette.getByRole("button", { name: "Add tdd to the canvas" }).click();
  await expect(card).toHaveCount(1);
  await page.getByRole("group", { name: "Canvas edits" }).getByRole("button", { name: "Reset" }).click();
  await expect(card).toHaveCount(0);
  await page.getByRole("group", { name: "Canvas edits" }).getByRole("button", { name: "Undo" }).click();
  await expect(card).toHaveCount(1);

  // An Add that also draws links is one step: one Undo takes the card and every link away,
  // and the details pane stops showing it.
  const links = page.locator(".canvas__label", { hasText: "applies to" });
  const linksBefore = await links.count();
  await palette.getByRole("button", { name: "Add refund-skills to the canvas" }).click();
  const repoCard = page.locator('.canvas__node[aria-label*="refund-skills"]');
  await expect(repoCard).toHaveCount(1);
  await expect.poll(() => links.count()).toBeGreaterThan(linksBefore);
  await page.getByRole("group", { name: "Canvas edits" }).getByRole("button", { name: "Undo" }).click();
  await expect(repoCard).toHaveCount(0);
  await expect(links).toHaveCount(linksBefore);
  await expect(page.locator(".insp")).not.toContainText("refund-skills");
});

test("phone and tablet: one pane at a time, no horizontal scroll", async ({ page }) => {
  for (const [w, h] of [
    [390, 844],
    [768, 1024],
  ]) {
    await page.setViewportSize({ width: w, height: h });
    await open(page, 3);
    const view = page.getByRole("tablist", { name: "View" });
    await expect(view).toBeVisible();
    await expect(block(page, "Step 1: triage")).toBeVisible();
    await view.getByRole("tab", { name: "Library" }).click();
    await expect(page.getByRole("region", { name: "Library" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Canvas" })).toBeHidden();
    await view.getByRole("tab", { name: "Details" }).click();
    await expect(page.getByRole("tab", { name: "Suggestions" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `${w}px`).toBeLessThanOrEqual(0);
    await noA11yViolations(page);
  }
});

test("slim this workflow: confirm, progress, colours by contribution, apply and undo", async ({ page }) => {
  const lab = await (await page.request.get("/api/lab")).json();
  const wf = lab.disciplines.flatMap((d: { workflows: { id: string; name: string; steps: { id: string; kind: string; name: string }[] }[] }) => d.workflows).find((w: { name: string }) => w.name === "Fix a bug");
  const dead = wf.steps.find((s: { name: string }) => s.name === "Review the diff");
  const essential = wf.steps.find((s: { name: string }) => s.name === "Implement");
  const row = {
    bench: "qa", bench_name: "QA", id: 1, workflow: wf.name, treatment: `workflow-${wf.id}`, verdict: "helps", status: "done",
    model: "claude-sonnet-5-5", spent_usd: 1, pass_with: 1, pass_without: 0.5, diff: 0.5, ci_low: 0.2, ci_high: 0.7, n_pairs: 2,
    reused: 0, saved_usd: 0, adherence: null,
  };
  let polls = 0;
  await page.route("**/api/lab/results", (r) => r.fulfill({ json: [row] }));
  await page.route(/\/api\/lab\/ablate/, (r) => {
    const url = r.request().url();
    const job = { id: "j1", workflow: wf.id, bench: "qa", budget: 2, spent_usd: 0.2, status: "running", note: "", variants: [
      { key: dead.id, kind: "drop", label: `Without ${dead.name}`, experiment_id: 2, status: "running", detail: "" },
      { key: essential.id, kind: "drop", label: `Without ${essential.name}`, experiment_id: null, status: "pending", detail: "" },
    ] };
    if (url.endsWith("/preview")) return r.fulfill({ json: { count: 2, of: 2, variants: job.variants.map((v) => v.label) } });
    if (r.request().method() === "POST") return r.fulfill({ json: job });
    if (++polls < 2) return r.fulfill({ json: job });
    return r.fulfill({ json: { ...job, status: "done", spent_usd: 0.4, variants: job.variants.map((v) => ({ ...v, status: "done" })), contributions: {
      [dead.id]: { kind: "drop", marginal_pts: 1, saved_cost_usd: 0.02, verdict: "dead weight" },
      [essential.id]: { kind: "drop", marginal_pts: 40, saved_cost_usd: 0.01, verdict: "essential" },
    } } });
  });
  // A workflow is picked on Build; Measure (its own page) has no Workflows list.
  await open(page, 3, "lab");
  const list = page.getByRole("region", { name: "Workflows" });
  await list.locator(".pal-group").filter({ has: page.locator(".pal-group__title", { hasText: /^Development$/ }) }).locator("summary").click();
  await list.getByRole("button", { name: /^Fix a bug/ }).last().click();
  await toStep(page, 4);
  await page.getByRole("button", { name: "Fit everything" }).click();
  const steps = page.locator(".canvas__node");
  const before = await steps.count();

  await page.getByRole("button", { name: "Find the Slimmest Version" }).click();
  await expect(page.getByText("Measure 2 Slimmer Variants?")).toBeVisible();
  await expect(page.getByText(/baseline from this result is reused/)).toBeVisible();
  await page.getByRole("button", { name: /^Start, up to \$/ }).last().click();
  await expect(page.getByText("Measuring Variants")).toBeVisible();
  await expect(page.getByText("Slimming Done")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".slim--dead-weight")).toHaveCount(1);
  await expect(page.locator(".slim--essential")).toHaveCount(1);
  await expect(page.getByLabel("What each step contributes")).toBeVisible();
  await noA11yViolations(page);

  await page.getByRole("button", { name: /^Apply the Slimmed Workflow/ }).click();
  await expect(steps).toHaveCount(before - 1);
  await expect(page.locator(".slim")).toHaveCount(0);
  // Measure's map is read-only, but once a version is applied there Undo shows to take it back.
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(steps).toHaveCount(before);
});

test("improve from failures: confirm, see the edits, measure them, and the held-out gate speaks", async ({ page }) => {
  // This one asks Claude (the fake's model), whatever helper an earlier test left chosen. Set on the
  // server before the page reads it: a check of the page could run before its Local models load.
  const origin = `http://127.0.0.1:${process.env.PG_E2E_PORT ?? 7361}`; // a write needs the app's Origin
  expect((await page.request.post("/api/local-models/helper", { headers: { origin }, data: { id: null } })).ok()).toBe(true);
  // A workflow is picked on Build; Measure (its own page) has no Workflows list.
  await open(page, 3, "lab");
  const list = page.getByRole("region", { name: "Workflows" });
  await list.locator(".pal-group").filter({ has: page.locator(".pal-group__title", { hasText: /^Development$/ }) }).locator("summary").click();
  await list.getByRole("button", { name: /^Refactor safely/ }).last().click();
  await toStep(page, 4);
  await page.getByLabel("Bench").selectOption("finance");
  await page.getByRole("button", { name: /Rig & Measure/ }).click();
  await page.getByRole("button", { name: /^Start, up to/ }).click();
  const results = page.getByRole("region", { name: "Measured workflows" });
  const mine = results.locator(".result").filter({ hasText: "Accounts payable" });
  const parent = mine.filter({ hasText: "Refactor safely" }).filter({ hasNotText: "(improved)" });
  await expect(parent).toHaveCount(1, { timeout: 60_000 });

  await expect(parent.getByRole("button", { name: "Improve from Failures" })).toBeVisible({ timeout: 60_000 });
  // The model is called only after the confirm, and the card says only visible tasks go to it.
  await parent.getByRole("button", { name: "Improve from Failures" }).click();
  await expect(parent.getByText(/One call to .*; only visible tasks are shown to it/)).toBeVisible();
  await parent.getByRole("button", { name: /^Ask / }).click();
  const proposal = parent.getByLabel("Proposed improvement");
  await expect(proposal).toContainText("Run the checks again before finishing.");
  await expect(proposal).toContainText("Three failures ended without a final check.");
  await noA11yViolations(page);

  // Measure it: a second result, compared with the first on visible and held-out tasks.
  await proposal.getByRole("button", { name: /^Measure It/ }).click();
  const child = mine.filter({ hasText: "(improved)" });
  await expect(child).toHaveCount(1, { timeout: 60_000 });
  await expect(child.locator(".overfit-pill")).toHaveText(/Generalises|Overfit: Better on Visible Tasks, Not on Held-Out|Held-Out Tasks Don't Settle It/, { timeout: 30_000 });

  // Use This Version: it becomes your workflow in the Lab, and Cmd/Ctrl+Z brings the old one back.
  await parent.getByRole("button", { name: "Improve from Failures" }).click();
  await parent.getByRole("button", { name: /^Ask / }).click();
  await parent.getByRole("button", { name: "Use This Version" }).click();
  const added = page.locator(".canvas__node", { hasText: "Run the checks again before finishing." });
  await expect(added.first()).toBeVisible();
  // Measure's map is read-only, but once a version is applied there Undo shows to bring the old one back.
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(added).toHaveCount(0);
});

test("take it to any agent: a change brief for the repo with its accepted suggestions, a new project for a workflow, copy, save", async ({ page }) => {
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  // Accept a suggestion on the Suggestions tab: in the brief it becomes a task.
  await open(page, 3);
  await page.getByRole("tab", { name: "Suggestions" }).click();
  const title = "Build the link from Ledger to Audit export";
  await page.locator(".prop", { hasText: title }).getByRole("button", { name: "Accept" }).click();
  await expect(page.locator(".prop--accepted", { hasText: title })).toBeVisible();
  // The fold-out with the suggestions lists the files they touch, not a new project's tree.
  await page.getByText("Files the Accepted Suggestions Touch").click();
  await expect(page.locator("details.structure")).toContainText(/Audit export|Accept a suggestion|name no files/);
  await expect(page.locator("details.structure")).not.toContainText("orchestration/graph");

  await toStep(page, 5);
  const step = page.locator("main.steppage");
  await expect(step.getByRole("heading", { name: "Ship It to Any Agent" })).toBeVisible();
  const md = step.getByLabel("BUILD.md");
  // With accepted suggestions, the brief opens with them, so Copy gets the tasks.
  await expect(step.getByRole("radio", { name: "With the Accepted Suggestions" })).toHaveAttribute("aria-checked", "true");
  await expect(md).toContainText(new RegExp(`### \\d+\\. ${title}`));
  await step.getByRole("radio", { name: "As It Is" }).click();
  // The repo as it is: the changes to make in it, in its language, checked with its own tests.
  await expect(md).toContainText("# BUILD:");
  await expect(md).toContainText(/Changes to make in \S+ \(Python/);
  await expect(md).toContainText("## Current setup");
  await expect(md).toContainText("- CLAUDE.md: yes (at the root)");
  await expect(md).toContainText("`pytest -q` (from CLAUDE.md)");
  await expect(md).toContainText("accepted suggestions are left out");
  for (const stale of ["agentic-ai-project", "## Project layout", /\bProve\b/, /Rig a workflow/i, "POST /api"]) {
    await expect(md).not.toContainText(stale);
  }
  // The repo was measured in the run test: the brief leads with that result's Rig score and lists it.
  // Its own skill, by name (the seeded GitHub skill's run isn't on this canvas).
  await expectRigCard(step.getByRole("region", { name: "Rig score for refund-policy" }));
  await expect(md).toContainText("| measured | change (points) | pairs | verdict | Rig score |");
  await noA11yViolations(page);
  await step.getByRole("button", { name: "Copy BUILD.md" }).click();
  await expect(step.getByRole("status")).toContainText("Copied BUILD.md.");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("# BUILD:");
  await step.getByRole("button", { name: "Copy rig.json" }).click();
  await expect(step.getByRole("status")).toContainText("Copied rig.json.");
  const json = JSON.parse(await page.evaluate(() => navigator.clipboard.readText()));
  expect(json.kind).toBe("change");
  expect(json.evals.api).toContain("/api/scenarios/");
  await step.getByRole("button", { name: "Save to the Repo" }).click();
  await expect(step.getByRole("status")).toContainText("BUILD.md");
  // With the Accepted Suggestions: each accepted one is a task, with why, what to do and the effort.
  await step.getByRole("radio", { name: "With the Accepted Suggestions" }).click();
  await expect(md).toContainText(new RegExp(`### \\d+\\. ${title}`));
  await expect(md).toContainText("- effort: ");
  await expect(md).not.toContainText("left out");

  // A Lab workflow (nothing yet): a new project, its language a suggestion.
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await toStep(page, 3);
  await expect(page.locator(".canvas__node").first()).toBeVisible();
  await toStep(page, 5);
  const wd = page.locator("main.steppage");
  await expect(wd.getByLabel("BUILD.md")).toContainText("## Budgets");
  await expect(wd.getByLabel("BUILD.md")).toContainText("Workflow steps:");
  await expect(wd.getByLabel("BUILD.md")).toContainText("## Project layout");
  await expect(wd.getByLabel("BUILD.md")).toContainText("(suggested:");
  await wd.getByRole("button", { name: "Save to the Library" }).click();
  await expect(wd.getByRole("status")).toContainText("BUILD.md");
});

test("pick a design: ranked for the use case from step 1, read it, compare it with the repo as a blueprint", async ({ page }) => {
  await open(page, 1);
  await goalBox(page, TAG).fill("answer questions over 500 PDFs with tables and citations");
  await page.getByRole("button", { name: /^Next: Design/ }).click();
  const best = page.getByRole("region", { name: "Recommended architectures" });
  await expect(best.locator("li.prop").first()).toContainText("Multimodal RAG");
  await expect(best.locator("li.prop").first()).toContainText("Because you said 'PDFs with tables'"); // only the words that matched
  // A plain fit label, never a score.
  await expect(best.getByTestId("fit-label").first()).toHaveText("Strong Fit");
  await expect(best).not.toContainText(/score \d/);
  // The use case is written once, in step 1; here it is quoted with a way back.
  await expect(page.getByLabel("What do you want to build?")).toHaveCount(0);
  await expect(page.locator(".garage-for")).toContainText("500 PDFs");
  // Every design is a card with a small diagram of its parts and how they connect.
  const naive = page.locator(".archcard", { hasText: "Naive RAG" });
  await expect(naive).toBeVisible();
  await expect(naive.getByRole("img", { name: /^Naive RAG: / })).toBeVisible();
  expect(await naive.locator(".archmini rect").count()).toBeGreaterThan(4);
  await noA11yViolations(page);

  // Read it: summary, editable parameters with defaults, trade-offs, sources.
  await best.locator("li.prop").first().getByRole("button", { name: "See This Design" }).click();
  await expect(page.getByRole("heading", { name: "Multimodal RAG" })).toBeVisible();
  const dpi = page.getByLabel(/page_dpi/);
  await expect(dpi).toHaveValue("150");
  await dpi.fill("200");
  await expect(dpi).toHaveValue("200");
  await expect(page.getByRole("list", { name: "Trade-offs" })).toContainText("latency high");
  await expect(page.getByRole("link", { name: /ColPali/ })).toHaveAttribute("href", /arxiv\.org/);
  await noA11yViolations(page);

  // Compare it: step 3 draws it as a blueprint, only its own parts; Undo and Reset don't apply.
  await page.getByRole("button", { name: "Show on the Canvas" }).click();
  await expect(page.getByRole("radio", { name: "Blueprint: Multimodal RAG" })).toBeChecked();
  await expect(page.locator(".canvas__node", { hasText: "Vision embedder" })).toBeVisible();
  await expect(page.locator(".canvas__node", { hasText: "Page renderer" })).toBeVisible();
  await expect(page.locator(".canvas__node", { hasText: "Refund API" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Undo" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Reset" })).toBeDisabled();
  await noA11yViolations(page);

  // The brief in step 5 has the design to move toward, with the value set on it and the default.
  await toStep(page, 5);
  const md = page.locator("main.steppage").getByLabel("BUILD.md");
  await expect(md).toContainText("## Design to move toward: Multimodal RAG");
  await expect(md).toContainText("| `page_dpi` | 200 (changed) | 150 |");
  await toStep(page, 3);

  // Back to the repo's own architecture; the blueprint view goes away.
  await page.getByRole("radio", { name: "As It Is" }).click();
  await expect(page.getByRole("radio", { name: /^Blueprint/ })).toHaveCount(0);
  await expect(page.locator(".canvas__node", { hasText: "Refund API" })).toBeVisible();
});

test("a harness repo opens as its parts and their links; the repo's own blocks can be removed from the plan", async ({ page }) => {
  await open(page, 3);
  const palette = page.getByRole("region", { name: "Library" });
  await libraryKind(palette, "Harness Techniques");
  await palette.getByRole("button", { name: "Add ralph to the canvas" }).click();

  // Its parts, by kind, with the links its own text shows: the command uses both agents.
  for (const label of ["GitHub repo ralph", "Instructions CLAUDE", "Command ship", "Agent planner", "Agent reviewer", "Hook guard"]) {
    await expect(block(page, label)).toBeVisible();
  }
  await expect(block(page, "GitHub repo ralph")).toContainText("From GitHub · 5 parts");
  await expect(page.locator(".insp")).toContainText("Laid out as its 5 parts");
  await block(page, "Command ship").locator(".block__body").click();
  await expect(page.getByRole("button", { name: "Remove the link to planner" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove the link to reviewer" })).toBeVisible();
  await block(page, "Agent planner").locator(".block__body").click();
  await expect(page.locator(".insp")).toContainText("Plans the change");
  await expect(page.getByRole("link", { name: /Read it on GitHub/ })).toHaveAttribute("href", "https://github.com/loops/ralph/blob/main/.claude/agents/planner.md");
  await noA11yViolations(page);

  // One Undo takes the whole harness away again.
  await page.getByRole("group", { name: "Canvas edits" }).getByRole("button", { name: "Undo" }).click();
  await expect(block(page, "GitHub repo ralph")).toHaveCount(0);
  await expect(block(page, "Command ship")).toHaveCount(0);

  // The close button sits inside the card's header at any zoom.
  await libraryKind(palette, "Skills");
  await palette.getByRole("button", { name: "Add tdd to the canvas" }).click();
  const tdd = block(page, "Skill tdd");
  const [head, x] = [(await tdd.locator(".block__head").boundingBox())!, (await tdd.locator(".node__remove").boundingBox())!];
  expect(x.x + x.width).toBeLessThanOrEqual(head.x + head.width + 1);

  // A block the repo already has: off the plan with its lines, back with Undo, left out of the brief.
  const gateway = page.locator(".canvas__node", { hasText: "Gateway" }).first();
  await expect(gateway).toBeVisible();
  await page.getByRole("button", { name: "Remove Gateway from the plan" }).click();
  await expect(page.locator(".canvas__node", { hasText: "Gateway" })).toHaveCount(0);
  await expect(page.locator(".layer")).toContainText("1 removed from the plan");
  await page.getByRole("group", { name: "Canvas edits" }).getByRole("button", { name: "Undo" }).click();
  await expect(page.locator(".canvas__node", { hasText: "Gateway" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Remove Gateway from the plan" }).click();
  await toStep(page, 5);
  const step = page.locator("main.steppage");
  await expect(step).toContainText("Leaves out 1 part you removed and adds 1 you placed on the canvas.");
  await expect(step.getByLabel("BUILD.md")).toContainText("# BUILD:");
  await expect(step.getByLabel("BUILD.md")).not.toContainText("### Gateway");
});

test("dragging a harness repo lays it out as its parts where it lands; the brief has what you placed and drew", async ({ page }) => {
  await open(page, 3);
  await page.evaluate(() => Object.keys(localStorage).forEach((k) => k.startsWith("pg.canvas") && localStorage.removeItem(k)));
  await page.reload();
  const palette = page.getByRole("region", { name: "Library" });
  const edits = page.getByRole("group", { name: "Canvas edits" });
  await expect(block(page, "Step 2: fix")).toBeVisible();
  // Where the blocks already drawn are, in canvas space (the canvas may pan to show the drop).
  const world = async () =>
    page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>(".canvas__node")].map((n) => ({
        label: n.getAttribute("aria-label"),
        x: n.offsetLeft,
        y: n.offsetTop,
        width: n.offsetWidth,
        height: n.offsetHeight,
      })),
    );
  const before = await world();
  await libraryKind(palette, "Harness Techniques");
  const sb = (await page.locator(".canvas__surface").boundingBox())!;
  const point = { x: sb.x + sb.width / 2, y: sb.y + sb.height / 2 };
  await drag(page, palette.locator(".pal-item__main", { hasText: "ralph" }), point);

  // Like Add: the repo and its parts with their links, not one card.
  const labels = ["GitHub repo ralph", "Instructions CLAUDE", "Command ship", "Agent planner", "Agent reviewer", "Hook guard"];
  for (const label of labels) await expect(block(page, label)).toBeVisible();
  await expect(block(page, "GitHub repo ralph")).toContainText("From GitHub · 5 parts");
  // In view where it landed (the canvas pans to it), covering none of the blocks already drawn.
  const ralph = (await block(page, "GitHub repo ralph").boundingBox())!;
  expect(ralph.x >= sb.x && ralph.y >= sb.y && ralph.x + ralph.width <= sb.x + sb.width && ralph.y + ralph.height <= sb.y + sb.height).toBe(true);
  const overlaps = (a: { x: number; y: number; width: number; height: number }, b: typeof a) =>
    a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
  const after = await world();
  for (const label of labels) {
    const nb = after.find((n) => n.label === label)!;
    expect(before.filter((b) => overlaps(nb, b)).map((b) => b.label)).toEqual([]);
  }
  // Its own links came with it: the command uses both agents.
  await page.getByRole("button", { name: "Fit everything" }).click();
  await block(page, "Command ship").locator(".block__body").click();
  await expect(page.getByRole("button", { name: "Remove the link to planner" })).toBeVisible();

  // One Undo takes the whole drop away.
  await edits.getByRole("button", { name: "Undo" }).click();
  for (const label of labels) await expect(block(page, label)).toHaveCount(0);
  await expect(edits.getByRole("button", { name: "Undo" })).toBeDisabled();

  // Placed again, with a skill wired to a step: step 5's brief describes all of it.
  await drag(page, palette.locator(".pal-item__main", { hasText: "ralph" }), point);
  await expect(block(page, "Hook guard")).toBeVisible();
  await libraryKind(palette, "Skills");
  await drag(page, palette.locator(".pal-item__main", { hasText: "tdd" }), await center(block(page, "Step 2: fix")));
  await expect(block(page, "Skill tdd")).toBeVisible();
  await toStep(page, 5);
  const step = page.locator("main.steppage");
  await expect(step).toContainText("Adds 7 parts you placed on the canvas.");
  const md = step.getByLabel("BUILD.md");
  await expect(md).toContainText("## Skills to add");
  await expect(md).toContainText(/- \*\*tdd\*\*: (in this repo at|a local folder:) `/);
  await expect(md).toContainText("## Parts from GitHub repos");
  await expect(md).toContainText("### ralph (loops/ralph, harness)");
  await expect(md).toContainText("- command **ship** `.claude/commands/ship.md` (https://github.com/loops/ralph/blob/main/.claude/commands/ship.md): Ship one change");
  await expect(md).toContainText("## Links on the canvas");
  await expect(md).toContainText("- skill tdd -> step fix: applies to");
  await expect(md).toContainText("- command ship -> agent planner: uses");
  await noA11yViolations(page);
});

test("a design picked in step 2 opens as its own workflow in Nothing yet; Next asks before leaving it", async ({ page }) => {
  await open(page, 1, "lab");
  await page.getByLabel("What you're building").fill("triage support tickets and hand refunds over $500 to a person");
  await page.getByRole("button", { name: /^Next: Design/ }).click();
  await openBlueprints(page);
  await designCard(page, "Human-in-the-loop approvals").click();
  await expect(page.getByRole("heading", { name: "Human-in-the-loop approvals" })).toBeVisible();

  // Next with a design open asks first; Keep Browsing stays on the step.
  await page.getByRole("button", { name: /^Next: Build/ }).click();
  const ask = page.getByRole("group", { name: "Use Human-in-the-loop approvals?" });
  await expect(ask).toBeVisible();
  await noA11yViolations(page);
  await ask.getByRole("button", { name: "Keep Browsing" }).click();
  await expect(page.getByRole("heading", { name: /^(Choose a Design|Keep .+'s Design, or Start from Another)$/ })).toBeVisible();
  await page.getByRole("button", { name: /^Next: Build/ }).click();
  await ask.getByRole("button", { name: "Use It" }).click();

  // The canvas has the design's own workflow, set up for the discipline the use case points at.
  await page.getByRole("button", { name: "Fit everything" }).click();
  // In Support's words, with the use case's own limit: no "plan the change".
  const gate = page.locator(".canvas__node", { hasText: "Manager approval" });
  await expect(gate).toBeVisible();
  await expect(gate).toContainText("$500");
  await expect(page.locator(".canvas__node", { hasText: "Plan the change" })).toHaveCount(0);
  await expect(page.locator(".insp__band")).toHaveText("Agentic pattern");
  await expect(page.locator(".insp__title")).toHaveText("Human-in-the-loop approvals");
  await expect(page.locator(".labhost__design")).toContainText("set up for Support");
  await expect(page.locator(".canvas__node", { hasText: "Build a feature" })).toHaveCount(0);

  // "Use This Design" from the detail: a RAG design opens its RAG workflow; another pattern its pattern.
  for (const [name, step, band] of [
    ["Agentic RAG", "Plan the sub-questions", "RAG architecture"],
    ["Evaluator-optimizer", "Evaluator", "Agentic pattern"],
  ] as const) {
    await toStep(page, 2);
    await page.getByRole("button", { name: "All Architectures" }).click();
    await openBlueprints(page);
    await designCard(page, name).click();
    await page.getByRole("button", { name: "Use This Design" }).click();
    await page.getByRole("button", { name: "Fit everything" }).click();
    await expect(page.locator(".canvas__node", { hasText: step }).first()).toBeVisible();
    await expect(page.locator(".insp__band")).toHaveText(band);
  }

  // Start blank: no design, a one-step workflow of your own.
  await toStep(page, 2);
  await page.getByRole("button", { name: "All Architectures" }).click();
  await openBlueprints(page);
  await designCard(page, "Router").click();
  // The design opens once its entry is read; Next asks about the one that is open.
  await expect(page.getByRole("button", { name: "Use This Design" })).toBeVisible();
  await page.getByRole("button", { name: /^Next: Build/ }).click();
  await page.getByRole("group", { name: "Use Router?" }).getByRole("button", { name: "Start Blank" }).click();
  await expect(page.locator('.canvas__node[aria-label="Step 1: New step"]')).toBeVisible();
  // Start blank drops the link, and says so once.
  await expect(page.locator(".labhost__design")).toHaveText(/^Started blank: this workflow isn't linked to Evaluator-optimizer\./);
  await expect(page.getByRole("button", { name: "Detach from Design" })).toHaveCount(0);
});

test("work survives a reload: the Lab draft, the compare set, the design and its parameters, the repo's blueprint", async ({ page }) => {
  await open(page, 2, "lab");
  await openBlueprints(page);
  await designCard(page, "Corrective RAG").click();
  await page.getByLabel(/\btop_k\b/).fill("4");
  await page.getByRole("button", { name: "Use This Design" }).click();
  await page.getByRole("button", { name: "Fit everything" }).click();
  const steps = page.locator('.canvas__node[aria-label^="Step "]');
  const before = await steps.count();
  await page.getByRole("button", { name: "Remove the step Answer with citations" }).click();
  await expect(steps).toHaveCount(before - 1);
  await expect(page.locator(".insp__band")).toHaveText("Your workflow");
  await page.getByRole("button", { name: "Compare" }).click();

  await page.reload();
  await expect(page.locator(".insp__band")).toHaveText("Your workflow");
  await expect(page.locator(".insp__title-input")).toHaveValue(/^My Corrective RAG/);
  await page.getByRole("button", { name: "Fit everything" }).click();
  await expect(steps).toHaveCount(before - 1);
  await expect(page.getByRole("region", { name: "Compared workflows" }).locator("li")).toHaveCount(1);
  await expect(page.locator(".labhost__design")).toContainText("Corrective RAG");
  // Over to My repo and back: the edited draft, not the design's original, is on the canvas.
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await toStep(page, 3);
  await expect(page.locator(".insp__band")).toHaveText("Your workflow");
  await page.getByRole("button", { name: "Fit everything" }).click();
  await expect(steps).toHaveCount(before - 1);
  await toStep(page, 2);
  await expect(page.getByRole("heading", { name: "Corrective RAG (CRAG)" })).toBeVisible();
  await expect(page.getByLabel(/\btop_k\b/)).toHaveValue("4");

  // A draft that no longer checks out is dropped, and said once.
  await page.evaluate(() => localStorage.setItem("pg.lab.wf", JSON.stringify({ id: "gone", name: "Broken", steps: [] })));
  await page.reload();
  await toStep(page, 3);
  await expect(page.getByText("Your earlier draft couldn't be restored, so a starter workflow is open instead.")).toBeVisible();
  await page.reload();
  await expect(page.getByText(/Your earlier draft couldn't be restored/)).toHaveCount(0);

  // My repo: a catalog blueprint on the canvas stays open across a reload.
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await toStep(page, 2);
  await openBlueprints(page);
  await designCard(page, "Naive RAG").click();
  await page.getByRole("button", { name: "Show on the Canvas" }).click();
  await expect(page.getByRole("radio", { name: "Blueprint: Naive RAG" })).toBeChecked();
  await page.reload();
  await expect(page.getByRole("radio", { name: "Blueprint: Naive RAG" })).toBeChecked();
  await page.getByRole("radio", { name: "As It Is" }).click();
  await page.reload();
  await expect(page.getByRole("radio", { name: "As It Is" })).toBeChecked();
});

test("two goals: Nothing yet's own and each repo's saved one; switching repos shows that repo's; never saved without an edit", async ({ page }) => {
  const puts: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "PUT" && r.url().includes("/api/usecase")) puts.push(r.postData() ?? "");
  });
  const goalOf = async (repo: string) => {
    const repos = (await (await page.request.get("/api/repos")).json()) as { id: string; name: string }[];
    const id = repos.find((r) => r.name === repo)!.id;
    return ((await (await page.request.get(`/api/project?repo=${id}`)).json()) as { use_case: string | null }).use_case ?? "";
  };
  const saved = await goalOf(TAG);
  expect(saved).not.toBe("");

  // Nothing yet: its own box, kept in this browser. (A bare URL opens Home; Describe has its own link.)
  await page.goto("/#/describe");
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  const lab = page.getByLabel("What you're building");
  await expect(lab).toHaveValue("");
  await lab.fill("A support agent that answers from our policy docs");

  // My repo: the repo's saved goal, labelled as saved; the Nothing yet text never comes across.
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await page.getByRole("radio", { name: TAG, exact: true }).click();
  const box = goalBox(page, TAG);
  await expect(box).toHaveValue(saved);
  await expect(page.getByRole("button", { name: "Save Goal" })).toBeDisabled();
  await noA11yViolations(page);
  // Another repo shows its own goal (none) at once, not the last one's text.
  await page.getByRole("radio", { name: `${TAG}-blog`, exact: true }).click();
  const blog = goalBox(page, `${TAG}-blog`);
  await expect(blog).toHaveValue("");
  await expect(page.getByLabel(`Goal for ${TAG}-blog`, { exact: true })).toBeVisible();
  await expect(page.getByText(`${TAG}-blog has no goal saved yet.`)).toBeVisible();
  // Leaving by Next and by tabs without an edit saves nothing.
  await page.getByRole("button", { name: /^Next: Design/ }).click();
  await toStep(page, 3);
  await toStep(page, 1);
  expect(puts).toEqual([]);
  expect(await goalOf(`${TAG}-blog`)).toBe("");

  // An edit is explicit: Save Goal, then the button says Saved.
  await blog.fill("Keep the blog's build green");
  await expect(page.getByText(`Unsaved draft, only in this browser: every step uses it. Save Goal makes it ${TAG}-blog's goal.`)).toBeVisible();
  // Switching away and back: each repo's box is its own.
  await page.getByRole("radio", { name: TAG, exact: true }).click();
  await expect(box).toHaveValue(saved);
  await page.getByRole("radio", { name: `${TAG}-blog`, exact: true }).click();
  await expect(blog).toHaveValue("Keep the blog's build green");
  await page.getByRole("button", { name: "Save Goal" }).click();
  await expect(page.getByRole("button", { name: "Saved" })).toBeDisabled();
  await expect.poll(() => goalOf(`${TAG}-blog`)).toBe("Keep the blog's build green");
  await expect(page.getByLabel(`Saved goal for ${TAG}-blog`, { exact: true })).toHaveValue("Keep the blog's build green");
  expect(puts).toHaveLength(1);
  expect(await goalOf(TAG)).toBe(saved);

  // Next after an edit never saves: the draft goes on as the goal in use, said on every step,
  // and Save Goal there writes it.
  await blog.fill("Keep the blog's build green and its links alive");
  await page.getByRole("button", { name: /^Next: Design/ }).click();
  const bar = page.getByRole("status", { name: "Unsaved goal" });
  await expect(bar).toContainText("Unsaved goal — only in this browser.");
  await toStep(page, 3);
  await expect(bar).toBeVisible();
  expect(puts).toHaveLength(1);
  expect(await goalOf(`${TAG}-blog`)).toBe("Keep the blog's build green");
  await bar.getByRole("button", { name: "Save Goal" }).click();
  await expect(bar).toHaveCount(0);
  await expect.poll(() => goalOf(`${TAG}-blog`)).toBe("Keep the blog's build green and its links alive");
  expect(puts).toHaveLength(2);

  // The Nothing yet goal is still its own, after a reload too.
  await page.reload();
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^Nothing Yet/ }).click();
  await expect(lab).toHaveValue("A support agent that answers from our policy docs");
  expect(await goalOf(TAG)).toBe(saved);
  expect(puts).toHaveLength(2);
});

test("workspace: the Describe tab saves a repo's goal only with Save Goal, and tabs never save", async ({ page }) => {
  const puts: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "PUT" && r.url().includes("/api/usecase")) puts.push(r.postData() ?? "");
  });
  await open(page, 1);
  await page.getByRole("button", { name: "Skip the Guide" }).click();
  const tabs = page.getByRole("navigation", { name: "Workspace" });
  await tabs.getByRole("button", { name: "Describe" }).click();
  await page.getByRole("radio", { name: `${TAG}-blog`, exact: true }).click();
  const blog = goalBox(page, `${TAG}-blog`);
  // The goal the test above saved: shown once the repo's project is read.
  const before = "Keep the blog's build green and its links alive";
  await expect(blog).toHaveValue(before);
  await blog.fill(`${before} (edited)`);
  await expect(page.getByText(/^Unsaved draft, only in this browser/)).toBeVisible();
  await tabs.getByRole("button", { name: "Design" }).click();
  await tabs.getByRole("button", { name: "Describe" }).click();
  expect(puts).toEqual([]);
  // The edit waits in the box, unsaved, until Save Goal.
  await expect(blog).toHaveValue(`${before} (edited)`);
  await page.getByRole("button", { name: "Save Goal" }).click();
  await expect(page.getByRole("button", { name: "Saved" })).toBeVisible();
  expect(puts).toHaveLength(1);
  // Put it back for the tests after this one.
  await blog.fill(before);
  await page.getByRole("button", { name: "Save Goal" }).click();
  await expect(page.getByRole("button", { name: "Saved" })).toBeVisible();
});

test("one set of step names from the start; a reload reopens the last step, guided or not", async ({ page }) => {
  const NAMES = ["Describe", "Design", "Build", "Measure", "Ship"];
  await open(page, 1, "lab");
  const steps = page.getByRole("navigation", { name: "Steps" });
  await expect(steps.locator(".stepbar__label")).toHaveText(NAMES);
  await expect(page.getByText("Step 1 of 5 · Describe")).toBeVisible();
  await page.getByRole("button", { name: "Next: Design" }).click();
  await expect(page.getByText("Step 2 of 5 · Design")).toBeVisible();
  await expect(page.locator(".steppage__hint")).toHaveText(/^Keep your design, or start from an architecture/);
  await page.getByRole("button", { name: "Next: Build" }).click();
  await expect(page.locator(".stagehead")).toContainText("Step 3 of 5 · Build");
  // Reload: back on Build, not Describe.
  await page.reload();
  await expect(steps.getByRole("button", { name: /^3\. Build/ })).toHaveAttribute("aria-current", "step");
  await page.getByRole("button", { name: "Next: Measure" }).click();
  await page.getByRole("button", { name: "Next: Ship" }).click();
  // Through the whole path: the same names, now as tabs.
  const tabs = page.getByRole("navigation", { name: "Workspace" });
  await expect(tabs.getByRole("button")).toHaveText([...NAMES, "Runs"]);
  await expect(page.getByText(/Rig reopens where you were/)).toBeVisible();
  await tabs.getByRole("button", { name: "Measure" }).click();
  await page.reload();
  await expect(tabs.getByRole("button", { name: "Measure" })).toHaveAttribute("aria-current", "page");
  // No old names anywhere on the way.
  for (const old of ["Swap parts", "Take it", "Pick a design"]) await expect(page.getByText(old)).toHaveCount(0);
});

test("Design in a repo: keep its design first, catalog folded below; Next with nothing chosen keeps it, no question", async ({ page }) => {
  await open(page, 2);
  const keep = page.locator(".keep-card--first");
  await expect(keep).toContainText(`Keep ${TAG}'s Design and Improve Its Agent Setup`);
  await expect(keep).toContainText("Recommended");
  await expect(keep.locator("p")).toContainText("how the coding agent works");
  // A goal about the agent: the catalog is folded behind one line until asked for.
  const prints = page.getByTestId("blueprints");
  await expect(prints.locator("summary")).toContainText("Start from a Blueprint Instead");
  await expect(page.locator("[aria-label='Catalog']")).toHaveCount(0);
  await prints.locator("summary").click();
  await expect(page.locator("[aria-label='Catalog']")).toBeVisible();
  // The keep card comes before the catalog.
  const order = await page.evaluate(() => {
    const k = document.querySelector(".keep-card--first")!;
    const c = document.querySelector("[aria-label='Catalog']")!;
    return k.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING;
  });
  expect(order).toBeTruthy();
  await noA11yViolations(page);
  // Open a design only to read it, then Next: the repo's own design, no question asked.
  await openBlueprints(page);
  await designCard(page, "Naive RAG").click();
  await page.getByRole("button", { name: "Next: Build" }).click();
  await expect(page.getByRole("group", { name: /^Show / })).toHaveCount(0);
  // The repo's own design: as it is, or with what was accepted (Build opens on that when any were).
  await expect(page.locator('.viewmode [aria-checked="true"]')).toHaveText(/^(As It Is|With Accepted · \d+)$/);
  await expect(page.getByRole("radio", { name: /^Blueprint/ })).toHaveCount(0);
});

test("Explain the top three: says it's asking the model and what it costs, then the answer or the error", async ({ page }) => {
  let fail = false;
  await page.route("**/api/garage/recommend**", async (route) => {
    const body = JSON.parse(route.request().postData() ?? "{}") as { explain?: boolean };
    if (!body.explain) return route.continue();
    await new Promise((r) => setTimeout(r, 800));
    if (fail) return route.fulfill({ status: 502, contentType: "application/json", body: JSON.stringify({ detail: "The model is busy." }) });
    const got = await (await route.fetch({ postData: JSON.stringify({ ...body, explain: false }) })).json();
    got.picks[0].explanation = "Fits because the PDFs have tables.";
    return route.fulfill({ json: got });
  });
  await open(page, 1, "lab");
  await page.getByLabel("What you're building").fill("answer questions over 500 PDFs with tables and citations");
  await page.getByRole("button", { name: "Next: Design" }).click();
  const ask = page.getByRole("button", { name: "Explain the Top Three with the Model (≈$0.01)" });
  fail = true;
  await ask.click();
  await expect(page.getByRole("status").filter({ hasText: "Asking the model (≈$0.01)…" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("Couldn't ask the model: The model is busy.");
  fail = false;
  await ask.click();
  await expect(page.getByText("Asking the model (≈$0.01)…")).toBeVisible();
  await expect(page.getByText("Fits because the PDFs have tables.")).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(ask).toHaveCount(0);
});

test("Design with too little to rank on: no Explain offer, the close designs and what to add", async ({ page }) => {
  await open(page, 1, "lab");
  await page.getByLabel("What you're building").fill("support agent workflow");
  await page.getByRole("button", { name: "Next: Design" }).click();
  await expect(page.getByText("Only 'support' and 'workflow' matched, too little to rank on.")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Explain the Top Three/ })).toHaveCount(0);
  await expect(page.getByText("No fits yet", { exact: true })).toBeVisible();
  await expect(page.getByText("Best fits", { exact: true })).toHaveCount(0);
  const close = page.getByRole("region", { name: "Close, not a fit yet" });
  await expect(close.getByRole("button", { name: /^See This Design/ })).toHaveCount(3);
  await expect(page.getByTestId("fit-label")).toHaveCount(0);
  await expect(page.getByText("when the work is handed to another agent or a person")).toBeVisible();
  await noA11yViolations(page);
  await close.getByRole("button", { name: "See This Design: Router" }).click();
  await expect(page.getByRole("heading", { name: "Router" })).toBeVisible();
});

test("Lab: an edited draft is kept in Your drafts on switching, with Undo; removing one asks first", async ({ page }) => {
  await open(page, 3, "lab");
  const list = page.getByRole("region", { name: "Workflows" });
  await list.locator(".pal-group").filter({ has: page.locator(".pal-group__title", { hasText: "RAG architectures" }) }).locator("summary").click();
  await list.getByRole("button", { name: /^Agentic RAG/ }).last().click();
  await page.getByRole("button", { name: "Fit everything" }).click();
  const steps = page.locator('.canvas__node[aria-label^="Step "]');
  const n = await steps.count();
  await page.getByRole("button", { name: "Remove the step Check the citations" }).click();
  await expect(steps).toHaveCount(n - 1);
  const NAME = "My Agentic RAG (plan, look up in parallel, synthesise, check)";
  await expect(page.locator(".insp__title-input")).toHaveValue(NAME);

  // Another workflow: the draft is kept, and the switch says where it went.
  await list.getByRole("button", { name: /^Naive RAG/ }).last().click();
  const note = page.getByRole("status").filter({ hasText: "Switched to Naive RAG" });
  await expect(note).toContainText(`Your draft ${NAME} is in Your Drafts.`);
  const drafts = page.getByRole("list", { name: "Your Drafts" });
  await expect(drafts.getByRole("button", { name: /^My Agentic RAG/ })).toBeVisible();
  await noA11yViolations(page);
  // Undo: the draft is back on the canvas, as edited.
  await note.getByRole("button", { name: "Undo" }).click();
  await expect(page.locator(".insp__title-input")).toHaveValue(NAME);
  await page.getByRole("button", { name: "Fit everything" }).click();
  await expect(steps).toHaveCount(n - 1);
  // Kept across a reload, and opened from the list.
  await list.getByRole("button", { name: /^Naive RAG/ }).last().click();
  await page.reload();
  await drafts.getByRole("button", { name: /^My Agentic RAG/ }).click();
  await expect(page.locator(".insp__title-input")).toHaveValue(NAME);
  // Removing asks first; Cancel keeps it.
  await drafts.getByRole("button", { name: `Remove the draft ${NAME}` }).click();
  const confirm = page.getByRole("group", { name: `Remove ${NAME}?` });
  await confirm.getByRole("button", { name: "Cancel" }).click();
  await expect(drafts.getByRole("button", { name: /^My Agentic RAG/ })).toBeVisible();
  await drafts.getByRole("button", { name: `Remove the draft ${NAME}` }).click();
  await confirm.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(drafts).toHaveCount(0);
});

test("Lab: the Discipline choice filters the starters and is remembered; the matcher offer is only under Advanced", async ({ page }) => {
  await open(page, 3, "lab");
  const list = page.getByRole("region", { name: "Workflows" });
  // The matcher's offer isn't in the Workflows panel.
  await expect(list.getByRole("button", { name: /skill matcher/ })).toHaveCount(0);
  await expect(list.getByTestId("matcher-status")).toHaveCount(0);

  const d = page.getByLabel("Discipline", { exact: true });
  await expect(d).toBeVisible();
  await d.selectOption("support");
  const starters = list.locator(".pal-section", { has: page.locator(".pal-section__title", { hasText: /^Starters/ }) });
  await expect(starters.locator(".pal-section__title")).toHaveText("Starters · Support");
  await expect(starters.locator(".pal-group__title")).toHaveText(["Support"]);
  await expect(list.getByText(/Showing Support starters/)).toBeVisible();
  await page.reload();
  await expect(d).toHaveValue("support");
  await expect(starters.locator(".pal-group__title")).toHaveText(["Support"]);

  // A support workflow measures on the support bench by default.
  await starters.getByRole("button", { name: /^Handle a ticket/ }).click();
  await page.getByRole("button", { name: "Fit everything" }).click();
  await page.locator('.canvas__node[aria-label^="Step "] .block__body').first().click();
  // Advanced: Better Skill Matching, under the skill picker, with a plain-words confirm.
  const adv = page.getByRole("button", { name: "Advanced: Better Skill Matching" });
  await adv.click();
  const box = page.getByRole("group", { name: "Better skill matching" });
  await expect(box).toContainText("downloads them once (≈1,140 MB)");
  await expect(box).toContainText("1.9 GB of memory");
  await expect(box.getByTestId("matcher-status")).toHaveText("Skills are matched by word rules.");
  await noA11yViolations(page);
  await box.getByRole("button", { name: "Cancel" }).click();
  await expect(box).toHaveCount(0);
  await adv.click();
  await box.getByRole("button", { name: "Download ≈1,140 MB and Turn It On" }).click();
  await expect(box.getByTestId("matcher-status")).toHaveText(
    "Couldn't get the skill matcher (no network in the demo); skills matched by word rules.",
    { timeout: 15_000 },
  );
  await box.getByRole("button", { name: "Turn It Off" }).click();
  await expect(page.getByTestId("matcher-status")).toHaveText("Skills are matched by word rules.");

  await toStep(page, 4);
  const bench = page.getByLabel("Bench");
  await expect(bench.locator("option:checked")).toHaveText(/^Answer support tickets by policy/);
  // Public benchmarks sit behind one entry, not in the main list.
  await expect(bench.locator("option", { hasText: "· public" })).toHaveCount(0);
  await expect(bench.locator("option", { hasText: /^More: Public Benchmarks \(\d+\)…$/ })).toHaveCount(1);
  // The Discipline choice is in the Workflows list, on Build.
  await toStep(page, 3);
  await d.selectOption("");
});

test("opening a repo asks for its skills' rough estimates in one batched request", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/estimate")) asked.push(new URL(r.url()).pathname);
  });
  await open(page, 3);
  await expect(block(page, "Skill in repo refund-policy")).toBeVisible();
  await page.waitForTimeout(800);
  expect(asked.filter((a) => a === "/api/estimate")).toEqual([]);
  expect(asked.filter((a) => a === "/api/estimate/batch")).toHaveLength(1);
});

test("guide to workspace: skip it, tabs without numbers, opens on Build, Build and Measure are two pages in the Lab, guide again", async ({ page }) => {
  await open(page, 1, "lab");
  await page.getByRole("button", { name: "Skip the Guide" }).click();
  const tabs = page.getByRole("navigation", { name: "Workspace" });
  await expect(tabs.getByRole("button")).toHaveText(["Describe", "Design", "Build", "Measure", "Ship", "Runs"]);
  await expect(tabs.getByRole("link", { name: "Home" })).toBeVisible();
  await expect(tabs.getByRole("button", { name: "Build" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("navigation", { name: "Steps" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Next:/ })).toHaveCount(0);
  // No guided Back/Next, but the page's own way back stays, named for where it goes.
  await expect(page.getByRole("button", { name: "Back", exact: true })).toHaveCount(0);
  await expect(page.locator(".stagehead").getByRole("button", { name: "Back to Design" })).toBeVisible();
  // The Lab's workflow arrives on its own request, slower late in a full run (the server then holds
  // every earlier spec's results): scan the page once it is drawn, not while the canvas is still
  // being laid out over the page head, and read its name only once it is there.
  const title = page.locator(".insp__title");
  await expect(title).toBeVisible();
  await expect(page.locator('.canvas__node[aria-label^="Step "]').first()).toBeVisible();
  await noA11yViolations(page);

  // In the Lab, Build and Measure are two pages, each with its own heading and forward action; the
  // workflow on the canvas is the same one (the Lab stays mounted).
  await expect(page.getByRole("tablist", { name: "Details panel" })).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1, name: "Build the Workflow" })).toBeVisible();
  const name = await title.textContent();
  await page.getByRole("button", { name: "Measure This Workflow" }).click();
  await expect(tabs.getByRole("button", { name: "Measure" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { level: 1, name: "Measure the Workflow" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: "Build the Workflow" })).toHaveCount(0);
  await expect(page.getByLabel("Bench")).toBeVisible();
  await expect(page.getByTestId("try-it")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Add Step/ })).toBeHidden();
  await expect(page.locator(".insp__title")).toHaveText(name!);
  await tabs.getByRole("button", { name: "Build" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Build the Workflow" })).toBeVisible();
  await expect(page.getByLabel("Bench")).toHaveCount(0);
  await toStep(page, 2);
  await expect(page.getByText(/^Step \d of 5/)).toHaveCount(0);

  // A returning visit reopens the step you were on, as a workspace too.
  await page.reload();
  await expect(tabs.getByRole("button", { name: "Design" })).toHaveAttribute("aria-current", "page");

  // The guide comes back from the menu; going through to step 5 makes it a workspace again.
  await page.getByRole("button", { name: "Menu" }).click();
  await page.getByRole("button", { name: "Show the Guide Again" }).click();
  await expect(page.getByRole("navigation", { name: "Steps" })).toBeVisible();
  await expect(page.getByText("Step 1 of 5 · Describe")).toBeVisible();
  await toStep(page, 5);
  await expect(page.getByText(/That's the whole path/)).toBeVisible();
  await expect(tabs).toBeVisible();
});

test("Runs: every run from every repo and the Lab in one table, opened in context, forgotten only after a confirm", async ({ page }) => {
  await open(page, 1);
  // Nothing running: the run pill is a quiet link.
  await page.locator(".topbar").getByRole("button", { name: "Runs", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Runs", exact: true })).toBeVisible();
  const table = page.getByRole("region", { name: "Every run" });
  await expect(table.locator("tbody tr", { hasText: "refund-policy" }).first()).toContainText(TAG);
  await expect(table.locator("tbody tr", { hasText: "bench" }).first()).toBeVisible();
  for (const col of ["Measured", "Model", "Pairs", "Result", "Rig score", "Validity", "Spent"]) {
    await expect(table.getByRole("columnheader", { name: col })).toBeVisible();
  }
  await expect(table.locator("tbody tr").first()).toContainText(/\$\d+\.\d\d of \$\d+\.\d\d/);
  await noA11yViolations(page);

  // Forget asks first: No keeps it, Yes removes it (a Lab run: the seeded repo run stays).
  const rows = table.locator("tbody tr");
  const n = await rows.count();
  const last = table.locator("tbody tr", { hasText: "bench" }).last();
  await last.getByRole("button", { name: /^Forget the run / }).click();
  await last.getByRole("button", { name: "No" }).click();
  await expect(rows).toHaveCount(n);
  await last.getByRole("button", { name: /^Forget the run / }).click();
  await last.getByRole("button", { name: "Yes" }).click();
  await expect(rows).toHaveCount(n - 1);

  // Open in Context, from a run's own page: a repo run on that repo's Measure; a Lab run on the
  // Lab's Measure with its workflow (each asks first when it switches; see evidence.spec.ts).
  await table.locator("tbody tr", { hasText: "refund-policy" }).first().getByRole("link", { name: /^View / }).click();
  await page.getByRole("button", { name: "Open in Context" }).click();
  const ask = page.getByRole("alertdialog", { name: "Open in Context" });
  if (await ask.isVisible()) await ask.getByRole("button", { name: /^Switch to / }).click();
  await expect(page.getByRole("heading", { name: "Tasks to Measure On" })).toBeVisible();
  await page.locator(".topbar").getByRole("button", { name: "Runs", exact: true }).click();
  const lab = table.locator("tbody tr", { hasText: "bench" }).first();
  const what = await lab.locator(".runs__name").innerText();
  await lab.getByRole("link", { name: /^View / }).click();
  await page.getByRole("button", { name: "Open in Context" }).click();
  await page.getByRole("alertdialog", { name: "Open in Context" }).getByRole("button", { name: "Open in the Lab" }).click();
  await expect(page.getByLabel("Bench")).toBeVisible();
  await expect(page.locator(".insp__title, .insp__title-input").first()).toBeVisible();
  expect(what.length).toBeGreaterThan(0);
});

test("a run is priced before sign-in: the estimate next to Stop at, and Sign In to Run", async ({ page }) => {
  await open(page, 4, "lab");
  await page.locator(".agent-pill").click();
  await page.getByRole("radio", { name: /Codex/ }).click();
  await page.getByRole("dialog", { name: "Agent" }).getByRole("button", { name: "Close" }).click();
  await expect(page.locator(".agent-pill")).toContainText("Codex · sign in");
  await page.getByLabel("Bench").selectOption("qa");
  await expect(page.getByTestId("run-cost")).toHaveText(/^≈ \$\d+\.\d\d for the full run \(\d+ pairs?, \d+ trials\)|^Stops at \$/);
  await expect(page.getByText(/a first guess: nothing measured yet|from earlier runs on this bench/).first()).toBeVisible();
  await page.getByLabel(/Stop at/).fill("0.5");
  await expect(page.getByTestId("run-cost")).toHaveText(/^Stops at \$0\.50 \(about \d+ of \d+ pairs?\)\. The full run would cost ≈ \$\d+\.\d\d\.$/);
  await expect(page.getByTestId("run-detect")).toHaveText(/an effect smaller than about ±\d+ pts can't be told from noise|doesn't pay for one pair/);
  await page.getByRole("button", { name: "Sign In to Run" }).click();
  await expect(page.getByRole("dialog", { name: "Agent" })).toBeVisible();
  await noA11yViolations(page);

  // On a repo too, and the run review opens once signed in.
  await page.getByRole("radio", { name: /Claude Code/ }).click();
  await page.getByRole("dialog", { name: "Agent" }).getByRole("button", { name: "Close" }).click();
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await toStep(page, 4);
  await expect(page.getByTestId("run-cost")).toBeVisible();
  await expect(page.getByRole("button", { name: "Review the Run" })).toBeEnabled();
});

test("no model call unless asked: typing in step 1, a new skill card, and picks for this repo stay model-free", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (r) => {
    const u = r.url();
    if (u.includes("/api/estimate")) asked.push(`estimate ${r.postData() ?? ""}`);
    if (u.includes("/api/recommend")) asked.push(`recommend ${u}`);
  });
  // Typing a goal fires nothing per keystroke (the repo's skills' one rough batch on opening aside).
  await open(page, 1);
  await expect(goalBox(page, TAG)).not.toHaveValue("");
  await expect.poll(() => asked.filter((a) => a.startsWith("estimate")).length).toBeGreaterThan(0);
  const before = asked.length;
  await goalBox(page, TAG).pressSequentially(" for refunds", { delay: 15 });
  await page.waitForTimeout(400);
  expect(asked.slice(before).filter((a) => a.startsWith("estimate"))).toEqual([]);

  await toStep(page, 3);
  await page.evaluate(() => Object.keys(localStorage).forEach((k) => k.startsWith("pg.canvas") && localStorage.removeItem(k)));
  await page.reload();
  const palette = page.getByRole("region", { name: "Library" });
  await libraryKind(palette, "Skills");
  // careful-review: never measured here (tdd was, by the run test above).
  await page.getByRole("button", { name: "Add careful-review to the canvas" }).click();
  const tdd = block(page, "Skill careful-review");
  // The rough estimate at once, and no model asked for it.
  await expect(tdd.locator(".est")).toHaveText(/^Rough [+-]?\d+ pts$/);
  await tdd.locator(".block__body").click();
  const sharpen = page.getByRole("button", { name: "Sharpen with the Model (≈$0.01)" });
  await expect(sharpen).toBeVisible();
  expect(asked.filter((a) => a.includes('"model":true'))).toEqual([]);
  // One click, one model estimate for that card.
  await sharpen.click();
  await expect(tdd.locator(".est")).toHaveText("≈ +6 pts");
  expect(asked.filter((a) => a.includes('"model":true'))).toHaveLength(1);
  await expect(sharpen).toHaveCount(0);

  // Picked for this repo: the rough picker (or picks a model already made for these needs,
  // shown again for free), with a button that asks the model.
  await sortBy(palette, "Picked for This Repo");
  await expect(palette.locator(".picked__basis")).toContainText(/Rough picks from the repo's needs, no model\.|Picked by the cheapest model/);
  expect(asked.filter((a) => a.includes("model=true"))).toEqual([]);
  await palette.getByRole("button", { name: /^Ask the model (to pick|again) \(≈\$0\.02\)$/ }).click();
  await expect(palette.getByText("Picked by the cheapest model from the repo's needs.")).toBeVisible();
  expect(asked.filter((a) => a.includes("model=true"))).toHaveLength(1);
});

test("checks: prose can't be added, an approved prose check is flagged and left out of runs, a changed goal flags scenarios", async ({ page }) => {
  await open(page, 4);
  const item = page.locator(".list li", { hasText: "Token cost" });
  await expect(item.getByTestId("check-problem")).toHaveText("Approved, but the Check Isn't a Command");
  await item.getByRole("button", { name: /Token cost/ }).click();
  await expect(item.getByRole("note")).toContainText("token is not a program");
  // It can be rewritten as a command in place; a sentence there is refused with the same reason.
  await item.getByLabel("Write it as a command").fill("reduce the tokens");
  await item.getByRole("button", { name: "Save Check" }).click();
  await expect(item.getByRole("alert")).toContainText("isn't a command");
  // The run leaves it out and says so.
  await expect(page.getByTestId("left-out")).toContainText("Left out: Token cost.");

  await page.getByRole("button", { name: "+ Add Task" }).click();
  await page.getByLabel("What should the agent do?").fill("Works");
  await page.getByLabel("Instruction the agent gets").fill("Make it work.");
  await page.getByLabel("Check: a shell command").fill("make sure it works");
  await page.getByRole("button", { name: "Add Task", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "reads as a sentence, not a command" })).toBeVisible();

  // The goal the generated scenarios were written for, then another one.
  const SEED = "Fix refund bugs without breaking the plan limits.";
  const setGoal = async (text: string) => {
    await toStep(page, 1);
    await goalBox(page, TAG).fill(text);
    // Only Save Goal writes it (Next never does); the same text as saved has nothing to save.
    const save = page.getByRole("button", { name: "Save Goal" });
    if (await save.isEnabled()) {
      await save.click();
      await expect(page.getByRole("button", { name: "Saved" })).toBeVisible();
    }
    await toStep(page, 4);
  };
  await setGoal(SEED);
  await expect(page.getByTestId("goal-changed")).toHaveCount(0);
  await setGoal("Answer billing questions in three languages.");
  await expect(page.getByTestId("goal-changed").first()).toHaveText("Written for a Different Goal");
  await page.locator(".list li", { hasText: "The limits file is gone" }).getByRole("button").first().click();
  await expect(page.getByRole("note").filter({ hasText: "generated for an earlier one" })).toBeVisible();
  await noA11yViolations(page);
  await setGoal(SEED);
  await expect(page.getByTestId("goal-changed")).toHaveCount(0);
});

test("results that aren't evidence: badged, sorted last, off the frontier; estimates say where they come from", async ({ page }) => {
  const valid = { status: "valid", badge: null, reason: null };
  const never = { status: "invalid", badge: "Invalid: the workflow was never opened", reason: 'The "with" trials mostly ran without it, so the difference isn\'t its.' };
  const base = {
    bench: "qa", bench_name: "QA", model: "claude-sonnet-5-5", agent: "claude-code", status: "done", spent_usd: 1, reused: 0, saved_usd: 0,
    ci_low: -0.2, ci_high: 0.6, n_pairs: 2, adherence: null,
  };
  const results = [
    { ...base, id: 1, workflow: "Fix a bug", treatment: "workflow-a", verdict: "inconclusive", diff: 0.2, pass_with: 1, pass_without: 0.5, validity: valid },
    { ...base, id: 2, workflow: "Never opened", treatment: "workflow-b", verdict: "helps", diff: 0.9, pass_with: 1, pass_without: 0.1, validity: never,
      adherence: { trials: 3, read: 3, followed: 0, steps_run: 0, models_ok: 0, loop_broken: 0, not_opened: 3, not_applied: 3, missing: [], wrong_model: [] } },
  ];
  const row = (id: number, workflow: string, diff: number, validity: object) => ({
    experiment_id: id, workflow, treatment: `workflow-${id}`, model: "claude-sonnet-5-5", agent: "claude-code", validity, n_pairs: 2, diff,
    ci_low: diff - 0.3, ci_high: diff + 0.3, pass_with: 1, pass_without: 0.5, cost_per_trial_usd: 0.4 + id / 10, mean_duration_s: 60, per_task: {},
  });
  await page.route("**/api/lab/results", (r) => r.fulfill({ json: results }));
  await page.route(/\/api\/lab\/matrix/, (r) =>
    r.fulfill({ json: { bench: "qa", latest: null, tasks: [], rows: [row(1, "Fix a bug", 0.2, valid), row(2, "Never opened", 0.9, never)] } }),
  );
  await open(page, 3, "lab");
  // Every estimate says where it comes from, in the same words.
  const badges = page.getByTestId("estimate-badge");
  await expect(badges.first()).toHaveText(/^≈ [+-]?[\d.]+ pts · guess from shape$|^[+-]?[\d.]+ pts · estimated from \d+ valid runs?$/);
  await expect(page.getByText(/learned from \d+ run/)).toHaveCount(0);

  await page.getByRole("radio", { name: "Results" }).click();
  await page.getByLabel("Results from").selectOption("qa");
  const chart = page.getByRole("region", { name: "Cost against lift for each workflow" });
  await expect(chart.locator(".matrix__dot")).toHaveCount(1);
  await expect(chart.getByRole("button", { name: /^Fix a bug/ })).toBeVisible();
  const off = page.getByTestId("not-evidence");
  await expect(off).toContainText("Never opened");
  await expect(off).toContainText("Invalid: the workflow was never opened");
  await noA11yViolations(page);

  await toStep(page, 4);
  // Neither is the workflow open in the Lab: both are under "Other runs", by name.
  const measured = page.getByRole("region", { name: "Measured workflows" });
  await measured.getByTestId("other-runs").locator("summary").click();
  await expect(measured.getByTestId("other-runs")).toContainText("Never opened");
  await expect(measured.getByTestId("other-runs")).toContainText("Fix a bug");
  await expect(measured.getByTestId("other-runs")).toContainText("Invalid: the workflow was never opened");
  // The nudge's words follow the box.
  const nudge = page.getByTestId("nudge-state");
  await expect(nudge).toHaveText(/· on: the prompt tells the agent to open it/);
  // In the Lab's words, as on a repo's Measure: the thing measured is a workflow, never a "treatment".
  await page.getByRole("checkbox", { name: /^Tell the agent to open the workflow in the prompt/ }).uncheck();
  await expect(nudge).toHaveText(" · off: the workflow has to be found, as in real use");
  await expect(page.getByRole("region", { name: "Measure", exact: true })).not.toContainText(/treatment/i);
});

test("Try it: priced first, sign-in gated, a fake try shows each answer with its steps and cost, and an input becomes a draft task", async ({ page }) => {
  await open(page, 4, "lab");
  // Not signed in (Codex here): priced anyway, with no hard cap said, and "Sign In to Try".
  await page.locator(".agent-pill").click();
  await page.getByRole("radio", { name: /Codex/ }).click();
  await page.getByRole("dialog", { name: "Agent" }).getByRole("button", { name: "Close" }).click();
  const box = page.getByTestId("try-it");
  await expect(box).toBeVisible();
  await expect(box).toContainText("One try shows what it does; Measure tells you whether it helps.");
  const price = page.getByTestId("try-price");
  await expect(price).toContainText(/^≈ \$\d+\.\d\d for 1 input \(at most \$\d+\.\d\d, no hard cap\)/);
  await expect(box.getByRole("textbox", { name: "Input 1" })).toHaveAttribute("placeholder", /.{20,}/);
  await box.getByRole("button", { name: "Sign In to Try" }).click();
  await expect(page.getByRole("dialog", { name: "Agent" })).toBeVisible();
  await page.getByRole("radio", { name: /Claude Code/ }).click();
  await page.getByRole("dialog", { name: "Agent" }).getByRole("button", { name: "Close" }).click();

  // Signed in: a hard cap, the price for every input, and nothing runs before the click.
  const tries: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && /\/api\/try(\?|$)/.test(r.url())) tries.push(r.url());
  });
  await box.getByRole("textbox", { name: "Input 1" }).fill("Hi, I bought the annual plan last week and want a refund. Order 48213.");
  await box.getByRole("button", { name: /^Add Another/ }).click();
  await box.getByRole("textbox", { name: "Input 2" }).fill("Bug: clicking Save twice creates two invoices.");
  await expect(price).toContainText(/^≈ \$\d+\.\d\d for 2 inputs \(at most \$\d+\.\d\d, hard cap\)/);
  await noA11yViolations(page);
  expect(tries).toEqual([]);
  await box.getByRole("button", { name: /^Run 2 Inputs, up to \$\d+\.\d\d$/ }).click();
  const cards = box.getByTestId("try-result");
  await expect(cards).toHaveCount(2);
  await expect(page.getByTestId("try-progress")).toHaveText(/^Done · \$0\.24 spent of \$\d+\.\d\d$/, { timeout: 15_000 });
  expect(tries).toHaveLength(1);
  await expect(cards.nth(0)).toContainText("issued a full refund");
  await expect(cards.nth(0)).toContainText(/Ran \d+ of \d+ steps/);
  await expect(cards.nth(0)).toContainText("$0.12");
  await expect(cards.nth(1).locator("pre.code")).toContainText("if saving:");
  await expect(cards.nth(0).getByTestId("try-grade")).toHaveCount(0); // grading is off unless ticked
  await noA11yViolations(page);
  // The form comes back only after the answers are cleared, with the inputs kept for another go.
  await expect(box.getByRole("button", { name: /^Run 2 Inputs/ })).toHaveCount(0);
  await box.getByRole("button", { name: "Clear the Answers and Edit the Inputs" }).click();
  await expect(cards).toHaveCount(0);
  await expect(box.getByRole("textbox", { name: "Input 2" })).toHaveValue("Bug: clicking Save twice creates two invoices.");

  // On the repo's Measure page: a skill on the canvas, tried once, the input kept as a draft.
  await toStep(page, 1);
  await page.getByRole("radio", { name: /^My Repo/ }).click();
  await toStep(page, 4);
  const repoBox = page.getByTestId("try-it");
  await expect(repoBox).toBeVisible();
  await repoBox.getByRole("textbox", { name: "Input 1" }).fill("Refund ticket T-9: the customer was charged twice.");
  await repoBox.getByRole("button", { name: /^Run 1 Input, up to/ }).click();
  await expect(repoBox.getByTestId("try-result")).toContainText("issued a full refund", { timeout: 15_000 });
  await expect(repoBox.getByTestId("try-result")).toContainText(/Opened the skill|Didn't open the skill/);
  await repoBox.getByRole("button", { name: "Save as a Task" }).click();
  await expect(repoBox.getByText(/^Saved as the draft task try-refund-ticket-t-9/)).toBeVisible();
  const scenarios = (await (await page.request.get("/api/scenarios")).json()) as { id: string; check: string | null; runnable: boolean }[];
  const kept = scenarios.find((s) => s.id.startsWith("try-refund-ticket-t-9"));
  expect(kept && kept.check === null && !kept.runnable).toBe(true);
});
