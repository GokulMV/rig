import type { FullSize } from "../lib/types";

export type Size = "pilot" | "full";

/** A full run is at least 20 pairs (engine gate.trial_count), in whole repeats of the tasks. */
export function pairsFor(size: Size, tasks: number): number {
  return tasks ? Math.ceil((size === "pilot" ? tasks : Math.max(20, tasks)) / tasks) * tasks : 0;
}

/** The "Full" choice's label: what the budget buys (the engine's words, trial-budget: full_label),
 * or just "Full" until it is priced. Never a promise the budget can't keep. */
export function fullLabel(full: FullSize | null | undefined): string {
  return full?.text ?? "Full";
}

/** Pilot or full, with the full run said as what this budget buys. */
export function RunSize({
  size,
  onSize,
  full,
  disabled = false,
}: {
  size: Size;
  onSize: (s: Size) => void;
  full: FullSize | null | undefined;
  disabled?: boolean;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label="Run size">
      <button type="button" role="radio" aria-checked={size === "pilot"} disabled={disabled} onClick={() => onSize("pilot")}>
        Pilot · quick
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={size === "full"}
        disabled={disabled}
        onClick={() => onSize("full")}
        data-testid="run-size-full"
        data-state={full?.state}
      >
        {fullLabel(full)}
      </button>
    </div>
  );
}
