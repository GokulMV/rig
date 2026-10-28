import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import type { RunEvent, Started } from "../lib/types";
import { LiveRun } from "./Results";

let feed: RunEvent[] = [];
vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  follow: (_id: number, onEvent: (e: RunEvent) => void) => {
    for (const e of feed) onEvent(e);
    return () => undefined;
  },
}));

const started: Started = { id: 3, repeats: 1, scenarios: ["a", "b"], trials: 4, model: "claude-sonnet-5-5", budget: 5, commit: null, dirty: false };

test("keep going on the pass rate reads as before", () => {
  feed = [
    { type: "extended", repeats: 2, pairs: 2, look: 1 },
    { type: "settled", reason: "decided at the stricter interval (helps)", pairs: 4, looks: 1 },
  ];
  render(<LiveRun started={started} onDone={() => undefined} />);
  expect(screen.getByText("Not decided yet at 2 pairs: added a batch (1 so far).")).toBeInTheDocument();
  expect(screen.getByText("Stopped adding pairs at 4: decided at the stricter interval (helps).")).toBeInTheDocument();
});

test("keep going on a saving says what it is still waiting for, and why it stopped", () => {
  feed = [
    { type: "extended", repeats: 6, pairs: 2, look: 1, waiting: "the saving and the pass-rate guard" },
    { type: "extended", repeats: 11, pairs: 12, look: 2, waiting: "the pass-rate guard" },
    { type: "settled", reason: "reached 92 pairs, with the pass-rate guard still undecided", pairs: 92, looks: 9 },
  ];
  render(<LiveRun started={started} onDone={() => undefined} />);
  expect(screen.getByText("Not decided yet at 12 pairs: waiting on the pass-rate guard; added a batch (2 so far).")).toBeInTheDocument();
  expect(screen.getByText("Stopped adding pairs at 92: reached 92 pairs, with the pass-rate guard still undecided.")).toBeInTheDocument();
});
