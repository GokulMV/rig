import { describe, expect, it } from "vitest";

import { alignSteps, diffWorkflows, notShared } from "./compareDiff";
import { pin, pinState, readPinned, writePinned, COMPARE_KEY, COMPARE_MAX } from "./compareSet";
import type { LabStep, LabWorkflow } from "./types";

const step = (id: string, name: string, extra: Partial<LabStep> = {}): LabStep => ({
  id,
  name,
  does: name,
  kind: "do",
  model: "claude-sonnet-5-5",
  skills: [],
  ...extra,
});

function wf(id: string, steps: LabStep[], extra: Partial<LabWorkflow> = {}): LabWorkflow {
  const ids = steps.map((s) => s.id);
  return {
    id,
    name: id,
    discipline: "development",
    origin: "starter",
    steps,
    loop: null,
    edges: ids.slice(1).map((b, i) => [ids[i], b] as [string, string]),
    loops: [],
    harness: [],
    prior: 0,
    cost: 1,
    why: [],
    ...extra,
  };
}

const bugfix = wf("bugfix", [step("explore", "Explore the code"), step("test-first", "Write a failing test"), step("implement", "Implement"), step("run-tests", "Run the tests", { kind: "check" })], {
  loops: [["run-tests", "implement", 3]],
});

describe("aligning steps", () => {
  it("lines steps up by id, then by name", () => {
    const other = wf("other", [step("look", "Explore the code"), step("implement", "Make the change"), step("run-tests", "Run the tests", { kind: "check" })]);
    const rows = alignSteps([bugfix, other]);
    const by = Object.fromEntries(rows.map((r) => [r.key, r.steps.map((s) => s?.id ?? null)]));
    expect(by).toEqual({
      explore: ["explore", "look"], // same name, different id
      "test-first": ["test-first", null],
      implement: ["implement", "implement"], // same id, renamed
      "run-tests": ["run-tests", "run-tests"],
    });
  });

  it("never puts two steps of one workflow on the same row", () => {
    const twice = wf("twice", [step("a", "Review"), step("b", "Review")]);
    const rows = alignSteps([twice, wf("one", [step("c", "Review")])]);
    expect(rows.map((r) => r.steps.map((s) => s?.id ?? null))).toEqual([
      ["a", "c"],
      ["b", null],
    ]);
  });
});

describe("the differences", () => {
  it("lists nothing for identical workflows", () => {
    expect(diffWorkflows([bugfix, { ...bugfix, id: "copy" }])).toEqual([]);
  });

  it("says added, removed and renamed steps, model, skill, loop and rule changes, aligned by step", () => {
    const mine = wf(
      "mine",
      [
        step("explore", "Explore the code"),
        step("implement", "Make the change", { model: "claude-opus-5-5", skills: [{ path: "/s/tdd", name: "tdd" }] }),
        step("run-tests", "Run the tests", { kind: "check" }),
        step("review", "Review the diff", { kind: "think" }),
      ],
      { loops: [["run-tests", "implement", 4]], harness: ["guardrails"] },
    );
    const rows = diffWorkflows([bugfix, mine], {
      model: (m) => ({ "claude-sonnet-5-5": "Sonnet 5.5", "claude-opus-5-5": "Opus 5.5" })[m] ?? m,
      rule: (r) => (r === "guardrails" ? "Guardrails" : r),
    });
    expect(rows.map((r) => [r.kind, r.label, r.cells])).toEqual([
      ["step", "Step: Write a failing test", ["Write a failing test", null]],
      ["renamed", "Step renamed: Implement", ["Implement", "Make the change"]],
      ["model", "Model: Implement", ["Sonnet 5.5", "Opus 5.5"]],
      ["skills", "Skills: Implement", ["none", "tdd"]],
      ["step", "Step: Review the diff", [null, "Review the diff"]],
      ["loop", "Loop: Run the tests back to Implement", ["at most 3×", "at most 4×"]],
      ["rule", "Rule: Guardrails", [null, "on"]],
    ]);
  });

  it("a step removed from the middle isn't also an order change; side by side instead of in turn is", () => {
    const shorter = wf("short", [step("explore", "Explore the code"), step("implement", "Implement"), step("run-tests", "Run the tests", { kind: "check" })], {
      loops: [["run-tests", "implement", 3]],
    });
    expect(diffWorkflows([bugfix, shorter]).map((r) => r.kind)).toEqual(["step"]);
    const parallel = {
      ...shorter,
      id: "par",
      edges: [
        ["explore", "implement"],
        ["explore", "run-tests"],
      ] as [string, string][],
    };
    const order = diffWorkflows([shorter, parallel]).find((r) => r.kind === "order");
    expect(order?.cells).toEqual(["Explore the code → Implement → Run the tests", "Explore the code → Implement + Run the tests"]);
  });

  it("works across three or four: a cell per workflow, null where one hasn't got it", () => {
    const a = wf("a", [step("x", "Plan"), step("y", "Do it")]);
    const b = wf("b", [step("x", "Plan"), step("y", "Do it")], { discipline: "qa" });
    const c = wf("c", [step("y", "Do it")]);
    const rows = diffWorkflows([a, b, c], { discipline: (d) => d.toUpperCase() });
    expect(rows[0]).toEqual({ kind: "discipline", label: "Discipline", cells: ["DEVELOPMENT", "QA", "DEVELOPMENT"] });
    expect(rows[1]).toEqual({ kind: "step", label: "Step: Plan", cells: ["Plan", "Plan", null] });
    expect(notShared([a, b, c]).map((s) => [...s])).toEqual([["x"], ["x"], []]);
  });
});

describe("the compare set", () => {
  it("keeps up to four, updates a pinned copy in place, and reads an older set", () => {
    window.localStorage.clear();
    let list = pin([], bugfix, { id: "d1", name: "Design one" })!;
    expect(pinState(list, bugfix)).toBe("same");
    const edited = { ...bugfix, steps: bugfix.steps.slice(1) };
    expect(pinState(list, edited)).toBe("older");
    list = pin(list, edited, null)!;
    expect(list).toHaveLength(1);
    expect(list[0].design).toEqual({ id: "d1", name: "Design one" }); // kept when updated
    for (const id of ["b", "c", "d"]) list = pin(list, { ...bugfix, id }, null)!;
    expect(list).toHaveLength(COMPARE_MAX);
    expect(pin(list, { ...bugfix, id: "e" }, null)).toBeNull();
    writePinned(list);
    expect(readPinned().map((p) => p.wf.id)).toEqual(["bugfix", "b", "c", "d"]);
    // The Lab kept plain workflows before Compare had a page: still read, newest four.
    window.localStorage.setItem(COMPARE_KEY, JSON.stringify(["1", "2", "3", "4", "5"].map((id) => ({ ...bugfix, id }))));
    expect(readPinned().map((p) => [p.wf.id, p.design])).toEqual([
      ["2", null],
      ["3", null],
      ["4", null],
      ["5", null],
    ]);
  });
});
