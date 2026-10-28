import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { RIG_EXPLAIN } from "../fixtures/rigExplain";
import { api } from "../lib/api";
import { Home } from "./Home";

beforeEach(() => {
  vi.spyOn(api, "labResults").mockResolvedValue([]);
  vi.spyOn(api, "experimentsOf").mockResolvedValue([]);
  vi.spyOn(api, "rigExplain").mockResolvedValue(RIG_EXPLAIN);
});
afterEach(() => vi.restoreAllMocks());

const REPO = { id: "r1", name: "refund-desk", root: "/Users/me/code/refund-desk" } as never;

test("Home says what Rig is, and its two ways in start step 1 in that mode", async () => {
  const onStart = vi.fn();
  render(<Home repos={[REPO]} resume={null} onStart={onStart} onResume={() => undefined} onOpenRepo={() => undefined} />);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Swap One Part. Rerun With and Without. See What It Changed.");
  await userEvent.click(screen.getByRole("button", { name: "Rig a Repo" }));
  await userEvent.click(screen.getByRole("button", { name: "Rig a Workflow" }));
  expect(onStart.mock.calls).toEqual([["repo"], ["lab"]]);
  expect(screen.queryByRole("button", { name: /^Continue/ })).toBeNull();
  expect(screen.getByRole("link", { name: /How the Rig Score Works/ })).toHaveAttribute("href", "#/rig-score");
  // The example is the engine's own: 8 of 16 without, 13 of 16 with.
  expect(await screen.findByText("13 of 16 passed")).toBeInTheDocument();
  expect(screen.getByText("Illustration, Not a Real Run")).toBeInTheDocument();
  expect(await screen.findByText("No runs yet. Measure a change in step 4 and it shows here.")).toBeInTheDocument();
});

test("a returning visit can continue where it left off; an attached repo opens on step 1", async () => {
  const onResume = vi.fn();
  const onOpenRepo = vi.fn();
  render(<Home repos={[REPO]} resume={{ label: "Step 3 · Build", where: "Rig a Workflow" }} onStart={() => undefined} onResume={onResume} onOpenRepo={onOpenRepo} />);
  await userEvent.click(screen.getByRole("button", { name: "Continue: Step 3 · Build" }));
  await userEvent.click(screen.getByRole("button", { name: "Open refund-desk" }));
  expect(onResume).toHaveBeenCalledOnce();
  expect(onOpenRepo).toHaveBeenCalledWith("r1");
});

test("a real recorded run can take the illustration's place", async () => {
  render(<Home repos={[]} resume={null} onStart={() => undefined} onResume={() => undefined} onOpenRepo={() => undefined} proof={<figure>A recorded run</figure>} />);
  expect(screen.getByText("A recorded run")).toBeInTheDocument();
  expect(screen.queryByText("Illustration, Not a Real Run")).toBeNull();
});

test("the tour slot shows what it is given, and nothing without it", () => {
  const { rerender, container } = render(<Home repos={[]} resume={null} onStart={() => undefined} onResume={() => undefined} onOpenRepo={() => undefined} />);
  expect(container.querySelector("[data-slot='tour']")).toBeNull();
  rerender(<Home repos={[]} resume={null} onStart={() => undefined} onResume={() => undefined} onOpenRepo={() => undefined} tour={<button type="button">Take the tour</button>} />);
  expect(container.querySelector("[data-slot='tour']")).toContainElement(screen.getByRole("button", { name: "Take the tour" }));
});
