import { useEffect, useRef, useState } from "react";

import { Empty, ErrorNotice, KindChip, kindLabel, Skeleton } from "./Bits";
import { api, ApiError } from "../lib/api";
import { plural } from "../lib/format";
import type { DryRun, Generated, Kind, Project, Scenario } from "../lib/types";
import { KINDS } from "../lib/types";

export const MODELS = [
  { id: "claude-opus-5-5", label: "Opus 5.5 (writes the best checks)" },
  { id: "claude-sonnet-5-5", label: "Sonnet 5.5" },
  { id: "claude-haiku-5-5", label: "Haiku 5.5 (cheapest)" },
];
const DEFAULT_MIX: Record<Kind, number> = {
  typical: 4,
  edge: 2,
  adversarial: 2,
  failure: 2,
  overload: 1,
  imaginary: 2,
};
const KIND_HINT: Record<Kind, string> = {
  typical: "Everyday tasks",
  edge: "Unusual but legitimate",
  adversarial: "Misleading or unsafe asks",
  failure: "A broken environment",
  overload: "Too much to handle",
  imaginary: "Hypothetical; reported apart",
};
const ACCEPT = ".json,.pdf,.md,.markdown,.txt,.yaml,.yml,.toml,.csv,.mmd,.mermaid,.puml,.dot,.sql,.png,.jpg,.jpeg,.webp,.gif";

function message(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

export function Sources({
  project,
  onChanged,
  goal,
  onEditGoal,
}: {
  project: Project;
  onChanged: () => Promise<void>;
  /** The goal in use (Describe's box, saved or not): tasks are written from it. */
  goal?: string;
  /** Opens Describe, the one place the goal is edited. */
  onEditGoal?: () => void;
}) {
  const [busy, setBusy] = useState<"scan" | "upload" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const shown = (goal ?? project.use_case ?? "").trim();

  async function act(kind: "scan" | "upload", fn: () => Promise<void>) {
    setBusy(kind);
    setError(null);
    try {
      await fn();
      await onChanged();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(null);
    }
  }

  function upload(files: File[]) {
    if (files.length === 0) return;
    void act("upload", async () => {
      const r = await api.upload(files);
      const added = r.added.map(([, n]) => n);
      setUploadNote(
        [
          added.length ? `Added ${added.join(", ")}.` : "",
          r.skipped.length ? `Skipped ${r.skipped.join(", ")} (unsupported type).` : "",
        ]
          .filter(Boolean)
          .join(" "),
      );
    });
  }

  return (
    <section className="gen-part" aria-label="Add sources">
      <h3 className="insp__label">Sources</h3>
      <div className="section">
        {/* The goal is written in Describe, once; here it is only shown, so the two never differ. */}
        <div className="section" data-testid="generate-goal-copy">
          <h3>Goal</h3>
          <p className="small muted hint">Tasks are written for this goal, from Describe.</p>
          <blockquote className="goalcopy small">{shown || <span className="muted">No goal yet.</span>}</blockquote>
          {onEditGoal ? (
            <button type="button" className="linkish small" style={{ justifySelf: "start" }} onClick={onEditGoal}>
              Edit in Describe
            </button>
          ) : null}
        </div>

        <div className="section">
          <h3>Repository</h3>
          <p className="mono small" style={{ overflowWrap: "anywhere" }}>
            {project.root}
          </p>
          <div className="row row--between">
            <span className="small muted">
              {project.scanned
                ? `${plural(project.scan.files, "file")} read${project.scan.truncated ? " (stopped at the limit)" : ""}`
                : "Not read yet"}
            </span>
            <button
              type="button"
              className="btn btn--small"
              disabled={busy !== null}
              onClick={() => void act("scan", async () => void (await api.intake()))}
            >
              {busy === "scan" ? "Reading…" : project.scanned ? "Read Again" : "Read Repo"}
            </button>
          </div>
        </div>

        <div className="section">
          <h3>Files</h3>
          <p className="small muted hint">Graphify graph.json, PDFs, Markdown or images.</p>
          <button
            type="button"
            className="drop"
            data-over={over}
            onClick={() => input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setOver(false);
              upload(Array.from(e.dataTransfer.files));
            }}
            disabled={busy !== null}
          >
            <span>{busy === "upload" ? "Reading files…" : "Drop files here"}</span>
            <span className="small">or choose files</span>
          </button>
          <input
            ref={input}
            type="file"
            multiple
            accept={ACCEPT}
            className="visually-hidden"
            tabIndex={-1}
            aria-label="Choose files"
            onChange={(e) => {
              upload(Array.from(e.target.files ?? []));
              e.target.value = "";
            }}
          />
          {uploadNote ? (
            <p className="small" aria-live="polite">
              {uploadNote}
            </p>
          ) : null}
        </div>
        {error ? <ErrorNotice error={error} /> : null}
      </div>
    </section>
  );
}

