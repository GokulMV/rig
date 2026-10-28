import { Check, Download, Eye, FlaskConical, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import { measureBadge, useRules } from "../lib/rules";
import { ProjectStructure } from "./BuildSpec";
import { MeasureBadge } from "./MeasureBadge";
import type { Impact, Proposal, Suggestions } from "../lib/types";

const IMPACT: Record<Impact, string> = {
  reliability: "Reliability",
  speed: "Speed",
  agent: "Agent Success",
  clarity: "Clarity",
};
const KIND: Record<Proposal["kind"], string> = {
  split: "Split",
  merge: "Merge",
  add: "Add",
  reconnect: "Reconnect",
  move: "Move",
  remove: "Remove",
  check: "Check",
};
const EFFORT = { S: "an afternoon", M: "a few days", L: "a week or more" };

function ProposalCard({
  p,
  previewing,
  names,
  onPreview,
  onDecide,
  onMeasure,
}: {
  p: Proposal;
  previewing: boolean;
  names: Map<string, string>;
  onPreview: () => void;
  onDecide: (state: Proposal["state"]) => void;
  /** Open Measure on "A code change: before and after", for this suggestion. */
  onMeasure?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const mr = useRules("measurability");
  const mb = measureBadge({ kind: "proposal", p }, mr);
  // A change to the code is measured before and after: the badge leads straight there.
  const measurable = mb?.id === "before_after" && p.state !== "dismissed" && !!onMeasure;
  return (
    <li className={`prop prop--${p.state}${previewing ? " is-previewing" : ""}`} data-prop={p.id}>
      <div className="prop__head">
        <span className={`prop__kind prop__kind--${p.kind}`}>{KIND[p.kind]}</span>
        {p.state === "accepted" ? <span className="prop__state">Accepted</span> : null}
        <MeasureBadge b={mb} />
        {p.source === "review" ? <span className="prop__src">from the agent's review</span> : null}
        <span className="prop__effort" title={`Effort: ${EFFORT[p.effort]}`}>
          {p.effort}
        </span>
      </div>
      <button type="button" className="prop__title" aria-expanded={open} onClick={() => setOpen(!open)}>
        {p.title}
      </button>
      <div className="prop__impacts">
        {(Object.keys(p.impact) as Impact[]).map((k) => (
          <span key={k} className={`impact impact--${k}`}>
            {IMPACT[k]}
          </span>
        ))}
      </div>
      <p className="small">{p.why}</p>
      {mb ? (
        <p className="small muted prop__measure" data-testid="prop-measure">
          {mb.says}
        </p>
      ) : null}
      {open ? (
        <div className="prop__more">
          <div className="insp__label">What it does</div>
          <p className="small">{p.what}</p>
          <div className="insp__label">What it improves</div>
          <ul className="insp__points small">
            {(Object.entries(p.impact) as [Impact, string][]).map(([k, v]) => (
              <li key={k}>
                <strong>{IMPACT[k]}:</strong> {v}
              </li>
            ))}
          </ul>
          {p.targets.length ? (
            <>
              <div className="insp__label">Parts it touches</div>
              <p className="small">{p.targets.map((t) => names.get(t) ?? t.replace(/^step:/, "step ")).join(", ")}</p>
            </>
          ) : null}
          {p.evidence.length ? (
            <>
              <div className="insp__label">Evidence</div>
              <ul className="insp__points small mono">
                {p.evidence.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </>
          ) : null}
          <p className="small muted">
            Effort: {EFFORT[p.effort]}. Nothing changes in the code here: accepting draws it in "With Accepted" on the canvas and
            puts it in BUILD.md.
          </p>
        </div>
      ) : (
        <button type="button" className="linkish small" onClick={() => setOpen(true)}>
          Why, What It Does, and the Evidence
        </button>
      )}
      <div className="row prop__actions">
        {measurable ? (
          <button type="button" className="btn btn--small" onClick={onMeasure} data-testid="prop-measure-it">
            <FlaskConical size={13} aria-hidden="true" /> {mr?.before_after.measure_it}
          </button>
        ) : null}
        {p.delta && (p.delta.add?.length || p.delta.connect?.length || p.delta.remove?.length) ? (
          <button type="button" className="btn btn--small btn--quiet" aria-pressed={previewing} onClick={onPreview}>
            <Eye size={13} aria-hidden="true" /> {previewing ? "Previewing" : "Preview"}
          </button>
        ) : null}
        {p.state === "accepted" ? (
          <button type="button" className="btn btn--small btn--quiet" onClick={() => onDecide("open")}>
            Undo
          </button>
        ) : (
          <button type="button" className="btn btn--small btn--primary" onClick={() => onDecide("accepted")}>
            <Check size={13} aria-hidden="true" /> Accept
          </button>
        )}
        {p.state === "dismissed" ? (
          <button type="button" className="btn btn--small btn--quiet" onClick={() => onDecide("open")}>
            Bring Back
          </button>
        ) : p.state === "open" ? (
          <button type="button" className="btn btn--small btn--quiet" onClick={() => onDecide("dismissed")}>
            <X size={13} aria-hidden="true" /> Dismiss
          </button>
        ) : null}
      </div>
    </li>
  );
}

export function SuggestionsPanel({
  agent,
  preview,
  names,
  onPreview,
  onChanged,
  onAddTask,
  onMeasure,
}: {
  agent: { id: string; label: string } | null;
  preview: string | null;
  names: Map<string, string>;
  onPreview: (id: string | null) => void;
  onChanged: () => void;
  /** "Add a task for <step>" accepted: open Measure's Add task with that step. */
  onAddTask?: (step: string) => void;
  /** "Measure it" on a suggestion that changes the code: open Measure before and after, for it. */
  onMeasure?: (p: Proposal) => void;
}) {
  const [data, setData] = useState<Suggestions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [exported, setExported] = useState<string | null>(null);
  const load = () =>
    api.suggestions().then(
      (d) => {
        setData(d);
        setError(null);
      },
      (e) => setError(e instanceof ApiError ? e.message : String(e)),
    );
  useEffect(() => {
    void load();
  }, []);
  const reviewing = data?.review.state === "running";
  useEffect(() => {
    if (!reviewing) return;
    const t = window.setInterval(async () => {
      const r = await api.reviewStatus().catch(() => null);
      if (r && r.state !== "running") void load();
    }, 3000);
    return () => window.clearInterval(t);
  }, [reviewing]);

  if (error) return <p className="notice notice--error small">{error}</p>;
  if (!data) return <p className="small muted">Reading the architecture…</p>;
  const open = data.proposals.filter((p) => p.state === "open");
  const accepted = data.proposals.filter((p) => p.state === "accepted");
  const dismissed = data.proposals.filter((p) => p.state === "dismissed");
  const decide = async (p: Proposal, state: Proposal["state"]) => {
    await api.decide(p.id, state);
    if (preview === p.id) onPreview(null);
    await load();
    onChanged();
    // Accepting "Add a task for <step>" is a job for Measure: go and write it there.
    const step = p.targets.find((t) => t.startsWith("step:"));
    if (state === "accepted" && p.adds === "task" && step && onAddTask) {
      onAddTask(step.slice("step:".length));
      return;
    }
    // The card moved to another section: keep it in sight, clear of the sticky tabs.
    requestAnimationFrame(() => document.querySelector(`[data-prop="${p.id}"]`)?.scrollIntoView({ block: "nearest" }));
  };
  const card = (p: Proposal) => (
    <ProposalCard
      key={p.id}
      p={p}
      names={names}
      previewing={preview === p.id}
      onPreview={() => onPreview(preview === p.id ? null : p.id)}
      onDecide={(s) => void decide(p, s)}
      onMeasure={onMeasure ? () => onMeasure(p) : undefined}
    />
  );

  return (
    <div className="section">
      <div>
        <div className="insp__label">Suggested changes</div>
        <p className="small muted">
          Read from this repo's architecture and code, by written rules. Preview one to see it on the canvas; accept the ones you
          want. Accepted ones are drawn in “With Accepted” and go in BUILD.md; each says whether Measure can test it.
        </p>
      </div>

      {open.length ? <ul className="props">{open.map(card)}</ul> : <p className="small">Nothing open: everything was accepted or dismissed.</p>}

      {accepted.length ? (
        <>
          <div className="insp__label">Accepted · in “With Accepted” and BUILD.md</div>
          <ul className="props">{accepted.map(card)}</ul>
          <button
            type="button"
            className="btn btn--small"
            onClick={async () => {
              const p = await api.proposed();
              setExported(JSON.stringify(p.archify, null, 2));
            }}
          >
            <Download size={13} aria-hidden="true" /> Export as an Archify Spec
          </button>
          {exported ? (
            <>
              <label className="visually-hidden" htmlFor="archify-export">
                Proposed architecture, Archify JSON
              </label>
              <textarea id="archify-export" className="input mono draft" readOnly value={exported} onFocus={(e) => e.currentTarget.select()} />
              <p className="small muted">Save it as docs/architecture.architecture.json to keep it with the repo.</p>
            </>
          ) : null}
        </>
      ) : null}

      <ProjectStructure refreshKey={data.proposals.map((p) => p.id + p.state).join()} />

      <div className="signbox">
        <strong>
          <Sparkles size={14} aria-hidden="true" /> A Deeper Review
        </strong>
        {reviewing ? (
          <p className="small">{agent?.label ?? "The agent"} is reading the repo for more suggestions… they'll appear above.</p>
        ) : confirm ? (
          <>
            <p className="small">
              {agent?.label ?? "The agent"} reads the code with read-only tools and proposes changes the rules can't see. One agent
              session, on your sign-in. Each proposal must cite files in the repo, or it's dropped.
            </p>
            <div className="row" style={{ gap: 8 }}>
              <button
                type="button"
                className="btn btn--small btn--primary"
                onClick={async () => {
                  setConfirm(false);
                  try {
                    await api.review(agent?.id ?? "claude-code");
                  } catch (e) {
                    setError(e instanceof ApiError ? e.message : String(e));
                    return;
                  }
                  await load();
                }}
              >
                Review It
              </button>
              <button type="button" className="btn btn--small btn--quiet" onClick={() => setConfirm(false)}>
                Cancel
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="small muted">
              {data.review.state === "done"
                ? `Last review added ${data.review.count ?? 0} suggestion${data.review.count === 1 ? "" : "s"}.`
                : data.review.state === "error"
                  ? data.review.error
                  : "The agent reads the code and suggests what the rules can't see."}
            </p>
            <button type="button" className="btn btn--small" onClick={() => setConfirm(true)}>
              Ask {agent?.label ?? "the Agent"} to Review
            </button>
          </>
        )}
      </div>

      {dismissed.length ? (
        <details>
          <summary className="small muted">Dismissed ({dismissed.length})</summary>
          <ul className="props">{dismissed.map(card)}</ul>
        </details>
      ) : null}
    </div>
  );
}
