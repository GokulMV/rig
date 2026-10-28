import { plural } from "../lib/format";
import { measureBadge, useRules } from "../lib/rules";
import type { Proposed } from "../lib/types";
import { MeasureBadge } from "./MeasureBadge";

type Diff = NonNullable<Proposed["diff"]>;

/** What "With the accepted suggestions" adds to the brief over "As it is", in words: the tasks by
 * name, or why the two are the same (nothing accepted, or only diagram notes). */
export function shipDifference(accepted: number, d: Diff | null): { same: boolean; text: string; tasks: string[]; notes: string[] } {
  const tasks = (d?.task_items ?? []).map((x) => x.title);
  const notes = (d?.note_items ?? []).map((x) => x.title);
  if (!accepted) return { same: true, text: "No suggestions accepted yet, so the brief is the same either way. Accept some on Build to add them.", tasks, notes };
  if (!tasks.length)
    return {
      same: true,
      text: `Your ${plural(accepted, "accepted suggestion")} ${accepted === 1 ? "is a diagram note" : "are diagram notes"}: nothing to change in the code, so the changes in the brief are the same either way. “With” only lists ${accepted === 1 ? "it" : "them"} as notes.`,
      tasks,
      notes,
    };
  return {
    same: false,
    text: `“With the accepted suggestions” adds ${plural(tasks.length, "change")} to make${notes.length ? ` and ${plural(notes.length, "diagram note")}` : ""}:`,
    tasks,
    notes,
  };
}

/** Ship's choice of brief, with what the choice changes said under it. */
export function ShipToggle({
  source,
  onSource,
  accepted,
  diff,
}: {
  source: "repo" | "suggested";
  onSource: (s: "repo" | "suggested") => void;
  accepted: number;
  diff: Diff | null;
}) {
  const d = shipDifference(accepted, diff);
  const rules = useRules("measurability");
  // Each change with Build's badge for it (measurability), but "Brief only": the whole list is the brief.
  const badge = (measure: string | undefined, fallback: string) => {
    const b = measureBadge({ kind: "proposal", p: { measure: measure ?? fallback } }, rules);
    return b && b.id !== "brief" ? <MeasureBadge b={b} /> : null;
  };
  return (
    <div className="shiptoggle">
      <div className="segmented" role="radiogroup" aria-label="Which design" style={{ justifySelf: "start" }}>
        <button type="button" role="radio" aria-checked={source === "repo"} onClick={() => onSource("repo")}>
          As It Is
        </button>
        <button type="button" role="radio" aria-checked={source === "suggested"} onClick={() => onSource("suggested")} disabled={!accepted}>
          With the Accepted Suggestions
        </button>
      </div>
      <div className="small muted" data-testid="ship-difference" data-same={d.same}>
        <p>{d.text}</p>
        {d.same ? null : (
          <ul className="shiptoggle__list">
            {(diff?.task_items ?? []).map((t) => (
              <li key={t.id}>
                {t.title} {badge(t.measure, "brief")}
              </li>
            ))}
            {(diff?.note_items ?? []).map((t) => (
              <li key={t.id}>
                {t.title} {badge(t.measure, "note")}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
