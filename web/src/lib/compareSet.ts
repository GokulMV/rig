import { useEffect, useState } from "react";

import type { LabWorkflow } from "./types";

/** The workflows pinned for Compare, kept in this browser (the Lab's key since before Compare had
 * its own page, so a set pinned then still opens). Up to COMPARE_MAX, as the engine allows
 * (judge-experiment: compare.max). */
export const COMPARE_KEY = "pg.lab.compare";
export const COMPARE_MAX = 4;
const CHANGED = "pg-compare-changed";

/** A pinned workflow: a copy as it was when pinned, and the design open in the Lab then. */
export interface Pinned {
  wf: LabWorkflow;
  design?: { id: string; name: string } | null;
}

function isWorkflow(x: unknown): x is LabWorkflow {
  const w = x as LabWorkflow | null;
  return !!w && typeof w.id === "string" && typeof w.name === "string" && Array.isArray(w.steps);
}

/** Read the set; an older set (plain workflows) is read as pins without a design. */
export function readPinned(): Pinned[] {
  let raw: unknown;
  try {
    const s = window.localStorage.getItem(COMPARE_KEY);
    raw = s ? JSON.parse(s) : [];
  } catch {
    return [];
  }
  if (!Array.isArray(raw)) return [];
  const out: Pinned[] = [];
  for (const x of raw) {
    if (isWorkflow(x)) out.push({ wf: x, design: null });
    else if (x && typeof x === "object" && isWorkflow((x as Pinned).wf)) out.push({ wf: (x as Pinned).wf, design: (x as Pinned).design ?? null });
  }
  // The newest kept when an older, bigger set comes back.
  return out.slice(-COMPARE_MAX);
}

export function writePinned(list: Pinned[]): void {
  try {
    if (list.length) window.localStorage.setItem(COMPARE_KEY, JSON.stringify(list.slice(0, COMPARE_MAX)));
    else window.localStorage.removeItem(COMPARE_KEY);
  } catch {
    // Not remembered in a private window, or the browser's storage is full.
  }
  window.dispatchEvent(new Event(CHANGED));
}

/** The steps a run is recorded under the model of (as the engine's session_model_of picks it, for
 * Claude Code): the "do" steps, or every step when it has none. */
function mainSteps(wf: LabWorkflow): LabWorkflow["steps"] {
  const doing = wf.steps.filter((s) => s.kind === "do");
  return doing.length ? doing : wf.steps;
}

/** The model most of the work runs on; a tie goes to the earliest step's (gate.session_model). */
export function sessionModel(wf: LabWorkflow): string | null {
  const models = mainSteps(wf).map((s) => s.model);
  let best: string | null = null;
  let most = 0;
  for (const m of models) {
    const n = models.filter((x) => x === m).length;
    if (n > most) [best, most] = [m, n];
  }
  return best;
}

/** The workflow with its session model set to `model`: its main steps run on it, the rest as they
 * were. Unchanged (the same object) when it already runs on it. */
export function onModel(wf: LabWorkflow, model: string): LabWorkflow {
  if (sessionModel(wf) === model) return wf;
  const main = new Set(mainSteps(wf).map((s) => s.id));
  return { ...wf, steps: wf.steps.map((s) => (main.has(s.id) ? { ...s, model } : s)) };
}

/** Every pinned workflow on one session model, so one baseline is shared. */
export function allOnModel(list: Pinned[], model: string): Pinned[] {
  return list.map((p) => {
    const wf = onModel(p.wf, model);
    return wf === p.wf ? p : { ...p, wf };
  });
}

/** Same steps, links, loops, rules and name: an unchanged copy of what is pinned. */
export function sameShape(a: LabWorkflow, b: LabWorkflow): boolean {
  const shape = (w: LabWorkflow) =>
    JSON.stringify([w.name, w.steps.map((s) => [s.id, s.name, s.kind, s.model, s.does, s.skills.map((k) => k.path)]), w.edges, w.loops, [...w.harness].sort()]);
  return shape(a) === shape(b);
}

/** Where this workflow stands in the set: not in it, in it as it is, or in it as an older copy. */
export function pinState(list: Pinned[], wf: LabWorkflow): "out" | "same" | "older" {
  const p = list.find((x) => x.wf.id === wf.id);
  if (!p) return "out";
  return sameShape(p.wf, wf) ? "same" : "older";
}

/** Pin a workflow (or update its copy). False when the set is full and it isn't in it. */
export function pin(list: Pinned[], wf: LabWorkflow, design: Pinned["design"]): Pinned[] | null {
  const at = list.findIndex((x) => x.wf.id === wf.id);
  if (at >= 0) return list.map((x, i) => (i === at ? { wf, design: design ?? x.design ?? null } : x));
  if (list.length >= COMPARE_MAX) return null;
  return [...list, { wf, design: design ?? null }];
}

/** The set, the same in every component that shows it (the Lab's summary and the Compare page). */
export function useCompareSet(): [Pinned[], (next: Pinned[]) => void] {
  const [list, setList] = useState<Pinned[]>(readPinned);
  useEffect(() => {
    const on = () => setList(readPinned());
    window.addEventListener(CHANGED, on);
    window.addEventListener("storage", on); // another tab
    return () => {
      window.removeEventListener(CHANGED, on);
      window.removeEventListener("storage", on);
    };
  }, []);
  return [list, writePinned];
}
