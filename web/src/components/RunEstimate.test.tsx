import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { api } from "../lib/api";
import type { RunForecast } from "../lib/types";
import { RunEstimate } from "./RunEstimate";

const forecast = (over: Partial<RunForecast> = {}): RunForecast => ({
  pairs: 21,
  trials: 42,
  per_trial: { with: 1.18, without: 0.05 },
  source: { with: "measured on 3 earlier trials", without: "measured on 3 earlier trials" },
  measured_trials: { with: 3, without: 3 },
  per_pair: 1.23,
  total_usd: 25.83,
  free: false,
  pairs_in_budget: 4,
  detect: { pairs: 4, pts: 69, base_rate: 0.5 },
  sizing: { target_pts: 25, pairs: 31, usd: 38.5, planned_pairs: 21, planned_pts: 30, enough_planned: false, enough_budget: false },
  no_better_than_pilot: "At $5.00 this full run stops after 4 pairs: no more conclusive than the pilot.",
  model: "claude-sonnet-5-5",
  ...over,
});

test("says what it takes to tell the target from noise, sets that budget in one click, and warns when full is no better", async () => {
  vi.spyOn(api, "runEstimate").mockResolvedValue(forecast());
  const set = vi.fn();
  render(<RunEstimate budget={5} onSetBudget={set} canExtend request={{ pairs: 21, agent: "claude-code", bench: "bugfix", pilot_pairs: 4 }} />);
  expect(await screen.findByTestId("run-sizing", {}, { timeout: 2000 })).toHaveTextContent(
    `To tell a ±25 pts change from noise you need about 31 pairs ≈ $38.50. This run plans 21 pairs; with "Keep going until it's decided" on, it adds pairs up to the budget.`,
  );
  expect(screen.getByTestId("run-no-better")).toHaveTextContent("no more conclusive than the pilot");
  expect(screen.getByText(/measured on 3 earlier trials/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Set Budget to $38.50" }));
  expect(set).toHaveBeenCalledWith(38.5);
});

test("no button when more budget can't reach it, and no sizing once the budget does", async () => {
  const spy = vi.spyOn(api, "runEstimate").mockResolvedValue(forecast({ no_better_than_pilot: null }));
  const { rerender } = render(<RunEstimate budget={5} onSetBudget={() => undefined} request={{ pairs: 21, agent: "claude-code", repo: "r" }} />);
  expect(await screen.findByTestId("run-sizing", {}, { timeout: 2000 })).toHaveTextContent("This run plans 21 pairs, so at best about ±30 pts.");
  expect(screen.queryByRole("button", { name: /^Set Budget/ })).toBeNull();
  expect(screen.queryByTestId("run-no-better")).toBeNull();
  spy.mockResolvedValue(forecast({ sizing: { ...forecast().sizing!, enough_budget: true, enough_planned: true } }));
  rerender(<RunEstimate budget={40} onSetBudget={() => undefined} request={{ pairs: 31, agent: "claude-code", repo: "r" }} />);
  await vi.waitFor(() => expect(screen.queryByTestId("run-sizing")).toBeNull(), { timeout: 2000 });
});

test("a local model: no cost and no budget lines, but what its pairs can tell from noise", async () => {
  const free = forecast({
    free: true,
    pairs: 3,
    trials: 6,
    per_trial: { with: 0, without: 0 },
    per_pair: 0,
    total_usd: 0,
    pairs_in_budget: 3,
    detect: { pairs: 3, pts: 80, base_rate: 0.5 },
    sizing: { target_pts: 25, pairs: 31, usd: null, planned_pairs: 3, planned_pts: 80, enough_planned: false, enough_budget: false },
    no_better_than_pilot: null,
  });
  vi.spyOn(api, "runEstimate").mockResolvedValue(free);
  render(<RunEstimate budget={5} onSetBudget={() => undefined} request={{ pairs: 3, agent: "claude-code", repo: "r", local: true }} />);
  expect(await screen.findByTestId("run-cost", {}, { timeout: 2000 })).toHaveTextContent("A local model: no API cost (3 pairs, 6 trials, on this machine).");
  expect(screen.getByTestId("run-detect")).toHaveTextContent("With 3 pairs, an effect smaller than about ±80 pts can't be told from noise.");
  expect(screen.getByTestId("run-sizing")).toHaveTextContent("This run plans 3 pairs, so at best about ±80 pts.");
  expect(screen.queryByRole("button", { name: /^Set Budget/ })).toBeNull();
  expect(screen.queryByText(/Per pair/)).toBeNull();
  expect(screen.queryByText(/Stops at/)).toBeNull();
});

test("with keep going on, it says what the run may grow to, and hands that on for the confirm", async () => {
  const grows = {
    max_pairs: 12,
    usd: null,
    pairs_in_budget: 12,
    line: `With "Keep going until it's decided" on, it may grow to 12 pairs while it's undecided, its cap: a local model has no budget to stop it sooner.`,
  };
  const spy = vi.spyOn(api, "runEstimate").mockResolvedValue(forecast({ free: true, extends: grows }));
  const onExtends = vi.fn();
  render(
    <RunEstimate budget={5} canExtend onExtends={onExtends} request={{ pairs: 2, agent: "claude-code", repo: "r", local: true, size: "pilot", tasks: 2, auto: true }} />,
  );
  expect(await screen.findByTestId("run-extends", {}, { timeout: 2000 })).toHaveTextContent(grows.line);
  expect(spy).toHaveBeenCalledWith(expect.objectContaining({ auto: true, size: "pilot", tasks: 2 }));
  expect(onExtends).toHaveBeenLastCalledWith(grows);
});

test("with keep going off, nothing about growing", async () => {
  vi.spyOn(api, "runEstimate").mockResolvedValue(forecast());
  const onExtends = vi.fn();
  render(<RunEstimate budget={5} onExtends={onExtends} request={{ pairs: 21, agent: "claude-code", repo: "r", size: "pilot", tasks: 21 }} />);
  expect(await screen.findByTestId("run-cost", {}, { timeout: 2000 })).toBeInTheDocument();
  expect(screen.queryByTestId("run-extends")).toBeNull();
  expect(onExtends).toHaveBeenLastCalledWith(null);
});
