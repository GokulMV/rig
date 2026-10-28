import { useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import { useRigExplain } from "../lib/rigExplain";
import type { BeforeAfterCompare, BeforeAfterRefs, BeforeAfterWords, MetricId, MetricPlan, TreatmentItem } from "../lib/types";

/** What can be measured on Measure: a skill (from the canvas or the repo), or one of the repo's configs. */
export interface Change {
  path: string;
  name: string;
  kind: "skill" | "hook" | "mcp" | "instructions";
  /** A config: what the two arms get, in words (treatment-kinds compare_text). */
  compare?: TreatmentItem["compare"];
  compareText?: string;
  /** Instructions: the file it writes and its text, for an edited copy. */
  file?: string;
  text?: string;
}

const GROUPS: { kind: Change["kind"]; label: string }[] = [
  { kind: "skill", label: "Skills" },
  { kind: "instructions", label: "Instructions (CLAUDE.md, AGENTS.md)" },
  { kind: "hook", label: "Hooks" },
  { kind: "mcp", label: "MCP Servers" },
];

const WHERE: Record<string, string> = { repo: "in repo", user: "your skills folder", library: "library", draft: "your edited copy" };

/** A config from /api/treatments as a change on Measure: "CLAUDE.md · in repo, edited". */
export function configChange(t: TreatmentItem): Change {
  const where = WHERE[t.source ?? ""] ?? t.source ?? "";
  const note = t.compare === "edited" ? "edited, not committed" : t.compare === "new" ? "not committed" : t.compare === "same" ? "same in both arms" : "";
  return {
    path: t.path,
    name: [t.name, [where, note].filter(Boolean).join(", ")].filter(Boolean).join(" · "),
    kind: (t.kind ?? "skill") as Change["kind"],
    compare: t.compare,
    compareText: t.compare_text,
    file: t.file,
    text: t.text,
  };
}

/** A change that would measure nothing: both arms get the same file. */
export function measuresNothing(c: Change | undefined): boolean {
  return c?.compare === "same";
}

/** The change to measure, grouped by kind, with what each arm gets under it. */
export function ChangePicker({
  changes,
  value,
  onChange,
  onSaved,
}: {
  changes: Change[];
  value: string;
  onChange: (path: string) => void;
  /** After an edited copy is saved: reload, then pick it. */
  onSaved: (path: string) => Promise<void>;
}) {
  const chosen = changes.find((c) => c.path === value);
  return (
    <div className="field">
      <label htmlFor="run-change">Change to measure</label>
      <select id="run-change" className="select" value={value} onChange={(e) => onChange(e.target.value)}>
        {GROUPS.map((g) => {
          const mine = changes.filter((c) => c.kind === g.kind);
          return mine.length ? (
            <optgroup key={g.kind} label={g.label}>
              {mine.map((c) => (
                <option key={c.path} value={c.path}>
                  {c.name}
                </option>
              ))}
            </optgroup>
          ) : null;
        })}
      </select>
      {chosen && chosen.kind !== "skill" ? (
        <p className={`small ${measuresNothing(chosen) ? "notice notice--warning" : "muted"}`} data-testid="change-compare">
          {chosen.compareText}
        </p>
      ) : null}
      {chosen?.kind === "instructions" ? <InstructionsDraft key={chosen.path} change={chosen} onSaved={onSaved} /> : null}
    </div>
  );
}

/** Edit a copy of the chosen instructions; saved, it is measured against the committed file. */
function InstructionsDraft({ change, onSaved }: { change: Change; onSaved: (path: string) => Promise<void> }) {
  const file = change.file === "AGENTS.md" ? "AGENTS.md" : "CLAUDE.md";
  const [open, setOpen] = useState(measuresNothing(change));
  const [text, setText] = useState(change.text ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <details className="pal-group" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)} data-testid="instructions-draft">
      <summary>
        <span className="pal-group__title">Edit a copy of {file} to measure</span>
      </summary>
      <p className="small muted">
        The copy is kept in .proving-ground/, outside both arms. Measured, the &ldquo;with&rdquo; arm gets it in place of the committed {file}; the
        &ldquo;without&rdquo; arm keeps the committed one.
      </p>
      <label className="visually-hidden" htmlFor="instructions-text">
        Edited {file}
      </label>
      <textarea id="instructions-text" className="input mono" rows={8} value={text} onChange={(e) => setText(e.target.value)} />
      {error ? (
        <p className="notice notice--warning small" role="alert">
          {error}
        </p>
      ) : null}
      <button
        type="button"
        className="btn btn--small"
        disabled={busy || !text.trim() || text === change.text}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            const saved = await api.saveInstructions({ text, file });
            await onSaved(saved.path);
          } catch (e) {
            setError(e instanceof ApiError ? e.message : String(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Saving…" : "Save the Copy and Measure It"}
      </button>
    </details>
  );
}

export interface MetricOption {
  id: MetricId;
  name: string;
  describe: string;
}

/** Shown until GET /api/rig-score answers; the engine's words (the rig-score skill) replace them. */
export const METRIC_FALLBACK: MetricOption[] = [
  { id: "pass_rate", name: "Pass Rate", describe: "Does it solve more tasks? The lift is the rise in the pass rate." },
  { id: "tokens", name: "Tokens per Solved Task", describe: "Does it use fewer tokens for each task it solves, without solving fewer? Tokens are in + out as the agent reports them, cached input included." },
  { id: "cost", name: "Cost per Solved Task", describe: "Does each solved task cost less, without solving fewer?" },
  { id: "time", name: "Time per Solved Task", describe: "Does each solved task take less time, without solving fewer?" },
];

// Until GET /api/rig-score answers (judge-experiment: auto_extend.text).
const KEEP_GOING_FALLBACK = "adds pairs while the result is unclear, up to the budget. Stops early only when a stricter (99%) interval rules out zero.";
const KEEP_GOING_SAVING_FALLBACK = "adds pairs until the saving and the pass-rate guard are both decided, up to the budget.";

/** What the run is scored on: the pass rate, or a saving with the pass rate as a guard. */
export function MetricPicker({
  value,
  onChange,
  options,
  guardNote,
  hinted,
}: {
  value: MetricId;
  onChange: (m: MetricId) => void;
  options: MetricOption[];
  /** The engine's words for the pass rate as the guard (rig-score metric.guard_note). */
  guardNote: string | null;
  /** The goal's hint picked it. */
  hinted: boolean;
}) {
  const chosen = options.find((o) => o.id === value) ?? options[0];
  return (
    <div className="field" data-testid="metric-picker">
      <span className="label" id="run-metric-label">
        Score the run on
      </span>
      <div className="segmented" role="radiogroup" aria-labelledby="run-metric-label">
        {options.map((o) => (
          <button key={o.id} type="button" role="radio" aria-checked={o.id === value} aria-label={o.name} onClick={() => onChange(o.id)}>
            {short(o.name)}
          </button>
        ))}
      </div>
      <p className="small muted" data-testid="metric-describe">
        <b>{chosen.name}.</b> {chosen.describe}
        {chosen.id !== "pass_rate" && guardNote ? ` ${guardNote}` : ""}
        {hinted ? " Picked from your goal." : ""}
      </p>
    </div>
  );
}

/** "Tokens per Solved Task" → "Tokens": the segment's label; the full name is its accessible name. */
function short(name: string): string {
  return name.replace(/ per solved task$/i, "");
}

/** The metric choice's state: the goal's hint until the person picks one. */
export function useMetric(hint: MetricId | null | undefined): [MetricId, (m: MetricId) => void, boolean] {
  const [picked, setPicked] = useState<MetricId | null>(null);
  const [value, setValue] = useState<MetricId>(hint ?? "pass_rate");
  useEffect(() => {
    if (picked == null) setValue(hint ?? "pass_rate");
  }, [hint, picked]);
  return [
    value,
    (m: MetricId) => {
      setPicked(m);
      setValue(m);
    },
    picked == null && !!hint && hint !== "pass_rate",
  ];
}

/* ---------------- A code change, before and after ---------------- */

/** The two sides of a before/after run: the base commit, and the after side (null: the working tree). */
export interface BeforeAfterChoice {
  base: string;
  after: string | null;
}

const WORKING = "__working__";

/** The after side to start from: the uncommitted changes if there are any, else the newest other branch. */
export function defaultAfter(refs: BeforeAfterRefs): string | null {
  if (!refs.git || refs.dirty) return null;
  return refs.branches.find((b) => !b.current && b.sha !== refs.head.sha)?.name ?? null;
}

/** Pick the base commit and the after side; under them, what the run compares, or why it would
 * measure nothing (the measurability skill's words). Rig doesn't write the change. */
export function BeforeAfterPicker({
  words,
  value,
  onChange,
  onCompare,
}: {
  words: BeforeAfterWords;
  value: BeforeAfterChoice | null;
  onChange: (v: BeforeAfterChoice) => void;
  /** What the engine says the choice compares; null while asking, or when it can't be run. */
  onCompare: (c: BeforeAfterCompare | null) => void;
}) {
  const [refs, setRefs] = useState<BeforeAfterRefs | null>(null);
  const [cmp, setCmp] = useState<BeforeAfterCompare | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asks, setAsks] = useState(0);
  useEffect(() => {
    let live = true;
    api.beforeAfterRefs().then(
      (r) => {
        if (!live) return;
        setRefs(r);
        if (r.git && value === null) onChange({ base: "HEAD", after: defaultAfter(r) });
      },
      (e) => live && setError(e instanceof ApiError ? e.message : String(e)),
    );
    return () => {
      live = false;
    };
    // Asked again on "Check again": only the first answer picks the default sides.
  }, [asks]);
  useEffect(() => {
    if (!value || !refs?.git) return;
    let live = true;
    setCmp(null);
    setError(null);
    onCompare(null);
    api.beforeAfterCompare(value.base, value.after).then(
      (c) => {
        if (!live) return;
        setCmp(c);
        onCompare(c);
      },
      (e) => live && setError(e instanceof ApiError ? e.message : String(e)),
    );
    return () => {
      live = false;
    };
  }, [value?.base, value?.after, refs, asks]);

  if (refs && !refs.git)
    return (
      <p className="notice notice--warning small" data-testid="ba-not-git">
        {refs.says}
      </p>
    );
  const commits = refs?.git ? refs.commits.filter((c) => c.sha !== refs.head.sha) : [];
  const branches = refs?.git ? refs.branches.filter((b) => !b.current) : [];
  const head = refs?.git ? refs.head : null;
  const headLabel = head ? `HEAD${head.branch ? ` · ${head.branch}` : ""} (${head.short}) ${head.subject}` : "HEAD";
  const options = (
    <>
      {branches.length ? (
        <optgroup label="Branches">
          {branches.map((b) => (
            <option key={b.name} value={b.name}>
              {b.name} ({b.short}) {b.subject}
            </option>
          ))}
        </optgroup>
      ) : null}
      {commits.length ? (
        <optgroup label="Recent Commits">
          {commits.map((c) => (
            <option key={c.sha} value={c.sha}>
              {c.short} {c.subject}
            </option>
          ))}
        </optgroup>
      ) : null}
    </>
  );
  return (
    <div className="field" data-testid="before-after">
      <p className="small" data-testid="ba-lead">
        {words.lead}
      </p>
      <label htmlFor="ba-base">{words.base}</label>
      <select
        id="ba-base"
        className="select"
        value={value?.base ?? "HEAD"}
        disabled={!refs}
        onChange={(e) => onChange({ base: e.target.value, after: value?.after ?? null })}
      >
        <option value="HEAD">{headLabel}</option>
        {options}
      </select>
      <label htmlFor="ba-after">{words.after}</label>
      <select
        id="ba-after"
        className="select"
        value={value ? (value.after ?? WORKING) : WORKING}
        disabled={!refs}
        onChange={(e) => onChange({ base: value?.base ?? "HEAD", after: e.target.value === WORKING ? null : e.target.value })}
      >
        <option value={WORKING}>
          {words.working_tree[0].toUpperCase() + words.working_tree.slice(1)}
        </option>
        {options}
        <option value="HEAD">{headLabel}</option>
      </select>
      {error ? (
        <p className="notice notice--warning small" role="alert" data-testid="ba-error">
          {error}
        </p>
      ) : cmp ? (
        <div className={`small ${cmp.same ? "notice notice--warning" : "muted"}`} data-testid="ba-compare">
          <p>{cmp.says}</p>
          {cmp.same ? null : (
            <details>
              <summary data-testid="ba-files">{cmp.files_text}</summary>
              <ul className="mono">
                {cmp.files.map((f) => (
                  <li key={f}>{f}</li>
                ))}
                {cmp.n_files > cmp.files.length ? <li>…</li> : null}
              </ul>
            </details>
          )}
        </div>
      ) : (
        <p className="small muted">Reading the repo…</p>
      )}
      <button type="button" className="btn btn--small btn--quiet" style={{ justifySelf: "start" }} onClick={() => setAsks((n) => n + 1)}>
        Check Again
      </button>
    </div>
  );
}

