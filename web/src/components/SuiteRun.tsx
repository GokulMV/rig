import { useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import { verdictWord } from "../lib/evidence";
import { VERDICT_LABEL } from "../lib/format";
import type { RigMetric, SuiteView, Verdict } from "../lib/types";
import { MetricHeadline } from "./Results";
import { RigBadge, RigScore } from "./RigScore";

function pts(x: number | null | undefined) {
  if (x == null) return "–";
  const v = Math.round(x * 100);
  return `${v > 0 ? "+" : ""}${v}`;
}

/** A bench's own saving, with ÷ without as a change: 0.33 → "-67%". */
function change(m: RigMetric | undefined) {
  if (m?.ratio == null) return null;
  const v = Math.round((m.ratio - 1) * 100);
  return `${v >= 0 ? "+" : ""}${v}% ${m.name.split(" ")[0].toLowerCase()}`;
}

const STATE: Record<string, string> = {
  queued: "waiting",
  running: "running",
  done: "done",
  stopped: "stopped",
  skipped: "skipped",
  error: "failed",
};

/** One workflow across several benches: per-bench progress, then one pooled result. */
export function SuiteRun({ job, onDone, onClose }: { job: string; onDone: () => void; onClose: () => void }) {
  const [view, setView] = useState<SuiteView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const live = !view || view.status === "running" || view.status === "stopping";

  useEffect(() => {
    if (!live) {
      onDone();
      return;
    }
    let off = false;
    const tick = () =>
      api.suiteGet(job).then(
        (v) => !off && setView(v),
        (e) => !off && setError(e instanceof ApiError ? e.message : String(e)),
      );
    void tick();
    const t = setInterval(tick, 1500);
    return () => {
      off = true;
      clearInterval(t);
    };
  }, [job, live, onDone]);

  if (!view) return error ? <p className="notice notice--error small">{error}</p> : <p className="small muted" role="status">Starting…</p>;
  const p = view.pooled;
  const n = view.benches.length;
  // On a saving the pooled saving leads, the pooled pass rate is its guard (rig-score: Metric, Suites).
  const saving = p.rig?.metric;
  const pill = saving ? verdictWord(p.rig, p.verdict) : null;
  return (
    <section aria-label="Suite run">
      {error ? <p className="notice notice--error small">{error}</p> : null}
      <ul className="results">
        {view.benches.map((b) => (
          <li key={b.bench} className="result">
            <div className="result__top">
              <b>{b.name}</b>
              <span className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
                {b.rig && b.status === "done" ? <RigBadge score={b.rig.score} tone={b.rig.tone} provisional={b.rig.provisional} label={b.rig.label} /> : null}
                <span className="small muted">{STATE[b.status]}</span>
              </span>
            </div>
            {b.detail ? <div className="small adh">{b.detail}</div> : null}
          </li>
        ))}
      </ul>
      {live ? (
        <div className="row" style={{ gap: 8 }}>
          <span className="small muted num" role="status">
            {view.status === "stopping" ? "Stopping after the trial in progress… " : ""}${view.spent.toFixed(2)} of ${view.budget.toFixed(2)}
          </span>
          <button
            type="button"
            className="btn btn--small"
            disabled={view.status === "stopping"}
            onClick={() => api.suiteStop(job).catch((e) => setError(e instanceof ApiError ? e.message : String(e)))}
          >
            Stop
          </button>
        </div>
      ) : null}
      {!live ? (
        <button type="button" className="btn btn--small" onClick={onClose}>
          Close
        </button>
      ) : null}
      {p.n_pairs ? (
        <div className="result" aria-label={`Across ${n} Benches`}>
          <div className="result__top">
            <b>Across {n} Benches</b>
            {pill ? (
              <span className={`verdict-pill verdict-pill--${pill.tone}`}>{live ? "So Far" : pill.word}</span>
            ) : (
              <span className={`verdict-pill verdict-pill--${p.verdict}`}>{live ? "So Far" : (VERDICT_LABEL[p.verdict as Verdict] ?? p.verdict)}</span>
            )}
          </div>
          {saving ? <MetricHeadline m={saving} /> : null}
          <div className="result__nums num">
            <span className="result__diff">
              {saving ? "Pass rate " : null}
              {pts(p.diff)} pts
            </span>
            <span>95% interval {pts(p.ci_low)} to {pts(p.ci_high)} pts</span>
            <span>{p.n_pairs} pairs</span>
          </div>
          <ul className="small num" style={{ listStyle: "none", padding: 0, margin: "6px 0 0" }}>
            {view.benches.map((b) => (
              <li key={b.bench} className="row" style={{ justifyContent: "space-between" }}>
                <span>{b.name}</span>
                <span>
                  {b.n_pairs
                    ? `${saving && change(b.rig?.metric) ? `${change(b.rig?.metric)} · ` : ""}${pts(b.diff)} pts · ${b.n_pairs} pairs`
                    : "no pairs"}
                </span>
              </li>
            ))}
          </ul>
          <p className="small muted" data-testid="suite-pooling">
            {saving
              ? "Pooled over every bench's pairs: a bench weighs by its pairs and by what its tasks spend, and its interval resamples each bench's pairs within that bench."
              : "Benches count in proportion to their pairs, so a bench with more pairs weighs more."}
          </p>
          {p.rig && !live ? <RigScore rig={p.rig} compact title={`Rig Score across ${n} Benches`} /> : null}
        </div>
      ) : !live ? (
        <p className="small muted">No bench finished a pair, so there is nothing to pool.</p>
      ) : null}
    </section>
  );
}
