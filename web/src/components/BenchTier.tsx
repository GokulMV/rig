import { Gauge } from "lucide-react";
import { useState } from "react";

import { api, ApiError } from "../lib/api";
import type { BenchBaseline, BenchInfo, BenchTask, LabStarted, LabWorkflow, ProbePrice } from "../lib/types";

/** A tier's tasks: the standard ones, the hard ones, or both (standard first), as the engine runs them. */
export function tierTasks(b: BenchInfo, tier: string): BenchTask[] {
  const hard = b.hard ?? [];
  return tier === "hard" ? hard : tier === "all" ? [...b.scenarios, ...hard] : b.scenarios;
}

/** What the agent alone did on this tier with this session model, from trials already recorded. */
export function baselineOf(b: BenchInfo | null, tier: string, model: string | null): BenchBaseline | null {
  return (b && model && b.baseline?.[tier]?.[model]) || null;
}

/** Standard · Hard · Standard and hard, with each tier's task count. Only on a bench with a hard tier. */
export function TierChoice({ bench, tier, onTier }: { bench: BenchInfo; tier: string; onTier: (t: string) => void }) {
  const tiers = bench.tiers ?? [];
  if (tiers.length < 2) return null;
  return (
    <div className="field">
      <span className="small" id="tier-label">
        Tasks
      </span>
      <div className="segmented" role="radiogroup" aria-labelledby="tier-label">
        {tiers.map((t) => (
          <button key={t.id} type="button" role="radio" aria-checked={tier === t.id} onClick={() => onTier(t.id)}>
            {t.label} · {t.tasks}
          </button>
        ))}
      </div>
    </div>
  );
}

/** The agent alone on this bench: too easy (a workflow can only tie on quality), its measured rate,
 * or nothing yet; and the baseline check that finds out for little, priced before it runs. */
export function BaselineCheck({
  bench,
  tier,
  model,
  probe,
  ready,
  onStarted,
}: {
  bench: BenchInfo;
  tier: string;
  /** The session model the next run is recorded under; null when it isn't known here. */
  model: string | null;
  /** What the check runs on: the agent, the workflow (for its session model), a local model. */
  probe: { agent: string; workflow: LabWorkflow; local_model: string | null };
  /** Signed in (or on a local model): pricing doesn't need it, running does. */
  ready: boolean;
  onStarted: (s: LabStarted) => void;
}) {
  const [price, setPrice] = useState<ProbePrice | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const got = baselineOf(bench, tier, model);
  if (bench.imported || bench.public) return null; // their tasks are run as they are, not checked here
  const body = { bench: bench.id, tier, ...probe };
  return (
    <div className="small" data-testid="baseline">
      {got ? (
        <p className={got.too_easy ? "notice notice--warning small" : "small muted"} data-testid="baseline-text" style={{ margin: "4px 0" }}>
          {got.text}
          {got.too_easy ? "." : ` (${got.tasks_seen} of ${got.tasks} tasks).`}
        </p>
      ) : null}
      {error ? <p className="notice notice--error small">{error}</p> : null}
      {price ? (
        <div className="card" data-testid="probe-ask">
          <p className="small" style={{ marginTop: 0 }}>
            {price.offer}
          </p>
          <p className="small muted">
            {price.model_label}, {price.trials} &quot;without&quot; trial{price.trials === 1 ? "" : "s"} at about ${price.per_trial.toFixed(2)} each ({price.source}).
            {price.free ? "" : ` It stops at $${price.budget.toFixed(2)}.`}
          </p>
          <div className="row" style={{ gap: 8 }}>
            <button
              type="button"
              className="btn btn--primary btn--small"
              disabled={busy || !ready}
              title={ready ? undefined : "Sign in first"}
              onClick={async () => {
                setError(null);
                setBusy(true);
                try {
                  const s = await api.probe({ ...body, budget: price.free ? undefined : price.budget });
                  setPrice(null);
                  onStarted(s);
                } catch (e) {
                  setError(e instanceof ApiError ? e.message : String(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              {price.free ? "Run the Check" : `Run the Check, up to $${price.budget.toFixed(2)}`}
            </button>
            <button type="button" className="btn btn--quiet btn--small" onClick={() => setPrice(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="linkish"
          disabled={busy}
          onClick={async () => {
            setError(null);
            setBusy(true);
            try {
              setPrice(await api.probePrice(body));
            } catch (e) {
              setError(e instanceof ApiError ? e.message : String(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          <Gauge size={12} aria-hidden="true" /> {got ? "Check the Bench Again" : "Check the Bench First"}
        </button>
      )}
    </div>
  );
}
