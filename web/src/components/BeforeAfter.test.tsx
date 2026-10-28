import { act, fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import RULES from "../fixtures/rules.json";
import { api } from "../lib/api";
import { measureBadge, setRules } from "../lib/rules";
import type { BeforeAfterCompare, BeforeAfterRefs, ExperimentDetail, MeasureRules, Proposal } from "../lib/types";
import { armNames, Result, Trials } from "./Results";
import { BeforeAfterPicker, defaultAfter } from "./RunChoice";
import { SuggestionsPanel } from "./SuggestionsPanel";

const M = RULES.measurability as MeasureRules;
const W = M.before_after;

const refs = (dirty: boolean): BeforeAfterRefs => ({
  git: true,
  head: { sha: "a".repeat(40), short: "aaaaaaa", branch: "main", subject: "v1" },
  branches: [
    { name: "main", sha: "a".repeat(40), short: "aaaaaaa", subject: "v1", current: true },
    { name: "split-refunds", sha: "b".repeat(40), short: "bbbbbbb", subject: "Split the limits out", current: false },
  ],
  commits: [
    { sha: "a".repeat(40), short: "aaaaaaa", subject: "v1" },
    { sha: "c".repeat(40), short: "ccccccc", subject: "v0" },
  ],
  dirty,
});

const side = (label: string, sha: string | null) => ({ sha, short: sha?.slice(0, 7) ?? null, ref: null, label, subject: "", working_tree: sha === null });

const compared = (same: boolean): BeforeAfterCompare => ({
  base: side("HEAD (aaaaaaa)", "a".repeat(40)),
  after: side("split-refunds (bbbbbbb)", "b".repeat(40)),
  files: same ? [] : ["limits.py", "refunds.py"],
  n_files: same ? 0 : 2,
  name: "HEAD (aaaaaaa) → split-refunds (bbbbbbb)",
  same,
  says: same ? "split-refunds (bbbbbbb) has the same code as HEAD (aaaaaaa), so a run would measure nothing." : "Before: the code at HEAD (aaaaaaa). After: the code at split-refunds (bbbbbbb).",
  files_text: same ? "" : "2 files differ",
});

afterEach(() => vi.restoreAllMocks());

test("a split or merge suggestion is measured before and after, not 'coming soon'", () => {
  const b = measureBadge({ kind: "proposal", p: { measure: "before_after" } }, M)!;
  expect(b.says).toMatch(/make the change on a branch \(or leave it uncommitted\)/);
  expect(b.says).not.toMatch(/coming soon/);
  expect(M.states.app.says).not.toMatch(/coming soon/);
});

const proposal = (id: string, measure: string, state: Proposal["state"] = "open"): Proposal => ({
  id,
  title: `Suggestion ${id}`,
  kind: measure === "before_after" ? "split" : "check",
  targets: [],
  why: "why",
  what: "what",
  impact: {},
  effort: "S",
  evidence: [],
  delta: {},
  source: "rules",
  state,
  measure,
});

test("a suggestion that changes the code has Measure it, which hands Measure that suggestion", async () => {
  setRules("measurability", M);
  vi.spyOn(api, "suggestions").mockResolvedValue({
    proposals: [proposal("split", "before_after"), proposal("brief", "brief"), proposal("gone", "before_after", "dismissed")],
    review: { state: "idle" },
  });
  vi.spyOn(api, "buildSpec").mockReturnValue(new Promise(() => undefined));
  const onMeasure = vi.fn();
  render(<SuggestionsPanel agent={null} preview={null} names={new Map()} onPreview={() => undefined} onChanged={() => undefined} onMeasure={onMeasure} />);
  await act(async () => undefined);
  // Only the open (or accepted) one that changes the code: a brief item has nothing to run, and a
  // dismissed one isn't on the table.
  const links = screen.getAllByRole("button", { name: W.measure_it });
  expect(links).toHaveLength(1);
  expect(links[0].closest("[data-prop]")).toHaveAttribute("data-prop", "split");
  fireEvent.click(links[0]);
  expect(onMeasure).toHaveBeenCalledWith(expect.objectContaining({ id: "split", title: "Suggestion split" }));
  expect(W.for.replace("{title}", "Suggestion split")).toBe(
    "Measuring “Suggestion split”: pick the branch, commit or uncommitted changes that make it as the After side.",
  );
  setRules("measurability", null);
});

test("the after side starts on the uncommitted changes, else the newest other branch", () => {
  expect(defaultAfter(refs(true))).toBeNull();
  expect(defaultAfter(refs(false))).toBe("split-refunds");
  expect(defaultAfter({ git: false, says: "x" })).toBeNull();
});

test("the picker says plainly that Rig doesn't write the change, and what the run compares", async () => {
  vi.spyOn(api, "beforeAfterRefs").mockResolvedValue(refs(false));
  const ask = vi.spyOn(api, "beforeAfterCompare").mockResolvedValue(compared(false));
  const onChange = vi.fn();
  const onCompare = vi.fn();
  const { rerender } = render(<BeforeAfterPicker words={W} value={null} onChange={onChange} onCompare={onCompare} />);
  expect(screen.getByTestId("ba-lead")).toHaveTextContent("Make the change on a branch (or leave it uncommitted), then measure it against the commit before.");
  await act(async () => undefined);
  expect(onChange).toHaveBeenCalledWith({ base: "HEAD", after: "split-refunds" });
  rerender(<BeforeAfterPicker words={W} value={{ base: "HEAD", after: "split-refunds" }} onChange={onChange} onCompare={onCompare} />);
  await act(async () => undefined);
  expect(ask).toHaveBeenCalledWith("HEAD", "split-refunds");
  expect(onCompare).toHaveBeenLastCalledWith(expect.objectContaining({ same: false }));
  expect(screen.getByTestId("ba-compare")).toHaveTextContent("Before: the code at HEAD (aaaaaaa). After: the code at split-refunds (bbbbbbb).");
  expect(screen.getByTestId("ba-files")).toHaveTextContent("2 files differ");
  // The current branch is HEAD, so it isn't listed twice; the working tree is always offered.
  const after = screen.getByLabelText(W.after) as HTMLSelectElement;
  expect([...after.options].map((o) => o.value)).toEqual(["__working__", "split-refunds", "c".repeat(40), "HEAD"]);
  fireEvent.change(after, { target: { value: "__working__" } });
  expect(onChange).toHaveBeenLastCalledWith({ base: "HEAD", after: null });
});

test("the same code both ways is a warning, and no run can be started on it", async () => {
  vi.spyOn(api, "beforeAfterRefs").mockResolvedValue(refs(false));
  vi.spyOn(api, "beforeAfterCompare").mockResolvedValue(compared(true));
  const onCompare = vi.fn();
  render(<BeforeAfterPicker words={W} value={{ base: "HEAD", after: "main" }} onChange={() => undefined} onCompare={onCompare} />);
  await act(async () => undefined);
  expect(screen.getByTestId("ba-compare")).toHaveClass("notice--warning");
  expect(screen.getByTestId("ba-compare")).toHaveTextContent("so a run would measure nothing");
  expect(onCompare).toHaveBeenLastCalledWith(expect.objectContaining({ same: true }));
});

test("a repo with no commit says why there is nothing to measure before and after", async () => {
  vi.spyOn(api, "beforeAfterRefs").mockResolvedValue({ git: false, says: W.not_git });
  render(<BeforeAfterPicker words={W} value={null} onChange={() => undefined} onCompare={() => undefined} />);
  await act(async () => undefined);
  expect(screen.getByTestId("ba-not-git")).toHaveTextContent("isn't a git repo with a commit");
});

const detail = (ba: ExperimentDetail["before_after"]): ExperimentDetail => ({
  id: 9,
  treatment_name: "HEAD (aaaaaaa) → split-refunds (bbbbbbb)",
  treatment_kind: "before_after",
  treatment_hash: "a",
  model: "claude-sonnet-5-5",
  repeats: 2,
  budget_usd: 5,
  status: "done",
  created_at: "2026-10-28",
  spent_usd: 1,
  before_after: ba,
  summary: {
    headline: { n_pairs: 2, pass_with: 1, pass_without: 0.5, diff: 0.5, ci_low: -0.2, ci_high: 1 },
    verdict: "inconclusive",
    mde: 0.5,
    required_pairs: null,
    by_kind: {},
    synthetic: null,
    errored: 0,
    broken: 0,
    total: 4,
    unreliable: false,
    cost_with: 0.5,
    cost_without: 0.5,
  },
  trials: [
    { scenario_id: "t", kind: "typical", arm: "with", repeat: 0, outcome: "pass", tokens_in: 1, tokens_out: 1, cost_usd: 0.1, duration_s: 1, items_right: null, items_total: null },
    { scenario_id: "t", kind: "typical", arm: "without", repeat: 0, outcome: "fail", tokens_in: 1, tokens_out: 1, cost_usd: 0.1, duration_s: 1, items_right: null, items_total: null },
  ],
});

test("a before/after run names its arms After and Before, and says what after and before are", () => {
  setRules("measurability", M);
  const { base, after, files, n_files } = compared(false);
  const ba = { base, after, files, n_files };
  expect(armNames(detail(ba), W)).toMatchObject({ with: "After", without: "Before", card: "before vs after" });
  expect(armNames(detail(null), W)).toMatchObject({ with: "With", without: "Without", key: null });
  render(<Result detail={detail(ba)} />);
  expect(screen.getByTestId("arms-key")).toHaveTextContent('Before vs after: "after" is the code at split-refunds (bbbbbbb), "before" the code at HEAD (aaaaaaa).');
  expect(screen.getByText("After")).toBeInTheDocument();
  expect(screen.getByText("Before")).toBeInTheDocument();
  render(<Trials detail={detail(ba)} />);
  expect(screen.getAllByRole("cell").map((c) => c.textContent)).toEqual(expect.arrayContaining(["after", "before"]));
  setRules("measurability", null);
});
