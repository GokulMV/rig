import { axisHalfWidth, budgetPromise, goalHeading, plural, pts, usd } from "./format";

test("signed points", () => {
  expect(pts(0.18)).toBe("+18.0 pts");
  expect(pts(-0.052)).toBe("-5.2 pts");
  expect(pts(0)).toBe("0.0 pts");
  expect(pts(0.0001)).toBe("0.0 pts");
});

test("money and plurals", () => {
  expect(usd(3.5)).toBe("$3.50");
  expect(plural(1, "trial")).toBe("1 trial");
  expect(plural(1200, "trial")).toBe("1,200 trials");
});

test("axis fits the widest value in quarter steps, at most the full range", () => {
  expect(axisHalfWidth(0.05, 0.1)).toBe(0.25);
  expect(axisHalfWidth(-0.3, 0.12, 0.2)).toBe(0.5);
  expect(axisHalfWidth(null, 1.4)).toBe(1);
});

test("the budget promise says exactly what is guaranteed", () => {
  expect(budgetPromise(2, "Claude Code", true)).toBe(
    "Capped at $2.00: a pair starts only if its predicted cost fits, and Claude Code stops itself mid-trial at what is left (it can overrun by its last model call). A trial cut short counts as errored.",
  );
  expect(budgetPromise(2, "Codex", false)).toBe(
    "Won't start a pair predicted to go over $2.00. Codex can't be stopped mid-trial, so a trial that costs more than predicted can overrun $2.00 by the difference; then the run stops.",
  );
  expect(budgetPromise(2, "Qwen", true, true)).toBe("Stops at $2.00; a local model costs nothing.");
});

test("the goal box says whether it holds the saved goal or a draft", () => {
  expect(goalHeading("shop", true, false)).toBe("Saved goal for shop");
  expect(goalHeading("shop", true, true)).toBe("Draft goal for shop (unsaved)");
  expect(goalHeading("shop", false, true)).toBe("Goal for shop");
  expect(goalHeading("shop", false, false)).toBe("Goal for shop");
});
