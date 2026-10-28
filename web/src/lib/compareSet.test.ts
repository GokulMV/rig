import { describe, expect, it } from "vitest";

import { allOnModel, onModel, sessionModel } from "./compareSet";
import type { LabStep, LabWorkflow } from "./types";

const step = (id: string, kind: LabStep["kind"], model: string): LabStep => ({ id, name: id, does: id, kind, model, skills: [] });

const wf = (id: string, steps: LabStep[]): LabWorkflow => ({
  id,
  name: id,
  discipline: "development",
  origin: "starter",
  steps,
  loop: null,
  edges: [],
  loops: [],
  harness: [],
  prior: 0,
  cost: 1,
  why: [],
});

const OPUS = "claude-opus-5-5";
const SONNET = "claude-sonnet-5-5";
const HAIKU = "claude-haiku-5-5";

describe("a workflow's session model", () => {
  it("is the model most of its do steps run on, the earliest on a tie, as the engine picks it", () => {
    expect(sessionModel(wf("a", [step("p", "think", OPUS), step("d", "do", SONNET), step("c", "check", HAIKU)]))).toBe(SONNET);
    expect(sessionModel(wf("b", [step("d1", "do", HAIKU), step("d2", "do", OPUS), step("d3", "do", OPUS)]))).toBe(OPUS);
    expect(sessionModel(wf("c", [step("d1", "do", HAIKU), step("d2", "do", OPUS)]))).toBe(HAIKU);
    // No do steps: every step counts.
    expect(sessionModel(wf("d", [step("p", "think", OPUS), step("c", "check", OPUS), step("j", "judge", HAIKU)]))).toBe(OPUS);
  });

  it("moves to another model on its main steps only, leaving planning and checks as they were", () => {
    const w = wf("a", [step("p", "think", OPUS), step("d", "do", HAIKU), step("c", "check", HAIKU)]);
    const got = onModel(w, SONNET);
    expect(got.steps.map((s) => s.model)).toEqual([OPUS, SONNET, HAIKU]);
    expect(sessionModel(got)).toBe(SONNET);
    expect(w.steps[1].model).toBe(HAIKU); // the original is untouched
    expect(onModel(got, SONNET)).toBe(got); // already there: the same object
  });
});

describe("running the whole set on one model", () => {
  it("puts every pinned workflow on it, keeping the designs and the ones already there", () => {
    const on = { wf: wf("on", [step("d", "do", SONNET)]), design: { id: "x", name: "X" } };
    const off = { wf: wf("off", [step("d", "do", OPUS), step("c", "check", HAIKU)]), design: null };
    const got = allOnModel([on, off], SONNET);
    expect(got[0]).toBe(on);
    expect(got[1].wf.steps.map((s) => s.model)).toEqual([SONNET, HAIKU]);
    expect(got.map((p) => sessionModel(p.wf))).toEqual([SONNET, SONNET]);
    expect(got[1].design).toBeNull();
  });
});
