import { ArrowRight } from "lucide-react";

import { exampleVerdict, useRigExplain, weightPct } from "../lib/rigExplain";
import { pts } from "../lib/format";
import type { RigExplain } from "../lib/types";
import { Interval } from "./Interval";
import { RigScore } from "./RigScore";

/** The five parts' weights as one bar that adds up to 100. */
export function WeightBar({ parts, labelled = true }: { parts: RigExplain["parts"]; labelled?: boolean }) {
  return (
    <div
      className="weightbar"
      role="img"
      aria-label={`Weights: ${parts.map((p) => `${p.name} ${weightPct(p.weight)}`).join(", ")}`}
      data-testid="weight-bar"
    >
      {parts.map((p, i) => (
        <span key={p.id} className={`weightbar__seg weightbar__seg--${i}`} style={{ flexGrow: p.weight }} data-weight={p.weight}>
          {labelled ? (
            <>
              <span className="weightbar__name">{p.name}</span>
              <span className="weightbar__pct num">{weightPct(p.weight)}</span>
            </>
          ) : null}
        </span>
      ))}
    </div>
  );
}


/** Gates that share a cap, as one row: two reasons for "at most 20" read as one limit, not a repeat. */
export function gateGroups(gates: RigExplain["gates"]): [number, string[]][] {
  const by = new Map<number, string[]>();
  for (const g of gates) by.set(g.cap, [...(by.get(g.cap) ?? []), g.text]);
  return [...by.entries()].sort((a, b) => a[0] - b[0]);
}

/** #/rig-score: how the Rig score is made, from the engine's own definition and formula. */
export function RigExplainPage({ onMeasure }: { onMeasure: () => void }) {
  const { data, error } = useRigExplain();
  return (
    <main className="steppage rigx" id="main">
      <div className="steppage__inner">
        <div className="steppage__eyebrow">Rig Score</div>
        <h1 className="steppage__title" tabIndex={-1} data-page-title>
          How the Rig Score Works
        </h1>
        {error ? (
          <p className="notice notice--error small" role="alert">
            Couldn't read the Rig score's definition from the engine. {error}
          </p>
        ) : !data ? (
          <p className="muted">Reading the definition…</p>
        ) : (
          <RigExplainBody data={data} onMeasure={onMeasure} />
        )}
      </div>
    </main>
  );
}

function RigExplainBody({ data, onMeasure }: { data: RigExplain; onMeasure: () => void }) {
  const ex = data.example;
  const e = ex.evidence;
  const won = (rate: number) => Math.round(rate * e.n_pairs);
  return (
    <>
      <p className="steppage__lead muted">{data.intro}</p>

      <section className="rigx__section" aria-labelledby="rigx-parts">
        <h2 id="rigx-parts" className="rigx__h">
          Five Measured Parts, Weighted
        </h2>
        <WeightBar parts={data.parts} />
        <ol className="rigx__parts">
          {data.parts.map((p, i) => (
            <li key={p.id} className="rigx__part" data-testid="rigx-part">
              <div className="rigx__parthead">
                <span className={`rigx__swatch weightbar__seg--${i}`} aria-hidden="true" />
                <b>{p.name}</b>
                <span className="rigx__weight num">{weightPct(p.weight)}</span>
              </div>
              <div className="rigx__partbody">
                <p className="small">{p.measures}</p>
                <p className="small muted">
                  <span className="rigx__label">0 to 100:</span> {p.scale}
                  {p.needs_lift ? <span className="rigx__needs"> Counts only once a lift is shown.</span> : null}
                </p>
              </div>
            </li>
          ))}
        </ol>
        <p className="small muted">
          {data.missing} {data.no_credit}
        </p>
      </section>

      <section className="rigx__section" aria-labelledby="rigx-gates">
        <h2 id="rigx-gates" className="rigx__h">
          Gates That Cap It
        </h2>
        <p className="small muted">After the weighted sum, these limit how high the score can go.</p>
        <ul className="rigx__gates">
          {gateGroups(data.gates).map(([cap, texts]) => (
            <li key={cap}>
              <span className="rigx__cap num">
                <span className="visually-hidden">At most </span>
                <span aria-hidden="true">≤</span>
                {cap}
              </span>
              <span className="small rigx__why">
                {texts.map((t, i) => (
                  <span key={t}>
                    {i ? <span className="muted">Or: </span> : null}
                    {t}
                  </span>
                ))}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rigx__section" aria-labelledby="rigx-bands">
        <h2 id="rigx-bands" className="rigx__h">
          Bands
        </h2>
        <p className="small muted">The band comes from the evidence first, so it never contradicts the interval beside it; only a lift shown to help is placed by its number.</p>
        <ul className="rigx__bands">
          {data.bands.map((b) => (
            <li key={b.id}>
              <span className={`pill pill--${b.tone}`}>{b.label}</span>
              <span className="small">{b.when}</span>
            </li>
          ))}
        </ul>
        <p className="small muted">
          Beside the number, every result gets one plain verdict:{" "}
          {data.verdict.map((v, i) => (
            <span key={v.id}>
              {i ? " · " : ""}
              <b>{v.word}</b>
            </span>
          ))}
          .
        </p>
      </section>

      {data.metric ? (
        <section className="rigx__section" aria-labelledby="rigx-metric">
          <h2 id="rigx-metric" className="rigx__h">
            Scored on a Saving
          </h2>
          <p className="small" data-testid="rigx-metric">
            {data.metric.text}
          </p>
          <ul className="small">
            {data.metric.options.map((o) => (
              <li key={o.id}>
                <b>{o.name}.</b> {o.describe}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="rigx__section" aria-labelledby="rigx-example">
        <h2 id="rigx-example" className="rigx__h">
          Worked Example
        </h2>
        <p className="small">
          <span className="pill">Illustrative Inputs, Not a Real Run</span> <b>{ex.title}.</b> <span className="muted">{ex.note}</span>
        </p>
        <div className="rigx__evidence">
          <dl className="rigx__arms num">
            <div>
              <dt>Without</dt>
              <dd>
                {won(e.pass_without)} of {e.n_pairs} passed
              </dd>
            </div>
            <div>
              <dt>With</dt>
              <dd>
                {won(e.pass_with)} of {e.n_pairs} passed
              </dd>
            </div>
            <div>
              <dt>Change</dt>
              <dd>
                {pts(e.diff, 0)}, 95% interval {pts(e.ci_low, 0).replace(" pts", "")} to {pts(e.ci_high, 0).replace(" pts", "")}
              </dd>
            </div>
          </dl>
          <Interval low={e.ci_low} high={e.ci_high} diff={e.diff} verdict={exampleVerdict(data)} />
        </div>
        <p className="small muted">The numbers are made up to show the rules at work; the score below is the engine's own, from the same function every real run uses:</p>
        <RigScore rig={ex.result} title="Rig Score · Worked Example" name="Rig score for the worked example" howLink={false} />
      </section>

      <div className="rigx__foot">
        <button type="button" className="btn btn--primary" onClick={onMeasure}>
          Measure Something <ArrowRight size={14} aria-hidden="true" />
        </button>
        <a className="btn btn--quiet" href="#/home">
          Home
        </a>
      </div>
    </>
  );
}
