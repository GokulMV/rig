import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { api } from "../lib/api";
import type { MetricPlan, RunForecast } from "../lib/types";
import { RunEstimate } from "./RunEstimate";

afterEach(() => vi.restoreAllMocks());

const NEED = "Scored on tokens, the pass-rate guard needs about 39 pairs (≈ $28.08) before any saving can be credited (if the pass rate stays put and 1 pair in 40 disagrees each way).";
const SHORT = "This run plans 3 pairs: at best the pass rate's interval would reach about -47 pts, past the -10-pt margin, so no saving can be credited. Run Full with the budget for them, or score it on the pass rate.";

const forecast = (plan: MetricPlan): RunForecast =>
  ({
    pairs: 3,
    trials: 6,
    per_trial: { with: 0.36, without: 0.36 },
    source: { with: "measured on 14 earlier trials", without: "measured on 14 earlier trials" },
    measured_trials: { with: 14, without: 14 },
    per_pair: 0.72,
    total_usd: 2.16,
    free: false,
    detect: { pairs: 3, pts: 81, base_rate: 0.5 },
    sizing: { target_pts: 25, pairs: 31, usd: 22.3, planned_pairs: 3, planned_pts: 81, enough_planned: false, enough_budget: false },
    no_better_than_pilot: null,
    model: "claude-sonnet-5-5",
    metric_plan: plan,
  }) as RunForecast;

const short: MetricPlan = { metric: "tokens", need_pairs: 39, planned_pairs: 3, enough: false, need_usd: 28.08, lines: [NEED, SHORT] };

test("on tokens the sizing is the guard's, and a run too small for it is warned before it is paid for", async () => {
  vi.spyOn(api, "runEstimate").mockResolvedValue(forecast(short));
  const onPlan = vi.fn();
  render(<RunEstimate budget={5} onMetricPlan={onPlan} request={{ pairs: 3, agent: "claude-code", repo: "r", size: "pilot", tasks: 3, metric: "tokens" }} />);
  expect(await screen.findByTestId("metric-plan", {}, { timeout: 2000 })).toHaveTextContent(NEED);
  expect(screen.getByTestId("metric-plan-planned")).toHaveTextContent(SHORT);
  expect(screen.getByTestId("metric-plan-planned")).toHaveClass("notice--warning");
  // The pass-rate lines (±81 pts, ±25 pts in 31 pairs) aren't said for a saving.
  expect(screen.queryByTestId("run-detect")).toBeNull();
  expect(screen.queryByTestId("run-sizing")).toBeNull();
  expect(screen.queryByRole("button", { name: /Set Budget/ })).toBeNull(); // a pilot can't grow
  expect(onPlan).toHaveBeenLastCalledWith(short);
});

test("a full run on tokens offers the budget the guard needs", async () => {
  vi.spyOn(api, "runEstimate").mockResolvedValue(forecast(short));
  const set = vi.fn();
  render(<RunEstimate budget={5} onSetBudget={set} request={{ pairs: 3, agent: "claude-code", repo: "r", size: "full", tasks: 3, metric: "tokens" }} />);
  fireEvent.click(await screen.findByRole("button", { name: "Set Budget to $28.08" }, { timeout: 2000 }));
  expect(set).toHaveBeenCalledWith(28.08);
});

test("with keep going on, a run short of the guard is told it grows toward it, and offered the budget for it", async () => {
  const grows: MetricPlan = {
    ...short,
    extends: true,
    lines: [NEED, 'This run plans 3 pairs; with "Keep going until it\'s decided" on, it adds pairs until the saving and the guard are decided, up to 100 pairs or the budget. The budget pays for about 6 pairs, short of the guard\'s 39.'],
  };
  vi.spyOn(api, "runEstimate").mockResolvedValue(forecast(grows));
  const set = vi.fn();
  render(<RunEstimate budget={5} canExtend onSetBudget={set} request={{ pairs: 3, agent: "claude-code", bench: "qa", size: "pilot", tasks: 3, metric: "tokens", auto: true }} />);
  expect(await screen.findByTestId("metric-plan-planned", {}, { timeout: 2000 })).toHaveTextContent(grows.lines[1]);
  expect(screen.getByTestId("metric-plan-planned")).not.toHaveClass("notice--warning");
  fireEvent.click(screen.getByRole("button", { name: "Set Budget to $28.08" }));
  expect(set).toHaveBeenCalledWith(28.08);
});
