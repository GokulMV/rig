import type { LabResult, LocalRun, RigScore, Verdict } from "./types";
import { usd, VERDICT_LABEL } from "./format";

const VERDICT_TONE: Record<NonNullable<RigScore["verdict"]>["id"], Verdict> = { helps: "helps", doesnt: "hurts", cant: "inconclusive" };

/** What a trial came to, in words: "timed out" for a fail the agent ran out of time on. */
export function outcomeWord(t: { outcome: string; timed_out?: boolean }): string {
  return t.timed_out ? "timed out" : t.outcome;
}

/** The verdict word for a result: the engine's plain verdict when it has one, else from the
 * score's band, so the two never disagree. */
export function verdictWord(rig: RigScore | null | undefined, verdict: string | null | undefined): { word: string; tone: Verdict } {
  const v = (verdict && verdict in VERDICT_LABEL ? verdict : "inconclusive") as Verdict;
  // The engine's plain verdict, when the result carries one: Helps / Doesn't Help / Can't Tell Yet.
  if (rig?.verdict) return { word: rig.verdict.word, tone: VERDICT_TONE[rig.verdict.id] };
  switch (rig?.band) {
    case "not_evidence":
      return { word: "Not Evidence", tone: "inconclusive" };
    case "not_proven":
      return { word: "Not Proven", tone: "inconclusive" };
    case "doesnt":
      return v === "hurts" ? { word: "Hurts", tone: "hurts" } : { word: "Doesn't Help", tone: "hurts" };
    case "works":
    case "works_but":
    case "helps_but":
      return { word: "Helps", tone: "helps" };
    default:
      return { word: VERDICT_LABEL[v], tone: v };
  }
}

/** A run's treatment id as people read it: "owner__repo__skill" -> "skill (owner/repo)". */
export function humanName(id: string): string {
  const parts = id.split("__");
  if (parts.length === 3 && parts.every(Boolean)) return `${parts[2]} (${parts[0]}/${parts[1]})`;
  return id;
}

/** The model a run ran on, as people read it: a local model by its label, else the model id. */
export function modelText(r: { model: string; local_model?: LocalRun | null }): string {
  return r.local_model ? `${r.local_model.label} (local)` : r.model;
}

/** Is this Lab result a run of the workflow `wfId` (any agent's form of it)? */
export function ofWorkflow(r: Pick<LabResult, "workflow_id" | "treatment">, wfId: string): boolean {
  if (r.workflow_id) return r.workflow_id === wfId;
  const stem = `workflow-${wfId}`;
  return r.treatment === stem || ["codex", "gemini-cli", "opencode"].some((a) => r.treatment === `${stem}-${a}`);
}

/** "$2.90 of $2.00 · went over before the budget cap existed". */
export function spentText(spent: number, budget: number | null | undefined, over?: { note: string } | null): string {
  if (budget == null) return usd(spent);
  return `${usd(spent)} of ${usd(budget)}${over ? ` · ${over.note}` : ""}`;
}

/** A run's status in words (the engine's trial-budget status_words), for rows that don't carry
 * status_text: never the raw value. */
const STATUS_WORDS: Record<string, string> = {
  pending: "Waiting to start",
  running: "Running",
  done: "Done",
  stopped: "Stopped",
  stopped_budget: "Stopped at the budget",
  failed_preflight: "Couldn't start: a check passed before the agent did anything",
  error: "Couldn't run",
};

export function statusText(status: string, given?: string | null): string {
  if (given) return given;
  const s = STATUS_WORDS[status];
  if (s) return s;
  const plain = status.replace(/_/g, " ");
  return plain.charAt(0).toUpperCase() + plain.slice(1);
}

type Adherence = NonNullable<LabResult["adherence"]>;

/** Did the "with" trials follow the workflow, in one line (the same words on a bench's result and
 * on the run's own page). */
export function adherenceText(a: Adherence): string {
  const parts = [
    a.read
      ? `Followed the whole workflow in ${a.followed} of the ${a.read} "with" ${a.read === 1 ? "trial" : "trials"} whose logs could be read`
      : "No session logs to check it followed the workflow",
  ];
  if (a.skipped?.length) parts.push(`skipped (of those ${a.read}): ${a.skipped.map((x) => `${x.step} in ${x.trials}`).join(", ")}`);
  else if (a.missing.length) parts.push(`skipped in at least one: ${a.missing.join(", ")}`);
  if (a.wrong_model.length) parts.push(a.wrong_model.join("; "));
  if (a.loop_broken) parts.push(`loop limit broken in ${a.loop_broken}`);
  if (a.not_opened) parts.push(`never opened the workflow in ${a.not_opened}`);
  return parts.join(" · ");
}

/** Every "with" trial whose logs could be read followed the whole workflow. */
export function adhered(a: Adherence): boolean {
  return !!a.read && a.followed === a.read;
}
