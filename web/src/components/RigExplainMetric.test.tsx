import { render, screen, within } from "@testing-library/react";

import { RIG_EXPLAIN } from "../fixtures/rigExplain";
import { api } from "../lib/api";
import { RigExplainPage } from "./RigExplain";

// Its own file: the explainer's data is cached per page load (lib/rigExplain), so per module here.
afterEach(() => vi.restoreAllMocks());

test("the metric choice is explained in the engine's words when it sends them", async () => {
  const metric = {
    text: "A run can be scored on tokens, cost or time per solved task instead of the pass rate.",
    default: "pass_rate" as const,
    margin_pts: 10,
    guard_note: "The pass rate is the guard.",
    options: [
      { id: "pass_rate" as const, name: "Pass Rate", describe: "Does it solve more tasks?" },
      { id: "tokens" as const, name: "Tokens per Solved Task", describe: "Does it use fewer tokens?" },
    ],
  };
  vi.spyOn(api, "rigExplain").mockResolvedValue({ ...RIG_EXPLAIN, metric });
  render(<RigExplainPage onMeasure={() => undefined} />);
  expect(await screen.findByTestId("rigx-metric")).toHaveTextContent(metric.text);
  const sec = screen.getByRole("region", { name: "Scored on a Saving" });
  expect(within(sec).getAllByRole("listitem").map((l) => l.textContent)).toEqual([
    "Pass Rate. Does it solve more tasks?",
    "Tokens per Solved Task. Does it use fewer tokens?",
  ]);
});
