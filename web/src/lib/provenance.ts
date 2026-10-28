import type { LabWorkflow, Validity } from "./types";

/** Where a workflow's number comes from, in the same words everywhere (learned-priors):
 * "measured n=…" (this workflow, measured), "estimated from N valid runs" (similar valid runs
 * moved the guess) or "guess from shape" (too few valid pairs, or none). */
export interface Provenance {
  kind: "measured" | "learned" | "shape";
  /** The badge. */
  text: string;
  /** What lies behind it, for a tooltip. */
  title: string;
}

function runs(n: number) {
  return `${n} valid run${n === 1 ? "" : "s"}`;
}

/** Similar valid runs moved the guess: enough valid pairs (an older engine sends no basis). */
export function isLearned(wf: LabWorkflow): boolean {
  const l = wf.learned;
  return !!l && (l.basis ?? "learned") === "learned" && l.runs > 0;
}

/** Points expected: this workflow's own measurement, else what similar valid runs taught
 * where there are enough, else the guess. The number always matches provenance()'s badge. */
export function expected(wf: LabWorkflow): number {
  if (wf.proven) return Math.round(wf.proven.diff_pts * 10) / 10;
  return isLearned(wf) ? (wf.learned?.prior ?? wf.prior) : wf.prior;
}

export function provenance(wf: LabWorkflow): Provenance {
  const p = wf.proven;
  if (p) {
    return { kind: "measured", text: `measured n=${p.pairs}`, title: `${p.pairs} pairs on ${p.bench}, kept in this workflow's PROVEN.md` };
  }
  const l = wf.learned;
  if (l && isLearned(wf)) {
    return {
      kind: "learned",
      text: `estimated from ${runs(l.runs)}`,
      title: `${l.pairs} valid pairs of similar workflows moved the guess of ${l.guess} pts.${l.ignored ? ` ${l.ignored} more ignored: not evidence.` : ""}`,
    };
  }
  const why: string[] = ["Worked out from the workflow's steps, loops and rules; no run has measured it yet."];
  if (l && l.runs > 0) why.push(`${l.pairs} valid pairs of similar runs so far; ${l.need_pairs ?? "more"} needed before they move it.`);
  if (l?.ignored) why.push(`${l.ignored} similar run${l.ignored === 1 ? "" : "s"} ignored: not evidence (never opened, broken check, or nothing to win or lose).`);
  return { kind: "shape", text: "guess from shape", title: why.join(" ") };
}

/** The number, with ≈ when it is only a guess. */
export function expectedText(wf: LabWorkflow): string {
  const n = expected(wf);
  return `${wf.proven || isLearned(wf) ? "" : "≈ "}${n > 0 ? "+" : ""}${n}`;
}

/** Results that aren't evidence keep their place in lists, with this badge, and stay off charts. */
export function isEvidence(v: Validity | null | undefined): boolean {
  return !v || v.status === "valid";
}

/** What a workflow's number was the last time it was shown: to say why it moved. */
export interface Seen {
  n: number;
  runs: number;
  pairs: number;
}

export function seenOf(wf: LabWorkflow): Seen {
  return { n: expected(wf), runs: wf.learned?.runs ?? 0, pairs: wf.learned?.pairs ?? 0 };
}

/** The same workflow gets the same number (learned-priors); when it moved since it was last shown
 * because a new valid run was learned from, say so. Null when it didn't move, or an edit moved it. */
export function changeNote(prev: Seen | undefined, wf: LabWorkflow): string | null {
  if (!prev) return null;
  const now = seenOf(wf);
  if (now.n === prev.n) return null;
  const more = now.runs - prev.runs;
  if (more > 0) return `updated: learned from ${more} new run${more === 1 ? "" : "s"}`;
  if (now.pairs > prev.pairs) return `updated: learned from ${now.pairs - prev.pairs} new valid pairs`;
  return null;
}
