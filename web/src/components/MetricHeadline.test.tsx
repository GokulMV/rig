import { render, screen, within } from "@testing-library/react";

import type { RigMetric, RigScore as Rig } from "../lib/types";
import { MetricHeadline } from "./Results";
import { RigScore } from "./RigScore";

const metric: RigMetric = {
  id: "tokens",
  name: "Tokens per Solved Task",
  n: 40,
  margin_pts: 10,
  guard: "Pass rate: 32 of 40 passed with vs 32 of 40 passed without (+0 pts; at worst -7 pts, within the 10-pt margin)",
  noninferior: true,
  headline: "Tokens per Solved Task: with 21.4k vs without 44.1k (-51%, 95% interval -58% to -45%)",
};

test("Results leads a metric run with the saving and the pass rate as its guard", () => {
  render(<MetricHeadline m={metric} />);
  expect(screen.getByTestId("metric-line")).toHaveTextContent(metric.headline!);
  // The bracket wraps as one piece, never mid-interval.
  expect(screen.getByTestId("metric-line").querySelector(".nowrap")).toHaveTextContent("(-51%, 95% interval -58% to -45%)");
  expect(screen.getByTestId("metric-guard")).toHaveTextContent(/within the 10-pt margin\)$/);
  expect(screen.getByTestId("metric-headline")).not.toHaveClass("metric-head--held");
});

test("a saving not yet credited says so", () => {
  render(<MetricHeadline m={{ ...metric, noninferior: false, guard: "Pass rate: … past the 10-pt margin)" }} />);
  expect(screen.getByTestId("metric-headline")).toHaveClass("metric-head--held");
  expect(screen.getByTestId("metric-guard")).toHaveTextContent("no saving is credited until the pass rate is shown to hold");
  render(<MetricHeadline m={{ ...metric, headline: null, guard: null, missing: "unsolved" }} />);
  expect(screen.getAllByTestId("metric-line")[1]).toHaveTextContent("Tokens per Solved Task: nothing to compare yet.");
});

test("Cost on a tokens run reads as in Lift, not as unmeasured", () => {
  const rig: Rig = {
    score: 93,
    band: "works",
    tone: "positive",
    label: "Works — use it",
    reason: "Every part holds up",
    provisional: false,
    pairs: 40,
    parts: [
      { id: "lift", name: "Lift", weight: 0.6, score: 90, detail: "the cut in tokens per solved task is at least 45% (target 50%)", counted: true },
      { id: "cost", name: "Cost", weight: 0, score: null, detail: "in Lift: Tokens per Solved Task is what is measured", counted: false, folded: true },
      { id: "holds_up", name: "Holds Up", weight: 0.15, score: null, detail: "no held-out tasks", counted: false },
    ],
    gates: [],
  } as Rig;
  render(<RigScore rig={rig} />);
  const cost = screen.getByText("in Lift: Tokens per Solved Task is what is measured").closest("li")!;
  expect(within(cost).getByText("in Lift")).toBeInTheDocument();
  const held = screen.getByText("no held-out tasks").closest("li")!;
  expect(within(held).getByText("not measured")).toBeInTheDocument();
});
