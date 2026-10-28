import { act, fireEvent, render, renderHook, screen, within } from "@testing-library/react";
import { useEffect } from "react";
import { vi } from "vitest";

import { api } from "../lib/api";
import type { MetricPlan, TreatmentItem } from "../lib/types";
import { type Change, ChangePicker, configChange, measuresNothing, METRIC_FALLBACK, MetricPicker, useMetric, useMetricChoice } from "./RunChoice";

const item = (over: Partial<TreatmentItem>): TreatmentItem => ({
  name: "CLAUDE.md",
  description: "",
  path: "/r/CLAUDE.md",
  evidence: null,
  source: "repo",
  kind: "instructions",
  compare: "same",
  compare_text: "This is the CLAUDE.md both arms already have, so a run would measure nothing.",
  file: "CLAUDE.md",
  text: "Run the tests.\n",
  ...over,
});

const changes = (): Change[] => [
  { path: "/s/tdd", name: "tdd", kind: "skill" },
  configChange(item({})),
  configChange(item({ name: "lint", path: "/r/.claude/hooks/lint", kind: "hook", compare: "hook", compare_text: "With: its hooks are merged" })),
  configChange(item({ name: "docs", path: "/u/docs", kind: "mcp", source: "user", compare: "mcp", compare_text: "With: the server is added" })),
];

test("a config is labelled by where it is and what a run of it compares", () => {
  expect(configChange(item({ compare: "edited" })).name).toBe("CLAUDE.md · in repo, edited, not committed");
  expect(configChange(item({ compare: "new" })).name).toBe("CLAUDE.md · in repo, not committed");
  expect(configChange(item({ compare: "same" })).name).toBe("CLAUDE.md · in repo, same in both arms");
  expect(configChange(item({ name: "claude-md-edit", source: "draft", compare: "replaces" })).name).toBe("claude-md-edit · your edited copy");
  expect(measuresNothing(configChange(item({ compare: "same" })))).toBe(true);
  expect(measuresNothing(configChange(item({ compare: "edited" })))).toBe(false);
});

test("the change picker groups skills, instructions, hooks and MCP servers, and says what each arm gets", () => {
  const onChange = vi.fn();
  const { rerender } = render(<ChangePicker changes={changes()} value="/s/tdd" onChange={onChange} onSaved={async () => undefined} />);
  const select = screen.getByLabelText("Change to measure");
  const groups = within(select).getAllByRole("group").map((g) => g.getAttribute("label"));
  expect(groups).toEqual(["Skills", "Instructions (CLAUDE.md, AGENTS.md)", "Hooks", "MCP Servers"]);
  expect(screen.queryByTestId("change-compare")).toBeNull(); // a skill: nothing to say
  fireEvent.change(select, { target: { value: "/r/.claude/hooks/lint" } });
  expect(onChange).toHaveBeenCalledWith("/r/.claude/hooks/lint");
  rerender(<ChangePicker changes={changes()} value="/r/.claude/hooks/lint" onChange={onChange} onSaved={async () => undefined} />);
  expect(screen.getByTestId("change-compare")).toHaveTextContent("With: its hooks are merged");
  expect(screen.queryByTestId("instructions-draft")).toBeNull();
  // The committed CLAUDE.md: a warning, and the editor opens on it.
  rerender(<ChangePicker changes={changes()} value="/r/CLAUDE.md" onChange={onChange} onSaved={async () => undefined} />);
  expect(screen.getByTestId("change-compare")).toHaveClass("notice--warning");
  expect(screen.getByTestId("instructions-draft")).toHaveAttribute("open");
  expect(screen.getByLabelText("Edited CLAUDE.md")).toHaveValue("Run the tests.\n");
});

test("an edited copy is saved, then picked", async () => {
  const saved = vi.spyOn(api, "saveInstructions").mockResolvedValue({ path: "/r/.proving-ground/treatments/claude-md-edit", name: "claude-md-edit", file: "CLAUDE.md" });
  const onSaved = vi.fn(async () => undefined);
  render(<ChangePicker changes={changes()} value="/r/CLAUDE.md" onChange={() => undefined} onSaved={onSaved} />);
  const button = screen.getByRole("button", { name: "Save the Copy and Measure It" });
  expect(button).toBeDisabled(); // unchanged: nothing to measure
  fireEvent.change(screen.getByLabelText("Edited CLAUDE.md"), { target: { value: "Run the tests. Say less." } });
  await act(async () => {
    fireEvent.click(button);
  });
  expect(saved).toHaveBeenCalledWith({ text: "Run the tests. Say less.", file: "CLAUDE.md" });
  expect(onSaved).toHaveBeenCalledWith("/r/.proving-ground/treatments/claude-md-edit");
});

const GUARD = "The pass rate is the guard: until its 95% interval shows it is at most 10 pts worse, no saving is credited.";

