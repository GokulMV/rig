import type { Proven, RigScore as Rig, RigTone } from "../lib/types";
import { Term } from "./Term";

/** The Rig score: the number, its band, why, and the five parts it is made of. */
export function RigScore({
  rig,
  compact = false,
  title = "Rig Score",
  name,
  howLink = true,
  context,
}: {
  rig: Rig;
  compact?: boolean;
  /** The kicker above the label. */
  title?: string;
  /** What the region is called to a screen reader, when there are several on a page. */
  name?: string;
  /** "How is this scored?", to the Rig score's explainer (#/rig-score). Off on that page itself. */
  howLink?: boolean;
  /** What the two arms were, beside the title: "before vs after" for a code change. */
  context?: string | null;
}) {
  const none = rig.score == null;
  const notEvidence = rig.band === "not_evidence";
  const cls = ["rig", `rig--${rig.tone}`, compact ? "rig--compact" : "", rig.provisional ? "rig--provisional" : "", notEvidence ? "rig--not-evidence" : ""]
    .filter(Boolean)
    .join(" ");
  // Only caps the number is actually held by; the provisional note always says how few pairs.
  const gates = rig.gates.filter((g) => g.binding !== false || g.id === "provisional");
  const v = rig.verdict;
  const number = (
    <div className="rig__num num">
      <span className="rig__value" aria-hidden="true">
        {none ? "—" : rig.score}
      </span>
      {none ? null : (
        <span className="rig__of" aria-hidden="true">
          /100
        </span>
      )}
      <span className="visually-hidden">
        {none ? `${title}: ${notEvidence ? "no score, not evidence" : "not measured"}.` : `${title}: ${rig.score} out of 100.`}
      </span>
    </div>
  );
  const kicker = (
    <span className="rig__kickrow">
      <span className="rig__kicker">
        {title}
        {context ? (
          <span className="rig__prov" data-testid="rig-context">
            {" "}
            · {context}
          </span>
        ) : null}
        {rig.provisional ? <span className="rig__prov"> · provisional: {rig.pairs} {rig.pairs === 1 ? "pair" : "pairs"}</span> : null}
      </span>
      {compact ? null : <Term k="rig-score" />}
      {howLink ? (
        <a className="rig__how small" href="#/rig-score">
          How Is This Scored?
        </a>
      ) : null}
    </span>
  );
  return (
    <section className={cls} aria-label={name ?? title} data-testid="rig-score" data-band={rig.band} data-verdict={v?.id}>
      {v ? (
        // The plain answer is the headline; the 0-100 number and its band sit beside it.
        <>
          <div className="rig__head rig__head--verdict">
            <div className="rig__words">
              {kicker}
              <span className={`rig__verdict rig__verdict--${v.tone}`} data-testid="rig-verdict">
                {v.word}
              </span>
            </div>
            <div className="rig__side">
              {number}
              <span className="rig__label">{rig.label}</span>
            </div>
          </div>
          <p className="rig__why" data-testid="rig-why">
            {v.reason} <span className="rig__next">{v.next}</span>
          </p>
          {v.facts.length && !compact ? (
            <ul className="rig__facts small num" data-testid="rig-facts">
              {v.facts.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          ) : null}
          {/* The score's own reason, one quiet line: its drags, or why it isn't evidence. */}
          {(none && !notEvidence) || rig.reason === v.reason ? null : (
            <p className="rig__reason small muted">
              {none ? "" : "Score: "}
              {rig.reason}
            </p>
          )}
        </>
      ) : (
        <>
          <div className="rig__head">
            {number}
            <div className="rig__words">
              {kicker}
              <span className="rig__label">{rig.label}</span>
            </div>
          </div>
          <p className="rig__reason">{rig.reason}</p>
        </>
      )}
      {none ? null : (
        <ul className="rig__parts">
          {rig.parts.map((p) => {
            const off = p.score == null;
            const noCredit = !off && p.counted === false;
            // Cost on a tokens or cost run: what Lift measures, so scored there, not twice.
            const folded = off && p.folded;
            return (
              <li key={p.id} className={`rig__part${off ? " rig__part--off" : ""}${noCredit ? " rig__part--nocredit" : ""}`}>
                <span className="rig__name">
                  {p.name} <span className="rig__weight num">{Math.round(p.weight * 100)}%</span>
                </span>
                <span className="rig__track" aria-hidden="true">
                  {!off && !noCredit ? <span className="rig__fill" style={{ width: `${p.score}%` }} /> : null}
                </span>
                <span className="rig__score num">{folded ? "in Lift" : off ? "not measured" : noCredit ? "no credit" : Math.round(p.score!)}</span>
                <span className="rig__detail">
                  {p.detail}
                  {noCredit && p.note ? ` · ${p.note}` : ""}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {rig.formula ? (
        <p className="rig__formula small muted num" data-testid="rig-formula">
          {rig.formula.text}
        </p>
      ) : null}
      {gates.length && !compact ? (
        <ul className="rig__gates">
          {gates.map((g) => (
            <li key={g.id}>{g.text}</li>
          ))}
        </ul>
      ) : null}
      {rig.ledger_text ? (
        <p className="rig__ledger small muted num" data-testid="rig-ledger">
          Trials: {rig.ledger_text}
        </p>
      ) : null}
    </section>
  );
}

/** The small form, for a list item: "Rig 72". */
export function RigBadge({ score, tone, provisional, label, band }: { score: number | null; tone: RigTone; provisional?: boolean; label?: string; band?: string }) {
  if (score == null && band === "not_evidence")
    return (
      <span className="rig-badge rig-badge--neutral" title="Not evidence: no Rig score" data-testid="rig-badge">
        Not Evidence
      </span>
    );
  if (score == null) return null;
  const what = `Rig score ${score} out of 100${label ? `: ${label}` : ""}${provisional ? " (provisional: few pairs)" : ""}`;
  return (
    <span className={`rig-badge rig-badge--${tone}${provisional ? " rig-badge--provisional" : ""} num`} title={what} data-testid="rig-badge">
      <span aria-hidden="true">Rig {score}</span>
      <span className="visually-hidden">{what}</span>
    </span>
  );
}

/** The badge from a skill folder's `proven:` claim, when it carries a score. */
export function ProvenRig({ proven }: { proven: Proven | null | undefined }) {
  if (!proven || proven.rig == null) return null;
  return <RigBadge score={proven.rig} tone={proven.rig_tone ?? "neutral"} provisional={proven.rig_provisional} />;
}
