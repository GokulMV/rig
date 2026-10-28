import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { api } from "../lib/api";
import type { LabWorkflow, LocalRepoWords, TryPrice } from "../lib/types";
import { TryIt } from "./TryIt";

const words: LocalRepoWords = {
  sign_in: "{agent} · your sign-in",
  group: "Local Models (Free, on This Machine)",
  cant_run: " · can't run Claude Code",
  none: "",
  notice: "",
  nudge: "",
  confirm: "",
  start: "Start, Free",
  cost_metric: "",
  try_price: "Free: each input runs once on {label} on this machine, with {factor}× the try's time limit. Nothing is billed, so there is no budget to set.",
  try_start: "Run {inputs}, Free",
  try_note: "Each input runs once, in an isolated test copy of the repo, never in your own files. Free, on {label}; nothing runs until you click.",
  try_note_workflow: "Each input runs once, in an isolated test copy, never in your own files. Free, on {label}; nothing runs until you click.",
};
const local = { id: "local:ollama-11434-qwen3-8b", label: "qwen3:8b · ollama", base: "http://127.0.0.1:11434", model: "qwen3:8b", kind: "ollama", anthropic: true };
const wf = { id: "refunds", name: "Answer refunds", discipline: "support", steps: [] } as unknown as LabWorkflow;
const price = (p: Partial<TryPrice>): TryPrice => ({
  inputs: 1, per_input: 0, judge_per_input: 0, total_usd: 0, cap_usd: 2, hard_cap: true, source: "a local model", free: true,
  inputs_in_budget: 1, model: local.id, gradable: true, placeholder: "", discipline: "support", model_label: "qwen3:8b · ollama (local)", steps: 3, ...p,
}); // prettier-ignore

test("a Lab workflow on a local model is tried for free; checking each answer is priced and capped", async () => {
  vi.spyOn(api, "tryExample").mockResolvedValue({ kind: "support", example: "" });
  const priced = vi.spyOn(api, "tryPrice").mockImplementation(async (b) => price(b.grade ? { judge_per_input: 0.01, total_usd: 0.01 } : {}));
  render(<TryIt workflow={wf} agent={{ id: "claude-code", label: "Claude Code", ready: false }} local={local} localWords={words} timeoutFactor={3} first />);
  expect(await screen.findByTestId("try-price-local", {}, { timeout: 2000 })).toHaveTextContent(
    "Free: each input runs once on qwen3:8b · ollama on this machine, with 3× the try's time limit.",
  );
  expect(priced.mock.calls[0][0]).toMatchObject({ agent: "claude-code", local_model: local.id });
  expect(screen.queryByLabelText("Stop this try at (USD)")).toBeNull();
  // No sign-in needed, and the workflow's own note (no repo).
  expect(screen.getByRole("button", { name: "Run 1 Input, Free" })).toBeInTheDocument();
  expect(screen.getByText(/^Each input runs once, in an isolated test copy, never in your own files\. Free, on qwen3:8b · ollama/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("checkbox", { name: /Check each answer against the goal/ }));
  expect(await screen.findByLabelText("Stop this try at (USD)")).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: /^Run 1 Input, up to \$/ }, { timeout: 2000 })).toBeInTheDocument();
  expect(screen.queryByTestId("try-price-local")).toBeNull();
});
