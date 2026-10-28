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

test("a run on a local model names it by its label and reads as free, not against a budget", () => {
  feed = [];
  const local = { id: "local:ollama-11434-qwen3-8b", label: "qwen3:8b · ollama" };
  render(<LiveRun started={{ ...started, model: local.id, local_model: local }} onDone={() => undefined} />);
  expect(screen.getByTestId("live-local")).toHaveTextContent("On qwen3:8b · ollama (local) · free");
  expect(screen.queryByText(/local:ollama/)).toBeNull();
  expect(screen.queryByText("$0.00 of $5.00")).toBeNull();
});

test("a run on the signed-in agent still counts against its budget", () => {
  feed = [];
  render(<LiveRun started={started} onDone={() => undefined} />);
  expect(screen.getByText("$0.00 of $5.00")).toBeInTheDocument();
  expect(screen.queryByTestId("live-local")).toBeNull();
});
