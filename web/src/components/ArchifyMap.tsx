import { Network } from "lucide-react";
import { useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import type { Architecture, MapJob } from "../lib/types";

/** "Map with Archify": the agent reads the repo (read-only) and writes the architecture. */
export function ArchifyMap({
  architecture,
  agent,
  onMapped,
}: {
  architecture: Architecture | null;
  agent: { id: string; label: string } | null;
  onMapped: () => Promise<void>;
}) {
  const [job, setJob] = useState<MapJob>({ state: "idle" });
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const running = job.state === "running";

  // On open: pick up a mapping already running (another tab, a reload).
  useEffect(() => {
    api.mapStatus().then(setJob, () => undefined);
  }, []);

  // While running: follow it, and redraw the canvas once it's done.
  useEffect(() => {
    if (!running) return;
    let live = true;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const j = await api.mapStatus();
        if (!live) return;
        if (j.state === "running") timer = window.setTimeout(poll, 2500);
        else {
          if (j.state === "done") await onMapped();
          setJob(j);
        }
      } catch {
        if (live) timer = window.setTimeout(poll, 5000);
      }
    };
    timer = window.setTimeout(poll, 2500);
    return () => {
      live = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [running, onMapped]);

  if (architecture?.source === "archify") return null; // The repo's own spec always wins.

  const failed = job.state === "error" ? job.error : error;

  return (
    <div className="archify" aria-live="polite">
      {job.state === "running" ? (
        <div className="archify__run">
          <Stack3D />
          <span className="archify__runtext">
            <strong>Mapping with Archify</strong>
            <span className="archify__sub">
              {agent?.label ?? "The agent"} is reading the repo, read-only · <Elapsed since={job.started_at} /> · usually 1–3 min
            </span>
          </span>
        </div>
      ) : confirming ? (
        <>
          <span className="archify__line">
            <strong>Map with Archify?</strong>
          </span>
          <span className="archify__sub">
            {agent?.label ?? "The agent"} reads this repo with read-only tools (no shell, no edits, no web) and writes an
            Archify architecture spec. One agent session, on your sign-in.
          </span>
          <span className="row" style={{ gap: 8 }}>
            <button
              type="button"
              className="btn btn--small btn--primary"
              onClick={async () => {
                setError(null);
                try {
                  setJob(await api.mapArchitecture(agent?.id ?? "claude-code"));
                  setConfirming(false);
                } catch (e) {
                  setError(e instanceof ApiError ? e.message : String(e));
                  setConfirming(false);
                }
              }}
            >
              Map It
            </button>
            <button type="button" className="btn btn--small btn--quiet" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </span>
        </>
      ) : (
        <>
          {/* One compact control: the check's result rides on the button; the details are its title. */}
          <button
            type="button"
            className="btn btn--small"
            onClick={() => setConfirming(true)}
            title={architecture?.check ? `Checked against the code: ${architecture.check.summary}.` : undefined}
          >
            <Network size={14} aria-hidden="true" />
            {architecture?.source === "mapped" ? "Map Again" : "Map with Archify"}
            {architecture?.check ? (
              <span
                className={`archify__badge check check--${architecture.check.missing ? "missing" : architecture.check.weak ? "weak" : "found"}`}
              >
                {architecture.check.found}/{architecture.check.total} found
              </span>
            ) : null}
          </button>
          {failed ? (
            <span className="archify__sub" role="alert" style={{ color: "var(--negative)" }}>
              {failed}
            </span>
          ) : null}
        </>
      )}
    </div>
  );
}

function Elapsed({ since }: { since?: number }) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(t);
  }, []);
  const s = Math.max(0, Math.round(now - (since ?? now)));
  return <span className="num">{s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`}</span>;
}

/** Three layers of an architecture, in 3D, stacking and settling while the agent reads. */
function Stack3D() {
  return (
    <span className="stack3d" aria-hidden="true">
      <span className="stack3d__scene">
        {[0, 1, 2].map((i) => (
          <span key={i} className={`stack3d__slab stack3d__slab--${i}`}>
            <span className="stack3d__top" />
            <span className="stack3d__side stack3d__side--front" />
            <span className="stack3d__side stack3d__side--right" />
          </span>
        ))}
        <span className="stack3d__spark" />
      </span>
    </span>
  );
}
