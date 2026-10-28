import { Square } from "lucide-react";
import { useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import type { ActiveRun } from "../lib/types";

const POLL_MS = 5000;

/** In the top bar on every step: what is running anywhere, what it has spent, and a Stop.
 * With nothing running, a quiet link to every run. */
export function RunPill({ onOpen, onRuns }: { onOpen: (run: ActiveRun) => void; onRuns?: () => void }) {
  const [run, setRun] = useState<ActiveRun | null>(null);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    const tick = () =>
      api.activeRun().then(
        (r) => {
          if (!live) return;
          setRun(r.running);
          if (!r.running) setStopping(false);
        },
        () => undefined,
      );
    void tick();
    const t = window.setInterval(tick, POLL_MS);
    return () => {
      live = false;
      window.clearInterval(t);
    };
  }, []);
  if (!run)
    return onRuns ? (
      <button type="button" className="btn btn--small btn--quiet runpill__quiet" onClick={onRuns} title="Every run, past and present">
        Runs
      </button>
    ) : null;
  const where = run.kind === "repo" ? run.repo_name : `bench ${run.bench}`;
  return (
    <div className="runpill" role="status">
      <button type="button" className="runpill__main" onClick={() => onOpen(run)} title="Open this run">
        <span className="runpill__dot" aria-hidden="true" />
        <span>
          {stopping ? "Stopping" : "Running"}: <b>{run.treatment}</b> on {where}
        </span>
        <span className="num muted">
          ${run.spent_usd.toFixed(2)} of ${run.budget_usd.toFixed(2)}
        </span>
      </button>
      <button
        type="button"
        className="runpill__stop"
        disabled={stopping}
        title="Stop after the trial in progress"
        aria-label="Stop this run"
        onClick={async () => {
          setError(null);
          setStopping(true);
          try {
            if (run.kind === "repo" && run.repo) await api.stopExperiment(run.id, run.repo);
            else if (run.bench) await api.labStop(run.bench, run.id);
          } catch (e) {
            setStopping(false);
            setError(e instanceof ApiError ? e.message : String(e));
          }
        }}
      >
        <Square size={11} aria-hidden="true" /> Stop
      </button>
      {error ? <span className="small" style={{ color: "var(--negative)" }}>{error}</span> : null}
    </div>
  );
}
