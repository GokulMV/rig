import type { Verdict } from "./types";

/** A paired difference (0.18) as signed points: "+18.0 pts". */
export function pts(x: number, digits = 1): string {
  const v = x * 100;
  const s = Math.abs(v) < 0.05 ? (0).toFixed(digits) : v.toFixed(digits);
  return `${v > 0.049 ? "+" : ""}${s} pts`;
}

export function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

export function usd(x: number): string {
  return `$${x.toFixed(2)}`;
}

/** Exactly what "Stop at" guarantees (engine skill trial-budget), never more. `hardCap`: the
 * agent stops itself mid-trial at a dollar amount (Claude Code); otherwise only whole pairs
 * predicted to go over are held back. */
export function budgetPromise(budget: number, agent: string, hardCap: boolean, local = false): string {
  const b = usd(budget);
  if (local) return `Stops at ${b}; a local model costs nothing.`;
  if (hardCap)
    return `Capped at ${b}: a pair starts only if its predicted cost fits, and ${agent} stops itself mid-trial at what is left (it can overrun by its last model call). A trial cut short counts as errored.`;
  return `Won't start a pair predicted to go over ${b}. ${agent} can't be stopped mid-trial, so a trial that costs more than predicted can overrun ${b} by the difference; then the run stops.`;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;
}

/** The repo goal box's heading: whether the box holds the saved goal, a draft of it, or a first one. */
export function goalHeading(repo: string, hasSaved: boolean, dirty: boolean): string {
  if (!hasSaved) return `Goal for ${repo}`;
  return dirty ? `Draft goal for ${repo} (unsaved)` : `Saved goal for ${repo}`;
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  helps: "Helps",
  hurts: "Hurts",
  inconclusive: "Inconclusive",
};

/** Symmetric axis half-width that fits the interval and the detectable band, in 0.25 steps. */
export function axisHalfWidth(...values: (number | null | undefined)[]): number {
  const m = Math.max(0.25, ...values.filter((v): v is number => v != null).map(Math.abs));
  return Math.min(1, Math.ceil(m * 4) / 4);
}

/** The "With accepted" banner when the suggestions drawn change no parts or links: say so, rather
 * than "New 0 parts · Removed 0 parts · 0 new links". Only accepted ones are drawn (or one previewed). */
export function notesOnly(accepted: number, preview = false): string {
  if (preview) return "Previewing one open suggestion: a diagram note, so no parts or links change";
  return `${plural(accepted, "accepted suggestion")}, all diagram notes: no parts or links change`;
}

/** The "With accepted" tab's tooltip: the count in the brief's unit, then what it changes on the canvas. */
export function suggestedTitle(d: {
  added: string[];
  removed: string[];
  connected: number;
  disconnected: number;
  tasks?: number;
  notes?: number;
  open?: number;
}): string {
  const said = [
    d.tasks ? `${plural(d.tasks, "task")} from accepted suggestions (what BUILD.md lists)` : "",
    d.notes ? `${plural(d.notes, "note")} on the diagram` : "",
    d.open ? `${d.open} open, not drawn until accepted or previewed` : "",
  ].filter(Boolean);
  const canvas = [
    d.added.length ? `${plural(d.added.length, "new part")}` : "",
    d.removed.length ? `${d.removed.length} removed` : "",
    d.connected ? `${plural(d.connected, "new link")}` : "",
    d.disconnected ? `${d.disconnected} cut` : "",
  ].filter(Boolean);
  return [said.join(" · ") || "No accepted suggestions yet", canvas.length ? `On the canvas: ${canvas.join(", ")}` : ""]
    .filter(Boolean)
    .join(". ");
}
