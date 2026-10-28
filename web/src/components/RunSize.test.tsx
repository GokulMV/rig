import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { api } from "../lib/api";
import type { FullSize, RunForecast } from "../lib/types";
import { RunEstimate } from "./RunEstimate";
import { fullLabel, pairsFor, RunSize } from "./RunSize";

// The engine's words (trial-budget: full_label), one per state.
const FULL: Record<FullSize["state"], FullSize> = {
  conclusive: { state: "conclusive", pairs: 31, planned_pairs: 31, pts: 25, text: "Full · 31 pairs · conclusive to ±25 pts" },
  detects: { state: "detects", pairs: 20, planned_pairs: 20, pts: 31, text: "Full · 20 pairs · tells apart ±31 pts" },
  like_pilot: { state: "like_pilot", pairs: 4, planned_pairs: 20, pts: 70, text: "Full · stops at 4 pairs, like the pilot" },
  nothing: { state: "nothing", pairs: 0, planned_pairs: 20, pts: null, text: "Full · the budget pays for no pair" },
};

test("the Full label is what the budget buys, and never says conclusive before it is priced", () => {
  expect(fullLabel(null)).toBe("Full");
  expect(fullLabel(undefined)).toBe("Full");
  for (const f of Object.values(FULL)) expect(fullLabel(f)).toBe(f.text);
  expect(Object.values(FULL).filter((f) => fullLabel(f).includes("conclusive")).map((f) => f.state)).toEqual(["conclusive"]);
});

test("each state shows on the Full choice, which still picks the size", () => {
  const onSize = vi.fn();
  const { rerender } = render(<RunSize size="pilot" onSize={onSize} full={null} />);
  const full = () => screen.getByRole("radio", { name: /^Full/ });
  expect(full()).toHaveTextContent(/^Full$/);
  for (const f of Object.values(FULL)) {
    rerender(<RunSize size="pilot" onSize={onSize} full={f} />);
    expect(full()).toHaveTextContent(f.text);
    expect(full()).toHaveAttribute("data-state", f.state);
  }
  fireEvent.click(full());
  expect(onSize).toHaveBeenCalledWith("full");
  expect(screen.getByRole("radio", { name: "Pilot · quick" })).toHaveAttribute("aria-checked", "true");
  rerender(<RunSize size="full" onSize={onSize} full={FULL.detects} disabled />);
  expect(full()).toBeDisabled();
  expect(full()).toHaveAttribute("aria-checked", "true");
});

test("a full run is at least 20 pairs, in whole repeats of the tasks", () => {
  expect(pairsFor("pilot", 5)).toBe(5);
  expect(pairsFor("full", 5)).toBe(20);
  expect(pairsFor("full", 6)).toBe(24);
  expect(pairsFor("full", 25)).toBe(25);
  expect(pairsFor("full", 0)).toBe(0);
});

test("the estimate hands the Full label up, and nothing once there is nothing to price", async () => {
  const f: RunForecast = {
    pairs: 5,
    trials: 10,
    per_trial: { with: 1.18, without: 0.05 },
    source: { with: "measured on 3 earlier trials", without: "measured on 3 earlier trials" },
    per_pair: 1.23,
    total_usd: 6.15,
    free: false,
    pairs_in_budget: 4,
    detect: { pairs: 4, pts: 70, base_rate: 0.5 },
    full: FULL.like_pilot,
    model: "claude-sonnet-5-5",
  };
  const spy = vi.spyOn(api, "runEstimate").mockResolvedValue(f);
  const onFull = vi.fn();
  const req = { pairs: 5, agent: "claude-code", bench: "bugfix", pilot_pairs: 5, full_pairs: 20 };
  const { rerender } = render(<RunEstimate budget={5} request={req} onFull={onFull} />);
  await vi.waitFor(() => expect(onFull).toHaveBeenLastCalledWith(FULL.like_pilot), { timeout: 2000 });
  expect(spy).toHaveBeenLastCalledWith({ ...req, budget: 5 });
  rerender(<RunEstimate budget={5} request={null} onFull={onFull} />);
  await vi.waitFor(() => expect(onFull).toHaveBeenLastCalledWith(null));
});