export function Findings({ project, onChanged }: { project: Project; onChanged: () => Promise<void> }) {
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  async function onScan() {
    setScanning(true);
    setScanError(null);
    try {
      await api.intake();
      await onChanged();
    } catch (e) {
      setScanError(message(e));
    } finally {
      setScanning(false);
    }
  }
  const langs = Object.entries(project.scan.languages).sort((a, b) => b[1] - a[1]);
  const maxLang = langs[0]?.[1] ?? 1;
  const g = project.graph;
  return (
    <section className="gen-part" aria-label="What was found">
      <h3 className="insp__label">What was found</h3>
      <div className="section">
        {!project.scanned && project.sources.length === 0 ? (
          <Empty title="Nothing Read Yet">
            <p>Read the repository to see its languages, stack, agent setup and skills.</p>
            <button type="button" className="btn btn--primary" onClick={() => void onScan()} disabled={scanning}>
              {scanning ? "Reading…" : "Read Repo"}
            </button>
          </Empty>
        ) : null}
        {scanError ? <ErrorNotice error={scanError} /> : null}

        {project.scanned ? (
          <>
            <div className="section">
              <h3>Languages</h3>
              {langs.length === 0 ? (
                <p className="muted">No source files recognised.</p>
              ) : (
                <ul className="list" aria-label="Files per language" style={{ maxWidth: 520 }}>
                  {langs.slice(0, 8).map(([name, n]) => (
                    <li key={name} className="slider" style={{ gridTemplateColumns: "120px minmax(0,1fr) 56px", padding: "6px 0" }}>
                      <span>{name}</span>
                      <span className="progress" aria-hidden="true">
                        <span style={{ width: `${(n / maxLang) * 100}%` }} />
                      </span>
                      <span className="num muted" style={{ textAlign: "right" }}>
                        {n}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="section">
              <h3>Stack</h3>
              <div className="tags">
                {project.scan.stack.length ? (
                  project.scan.stack.map((s) => (
                    <span key={s} className="pill">
                      {s}
                    </span>
                  ))
                ) : (
                  <span className="muted">Nothing detected</span>
                )}
              </div>
            </div>
            <div className="section">
              <h3>Agent Setup</h3>
              <div className="tags">
                {project.scan.agent_setup.length ? (
                  project.scan.agent_setup.map((s) => (
                    <span key={s} className="pill">
                      {s}
                    </span>
                  ))
                ) : (
                  <span className="muted">No CLAUDE.md, AGENTS.md, skills or MCP config found</span>
                )}
              </div>
            </div>
            <div className="section">
              <h3>Skills in the Repo</h3>
              {project.scan.skills.length ? (
                <ul className="list">
                  {project.scan.skills.map((s) => (
                    <li key={s.path} style={{ padding: "8px 0" }}>
                      <div className="item__name">{s.name}</div>
                      <div className="item__desc">{s.description || "No description"}</div>
                      <div className="mono small muted">{s.path}</div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">None. Skills you test can come from your own folder too.</p>
              )}
            </div>
          </>
        ) : null}

        {g ? (
          <div className="section">
            <h3>Knowledge Graph</h3>
            <dl className="kv">
              <dt>File</dt>
              <dd className="mono">{g.name}</dd>
              <dt>Size</dt>
              <dd className="num">
                {plural(g.nodes, "node")}, {plural(g.edges, "edge")}
                {g.communities != null ? `, ${plural(g.communities, "community", "communities")}` : ""}
              </dd>
              {g.top && g.top.length ? (
                <>
                  <dt>Most connected</dt>
                  <dd>{g.top.slice(0, 6).join(", ")}</dd>
                </>
              ) : null}
            </dl>
          </div>
        ) : null}

        {project.sources.length ? (
          <div className="section">
            <h3>Everything the Generator Can Read</h3>
            <div className="table-wrap" tabIndex={0} role="region" aria-label="Sources the generator can read">
              <table>
                <thead>
                  <tr>
                    <th>Kind</th>
                    <th>Name</th>
                    <th className="n">About</th>
                  </tr>
                </thead>
                <tbody>
                  {project.sources.map((s) => (
                    <tr key={s.id}>
                      <td>{s.kind}</td>
                      <td className="mono">{s.name}</td>
                      <td className="n muted">{s.kind === "image" ? "image" : plural(Math.ceil(s.chars / 4), "token")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

export function Generate({
  project,
  scenarios,
  onChanged,
  draft,
}: {
  project: Project;
  scenarios: Scenario[] | null;
  onChanged: () => Promise<void>;
  /** The unsaved goal to write from instead of the saved one; undefined when there is none. */
  draft?: string;
}) {
  const [mix, setMix] = useState<Record<Kind, number>>(DEFAULT_MIX);
  const [model, setModel] = useState(MODELS[0].id);
  const [preview, setPreview] = useState<DryRun | null>(null);
  const [state, setState] = useState<"idle" | "previewing" | "generating">("idle");
  const [result, setResult] = useState<Generated | null>(null);
  const [error, setError] = useState<{ message: string; problems: string[] } | null>(null);
  const total = KINDS.reduce((n, k) => n + mix[k], 0);
  const mixText = KINDS.filter((k) => mix[k] > 0)
    .map((k) => `${k}=${mix[k]}`)
    .join(",");
  // The estimate was for another goal.
  useEffect(() => setPreview(null), [draft]);

  async function run(kind: "previewing" | "generating") {
    setState(kind);
    setError(null);
    try {
      if (kind === "previewing") {
        setPreview(await api.dryRun(mixText, model, draft));
      } else {
        setResult(await api.generate(mixText, model, draft));
        setPreview(null);
        await onChanged();
      }
    } catch (e) {
      setError({ message: message(e), problems: e instanceof ApiError ? e.problems : [] });
    } finally {
      setState("idle");
    }
  }

  const approved = scenarios?.filter((s) => s.runnable).length ?? 0;
  return (
    <section className="gen-part" aria-label="Generate tasks">
      <h3 className="insp__label">Generate tasks</h3>
      <div className="section">
        {scenarios && scenarios.length > 0 ? (
          <p className="notice">
            {plural(scenarios.length, "task")} on disk, {approved} approved. New ones are added beside them.
          </p>
        ) : null}
        <fieldset className="section" style={{ border: 0, margin: 0, padding: 0 }}>
          <legend className="row row--between" style={{ width: "100%", padding: 0 }}>
            <h3>Mix</h3>
            <span className="small muted num">{plural(total, "task")}</span>
          </legend>
          {KINDS.map((k) => (
            <div key={k} className="slider">
              <label htmlFor={`mix-${k}`} title={KIND_HINT[k]}>
                {kindLabel(k)}
              </label>
              <input
                id={`mix-${k}`}
                type="range"
                min={0}
                max={10}
                value={mix[k]}
                aria-describedby={`mix-${k}-hint`}
                onChange={(e) => {
                  setMix({ ...mix, [k]: Number(e.target.value) });
                  setPreview(null);
                }}
              />
              <output htmlFor={`mix-${k}`}>{mix[k]}</output>
              <span id={`mix-${k}-hint`} className="visually-hidden">
                {KIND_HINT[k]}
              </span>
            </div>
          ))}
        </fieldset>
        <div className="field">
          <label htmlFor="gen-model">Model</label>
          <select
            id="gen-model"
            className="select"
            value={model}
            onChange={(e) => {
              setModel(e.target.value);
              setPreview(null);
            }}
          >
            {MODELS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </div>

        {!preview ? (
          <button
            type="button"
            className="btn btn--block"
            disabled={total === 0 || state !== "idle"}
            onClick={() => void run("previewing")}
          >
            {state === "previewing" ? "Preparing…" : "Preview the Request"}
          </button>
        ) : (
          <div className="card enter" aria-live="polite">
            <h3>Ready to Send</h3>
            <dl className="kv small">
              <dt>Reads</dt>
              <dd>{preview.included.join(", ") || "nothing"}</dd>
              {preview.dropped.length ? (
                <>
                  <dt>Left out</dt>
                  <dd>{preview.dropped.join(", ")} (over the size limit)</dd>
                </>
              ) : null}
              <dt>Input</dt>
              <dd className="num">About {plural(preview.tokens_est, "token")}</dd>
              <dt>Model</dt>
              <dd className="mono">{preview.model}</dd>
            </dl>
            <p className="small muted">
              One Claude API call with your key. Output is checked as a whole; nothing is written if any part is wrong.
            </p>
            {!project.key_set ? (
              <p className="notice notice--warning small">
                Set ANTHROPIC_API_KEY in the shell that runs <code>rig serve</code>, then restart it.
              </p>
            ) : null}
            <div className="row">
              <button
                type="button"
                className="btn btn--primary"
                disabled={!project.key_set || state !== "idle"}
                onClick={() => void run("generating")}
              >
                {state === "generating" ? "Writing tasks…" : `Generate ${plural(total, "Task")}`}
              </button>
              <button type="button" className="btn btn--quiet" onClick={() => setPreview(null)} disabled={state !== "idle"}>
                Change
              </button>
            </div>
          </div>
        )}

        {state === "generating" ? (
          <div className="section" aria-live="polite">
            <p className="small muted">Writing the workflow, tasks and their checks. This usually takes one to three minutes.</p>
            <Skeleton lines={4} />
          </div>
        ) : null}
        {error ? <ErrorNotice error={error.message} problems={error.problems} /> : null}
        {result ? (
          <div className="section enter">
            <h3>{result.workflow.name}</h3>
            <p className="small muted">
              {plural(result.written, "file")} written, {result.tokens.in.toLocaleString()} tokens in,{" "}
              {result.tokens.out.toLocaleString()} out. Every check starts unreviewed.
            </p>
            <ul className="list">
              {result.scenarios.map((s) => (
                <li key={s.id} className="item__top" style={{ padding: "8px 0" }}>
                  <span className="mono small">{s.id}</span>
                  <span className="item__name" style={{ fontWeight: 400 }}>
                    {s.title}
                  </span>
                  <KindChip kind={s.kind} />
                </li>
              ))}
            </ul>
            <a className="btn" href="#prove">
              Review Checks in Prove
            </a>
          </div>
        ) : null}
      </div>
    </section>
  );
}
