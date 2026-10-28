import { useMemo, useState } from "react";

import { plural, pct, pts, usd } from "../lib/format";
import { isEvidence } from "../lib/provenance";
import { modelText } from "../lib/evidence";
import type { LabMatrix, LabMatrixRow } from "../lib/types";

const AGENT_LABEL: Record<string, string> = {
  "claude-code": "Claude Code",
  codex: "Codex",
  "gemini-cli": "Gemini CLI",
  opencode: "OpenCode",
};

/** Results for one bench: a cost-against-lift frontier, and each task's pass rate per workflow. */
export function Matrix({ data, benchName }: { data: LabMatrix; benchName: string }) {
  const [view, setView] = useState<"frontier" | "tasks">("frontier");
  return (
    <div className="matrix">
      <div className="matrix__top">
        <div className="segmented matrix__switch" role="tablist" aria-label="Results view">
          {(
            [
              ["frontier", "Frontier"],
              ["tasks", "By Task"],
            ] as const
          ).map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={view === id} onClick={() => setView(id)}>
              {label}
            </button>
          ))}
        </div>
        <span className="small muted">
          {benchName}: <span className="num">{plural(data.rows.length, "workflow")}</span> measured on{" "}
          <span className="num">{plural(data.tasks.length, "task")}</span>
        </span>
      </div>
      {view === "frontier" ? <Frontier rows={data.rows} /> : <ByTask rows={data.rows} tasks={data.tasks} />}
    </div>
  );
}

type Point = { row: LabMatrixRow; x: number; y: number; lo: number; hi: number };

/** Each axis as a range with round tick values. */
function scale(lo: number, hi: number, target = 4) {
  const span = hi - lo || 1;
  const raw = span / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10;
  const n0 = Math.floor(lo / step);
  const n1 = Math.ceil(hi / step);
  const ticks: number[] = [];
  for (let n = n0; n <= n1; n++) ticks.push(Number((n * step).toFixed(10)));
  return { min: n0 * step, max: n1 * step, ticks };
}

/** a dominates b when it costs no more, lifts no less, and is better on one of the two. */
function dominates(a: Point, b: Point): boolean {
  return a.x <= b.x && a.y >= b.y && (a.x < b.x || a.y > b.y);
}