/** The metric choice on Measure, the same for a repo and the Lab: the value, the picker, what the
 * confirm card says about it, and `onPlan` for RunEstimate's onMetricPlan (the guard's sizing). */
export function useMetricChoice(hint?: MetricId | null) {
  const [metric, setMetric, hinted] = useMetric(hint);
  const explained = useRigExplain().data?.metric;
  const [plan, onPlan] = useState<MetricPlan | null>(null);
  const options = explained?.options ?? METRIC_FALLBACK;
  const name = options.find((o) => o.id === metric)?.name ?? metric;
  const picker = <MetricPicker value={metric} onChange={setMetric} options={options} guardNote={explained?.guard_note ?? null} hinted={hinted} />;
  // "Keep going until it's decided" (the Lab): on a saving it waits for the saving and its guard.
  const keepGoing = explained?.keep_going?.[metric] ?? (metric === "pass_rate" ? KEEP_GOING_FALLBACK : KEEP_GOING_SAVING_FALLBACK);
  const confirm = (
    <>
      <p className="small" data-testid="confirm-metric">
        Scored on {name.toLowerCase()}
        {metric === "pass_rate" ? "." : ", with the pass rate as the guard."}
      </p>
      {plan && plan.metric === metric && !plan.enough ? (
        plan.extends ? (
          <p className="small" data-testid="confirm-metric-extends">
            {plan.lines.join(" ")}
          </p>
        ) : (
          <p className="notice notice--warning small" data-testid="confirm-metric-short">
            {plan.lines.join(" ")}
          </p>
        )
      ) : null}
    </>
  );
  return { metric, onPlan, picker, confirm, keepGoing };
}
