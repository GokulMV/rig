import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { RigScore } from "./RigScore";
import { Guide, StageHead, StepNav } from "./Journey";
import { RIG_EXPLAIN } from "../fixtures/rigExplain";

test("Build's head: its own heading and purpose; guided it has Back and Next, in the workspace a named Back and action", async () => {
  const onStep = vi.fn();
  const head = (workspace: boolean) => (
    <Guide.Provider value={{ workspace }}>
      <StageHead step={3} title="Build the workflow" lead="Pick a workflow." action={{ label: "Measure this workflow", to: 4 }} onStep={onStep} />
    </Guide.Provider>
  );
  const { rerender } = render(head(false));
  expect(screen.getByRole("heading", { level: 1, name: "Build the workflow" })).toBeInTheDocument();
  expect(screen.getByText("Step 3 of 5 · Build")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Next: Measure" }));
  await userEvent.click(screen.getByRole("button", { name: "Back" }));
  rerender(head(true));
  expect(screen.queryByText(/^Step 3 of 5/)).toBeNull();
  expect(screen.queryByRole("button", { name: /^Next:/ })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Measure this workflow" }));
  // The workspace keeps a way back too, named for where it goes: Measure is never a dead end.
  await userEvent.click(screen.getByRole("button", { name: "Back to Design" }));
  expect(onStep.mock.calls).toEqual([[4], [2], [4], [2]]);
  rerender(
    <Guide.Provider value={{ workspace: true }}>
      <StageHead step={4} title="Measure what it changed" lead="Run it." action={{ label: "Get the build brief", to: 5 }} onStep={onStep} />
    </Guide.Provider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Back to Build" }));
  expect(onStep.mock.calls.at(-1)).toEqual([3]);
});

test("every Rig score card links to how it is scored", () => {
  render(<RigScore rig={RIG_EXPLAIN.example.result} compact />);
  expect(screen.getByRole("link", { name: "How Is This Scored?" })).toHaveAttribute("href", "#/rig-score");
});

test("Describe, Design and Ship keep Back and Next in the workspace too, so no page is a dead end", async () => {
  const onStep = vi.fn();
  const nav = (workspace: boolean) => (
    <Guide.Provider value={{ workspace, onSkip: () => {} }}>
      <StepNav step={1} onStep={onStep} />
    </Guide.Provider>
  );
  const { rerender } = render(nav(false));
  expect(screen.getByRole("button", { name: "Skip the Guide" })).toBeInTheDocument();
  rerender(nav(true));
  expect(screen.queryByRole("button", { name: "Skip the Guide" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Next: Design" }));
  expect(onStep.mock.calls).toEqual([[2]]);
});