function Frontier({ rows }: { rows: LabMatrixRow[] }) {
  const [picked, setPicked] = useState<number | null>(null);
  // Local models cost nothing, so their trials are placed by how long they take.
  const durationAxis = rows.length > 0 && rows.every((r) => !r.cost_per_trial_usd);

  const { points, frontier, dominator, scales } = useMemo(() => {
    const plotted: Point[] = [];
    for (const r of rows) {
      // Not evidence (never opened, broken check, nothing to win or lose): listed below, never plotted.
      if (!isEvidence(r.validity)) continue;
      const x = durationAxis ? r.mean_duration_s : r.cost_per_trial_usd;
      if (r.diff == null || r.ci_low == null || r.ci_high == null || x == null) continue;
      plotted.push({ row: r, x, y: r.diff * 100, lo: r.ci_low * 100, hi: r.ci_high * 100 });
    }
    // The strongest dominator of each dominated point: the most lift, then the lowest cost.
    const dom = new Map<Point, Point>();
    for (const p of plotted) {
      const by = plotted.filter((q) => dominates(q, p)).sort((a, b) => b.y - a.y || a.x - b.x);
      if (by[0]) dom.set(p, by[0]);
    }
    const front = plotted.filter((p) => !dom.has(p)).sort((a, b) => a.x - b.x || b.y - a.y);
    return {
      points: plotted,
      frontier: front,
      dominator: dom,
      scales: {
        x: scale(0, Math.max(0, ...plotted.map((p) => p.x))),
        y: scale(Math.min(0, ...plotted.map((p) => p.lo)), Math.max(0, ...plotted.map((p) => p.hi))),
      },
    };
  }, [rows, durationAxis]);

  const notEvidence = rows.filter((r) => !isEvidence(r.validity));
  const notEvidenceList = notEvidence.length ? (
    <div className="matrix__invalid small" data-testid="not-evidence">
      <p className="muted">Not plotted, because they aren't evidence:</p>
      <ul>
        {notEvidence.map((r) => (
          <li key={r.experiment_id}>
            <b>{r.workflow}</b> <span className="pill pill--warning" title={r.validity?.reason ?? undefined}>{r.validity?.badge}</span>
          </li>
        ))}
      </ul>
    </div>
  ) : null;

  if (points.length === 0) {
    return (
      <>
        <p className="muted small">
          {notEvidence.length
            ? "No valid result on this bench yet, so there is nothing to plot."
            : "No workflow has finished pairs on this bench yet, so there is nothing to plot. Measure one here and it appears."}
        </p>
        {notEvidenceList}
      </>
    );
  }

  const px = (x: number) => ((x - scales.x.min) / (scales.x.max - scales.x.min)) * 100;
  const py = (y: number) => ((scales.y.max - y) / (scales.y.max - scales.y.min)) * 100;
  const costText = (p: Point) =>
    durationAxis ? `${Math.round(p.x)} seconds per trial` : `${usd(p.x)} per trial`;
  const selected = points.find((p) => p.row.experiment_id === picked) ?? frontier[frontier.length - 1] ?? points[0];
  const xTitle = durationAxis
    ? "Mean time per trial, in seconds (local models cost nothing, so time stands in for cost)"
    : "Cost per trial, in US dollars";

  return (
    <div className="matrix__frontier">
      <p className="small muted matrix__explain">
        Each dot is a workflow. Further left costs less per trial; higher gains more points over the baseline. Bars are the 95%
        interval. The line joins the workflows that no other one beats on both cost and lift.
      </p>
      <section className="matrix__chart" aria-label="Cost against lift for each workflow">
        <div className="matrix__frame">
          <svg className="matrix__lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" focusable="false">
            {scales.y.ticks.map((t) => (
              <line
                key={`y${t}`}
                x1={0}
                x2={100}
                y1={py(t)}
                y2={py(t)}
                className={t === 0 ? "matrix__zero" : "matrix__grid"}
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {frontier.length > 1 ? (
              <polyline
                className="matrix__front"
                points={frontier.map((p) => `${px(p.x)},${py(p.y)}`).join(" ")}
                vectorEffect="non-scaling-stroke"
              />
            ) : null}
            {points.map((p) => (
              <g key={p.row.experiment_id} className="matrix__bar">
                <line x1={px(p.x)} x2={px(p.x)} y1={py(p.hi)} y2={py(p.lo)} vectorEffect="non-scaling-stroke" />
                <line x1={px(p.x) - 1.2} x2={px(p.x) + 1.2} y1={py(p.hi)} y2={py(p.hi)} vectorEffect="non-scaling-stroke" />
                <line x1={px(p.x) - 1.2} x2={px(p.x) + 1.2} y1={py(p.lo)} y2={py(p.lo)} vectorEffect="non-scaling-stroke" />
              </g>
            ))}
          </svg>
          {scales.y.ticks.map((t) => (
            <span key={`yl${t}`} className="matrix__ytick num" style={{ top: `${py(t)}%` }}>
              {t > 0 ? `+${t}` : t}
            </span>
          ))}
          {scales.x.ticks.map((t) => (
            <span key={`xl${t}`} className="matrix__xtick num" style={{ left: `${px(t)}%` }}>
              {durationAxis ? `${t}s` : usd(t)}
            </span>
          ))}
          {points.map((p) => {
            const by = dominator.get(p);
            const isSel = p === selected;
            const title = by ? `costs more and solves less than ${by.row.workflow}` : p.row.workflow;
            return (
              <button
                key={p.row.experiment_id}
                type="button"
                className={`matrix__dot${by ? " matrix__dot--behind" : ""}${isSel ? " is-selected" : ""}`}
                style={{ left: `${px(p.x)}%`, top: `${py(p.y)}%` }}
                title={title}
                aria-label={`${p.row.workflow}: ${pts(p.row.diff ?? 0)} with a 95% interval of ${pts(p.lo / 100)} to ${pts(p.hi / 100)}, ${costText(p)}${by ? `. ${title}` : ""}`}
                aria-pressed={isSel}
                onClick={() => setPicked(p.row.experiment_id)}
              >
                <span className="visually-hidden">{p.row.workflow}</span>
              </button>
            );
          })}
        </div>
        <div className="matrix__axis matrix__axis--y small muted">Gain over the baseline, in points</div>
        <div className="matrix__axis matrix__axis--x small muted">{xTitle}</div>
      </section>
      <div className="matrix__detail small" aria-live="polite">
        <b>{selected.row.workflow}</b>{" "}
        <span className="num">{pts(selected.row.diff ?? 0)}</span> (95% interval{" "}
        <span className="num">
          {pts(selected.lo / 100)} to {pts(selected.hi / 100)}
        </span>
        ) · <span className="num">{costText(selected)}</span> · <span className="num">{selected.row.n_pairs}</span> pairs ·{" "}
        {modelText(selected.row)}, run with {AGENT_LABEL[selected.row.agent] ?? selected.row.agent}
        {dominator.has(selected) ? (
          <>
            {" "}
            · <span className="muted">costs more and solves less than {dominator.get(selected)?.row.workflow}</span>
          </>
        ) : (
          <>
            {" "}
            · <span className="muted">on the frontier</span>
          </>
        )}
      </div>
      {rows.length - notEvidence.length > points.length ? (
        <p className="small muted">
          {rows.length - notEvidence.length - points.length} of {rows.length} not plotted: no finished pairs or no cost yet.
        </p>
      ) : null}
      {notEvidenceList}
    </div>
  );
}

function tint(rate: number | null) {
  if (rate == null) return undefined;
  return { background: `color-mix(in srgb, var(--positive) ${Math.round(rate * 40)}%, var(--surface))` };
}

function ByTask({ rows, tasks }: { rows: LabMatrixRow[]; tasks: LabMatrix["tasks"] }) {
  return (
    <section className="matrix__tasks" aria-label="Pass rate by task">
      <p className="small muted">
        Pass rate on each task. The first column is the baseline with no workflow. Each workflow cell is shaded by its pass
        rate, and the number is the same figure written out.
      </p>
      <div className="matrix__scroll">
        <table className="matrix__table">
          <thead>
            <tr>
              <th scope="col">Task</th>
              <th scope="col" className="matrix__base">
                Without (baseline)
              </th>
              {rows.map((r) => (
                <th key={r.experiment_id} scope="col">
                  {r.workflow}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => {
              const base = rows.map((r) => r.per_task[t.id]?.without).find((v) => v != null) ?? null;
              return (
                <tr key={t.id}>
                  <th scope="row">{t.title}</th>
                  <td className="num matrix__base">{base == null ? "–" : pct(base)}</td>
                  {rows.map((r) => {
                    const cell = r.per_task[t.id];
                    const rate = cell?.with ?? null;
                    return (
                      <td
                        key={r.experiment_id}
                        className="num matrix__cell"
                        style={tint(rate)}
                        title={cell ? `${cell.n} trials on this workflow` : "Not run on this task"}
                      >
                        {rate == null ? "–" : pct(rate)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
