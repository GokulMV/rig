import { changeNote, expected, expectedText, isEvidence, provenance, seenOf } from "./provenance";
import type { LabWorkflow } from "./types";

const wf = (over: Partial<LabWorkflow>): LabWorkflow =>
  ({ id: "w", name: "W", discipline: "development", origin: "starter", steps: [], loop: null, edges: [], loops: [], prior: 4.5, cost: 1, why: [], ...over }) as LabWorkflow;

test("a guess from shape when nothing valid measured it, however many runs were ignored", () => {
  const p = provenance(wf({ learned: { prior: 4.5, guess: 4.5, runs: 0, pairs: 0, basis: "shape", need_pairs: 6, ignored: 1 } }));
  expect(p.kind).toBe("shape");
  expect(p.text).toBe("guess from shape");
  expect(p.title).toMatch(/1 similar run ignored: not evidence/);
  expect(provenance(wf({})).text).toBe("guess from shape");
  expect(expectedText(wf({}))).toBe("≈ +4.5");
});

test("too few valid pairs stays the guess, and says how many it needs", () => {
  const w = wf({ learned: { prior: 4.5, guess: 4.5, runs: 1, pairs: 2, basis: "shape", need_pairs: 6, ignored: 0 } });
  expect(provenance(w).text).toBe("guess from shape");
  expect(provenance(w).title).toMatch(/2 valid pairs of similar runs so far; 6 needed/);
  expect(expected(w)).toBe(4.5);
});

test("estimated from valid runs once there are enough; an older engine without basis counts as learned", () => {
  const w = wf({ learned: { prior: 12.3, guess: 4.5, runs: 3, pairs: 41, basis: "learned", need_pairs: 6 } });
  expect(provenance(w).text).toBe("estimated from 3 valid runs");
  expect(expectedText(w)).toBe("+12.3");
  expect(provenance(wf({ learned: { prior: 8, guess: 4.5, runs: 1, pairs: 9 } })).text).toBe("estimated from 1 valid run");
});

test("measured wins, and the number is the measurement", () => {
  const w = wf({ proven: { verdict: "helps", diff_pts: 17.04, pairs: 20, bench: "qa" }, learned: { prior: 9, guess: 4.5, runs: 2, pairs: 20, basis: "learned" } });
  expect(provenance(w).text).toBe("measured n=20");
  expect(expected(w)).toBe(17);
  expect(expectedText(w)).toBe("+17");
});

test("only valid results are evidence", () => {
  expect(isEvidence(undefined)).toBe(true);
  expect(isEvidence({ status: "valid", badge: null, reason: null })).toBe(true);
  expect(isEvidence({ status: "uninformative", badge: "Uninformative: both always pass", reason: "" })).toBe(false);
});

test("a number that moved says why only when a new valid run explains it", () => {
  const before = wf({ learned: { prior: 4.5, guess: 4.5, runs: 1, pairs: 4, basis: "shape", need_pairs: 6 } });
  const after = wf({ learned: { prior: 9, guess: 4.5, runs: 2, pairs: 8, basis: "learned", need_pairs: 6 } });
  expect(changeNote(undefined, after)).toBeNull(); // first time shown
  expect(changeNote(seenOf(before), before)).toBeNull(); // the same number: nothing to say
  expect(changeNote(seenOf(before), after)).toBe("updated: learned from 1 new run");
  expect(changeNote(seenOf(before), wf({ prior: 7 }))).toBeNull(); // an edit moved it, not a run
});
