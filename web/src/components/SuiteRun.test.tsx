import { render, screen, within } from "@testing-library/react";
import { vi } from "vitest";

import { api } from "../lib/api";
import type { RigMetric, RigScore, SuiteBench, SuiteView } from "../lib/types";
import { SuiteRun } from "./SuiteRun";

const metric = (ratio: number, headline: string, noninferior: boolean): RigMetric => ({
  id: "tokens",
  name: "Tokens per Solved Task",
  n: 0,
  margin_pts: 10,
  guard: noninferior ? "Pass rate: 40 of 40 passed with vs 40 of 40 passed without (+0 pts; at worst -9 pts, within the 10-pt margin)" : "Pass rate: …",
  noninferior,
  headline,
  ratio,
});

const rig = (m: RigMetric | undefined, verdict: "helps" | "cant"): RigScore =>
  ({
    score: 80,
    band: "works",
    tone: "positive",
    label: "Works",
    reason: "",
    provisional: false,
    pairs: 40,
    parts: [],
    gates: [],
    verdict: { id: verdict, word: verdict === "helps" ? "Helps" : "Can't Tell Yet", tone: "positive", reason: "", next: "", facts: [] },
    ...(m ? { metric: m } : {}),
  }) as RigScore;

const bench = (id: string, n: number, diff: number, m?: RigMetric): SuiteBench => ({
  bench: id,
  name: id,
  tasks: n,
  experiment: 1,
  status: "done",
  budget: 5,
  spent: 1,
  detail: null,
  diff,
  ci_low: -0.1,
  ci_high: 0.1,
  n_pairs: n,
  rig: rig(m, "cant"),
});

function view(saving: boolean): SuiteView {
  const pooled = saving ? metric(0.4, "Tokens per Solved Task: with 12.0k vs without 30.0k (-60%, 95% interval -64% to -55%)", true) : undefined;
  return {
    job: "j1",
    workflow: "Fix a bug",
    metric: saving ? "tokens" : "pass_rate",
    status: "done",
    budget: 20,
    spent: 4,
    benches: [
      bench("bugfix", 25, 0.04, saving ? metric(0.333, "", true) : undefined),
      bench("qa", 15, -0.1, saving ? metric(0.5, "", true) : undefined),
    ],
    pooled: { verdict: "inconclusive", diff: -0.02, ci_low: -0.09, ci_high: 0.09, n_pairs: 40, pass_with: 1, pass_without: 1, rig: rig(pooled, saving ? "helps" : "cant") },
  };
}

test("a suite on tokens leads its pooled result with the saving and the pass rate as the guard", async () => {
  vi.spyOn(api, "suiteGet").mockResolvedValue(view(true));
  render(<SuiteRun job="j1" onDone={() => undefined} onClose={() => undefined} />);
  const pool = await screen.findByLabelText("Across 2 Benches");
  expect(within(pool).getByTestId("metric-line")).toHaveTextContent("Tokens per Solved Task: with 12.0k vs without 30.0k (-60%, 95% interval -64% to -55%)");
  expect(within(pool).getByTestId("metric-guard")).toHaveTextContent(/^Pass rate: 40 of 40 .+within the 10-pt margin\)$/);
  // The pill is the saving's verdict, not the pass rate's "inconclusive"; the pass rate reads as such.
  const pill = pool.querySelector(".verdict-pill");
  expect(pill).toHaveTextContent(/^Helps$/);
  expect(pill).toHaveClass("verdict-pill--helps");
  expect(pool.querySelector(".result__diff")).toHaveTextContent(/^Pass rate -2 pts$/);
  // Each bench's own saving beside it, so one bench carrying the pool can be seen.
  expect(within(pool).getByText("-67% tokens · +4 pts · 25 pairs")).toBeInTheDocument();
  expect(within(pool).getByText("-50% tokens · -10 pts · 15 pairs")).toBeInTheDocument();
  expect(within(pool).getByTestId("suite-pooling")).toHaveTextContent("resamples each bench's pairs within that bench");
});

test("a suite on the pass rate reads as before", async () => {
  vi.spyOn(api, "suiteGet").mockResolvedValue(view(false));
  render(<SuiteRun job="j1" onDone={() => undefined} onClose={() => undefined} />);
  const pool = await screen.findByLabelText("Across 2 Benches");
  expect(within(pool).queryByTestId("metric-headline")).toBeNull();
  expect(within(pool).getByText("Inconclusive")).toHaveClass("verdict-pill--inconclusive");
  expect(pool.querySelector(".result__diff")).toHaveTextContent(/^-2 pts$/);
  expect(within(pool).getByText("+4 pts · 25 pairs")).toBeInTheDocument();
  expect(within(pool).getByTestId("suite-pooling")).toHaveTextContent("Benches count in proportion to their pairs");
});
