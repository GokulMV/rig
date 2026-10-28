import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { api } from "../lib/api";
import { COMPARE_KEY, readPinned } from "../lib/compareSet";
import type { BenchInfo, ComparePlan, Lab, LabStep, LabWorkflow } from "../lib/types";
import { Compare, ModelsNotice } from "./Compare";

const SONNET = "claude-sonnet-5-5";
const OPUS = "claude-opus-5-5";
const step = (id: string, kind: LabStep["kind"], model: string): LabStep => ({ id, name: id, does: id, kind, model, skills: [] });
const wf = (id: string, model: string): LabWorkflow => ({
  id,
  name: id === "a" ? "Fix a bug" : "Refactor safely",
  discipline: "development",
  origin: "starter",
  steps: [step("plan", "think", OPUS), step("fix", "do", model)],
  loop: null,
  edges: [["plan", "fix"]],
  loops: [],
  harness: [],
  prior: 0,
  cost: 1,
  why: [],
});

const ALIGN = {
  model: SONNET,
  label: "Sonnet 5.5",
  models: [SONNET, OPUS],
  extra_baseline_usd: 1.2,
  total_usd: 5.4,
  total_in_budget: 5.4,
  pairs_in_budget: 12,
  saving_usd: 2.1,
  notice: "2 models, so 2 baselines: +$1.20.",
  action: "Run All on Sonnet 5.5",
  result: "one shared baseline, ≈ $5.40 in total, saving $2.10.",
};

function plan(models: string[], align: ComparePlan["align"]): ComparePlan {
  return {
    bench: "bugfix",
    bench_name: "Bug fixing",
    size: "pilot",
    pairs: 6,
    budget: 20,
    share: 10,
    total_usd: align ? 7.5 : 5.4,
    total_in_budget: align ? 7.5 : 5.4,
    baselines: new Set(models).size,
    workflows: models.map((m, i) => ({
      id: i ? "b" : "a",
      name: i ? "Refactor safely" : "Fix a bug",
      model: m,
      pairs: 6,
      pairs_in_budget: 6,
      shared_baseline: 0,
      per_trial: { with: 0.5, without: 0.2 },
      source: null,
      budget: 10,
      predicted_usd: 3,
      predicted_in_budget: 3,
      baseline_usd: 1.2,
    })),
    align,
  };
}

const BENCH: BenchInfo = {
  id: "bugfix",
  name: "Bug fixing",
  discipline: "development",
  summary: "",
  scenarios: [{ id: "t1", kind: "typical", title: "t1", judged: false }],
  disciplines: ["development"],
  judged: false,
  calibration: null,
};

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem(COMPARE_KEY, JSON.stringify([{ wf: wf("a", SONNET) }, { wf: wf("b", OPUS) }]));
  vi.spyOn(api, "lab").mockResolvedValue({ models: { [SONNET]: { label: "Sonnet 5.5" }, [OPUS]: { label: "Opus 5.5" } }, harness: {}, templates: [] } as unknown as Lab);
  vi.spyOn(api, "benches").mockResolvedValue([BENCH]);
  vi.spyOn(api, "compareStanding").mockResolvedValue({ bench: "bugfix", bench_name: "Bug fixing", workflows: [], rank: null } as never);
});

afterEach(() => vi.restoreAllMocks());

test("the notice says what the second baseline costs and offers the one click", () => {
  const go = vi.fn();
  render(<ModelsNotice align={ALIGN} onAlign={go} />);
  expect(screen.getByTestId("compare-models")).toHaveTextContent(
    "2 models, so 2 baselines: +$1.20. A baseline on one model says nothing about another, and lifts against different baselines don't compare, so results across models are ranked by pass rate with the workflow. Run All on Sonnet 5.5: one shared baseline, ≈ $5.40 in total, saving $2.10.Run All on Sonnet 5.5",
  );
  fireEvent.click(screen.getByRole("button", { name: "Run All on Sonnet 5.5" }));
  expect(go).toHaveBeenCalledOnce();
});

