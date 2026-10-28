import { runnableKinds } from "../lib/rules";
import type { MeasureRules, MeasureState } from "../lib/types";

/** Whether Measure can test it, in a word (the measurability skill); the line why is its title. */
export function MeasureBadge({ b }: { b: (MeasureState & { id: string }) | null }) {
  if (!b) return null;
  return (
    <span className={`mbadge mbadge--${b.tone}`} title={b.says} data-measure={b.id}>
      {b.label}
    </span>
  );
}

/** The same, with its line: in the details panel, under "Can Measure test it?". */
export function MeasureLine({ b }: { b: (MeasureState & { id: string }) | null }) {
  if (!b) return null;
  return (
    <p className="small mline" data-testid="measure-line">
      <MeasureBadge b={b} /> {b.says}
    </p>
  );
}

/** Measure with nothing to run: what it can run, what on the canvas it can't and why, and the way
 * to Build (measurability: empty). `onBuild` goes there. */
export function MeasureEmpty({
  rules,
  notRunnable,
  onBuild,
}: {
  rules: MeasureRules | null;
  /** The things on the canvas Measure can't run, each with its state. */
  notRunnable: { name: string; b: (MeasureState & { id: string }) | null }[];
  onBuild: () => void;
}) {
  if (!rules) return <p className="small muted">Add a skill on Build first; then measure it here.</p>;
  const kinds = runnableKinds(rules);
  return (
    <div className="measure-empty" data-testid="measure-empty">
      <strong>{rules.empty.title}</strong>
      <p className="small">{rules.empty.lead.replace("{kinds}", kinds)}</p>
      {notRunnable.length ? (
        <ul className="measure-empty__list small">
          {notRunnable.map((x) => (
            <li key={x.name}>
              <b>{x.name}</b> <MeasureBadge b={x.b} /> <span className="muted">{x.b?.says}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <button type="button" className="btn btn--primary" onClick={onBuild}>
        {rules.empty.go}
      </button>
    </div>
  );
}
