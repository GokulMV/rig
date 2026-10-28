import { useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import { plural, usd } from "../lib/format";
import type { FullSize, LabWorkflow, MetricId, MetricPlan, RunExtends, RunForecast } from "../lib/types";

export type EstimateRequest = {
  pairs: number;
  agent: string;
  model?: string | null;
  bench?: string | null;
  repo?: string | null;
  workflow?: LabWorkflow | null;
  treatment_path?: string | null;
  local?: boolean;
  /** The pilot's pairs, so the estimate can say when the budget makes a full run no better. */
  pilot_pairs?: number | null;
  /** The full run's pairs, whatever size is chosen: what "Full" buys at this budget. */
  full_pairs?: number | null;
  /** One bench or repo: the size and its tasks. The engine then plans the pairs (a full run
   * grows with the budget up to the sizing) in place of pairs, pilot_pairs and full_pairs. */
  size?: "pilot" | "full";
  tasks?: number;
  /** A bench's tier: priced from that tier's earlier trials only. */
  tier?: string | null;
  /** Scored on a saving: the sizing is the pass-rate guard's (rig-score metric.plan), not the lift's. */
  metric?: MetricId;
  /** "Keep going until it's decided" is on: the answer says what the run may grow to, and a run
   * short of the guard adds pairs toward it. */
  auto?: boolean;
};

/** Next to "Stop at": the budget check's own prediction (trial-budget), before any sign-in, what
 * it can detect, and what it would take to detect the target change (with one click to set it). */
export function RunEstimate({
  request,
  budget,
  onSetBudget,
  canExtend = false,
  onFull,
  onMetricPlan,
  onExtends,
}: {
  request: EstimateRequest | null;
  budget: number;
  /** "Set budget to $X": what pays for the pairs that tell the target change from noise. */
  onSetBudget?: (usd: number) => void;
  /** The run can add pairs up to the budget ("Keep going until it's decided"). */
  canExtend?: boolean;
  /** What "Full" buys at this budget (asked for with full_pairs), for the run-size choice; null
   * until it is priced. */
  onFull?: (full: FullSize | null) => void;
  /** What the planned pairs can show on a saving metric (null otherwise, or until priced). */
  onMetricPlan?: (plan: MetricPlan | null) => void;
  /** What it may grow to with "Keep going until it's decided" on (null when off, or until priced). */
  onExtends?: (e: RunExtends | null) => void;
}) {
  const [got, setGot] = useState<RunForecast | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = request ? JSON.stringify(request) : "";
  const full = request && request.pairs > 0 && !error ? (got?.full ?? null) : null;
  useEffect(() => onFull?.(full), [full, onFull]);
  const plan = request && request.pairs > 0 && !error ? (got?.metric_plan ?? null) : null;
  useEffect(() => onMetricPlan?.(plan), [plan, onMetricPlan]);
  const grows = request && request.pairs > 0 && !error ? (got?.extends ?? null) : null;
  useEffect(() => onExtends?.(grows), [grows, onExtends]);
  useEffect(() => {
    if (!request || request.pairs <= 0) {
      setGot(null);
      return;
    }
    let live = true;
    // A short wait: typing a budget or switching benches asks once, not on every key.
    const t = window.setTimeout(() => {
      api.runEstimate({ ...request, budget }).then(
        (f) => {
          if (!live) return;
          setGot(f);
          setError(null);
        },
        (e) => live && setError(e instanceof ApiError ? e.message : String(e)),
      );
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, budget]);
  if (!request || request.pairs <= 0) return null;
  if (error) return <p className="small muted runest">Couldn't price this run: {error}</p>;
  if (!got) return <p className="small muted runest">Pricing the run…</p>;
  const sameSource = got.source.with === got.source.without;
  const short = got.pairs_in_budget !== undefined && got.pairs_in_budget < got.pairs;
  const d = got.detect;
  const z = got.sizing;
  return (
    <div className="runest" aria-live="polite">
      <p className="small num" data-testid="run-cost">
        {got.free ? (
          // Free: nothing to stop at, but what the pairs can tell from noise still holds.
          <>
            <b>A local model: no API cost</b> ({plural(got.pairs, "pair")}, {plural(got.trials, "trial")}, on this machine).
          </>
        ) : short ? (
          <>
            <b>Stops at {usd(budget)}</b> (about {got.pairs_in_budget} of {plural(got.pairs, "pair")}). The full run would cost ≈{" "}
            {usd(got.total_usd)}.
          </>
        ) : (
          <>
            <b>≈ {usd(got.total_usd)}</b> for the full run ({plural(got.pairs, "pair")}, {plural(got.trials, "trial")}); it stops at {usd(budget)}{" "}
            if trials cost more than predicted.
          </>
        )}
      </p>
      {grows ? (
        <p className="small num" data-testid="run-extends">
          {grows.line}
        </p>
      ) : null}
      {plan ? (
        // Scored on a saving: what the pass-rate guard needs, and whether these pairs get there.
        <div className="small num runest__size" data-testid="metric-plan">
          <span>{plan.lines[0]}</span>
          <p className={plan.enough || plan.extends ? "small" : "notice notice--warning small"} data-testid="metric-plan-planned">
            {plan.lines[1]}
          </p>
          {!plan.enough && (request.size === "full" || plan.extends) && plan.need_usd != null && onSetBudget && plan.need_usd > budget ? (
            <button type="button" className="btn btn--small" onClick={() => onSetBudget(plan.need_usd!)} data-testid="set-budget">
              Set Budget to {usd(plan.need_usd)}
            </button>
          ) : null}
        </div>
      ) : d ? (
        <p className="small num" data-testid="run-detect">
          With {plural(d.pairs, "pair")}, an effect smaller than about ±{d.pts} pts can't be told from noise.
        </p>
      ) : (
        <p className="notice notice--warning small" data-testid="run-detect">
          {usd(budget)} doesn't pay for one pair, so this run can't measure anything.
        </p>
      )}
      {got.no_better_than_pilot ? (
        <p className="notice notice--warning small" data-testid="run-no-better">
          {got.no_better_than_pilot}
        </p>
      ) : null}
      {z && !z.enough_budget && !plan ? (
        <div className="small num runest__size" data-testid="run-sizing">
          <span>
            To tell a ±{z.target_pts} pts change from noise you need about {plural(z.pairs, "pair")}
            {z.usd != null ? <> ≈ {usd(z.usd)}</> : null}.
            {z.enough_planned
              ? null
              : canExtend
                ? ` This run plans ${plural(z.planned_pairs, "pair")}; with "Keep going until it's decided" on, it adds pairs up to the budget.`
                : ` This run plans ${plural(z.planned_pairs, "pair")}, so at best about ±${z.planned_pts} pts.`}
          </span>
          {z.usd != null && onSetBudget && z.usd > budget && (z.enough_planned || canExtend) ? (
            <button type="button" className="btn btn--small" onClick={() => onSetBudget(z.usd!)} data-testid="set-budget">
              Set Budget to {usd(z.usd)}
            </button>
          ) : null}
        </div>
      ) : null}
      {got.free ? null : (
      <p className="small muted num">
        Per pair {usd(got.per_trial.with)} with + {usd(got.per_trial.without)} without:{" "}
        {sameSource ? got.source.with : `with ${got.source.with}; without ${got.source.without}`}. The budget check's own number, margin
        included; reused baseline trials cost less.
      </p>
      )}
    </div>
  );
}
