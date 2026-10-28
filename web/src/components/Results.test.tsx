import { render, screen, within } from "@testing-library/react";

import type { ExperimentDetail, Trial } from "../lib/types";
import { Result, Trials } from "./Results";

const trial = (arm: Trial["arm"], outcome: Trial["outcome"], right?: number, total?: number): Trial => ({
  scenario_id: "three-way-match",
  kind: "typical",
  arm,
  repeat: 0,
  outcome,
  tokens_in: 1000,
  tokens_out: 100,
  cost_usd: 0.1,
  duration_s: 10,
  items_right: right ?? null,
  items_total: total ?? null,
});

function detail(over: Partial<ExperimentDetail> = {}): ExperimentDetail {
  return {
    id: 7,
    treatment_name: "ap-checklist",
    treatment_kind: "skill",
    treatment_hash: "a",
    model: "claude-sonnet-5-5",
    repeats: 12,
    budget_usd: 10,
    status: "done",
    created_at: "2026-10-26",
    spent_usd: 2,
    validity: { status: "valid", badge: "", reason: "" } as ExperimentDetail["validity"],
    summary: {
      headline: { n_pairs: 12, pass_with: 0.75, pass_without: 0.83, diff: -0.08, ci_low: -0.4, ci_high: 0.25 },
      verdict: "inconclusive",
      mde: 0.3,
      required_pairs: null,
      by_kind: {},
      synthetic: null,
      errored: 0,
      broken: 0,
      total: 24,
      unreliable: false,
      cost_with: 1,
      cost_without: 1,
      items: {
        with: 132 / 144,
        without: 140 / 144,
        diff: -8 / 144,
        ci_low: -0.1,
        ci_high: -0.01,
        n: 12,
        right_with: 132,
        total_with: 144,
        right_without: 140,
        total_without: 144,
      },
    },
    trials: [trial("with", "fail", 11, 12), trial("without", "pass", 12, 12)],
    ...over,
  };
}

test("the run page says how many items each arm got right", () => {
  render(<Result detail={detail()} />);
  expect(screen.getByTestId("items-right")).toHaveTextContent(
    "Items right: 132 of 144 with · 140 of 144 without (-5.6 pts, 95% interval -10.0 pts to -1.0 pts)",
  );
});

test("no items line when not every pair counted items", () => {
  const d = detail();
  render(<Result detail={{ ...d, summary: { ...d.summary, items: undefined } }} />);
  expect(screen.queryByTestId("items-right")).toBeNull();
});

test("the trials table gets an Items column only when a check counted items", () => {
  const { unmount } = render(<Trials detail={detail()} />);
  const table = screen.getByRole("table");
  expect(within(table).getByRole("columnheader", { name: "Items" })).toBeInTheDocument();
  const rows = within(table).getAllByRole("row").slice(1);
  expect(rows[0]).toHaveTextContent("11/12");
  expect(rows[1]).toHaveTextContent("12/12");
  unmount();
  render(<Trials detail={detail({ trials: [trial("with", "pass"), trial("without", "fail")] })} />);
  expect(screen.queryByRole("columnheader", { name: "Items" })).toBeNull();
});

test("a timed-out trial reads 'timed out' in the trials table, with its detail on hover", () => {
  render(<Trials detail={detail({ trials: [{ ...trial("with", "fail"), timed_out: true, detail: "timed out after 600 s" }, trial("without", "pass")] })} />);
  const cells = screen.getAllByTestId("trial-outcome");
  expect(cells.map((c) => c.textContent)).toEqual(["timed out", "pass"]);
  expect(cells[0]).toHaveAttribute("title", "timed out after 600 s");
  expect(cells[0]).toHaveClass("outcome--timed-out");
});

test("a baseline check's page says what the agent alone did, and nothing about a change", () => {
  const d = { ...detail(), probe: true, probe_result: { passed: 6, total: 6, text: "The agent alone passed 6 of 6" } } as ExperimentDetail;
  render(<Result detail={d} />);
  expect(screen.getByTestId("probe-result")).toHaveTextContent("The agent alone passed 6 of 6");
  expect(screen.queryByTestId("verdict-word")).toBeNull();
  expect(screen.queryByText(/Can't Tell Yet|Inconclusive|Not enough evidence/)).toBeNull();
});