test("Run All on <model> puts every pinned workflow on it, prices the set again, and can be undone", async () => {
  const priced = vi.spyOn(api, "comparePlan").mockImplementation(async (body) => {
    const models = body.workflows.map((w) => w.steps.find((s) => s.kind === "do")!.model);
    return plan(models, new Set(models).size > 1 ? ALIGN : null);
  });
  render(<Compare agent={null} working={null} onBack={() => undefined} onOpen={() => undefined} onWork={() => undefined} onShip={() => undefined} onSignIn={() => undefined} />);
  const notice = await screen.findByTestId("compare-models", {}, { timeout: 2000 });
  expect(notice).toHaveTextContent("2 models, so 2 baselines: +$1.20.");
  expect(screen.getByTestId("compare-price")).toHaveTextContent("2 baselines: one per session model.");

  fireEvent.click(screen.getByRole("button", { name: "Run All on Sonnet 5.5" }));
  // The pinned copies moved: the second one's main step, not its planning step.
  expect(readPinned().map((p) => p.wf.steps.map((s) => s.model))).toEqual([
    [OPUS, SONNET],
    [OPUS, SONNET],
  ]);
  expect(screen.getByRole("status")).toHaveTextContent("All 2 run on Sonnet 5.5 now");
  await waitFor(() => expect(screen.getByTestId("compare-price")).toHaveTextContent("One shared baseline."), { timeout: 2000 });
  expect(screen.queryByTestId("compare-models")).toBeNull();
  expect(priced.mock.lastCall![0].workflows.map((w) => w.steps[1].model)).toEqual([SONNET, SONNET]);

  fireEvent.click(screen.getByRole("button", { name: "Undo" }));
  expect(readPinned()[1].wf.steps[1].model).toBe(OPUS);
  expect(await screen.findByTestId("compare-models", {}, { timeout: 2000 })).toBeVisible();
});

test("a result from before a workflow moved model is marked, its numbers kept apart, and the standing asks by each one's model", async () => {
  // Run all on Sonnet already done: both pinned on Sonnet, b's only result is from Opus.
  window.localStorage.setItem(COMPARE_KEY, JSON.stringify([{ wf: wf("a", SONNET) }, { wf: wf("b", SONNET) }]));
  vi.spyOn(api, "comparePlan").mockResolvedValue(plan([SONNET, SONNET], null));
  const old = {
    id: 7,
    bench: "bugfix",
    status: "done",
    verdict: "inconclusive",
    diff: 0.4,
    ci_low: -0.1,
    ci_high: 0.7,
    n_pairs: 5,
    pass_with: 0.5,
    pass_without: 0.1,
    spent_usd: 1,
    reused: 0,
    treatment: "workflow-b",
    model: OPUS,
    other_model: { model: OPUS, label: "Opus 5.5", text: "On Opus 5.5, not this one: not ranked. Measure it again to rank it." },
  };
  const standing = vi.spyOn(api, "compareStanding").mockResolvedValue({
    bench: "bugfix",
    bench_name: "Bug fixing",
    workflows: [
      { id: "a", name: "Fix a bug", result: null },
      { id: "b", name: "Refactor safely", result: old },
    ],
    models: { a: SONNET, b: SONNET },
    rank: { state: "too_few", by: "rig", by_text: "Ranked by Rig score", models: [], ranked: {}, lift_vs: {}, order: [], winner: null, close: null, more_pairs: null, text: "Measure at least two of them on this bench to rank them." },
  });
  render(<Compare agent={null} working={null} onBack={() => undefined} onOpen={() => undefined} onWork={() => undefined} onShip={() => undefined} onSignIn={() => undefined} />);
  expect(await screen.findByTestId("compare-other-model", {}, { timeout: 2000 })).toHaveTextContent("On Opus 5.5, not this one: not ranked.");
  const cell = screen.getByTestId("compare-other-model").closest("[data-testid=compare-result]")!;
  expect(cell).toHaveTextContent("On Opus 5.5: +40 pts vs Direct there · 5 pairs");
  expect(cell).not.toHaveTextContent("95% interval");
  // Whole workflows go to the standing, so the engine reads each one's session model from its steps.
  expect(standing.mock.lastCall![1].map((w) => ("steps" in w ? w.steps.length : 0))).toEqual([2, 2]);
});