test("the metric picker names each metric and the guard", () => {
  const onChange = vi.fn();
  const { rerender } = render(<MetricPicker value="pass_rate" onChange={onChange} options={METRIC_FALLBACK} guardNote={GUARD} hinted={false} />);
  const radios = screen.getAllByRole("radio");
  expect(radios.map((r) => r.textContent)).toEqual(["Pass Rate", "Tokens", "Cost", "Time"]);
  expect(screen.getByRole("radio", { name: "Pass Rate" })).toHaveAttribute("aria-checked", "true");
  expect(screen.getByTestId("metric-describe")).not.toHaveTextContent("guard");
  fireEvent.click(screen.getByRole("radio", { name: "Tokens per Solved Task" }));
  expect(onChange).toHaveBeenCalledWith("tokens");
  rerender(<MetricPicker value="tokens" onChange={onChange} options={METRIC_FALLBACK} guardNote={GUARD} hinted />);
  expect(screen.getByTestId("metric-describe")).toHaveTextContent(
    `Tokens per Solved Task. Does it use fewer tokens for each task it solves, without solving fewer? Tokens are in + out as the agent reports them, cached input included. ${GUARD} Picked from your goal.`,
  );
});

test("the goal's hint is the metric until one is picked", () => {
  const { result, rerender } = renderHook(({ hint }) => useMetric(hint), { initialProps: { hint: null as "tokens" | null } });
  expect(result.current[0]).toBe("pass_rate");
  rerender({ hint: "tokens" });
  expect(result.current[0]).toBe("tokens");
  expect(result.current[2]).toBe(true);
  act(() => result.current[1]("cost"));
  rerender({ hint: "tokens" });
  expect(result.current[0]).toBe("cost");
  expect(result.current[2]).toBe(false);
});

/** The choice as Measure lays it out, in either mode: the picker, then the confirm card's lines. */
function Choice({ plan }: { plan?: MetricPlan }) {
  const { picker, confirm, onPlan } = useMetricChoice();
  useEffect(() => onPlan(plan ?? null), [plan, onPlan]);
  return (
    <>
      {picker}
      <div data-testid="confirm">{confirm}</div>
    </>
  );
}

test("one metric choice for a repo and the Lab: picked, confirmed, and the guard's pairs said once", async () => {
  vi.spyOn(api, "rigExplain").mockRejectedValue(new Error("offline")); // the fallback words
  const short: MetricPlan = {
    metric: "tokens",
    need_pairs: 39,
    planned_pairs: 3,
    enough: false,
    need_usd: 28.08,
    lines: [
      "Scored on tokens, the pass-rate guard needs about 39 pairs (≈ $28.08) before any saving can be credited.",
      "This run plans 3 pairs: at best -47 pts, so no saving can be credited. Run Full with the budget for them, or score it on the pass rate.",
    ],
  };
  const { rerender } = render(<Choice plan={short} />);
  expect(screen.getByTestId("confirm-metric")).toHaveTextContent("Scored on pass rate.");
  // The plan is for tokens: nothing to warn about on the pass rate.
  expect(screen.queryByTestId("confirm-metric-short")).toBeNull();
  fireEvent.click(screen.getByRole("radio", { name: "Tokens per Solved Task" }));
  rerender(<Choice plan={short} />);
  expect(screen.getByTestId("confirm-metric")).toHaveTextContent("Scored on tokens per solved task, with the pass rate as the guard.");
  // Shown apart from the estimate, the warning keeps the number it refers to.
  expect(screen.getByTestId("confirm-metric-short")).toHaveTextContent(`${short.lines[0]} ${short.lines[1]}`);
  expect(screen.getByTestId("confirm-metric-short").textContent!.match(/39 pairs/g)).toHaveLength(1);
});

/** The Lab's "Keep going until it's decided" line for the metric picked. */
function KeepGoing({ plan }: { plan?: MetricPlan }) {
  const { picker, confirm, onPlan, keepGoing } = useMetricChoice();
  useEffect(() => onPlan(plan ?? null), [plan, onPlan]);
  return (
    <>
      {picker}
      <p data-testid="keep-going">{keepGoing}</p>
      <div data-testid="confirm">{confirm}</div>
    </>
  );
}

test("keep going says what it waits for: zero ruled out on the pass rate, the saving and its guard on a saving", async () => {
  const words = {
    pass_rate: "adds pairs while the result is unclear, up to the budget. Stops early only when a stricter (99%) interval rules out zero.",
    tokens: "adds pairs until the saving and the pass-rate guard are both decided, up to the budget or 100 pairs.",
    cost: "c",
    time: "t",
  };
  vi.spyOn(api, "rigExplain").mockResolvedValue({ metric: { text: "", default: "pass_rate", margin_pts: 10, guard_note: "", options: METRIC_FALLBACK, keep_going: words } } as never);
  const grows: MetricPlan = {
    metric: "tokens",
    need_pairs: 39,
    planned_pairs: 2,
    enough: false,
    extends: true,
    need_usd: 9.36,
    lines: ["Scored on tokens, the pass-rate guard needs about 39 pairs.", 'This run plans 2 pairs; with "Keep going until it\'s decided" on, it adds pairs until the saving and the guard are decided.'],
  };
  const { rerender } = render(<KeepGoing plan={grows} />);
  expect(await screen.findByText(words.pass_rate)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("radio", { name: "Tokens per Solved Task" }));
  rerender(<KeepGoing plan={grows} />);
  expect(screen.getByTestId("keep-going")).toHaveTextContent(words.tokens);
  // A run that will grow toward the guard isn't warned that it can't be credited.
  expect(screen.queryByTestId("confirm-metric-short")).toBeNull();
  expect(screen.getByTestId("confirm-metric-extends")).toHaveTextContent(grows.lines[1]);
});
