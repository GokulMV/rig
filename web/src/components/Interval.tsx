import { axisHalfWidth, pts } from "../lib/format";
import type { Verdict } from "../lib/types";

interface Props {
  low: number;
  high: number;
  diff: number;
  verdict: Verdict;
  /** Smallest difference this many pairs could detect; drawn as a band around zero. */
  mde?: number | null;
}

/** The paired difference and its 95% interval, drawn to scale against zero. */
export function Interval({ low, high, diff, verdict, mde }: Props) {
  const half = axisHalfWidth(low, high, mde);
  // Percent of the track from the left edge.
  const at = (v: number) => Math.round(((Math.max(-half, Math.min(half, v)) + half) / (2 * half)) * 1e5) / 1e3;
  const label = `Difference ${pts(diff)}, 95% interval ${pts(low)} to ${pts(high)}, axis ±${half * 100} pts`;
  return (
    <figure className={`interval interval--${verdict}`} role="img" aria-label={label}>
      <div className="interval__plot">
        {mde ? (
          <span className="interval__mde" style={{ left: `${at(-mde)}%`, width: `${at(mde) - at(-mde)}%` }} />
        ) : null}
        <span className="interval__zero" style={{ left: `${at(0)}%` }} />
        <span className="interval__bar" style={{ left: `${at(low)}%`, width: `${Math.max(0.6, at(high) - at(low))}%` }} />
        <span className="interval__point" style={{ left: `${at(diff)}%` }} />
      </div>
      <figcaption className="interval__axis" aria-hidden="true">
        <span>{`\u2212${half * 100}`}</span>
        <span style={{ left: `${at(0)}%` }}>0</span>
        <span>{`+${half * 100} pts`}</span>
      </figcaption>
    </figure>
  );
}
