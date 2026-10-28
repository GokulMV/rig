import { useState } from "react";
import { api } from "../lib/api";
import type { Forensics as ForensicsData, ForensicsPair, ForensicsSide, ForensicsStep } from "../lib/types";

const label = (s: ForensicsSide) => (s.outcome === "pass" ? "pass" : `${s.outcome} (${s.bucket.replace(/_/g, " ")})`);

function Column({ title, side, steps, at }: { title: string; side: ForensicsSide; steps: ForensicsStep[]; at: number | null }) {
  return (
    <div className="forensics__col">
      <div className="small">
        <b>{title}</b> · {label(side)}
      </div>
      <ol className="forensics__steps small">
        {steps.map((s, i) => (
          <li key={i} className={i === at ? "forensics__step forensics__step--diverged" : "forensics__step"}>
            <b>{s.tool}</b> {s.summary}
          </li>
        ))}
        {steps.length === 0 ? <li className="muted">No session log to read.</li> : null}
      </ol>
    </div>
  );
}

function Pair({ p }: { p: ForensicsPair }) {
  const failing = p.with.outcome !== "pass" ? p.with : p.without;
  return (
    <li className="forensics__pair">
      <div>
        <b>{p.scenario_id}</b> · with: {label(p.with)} vs without: {label(p.without)}
      </div>
      <div className="small muted">{failing.why}</div>
      <div className="forensics__cols">
        <Column title="With" side={p.with} steps={p.timeline_with} at={p.diverged_at} />
        <Column title="Without" side={p.without} steps={p.timeline_without} at={p.diverged_at} />
      </div>
    </li>
  );
}

/** "Why it changed": per pair of the same task that ended differently, what each run did. */
export function Forensics({ bench, id, pairs }: { bench: string; id: number; pairs: number }) {
  const [data, setData] = useState<ForensicsData | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = async () => {
    setOpen(!open);
    if (open || data) return;
    try {
      setData(await api.labForensics(bench, id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load it.");
    }
  };

  return (
    <div className="forensics">
      <button type="button" className="linkish" aria-expanded={open} onClick={() => void toggle()}>
        Why It Changed ({pairs} pairs)
      </button>
      {open ? (
        <div className="forensics__body">
          {error ? <p className="small">{error}</p> : null}
          {!data && !error ? <p className="small muted">Reading the trial logs...</p> : null}
          {data ? (
            <>
              <p className="small muted">
                {Object.entries(data.counts)
                  .map(([k, n]) => `${n} ${k.replace(/_/g, " ")}`)
                  .join(" · ") || "No failures to explain."}
              </p>
              <ul className="forensics__pairs">
                {data.pairs.map((p) => (
                  <Pair key={`${p.scenario_id}-${p.repeat}`} p={p} />
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
