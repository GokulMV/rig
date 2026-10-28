import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { api } from "../lib/api";
import type { BenchInfo, LabWorkflow, ProbePrice } from "../lib/types";
import { BaselineCheck, baselineOf, TierChoice, tierTasks } from "./BenchTier";

const task = (id: string, tier = "standard") => ({ id, kind: "typical", title: id.toUpperCase(), judged: false, tier });
const SONNET = "claude-sonnet-5-5";
const bench = (over: Partial<BenchInfo> = {}): BenchInfo => ({
  id: "finance",
  name: "Accounts payable",
  discipline: "finance",
  summary: "",
  scenarios: [task("a"), task("b")],
  hard: [task("hard-x", "hard")],
  tiers: [
    { id: "standard", label: "Standard", tasks: 2 },
    { id: "hard", label: "Hard", tasks: 1 },
    { id: "all", label: "Standard and hard", tasks: 3 },
  ],
  baseline: {
    standard: {
      [SONNET]: {
        passed: 5,
        total: 5,
        tasks_seen: 2,
        tasks: 2,
        too_easy: true,
        model_label: "Sonnet 5.5",
        text: "Too easy for Sonnet 5.5: the agent alone passed 5 of 5",
        warn: "A workflow can't show a lift on quality here; it can only show cost or speed. Try the hard tier.",
      },
    },
  },
  disciplines: ["finance"],
  judged: false,
  calibration: null,
  ...over,
});
const wf = { id: "w", name: "W", discipline: "finance", steps: [] } as unknown as LabWorkflow;
const price: ProbePrice = {
  trials: 1,
  per_trial: 0.3125,
  source: "a first guess: nothing measured yet",
  total_usd: 0.3125,
  budget: 0.5,
  free: false,
  bench: "finance",
  tier: "hard",
  model: SONNET,
  model_label: "Sonnet 5.5",
  offer: "Check the bench first: run the agent alone on each task once, about $0.31 for 1 trial.",
};

test("a tier's tasks, standard first in all; the baseline per tier and model", () => {
  const b = bench();
  expect(tierTasks(b, "standard").map((t) => t.id)).toEqual(["a", "b"]);
  expect(tierTasks(b, "hard").map((t) => t.id)).toEqual(["hard-x"]);
  expect(tierTasks(b, "all").map((t) => t.id)).toEqual(["a", "b", "hard-x"]);
  expect(baselineOf(b, "standard", SONNET)?.too_easy).toBe(true);
  expect(baselineOf(b, "hard", SONNET)).toBeNull();
  expect(baselineOf(b, "standard", "claude-opus-5-5")).toBeNull();
  expect(baselineOf(b, "standard", null)).toBeNull();
});

test("the tier choice shows only on a bench with a hard tier", () => {
  const onTier = vi.fn();
  const { rerender } = render(<TierChoice bench={bench()} tier="standard" onTier={onTier} />);
  expect(screen.getByRole("radio", { name: "Standard · 2" })).toHaveAttribute("aria-checked", "true");
  fireEvent.click(screen.getByRole("radio", { name: "Hard · 1" }));
  expect(onTier).toHaveBeenCalledWith("hard");
  rerender(<TierChoice bench={bench({ hard: [], tiers: [{ id: "standard", label: "Standard", tasks: 2 }] })} tier="standard" onTier={onTier} />);
  expect(screen.queryByRole("radiogroup")).toBeNull();
});

test("too easy is said; the check is priced before anything runs, and starts only on a click", async () => {
  const priced = vi.spyOn(api, "probePrice").mockResolvedValue(price);
  const started = vi.spyOn(api, "probe").mockResolvedValue({
    id: 7, bench: "finance", workflow: "Baseline check", trials: 1, scenarios: ["hard-x"], model: SONNET, budget: 0.5, probe: true, price,
  });
  const onStarted = vi.fn();
  const probe = { agent: "claude-code", workflow: wf, local_model: null };
  const { rerender } = render(<BaselineCheck bench={bench()} tier="standard" model={SONNET} probe={probe} ready onStarted={onStarted} />);
  expect(screen.getByTestId("baseline-text")).toHaveTextContent("Too easy for Sonnet 5.5: the agent alone passed 5 of 5.");
  rerender(<BaselineCheck bench={bench()} tier="hard" model={SONNET} probe={probe} ready onStarted={onStarted} />);
  expect(screen.queryByTestId("baseline-text")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /Check the Bench First/ }));
  expect(await screen.findByText(price.offer)).toBeInTheDocument();
  expect(priced).toHaveBeenCalledWith({ bench: "finance", tier: "hard", ...probe });
  expect(started).not.toHaveBeenCalled();
  expect(screen.getByText(/It stops at \$0\.50\./)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Run the Check, up to $0.50" }));
  await vi.waitFor(() => expect(onStarted).toHaveBeenCalled());
  expect(started).toHaveBeenCalledWith({ bench: "finance", tier: "hard", ...probe, budget: 0.5 });
});

test("signed out, the check can be priced but not run", async () => {
  vi.spyOn(api, "probePrice").mockResolvedValue(price);
  render(<BaselineCheck bench={bench()} tier="hard" model={SONNET} probe={{ agent: "claude-code", workflow: wf, local_model: null }} ready={false} onStarted={() => undefined} />);
  fireEvent.click(screen.getByRole("button", { name: /Check the Bench First/ }));
  expect(await screen.findByRole("button", { name: "Run the Check, up to $0.50" })).toBeDisabled();
});
