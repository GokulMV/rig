import { FileText, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api, ApiError, type BuildMore } from "../lib/api";
import { useDesignParams } from "../lib/designParams";
import type { BuildSpec as Spec, BuildSource, CanvasAdded } from "../lib/types";
import { RigScore } from "./RigScore";

/** One compact button; opens BUILD.md so any coding agent can build the architecture. */
export function BuildSpecButton({
  source,
  workflow,
  removed,
  added,
  className = "btn btn--small btn--quiet",
  saveLabel = "Save to the Repo",
  design,
  useCase,
}: {
  source: BuildSource;
  workflow?: unknown;
  removed?: string[];
  added?: CanvasAdded;
  design?: { id: string; values?: Record<string, string> } | null;
  useCase?: string;
  className?: string;
  saveLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    ref.current?.focus();
    const key = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [open]);
  const close = () => {
    setOpen(false);
    opener.current?.focus();
  };

  return (
    <>
      <button
        ref={opener}
        type="button"
        className={className}
        title="Export this as BUILD.md and rig.json for any coding agent"
        onClick={() => setOpen(true)}
      >
        <FileText size={14} aria-hidden="true" /> Ship to Any Agent
      </button>
      {open ? (
        <div className="buildspec__scrim" onClick={close}>
          <div
            className="buildspec"
            role="dialog"
            aria-modal="true"
            aria-label="Ship to Any Agent"
            tabIndex={-1}
            ref={ref}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="row buildspec__head">
              <strong>Ship to Any Agent</strong>
              <button type="button" className="btn btn--small btn--quiet" aria-label="Close" onClick={close}>
                <X size={14} aria-hidden="true" />
              </button>
            </div>
            <BuildSpecView source={source} workflow={workflow} removed={removed} added={added} design={design} useCase={useCase} saveLabel={saveLabel} />
          </div>
        </div>
      ) : null}
    </>
  );
}

/** BUILD.md for a source, with Copy and Save: in the dialog, or on the Ship step. */
export function BuildSpecView({
  source,
  workflow,
  saveLabel = "Save to the Repo",
  bare = false,
  removed = [],
  added,
  design,
  useCase,
}: {
  source: BuildSource;
  workflow?: unknown;
  saveLabel?: string;
  /** Architecture component ids removed on the canvas. */
  removed?: string[];
  /** What was placed on the canvas: in the brief as well as the repo. */
  added?: CanvasAdded;
  /** The Garage design chosen in step 2: its parameter values come from what was set there. */
  design?: { id: string; values?: Record<string, string> } | null;
  /** The goal in use (step 1, saved or not): the brief's Goal, and a new project's language. */
  useCase?: string;
  /** On a page that already says what BUILD.md is. */
  bare?: boolean;
}) {
  const [spec, setSpec] = useState<Spec | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const live = useDesignParams(design?.id);
  // A workflow's design link keeps the values it was used with; ones edited since in step 2 win.
  const values = design?.values ? { ...design.values, ...live } : live;
  const more: BuildMore = {
    ...(design ? { design: { id: design.id, parameters: values } } : {}),
    // The goal in use, sent even when empty, so a repo's brief never reads a different one.
    ...(useCase !== undefined ? { use_case: useCase.trim() } : {}),
  };
  const key = JSON.stringify([source, workflow ?? null, removed, added ?? null, more]);
  useEffect(() => {
    let live = true;
    setSpec(null);
    setError(null);
    setNote(null);
    api.buildSpec(source, workflow, removed, added, more).then(
      (s) => live && setSpec(s),
      (e) => live && setError(e instanceof ApiError ? e.message : String(e)),
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  // Only what is being shipped: this workflow, or the parts on the repo's canvas.
  const shipped = spec?.shipped ?? null;
  return (
    <>
      {bare ? null : <p className="small muted">Give BUILD.md to any coding agent; rig.json has the same as data.</p>}
      {error ? <p className="notice notice--error small">{error}</p> : null}
      {!spec && !error ? <p className="small muted">Writing the brief…</p> : null}
      {spec ? (
        <>
          {source === "design" ? null : shipped ? (
            // One run's score, never the whole brief's: say which run it is.
            <RigScore
              rig={shipped.rig}
              compact
              title={
                source === "workflow"
                  ? `Rig Score · This Workflow's Last Run${shipped.where ? ` on ${shipped.where}` : ""}`
                  : `Rig Score · ${shipped.name}, the Last Skill Measured${shipped.where ? ` on ${shipped.where}` : ""}`
              }
              name={`Rig score for ${shipped.name}`}
            />
          ) : (
            <p className="small muted" data-testid="ship-not-measured">
              Rig score: Not measured yet. Measure what you're shipping (step 4) and its score shows here.
            </p>
          )}
          <pre className="buildspec__text mono" tabIndex={0} aria-label="BUILD.md">
            {spec.markdown}
          </pre>
          <div className="row" style={{ gap: 8 }}>
            <button type="button" className="btn btn--small" onClick={() => void copy(spec.markdown, "BUILD.md", setNote)}>
              Copy BUILD.md
            </button>
            <button
              type="button"
              className="btn btn--small"
              onClick={() => void copy(JSON.stringify(spec.json, null, 2) + "\n", "rig.json", setNote)}
            >
              Copy rig.json
            </button>
            <button
              type="button"
              className="btn btn--small btn--primary"
              onClick={async () => {
                try {
                  const r = await api.buildSpecSave(source, workflow, removed, added, more);
                  setNote(`Saved ${r.markdown} and ${r.json}.`);
                } catch (e) {
                  setNote(e instanceof ApiError ? e.message : String(e));
                }
              }}
            >
              {saveLabel}
            </button>
          </div>
          {note ? (
            <p className="small" role="status">
              {note}
            </p>
          ) : null}
        </>
      ) : null}
    </>
  );
}

/** The newest measured result's Rig score in the brief, if any was measured. */

async function copy(text: string, what: string, say: (s: string) => void) {
  try {
    await navigator.clipboard.writeText(text);
    say(`Copied ${what}.`);
  } catch {
    say(what === "BUILD.md" ? "Couldn't copy here; select the text and copy it." : `Couldn't copy ${what} here; save it to the repo instead.`);
  }
}

/** The files the accepted suggestions touch, from the repo's brief: collapsed until asked for. */
export function ProjectStructure({ refreshKey }: { refreshKey: string }) {
  const [open, setOpen] = useState(false);
  const [changes, setChanges] = useState<NonNullable<Spec["json"]["changes"]> | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    api.buildSpec("suggested").then(
      (s) => setChanges(s.json.changes ?? []),
      (e) => setError(e instanceof ApiError ? e.message : String(e)),
    );
  }, [open, refreshKey]);
  const files = (changes ?? []).flatMap((t) => t.files.map((f) => `${f.path}${f.new ? " (new)" : ""}  # ${t.title}`));
  return (
    <details className="structure" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Files the Accepted Suggestions Touch</summary>
      {error ? <p className="notice notice--error small">{error}</p> : null}
      {changes ? (
        files.length ? (
          <pre className="buildspec__text mono small" tabIndex={0} aria-label="Files the Accepted Suggestions Touch">
            {files.join("\n")}
          </pre>
        ) : (
          <p className="small muted">{changes.length ? "The accepted suggestions name no files yet." : "Accept a suggestion to see the files it touches."}</p>
        )
      ) : open && !error ? (
        <p className="small muted">Working it out…</p>
      ) : null}
    </details>
  );
}
