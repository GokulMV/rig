import { useEffect, useState } from "react";

import { ErrorNotice, kindLabel } from "./Bits";
import { Interval } from "./Interval";
import { RigScore } from "./RigScore";
import { follow } from "../lib/api";
import { useRules } from "../lib/rules";
import { pct, plural, pts, usd } from "../lib/format";
import { isEvidence } from "../lib/provenance";
import { adhered, adherenceText, humanName, modelText, outcomeWord, spentText, statusText, verdictWord } from "../lib/evidence";
import type { ArmStats, BeforeAfterWords, ExperimentDetail, Kind, RigMetric, RunEvent, Started, Summary } from "../lib/types";
import { Term } from "./Term";

export function LiveRun({
  started,
  onDone,
  eventsUrl,
  onStop,
  title,
}: {
  started: Started;
  /** In place of "Experiment #N running" (a baseline check names itself). */
  title?: string;
  onDone: (ok: boolean) => void;
  /** Where to follow it, when not a repo experiment (a bench run). */
  eventsUrl?: string;
  /** Ask the run to stop after the trial in progress. */
  onStop?: () => Promise<void>;
}) {
  const arms = armNames(started, useRules("measurability")?.before_after);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [stopping, setStopping] = useState(false);
  useEffect(
    () =>
      follow(
        started.id,
        (e) => {
          setEvents((cur) => [...cur, e]);
          if (e.type === "finished" || e.type === "idle") onDone(true);
          if (e.type === "error") onDone(false);
        },
        () => setEvents([]),
        eventsUrl,
      ),
    [started.id, onDone, eventsUrl],
  );
  const trials = events.filter((e) => e.type === "trial") as Extract<RunEvent, { type: "trial" }>[];
  const broken = events.filter((e) => e.type === "broken") as Extract<RunEvent, { type: "broken" }>[];
  const spent = trials.length ? trials[trials.length - 1].spent_usd : 0;
  const error = events.find((e) => e.type === "error") as Extract<RunEvent, { type: "error" }> | undefined;
  const stopped = events.find((e) => e.type === "stopped_budget") as Extract<RunEvent, { type: "stopped_budget" }> | undefined;
  const stoppedByYou = events.some((e) => e.type === "stopped");
  const reusedEv = events.filter((e) => e.type === "reused") as { type: "reused"; trials: number; saved_usd: number }[];
  const reused = reusedEv.reduce((n, e) => n + e.trials, 0);
  // On a saving, `waiting` names what is still undecided: the saving, the pass-rate guard, or both.
  const extended = events.filter((e) => e.type === "extended") as { type: "extended"; repeats: number; pairs: number; look: number; waiting?: string }[];
  const settled = events.find((e) => e.type === "settled") as { type: "settled"; reason: string; pairs: number } | undefined;
  const done = trials.length + reused;
  // With auto-extend the run grows: the planned count is only the first batch.
  const planned = extended.length ? 0 : started.trials;
  return (
    <div className="section" aria-live="polite">
      <div className="row row--between">
        <h3 style={{ margin: 0 }}>{title ?? `Experiment #${started.id} Running`}</h3>
        {onStop && !stoppedByYou ? (
          <button
            type="button"
            className="btn btn--small"
            disabled={stopping}
            onClick={async () => {
              setStopping(true);
              try {
                await onStop();
              } catch {
                setStopping(false);
              }
            }}
          >
            {stopping ? "Stopping after this trial…" : "Stop"}
          </button>
        ) : null}
      </div>
      {done === 0 && broken.length === 0 && !error ? (
        <p className="small muted">
          Building the sandbox image and running every check once with no agent. The first build takes a few minutes.
        </p>
      ) : null}
      <div className="row row--between small num">
        <span>{planned ? `${done} of ${plural(planned, "trial")}` : `${plural(done, "trial")} done`}</span>
        {started.local_model ? (
          // Free: nothing to count against a budget, so the model it runs on is said instead.
          <span data-testid="live-local">On {modelText({ model: started.model, local_model: started.local_model })} · free</span>
        ) : (
          <span>
            {usd(spent)} of {usd(started.budget)}
          </span>
        )}
      </div>
      <div
        className="progress"
        role="progressbar"
        aria-label="Trials done"
        aria-valuemin={0}
        aria-valuemax={planned || undefined}
        aria-valuenow={done}
      >
        <span style={{ width: `${planned ? Math.min(100, (done / planned) * 100) : 100}%` }} />
      </div>
      {reused ? (
        <p className="small">
          Reused {plural(reused, "baseline trial")} from earlier runs on this bench: {usd(reusedEv.reduce((n, e) => n + e.saved_usd, 0))} not
          spent again.
        </p>
      ) : null}
      {extended.length ? (
        <p className="small">
          Not decided yet at {extended[extended.length - 1].pairs} pairs:{" "}
          {extended[extended.length - 1].waiting ? `waiting on ${extended[extended.length - 1].waiting}; ` : ""}added a batch ({extended.length}{" "}
          so far).
        </p>
      ) : null}
      {settled ? (
        <p className="small muted">
          Stopped adding pairs at {settled.pairs}: {settled.reason}.
        </p>
      ) : null}
      {broken.map((b) => (
        <p key={b.scenario_id} className="notice notice--warning small">
          {b.scenario_id}: setup failed, so it is skipped.
        </p>
      ))}
      {stopped ? (
        <p className="notice notice--warning small">
          Stopped at the budget{stopped.reason ? `: ${stopped.reason}` : ""}. {usd(stopped.spent_usd)} spent of {usd(started.budget)}.
        </p>
      ) : null}
      {stoppedByYou ? <p className="notice notice--warning small">Stopped, as you asked. The trials that ran are kept.</p> : null}
      {error ? <ErrorNotice error={error.detail} /> : null}
      {trials.length ? (
        <ul className="log" aria-label="Trials">
          {[...trials].reverse().map((t) => (
            <li key={`${t.scenario_id}-${t.arm}-${t.repeat}`} className="enter">
              <span className="mono">{t.scenario_id}</span>
              <span>{armWord(t.arm, arms)}</span>
              <span className={`outcome--${t.timed_out ? "timed-out" : t.outcome}`}>{outcomeWord(t)}</span>
              <span style={{ textAlign: "right" }}>{usd(t.spent_usd)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** The arms by name: "With" and "Without", or for a code change measured before and after,
 * "After" and "Before" with the line that says which code "after" and "before" are. */
export function armNames(
  detail: Pick<ExperimentDetail, "before_after">,
  words: BeforeAfterWords | null | undefined,
): { with: string; without: string; key: string | null; card: string | null } {
  const ba = detail.before_after;
  if (!ba || !words) return { with: "With", without: "Without", key: null, card: null };
  return {
    with: words.arms.with,
    without: words.arms.without,
    key: words.key.replace("{after}", ba.after.label).replace("{base}", ba.base.label),
    card: words.card,
  };
}

/** A trial's arm as the table and the live feed name it: "with", or "after" for a code change. */
function armWord(arm: string, arms: { with: string; without: string }): string {
  return (arm === "with" ? arms.with : arm === "without" ? arms.without : arm).toLowerCase();
}

export function Trials({ detail }: { detail: ExperimentDetail }) {
  const arms = armNames(detail, useRules("measurability")?.before_after);
  const [showAll, setShowAll] = useState(false);
  const trials = showAll ? detail.trials : detail.trials.slice(-12);
  // Only a check that counts items (RIG_ITEMS) gets the column.
  const counted = detail.trials.some((t) => t.items_total);
  return (
    <>
      {detail.trials.length ? (
        <div className="section">
          <div className="row row--between">
            <h3>Trials</h3>
            {detail.trials.length > 12 ? (
              <button type="button" className="btn btn--small btn--quiet" onClick={() => setShowAll(!showAll)}>
                {showAll ? "Show Latest 12" : `Show All ${detail.trials.length}`}
              </button>
            ) : null}
          </div>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Trials">
            <table>
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Arm</th>
                  <th>Outcome</th>
                  {counted ? <th className="n">Items</th> : null}
                  <th className="n">Tokens</th>
                  <th className="n">Cost</th>
                </tr>
              </thead>
              <tbody>
                {trials.map((t) => (
                  <tr key={`${t.scenario_id}-${t.arm}-${t.repeat}`}>
                    <td className="mono">
                      {t.scenario_id} #{t.repeat}
                    </td>
                    <td>{armWord(t.arm, arms)}</td>
                    <td className={`outcome--${t.timed_out ? "timed-out" : t.outcome}`} title={t.detail ?? undefined} data-testid="trial-outcome">
                      {outcomeWord(t)}
                    </td>
                    {counted ? (
                      <td className="n">{t.items_total ? `${t.items_right}/${t.items_total}` : "—"}</td>
                    ) : null}
                    <td className="n">{(t.tokens_in + t.tokens_out).toLocaleString()}</td>
                    <td className="n">{usd(t.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </>
  );
}

function KindRow({ label, s }: { label: string; s: ArmStats }) {
  return (
    <tr>
      <td>{label}</td>
      <td className="n">{s.n_pairs}</td>
      <td className="n">{pct(s.pass_with)}</td>
      <td className="n">{pct(s.pass_without)}</td>
      <td className="n">{pts(s.diff)}</td>
    </tr>
  );
}

function finding(s: Summary): string {
  const h = s.headline;
  if (!h) return "No complete pairs yet.";
  if (s.verdict === "helps") return `With the change, ${pct(h.pass_with)} passed against ${pct(h.pass_without)} without.`;
  if (s.verdict === "hurts") return `With the change, only ${pct(h.pass_with)} passed against ${pct(h.pass_without)} without.`;
  // Only a count the run hasn't reached yet says anything ("about 2 pairs" after 3 doesn't).
  return s.required_pairs && s.required_pairs > h.n_pairs
    ? `Not enough evidence either way. About ${plural(s.required_pairs, "pair")} would detect a difference this size.`
    : "Not enough evidence either way.";
}

/** "… (-67%, 95% interval -70% to -63%)": the bracket never breaks mid-interval; it wraps whole. */
function KeepInterval({ text }: { text: string }) {
  const at = text.lastIndexOf(" (");
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}{" "}
      <span className="nowrap">{text.slice(at + 1)}</span>
    </>
  );
}

/** A run scored on tokens, cost or time: the saving with its interval, and the pass rate as the guard. */
export function MetricHeadline({ m }: { m: RigMetric }) {
  return (
    <div className={`metric-head${m.noninferior === false ? " metric-head--held" : ""}`} data-testid="metric-headline">
      <span className="small muted">Scored on {m.name.toLowerCase()}</span>
      <p className="metric-head__line num" data-testid="metric-line">
        {m.headline ? <KeepInterval text={m.headline} /> : `${m.name}: nothing to compare yet.`}
      </p>
      {m.guard ? (
        <p className="small num" data-testid="metric-guard">
          {m.guard}
          {m.noninferior === false ? <span className="muted"> · no saving is credited until the pass rate is shown to hold</span> : null}
        </p>
      ) : null}
    </div>
  );
}

export function Result({ detail }: { detail: ExperimentDetail }) {
  const arms = armNames(detail, useRules("measurability")?.before_after);
  const s = detail.summary;
  const h = s.headline;
  // The word beside the score comes from the score's band, so they can't disagree.
  const v = verdictWord(detail.rig, s.verdict);
  // A baseline check ran only the agent alone: no change was measured, so nothing is said about one.
  const probe = (detail as ExperimentDetail & { probe?: boolean; probe_result?: { text: string } | null }).probe
    ? ((detail as { probe_result?: { text: string } | null }).probe_result?.text ?? "A baseline check: the agent alone")
    : null;
  return (
    <div className="section enter">
      {detail.rig ? <RigScore rig={detail.rig} context={arms.card} /> : null}
      <div className="verdict">
        <span className="small muted">
          #{detail.id} · {humanName(detail.treatment_name)} · {modelText(detail)} ·{" "}
          <span data-testid="run-status">{statusText(detail.status, detail.status_text)}</span>
        </span>
        {detail.rig ? null : probe ? (
          <span className="verdict__word" data-testid="probe-result">
            {probe}
          </span>
        ) : (
          // With a Rig score the card above is the verdict; its label is this word.
          <span className={`verdict__word verdict__word--${v.tone}`} data-testid="verdict-word">
            {v.word}
          </span>
        )}
        {probe ? (
          <span className="small muted">The agent alone, no change: how hard the bench is for it.</span>
        ) : arms.key ? (
          <span className="small muted" data-testid="arms-key">
            {arms.key}
          </span>
        ) : (
          <span className="small muted">
            With the change
            <Term k="change" /> against the baseline
            <Term k="baseline" />, on the same tasks.
          </span>
        )}
        {/* With a Rig score the card says it already, and the tiles below give the pass rates. */}
        {!detail.rig && !probe && (isEvidence(detail.validity) || detail.status === "running") ? <p>{finding(s)}</p> : null}
        {detail.adherence ? (
          <p className={`small adh${adhered(detail.adherence) ? " adh--ok" : ""}`} data-testid="run-adherence">
            {adherenceText(detail.adherence)}
          </p>
        ) : null}
        {detail.status !== "running" && !isEvidence(detail.validity) ? (
          detail.rig ? (
            // The card already says "Not evidence" and why; only what it doesn't say is left.
            <p className="small muted" data-testid="validity-note">
              Estimates don't count this run as a measurement of the change; its costs still price the next run.
            </p>
          ) : (
            <p className="notice notice--warning small" data-testid="validity-badge">
              <b>{detail.validity?.badge}</b> {detail.validity?.reason} Estimates don't count it as a measurement of the change; its costs still price the next run.
            </p>
          )
        ) : null}
      </div>
      {detail.rig?.metric ? <MetricHeadline m={detail.rig.metric} /> : null}
      {h ? (
        <div className="reveal-bar">
          <Interval low={h.ci_low} high={h.ci_high} diff={h.diff} verdict={s.verdict} mde={s.mde} />
          <p className="small muted num">
            {detail.rig?.metric ? "Pass rate: " : null}
            {pts(h.diff)}
            <Term k="pts" />, 95% interval
            <Term k="interval" /> {pts(h.ci_low)} to {pts(h.ci_high)}.
          </p>
          {s.mde ? (
            <p className="small muted num interval-key" data-testid="mde-key">
              <span className="interval-key__swatch" aria-hidden="true" />
              Shaded band: ±{Math.round(s.mde * 100)} pts around 0 — the smallest change {plural(h.n_pairs, "pair")} can detect
              <Term k="pairs" />
            </p>
          ) : null}
        </div>
      ) : null}
      {h ? (
        <div className="stats">
          <div>
            <span className="small muted">{arms.with}</span>
            <span className="value">{pct(h.pass_with)}</span>
          </div>
          <div>
            <span className="small muted">{arms.without}</span>
            <span className="value">{pct(h.pass_without)}</span>
          </div>
          <div>
            <span className="small muted">Pairs</span>
            <span className="value">{h.n_pairs}</span>
          </div>
        </div>
      ) : null}
      {s.items ? (
        <p className="small num" data-testid="items-right">
          Items right: {s.items.right_with} of {s.items.total_with} {arms.with.toLowerCase()} · {s.items.right_without} of{" "}
          {s.items.total_without} {arms.without.toLowerCase()}
          <span className="muted">
            {" "}
            ({pts(s.items.diff)}, 95% interval {pts(s.items.ci_low)} to {pts(s.items.ci_high)})
          </span>
        </p>
      ) : null}
      {s.unreliable ? (
        <p className="notice notice--warning small">
          Unreliable: {s.errored} of {plural(s.total, "trial")} errored (over 10%). Errored trials are left out.
        </p>
      ) : null}
      {s.broken ? <p className="notice notice--warning small">{plural(s.broken, "trial")} broken: setup failed.</p> : null}
      <dl className="kv small num">
        <dt>Cost</dt>
        <dd>
          {usd(s.cost_with)} {arms.with.toLowerCase()}, {usd(s.cost_without)} {arms.without.toLowerCase()}
        </dd>
        <dt>Spent</dt>
        <dd>
          {detail.local_model ? "Nothing: a local model" : spentText(detail.spent_usd, detail.budget_usd, detail.over_budget)}
        </dd>
      </dl>
      {Object.keys(s.by_kind).length || s.synthetic ? (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Results by kind">
          <table>
            <caption className="visually-hidden">Results by task kind</caption>
            <thead>
              <tr>
                <th>Kind</th>
                <th className="n">Pairs</th>
                <th className="n">{arms.with}</th>
                <th className="n">{arms.without}</th>
                <th className="n">Diff</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(s.by_kind).map(([k, st]) => (
                <KindRow key={k} label={kindLabel(k as Kind)} s={st} />
              ))}
              {s.synthetic ? <KindRow label="Imaginary (synthetic, not in the verdict)" s={s.synthetic} /> : null}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
