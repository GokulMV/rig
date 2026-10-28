import { render, screen, within } from "@testing-library/react";

import { RIG_EXPLAIN } from "../fixtures/rigExplain";
import { api } from "../lib/api";
import { RigExplainPage } from "./RigExplain";

afterEach(() => vi.restoreAllMocks());

test("the five parts, their weights adding up to 100%, the gates, the bands and the engine's worked example", async () => {
  vi.spyOn(api, "rigExplain").mockResolvedValue(RIG_EXPLAIN);
  render(<RigExplainPage onMeasure={() => undefined} />);
  const parts = await screen.findAllByTestId("rigx-part");
  expect(parts.map((p) => p.querySelector("b")!.textContent)).toEqual(["Lift", "Cost", "Followed", "Holds Up", "Reliable"]);
  const weights = parts.map((p) => Number(p.querySelector(".rigx__weight")!.textContent!.replace("%", "")));
  expect(weights.reduce((a, b) => a + b, 0)).toBe(100);
  expect(screen.getByTestId("weight-bar")).toHaveAccessibleName("Weights: Lift 40%, Cost 20%, Followed 15%, Holds Up 15%, Reliable 10%");
  // Hurts and "costs more for the same result" share the cap of 20: one row, two reasons.
  const gates = document.querySelectorAll(".rigx__gates li");
  expect(gates).toHaveLength(3);
  expect(gates[0]).toHaveTextContent(/^At most ≤20It makes results worse\.Or: Both always pass/);
  expect(document.querySelectorAll(".rigx__bands li")).toHaveLength(5);
  const ex = screen.getByRole("region", { name: "Worked Example" });
  // The number is the engine's (rig_score on the example), shown as it came.
  expect(within(ex).getByText(`Rig Score · Worked Example: ${RIG_EXPLAIN.example.result.score} out of 100.`)).toBeInTheDocument();
  expect(within(ex).getByTestId("rig-formula")).toHaveTextContent(RIG_EXPLAIN.example.result.formula!.text);
  expect(within(ex).queryByRole("link", { name: "How Is This Scored?" })).toBeNull();
});
