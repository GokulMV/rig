import type { ReactNode } from "react";

import { pts, VERDICT_LABEL } from "../lib/format";
import type { Evidence, Kind, Scenario, Verdict } from "../lib/types";

const VERDICT_TONE: Record<Verdict, string> = {
  helps: "pill--positive",
  hurts: "pill--negative",
  inconclusive: "",
};

export function VerdictPill({ verdict }: { verdict: Verdict }) {
  return <span className={`pill ${VERDICT_TONE[verdict]}`}>{VERDICT_LABEL[verdict]}</span>;
}

/** What is known about a treatment, in one short pill. The interval itself lives in the Evidence pane. */
export function EvidenceChip({ evidence }: { evidence: Evidence | null }) {
  if (!evidence) return <span className="pill pill--outline">Not Measured</span>;
  if (evidence.diff == null) return <span className="pill pill--outline">No Complete Pairs</span>;
  return (
    <span className={`pill ${VERDICT_TONE[evidence.verdict]}`}>
      {VERDICT_LABEL[evidence.verdict]} <span className="num">{pts(evidence.diff, 0)}</span>
    </span>
  );
}

const KIND_LABEL: Record<Kind, string> = {
  typical: "Typical",
  edge: "Edge",
  adversarial: "Adversarial",
  failure: "Failure",
  overload: "Overload",
  imaginary: "Imaginary",
};

export function kindLabel(k: Kind): string {
  return KIND_LABEL[k];
}

export function KindChip({ kind }: { kind: Kind }) {
  return <span className="pill pill--outline">{KIND_LABEL[kind]}</span>;
}

export function ReviewPill({ s }: { s: Scenario }) {
  const goal = s.goal_changed ? (
    <span className="pill pill--warning" data-testid="goal-changed" title="Generated for an earlier use case. Regenerate it, or check it still fits.">
      Written for a Different Goal
    </span>
  ) : null;
  let review;
  if (s.check && s.check_problem) {
    // Approved before checks were validated, or never approvable: it isn't run either way.
    review = (
      <span className="pill pill--warning" data-testid="check-problem" title={s.check_problem}>
        {s.runnable ? "Approved, but the Check Isn't a Command" : "Check Isn't a Command"}
      </span>
    );
  } else if (s.runnable) review = <span className="pill pill--positive">Approved</span>;
  else if (!s.check) review = <span className="pill pill--warning">No Check</span>;
  else review = <span className="pill pill--warning">Needs Review</span>;
  return goal ? (
    <span className="row" style={{ gap: 4, flexWrap: "wrap" }}>
      {review}
      {goal}
    </span>
  ) : (
    review
  );
}

export function PaneHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="pane__head">
      <h2>{title}</h2>
      <span className="spacer" />
      {children}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children}
    </div>
  );
}

export function ErrorNotice({ error, problems }: { error: string; problems?: string[] }) {
  return (
    <div className="notice notice--error" role="alert">
      {error}
      {problems && problems.length > 0 ? (
        <ul>
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="section" aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton" style={{ width: `${90 - i * 18}%` }} />
      ))}
    </div>
  );
}
