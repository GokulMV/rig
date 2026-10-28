import { ArrowLeft, FlaskConical, LogIn, PenLine, Rocket, Star, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api, ApiError } from "../lib/api";
import { diffWorkflows, edgesOf, notShared, stages, type DiffRow } from "../lib/compareDiff";
import { allOnModel, COMPARE_MAX, useCompareSet, type Pinned } from "../lib/compareSet";
import { budgetPromise, plural, usd } from "../lib/format";
import { expected, expectedText, provenance } from "../lib/provenance";
import type { BenchInfo, CompareAlign, CompareJobView, ComparePlan, CompareRank, CompareResult, CompareStanding, Lab as LabData, LabWorkflow } from "../lib/types";
import { KIND } from "./Lab";
import { RunSize } from "./RunSize";
import { RigBadge } from "./RigScore";

const JOB = "pg.compare.job"; // the run going, so leaving the page and coming back follows it
const BENCH = "pg.compare.bench"; // the bench chosen here, kept in this browser
const POLL_MS = 1500;

const ORIGIN: Record<LabWorkflow["origin"], string> = {
  starter: "Starter workflow",
  business: "Business process",
  rag: "RAG architecture",
  pattern: "Agentic pattern",
  random: "Random workflow",
  custom: "Your workflow",
};

const STATE: Record<CompareJobView["workflows"][number]["status"], string> = {
  queued: "Waiting its turn",
  running: "Measuring…",
  done: "Done",
  stopped: "Stopped",
  skipped: "Skipped",
  error: "Couldn't run",
};

function defaultBench(list: BenchInfo[], discipline: string): string {
  return (list.find((x) => x.discipline === discipline) ?? list.find((x) => x.disciplines.includes(discipline)) ?? list[0])?.id ?? "";
}

/** A change as signed whole points: 0.18 -> "+18". */
function signed(x: number | null | undefined): string {
  if (x == null) return "–";
  const v = Math.round(x * 100);
  return `${v > 0 ? "+" : ""}${v}`;
}

function sessionStore(key: string, value: string | null) {
  try {
    if (value === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, value);
  } catch {
    // Not kept: the run still goes on, and its results land in the columns once read again.
  }
}

function sessionRead(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function keptBench(): string {
  try {
    return window.localStorage.getItem(BENCH) ?? "";
  } catch {
    return "";
  }
}

function keepBench(id: string) {
  try {
    window.localStorage.setItem(BENCH, id);
  } catch {
    // Not remembered: the next visit picks a bench for the first workflow's discipline.
  }
}

// ---------- the mini diagram: the steps by stage, top to bottom ----------

const CELL_W = 150;
const CELL_H = 42;
const BOX_W = 138;
const BOX_H = 26;
const PAD = 8;

function short(s: string, max = 22): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

/** A workflow drawn small: a row per stage (parallel steps side by side), arrows for what follows
 * what, dashed curves for loops. Steps not every compared workflow has are drawn marked. */
function FlowMini({ wf, marked }: { wf: LabWorkflow; marked: Set<string> }) {
  const st = stages(wf);
  const widest = Math.max(1, ...st.map((r) => r.length));
  const loops = wf.loops ?? [];
  const width = PAD * 2 + (widest - 1) * CELL_W + BOX_W + (loops.length ? 18 : 0);
  const height = PAD * 2 + (st.length - 1) * CELL_H + BOX_H;
  const at = new Map<string, { x: number; y: number }>();
  st.forEach((ids, r) => {
    const offset = ((widest - ids.length) * CELL_W) / 2;
    ids.forEach((id, k) => at.set(id, { x: PAD + offset + k * CELL_W, y: PAD + r * CELL_H }));
  });
  const name = (id: string) => wf.steps.find((s) => s.id === id)?.name ?? id;
  const label = `${wf.name}: ${st.map((r) => r.map(name).join(" and ")).join(", then ")}${loops.length ? `; ${loops.map(([a, b, n]) => `${name(a)} back to ${name(b)} at most ${n} times`).join("; ")}` : ""}`;
  const mark = `cmpm-${wf.id.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return (
    <svg className="cmp-mini" viewBox={`0 0 ${width} ${height}`} style={{ maxHeight: height }} role="img" aria-label={label}>
      <defs>
        <marker id={mark} viewBox="0 0 6 6" refX="5.5" refY="3" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M0,0 L6,3 L0,6 z" fill="#9aa3ad" />
        </marker>
      </defs>
      {edgesOf(wf).map(([a, b]) => {
        const p = at.get(a);
        const q = at.get(b);
        if (!p || !q) return null;
        return (
          <line
            key={`${a}>${b}`}
            x1={p.x + BOX_W / 2}
            y1={p.y + BOX_H}
            x2={q.x + BOX_W / 2}
            y2={q.y - 1}
            stroke="#9aa3ad"
            strokeWidth={1.2}
            markerEnd={`url(#${mark})`}
          />
        );
      })}
      {loops.map(([a, b]) => {
        const p = at.get(a);
        const q = at.get(b);
        if (!p || !q) return null;
        const x = Math.max(p.x, q.x) + BOX_W;
        const d = `M${p.x + BOX_W},${p.y + BOX_H / 2} C${x + 16},${p.y + BOX_H / 2} ${x + 16},${q.y + BOX_H / 2} ${q.x + BOX_W + 1},${q.y + BOX_H / 2}`;
        return <path key={`loop-${a}>${b}`} d={d} fill="none" stroke="#9aa3ad" strokeWidth={1.2} strokeDasharray="3 3" markerEnd={`url(#${mark})`} />;
      })}
      {wf.steps.map((s) => {
        const p = at.get(s.id);
        if (!p) return null;
        const odd = marked.has(s.id);
        return (
          <g key={s.id} className={`cmp-mini__step${odd ? " is-diff" : ""}`}>
            <title>{`${s.name}${odd ? " (not in every workflow here)" : ""}`}</title>
            <rect x={p.x} y={p.y} width={BOX_W} height={BOX_H} rx={5} fill={odd ? "#fffbeb" : "#fff"} stroke={KIND[s.kind].color} strokeWidth={odd ? 2 : 1.2} />
            <text x={p.x + BOX_W / 2} y={p.y + BOX_H / 2 + 4} textAnchor="middle" fontSize={11} fill="#131416">
              {short(s.name)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ---------- one workflow's result on the bench ----------

/** A rate as whole percent: 0.95 -> "95%". */
function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

function ResultCell({
  result,
  status,
  detail,
  bench,
  across,
}: {
  result: CompareResult | null;
  status?: string;
  detail?: string | null;
  bench: string;
  /** Ranked across models: the pass rate with it and its interval, and what the lift is against. */
  across?: { ranked?: CompareRank["ranked"][string]; liftVs?: string } | null;
}) {
  const going = status === "running" || status === "queued";
  if (!result) {
    if (status) {
      return (
        <div className="cmp-result" data-testid="compare-result">
          <span className={`small${going ? "" : " muted"}`}>{STATE[status as keyof typeof STATE] ?? status}</span>
          {detail ? <span className="small adh">{detail}</span> : null}
        </div>
      );
    }
    return (
      <div className="cmp-result" data-testid="compare-result">
        <span className="small muted">Not measured on {bench} yet</span>
      </div>
    );
  }
  const valid = (result.validity?.status ?? "valid") === "valid";
  const live = result.status === "running" || status === "running";
  if (result.other_model) {
    // An earlier result on another model: said so, its numbers muted, never read as this one's.
    return (
      <div className="cmp-result" data-testid="compare-result">
        <span className="small" data-testid="compare-other-model">
          <b>{result.other_model.text}</b>
        </span>
        {result.n_pairs ? (
          <span className="num small muted">
            On {result.other_model.label}: {signed(result.diff)} pts vs Direct there · {plural(result.n_pairs, "pair")}
          </span>
        ) : null}
      </div>
    );
  }
  return (
    <div className="cmp-result" data-testid="compare-result">
      <span className="row" style={{ gap: 6 }}>
        {result.rig && !live ? (
          <RigBadge score={result.rig.score} tone={result.rig.tone} provisional={result.rig.provisional} label={result.rig.label} band={result.rig.band} />
        ) : null}
        {live ? <span className="small">Measuring… so far</span> : null}
        {!valid ? <span className="rig-badge rig-badge--neutral">{result.validity?.badge ?? "Not Evidence"}</span> : null}
      </span>
      {result.n_pairs && across?.ranked ? (
        <span className="num small" data-testid="compare-pass-with">
          <b>{pct(across.ranked.value)} pass with it</b> · 95% interval {pct(across.ranked.lo)} to {pct(across.ranked.hi)}
        </span>
      ) : null}
      {result.n_pairs ? (
        <span className="num small">
          <b>{signed(result.diff)} pts</b>
          {across?.liftVs ? ` ${across.liftVs}` : ""} · 95% interval {signed(result.ci_low)} to {signed(result.ci_high)} · {plural(result.n_pairs, "pair")}
        </span>
      ) : (
        <span className="small muted">No complete pairs yet</span>
      )}
      {!valid && result.validity?.reason ? <span className="small muted">{result.validity.reason}</span> : null}
      {result.rig && !live ? <span className="small muted">{result.rig.label}</span> : null}
      {status && status !== "done" && !live ? <span className="small muted">{STATE[status as keyof typeof STATE] ?? status}</span> : null}
      {detail ? <span className="small adh">{detail}</span> : null}
    </div>
  );
}

// ---------- more than one session model: one baseline each, or all on one ----------

/** Said before a run when the set is on more than one session model: each pays for its own
 * baseline, and one click puts them all on one so a single baseline is shared. */
export function ModelsNotice({ align, disabled, onAlign }: { align: CompareAlign; disabled?: boolean; onAlign: () => void }) {
  return (
    <div className="notice small cmp-models" data-testid="compare-models" role="group" aria-label="Session models">
      <span style={{ flex: 1 }}>
        <b>{align.notice}</b> A baseline on one model says nothing about another, and lifts against different baselines don't compare, so results
        across models are ranked by pass rate with the workflow. {align.action}: {align.result}
      </span>
      <button type="button" className="btn btn--small" disabled={disabled} onClick={onAlign}>
        {align.action}
      </button>
    </div>
  );
}

// ---------- the page ----------

/** Compare 2 to 4 workflows side by side: what each is, what differs, measured together on one
 * bench with one shared baseline, and a winner only when the intervals say so. */
export function Compare({
  agent,
  working,
  onBack,
  onOpen,
  onWork,
  onShip,
  onSignIn,
}: {
  agent: { id: string; label: string; ready: boolean; budget_cap?: boolean } | null;
  /** The workflow on the Lab's canvas now (Build and Measure open it). */
  working: string | null;
  onBack: () => void;
  /** Open this workflow on the Lab's canvas, in Build. */
  onOpen: (p: Pinned) => void;
  /** Put it on the Lab's canvas, staying here. */
  onWork: (p: Pinned) => void;
  /** Take it to Ship. */
  onShip: (p: Pinned) => void;
  onSignIn: () => void;
}) {
  const [pins, setPins] = useCompareSet();
  const [lab, setLab] = useState<LabData | null>(null);
  const [benches, setBenches] = useState<BenchInfo[] | null>(null);
  const [bid, setBidState] = useState(keptBench);
  const setBid = (id: string) => {
    setBidState(id);
    keepBench(id);
  };
  const [size, setSize] = useState<"pilot" | "full">("pilot");
  const [budget, setBudget] = useState(20);
  const [plan, setPlan] = useState<ComparePlan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [job, setJob] = useState<string | null>(() => sessionRead(JOB));
  const [view, setView] = useState<CompareJobView | null>(null);
  // The set's shape when this page started the run shown (unknown for one followed after a reload).
  const [jobShape, setJobShape] = useState<string | null>(null);
  const [standing, setStanding] = useState<CompareStanding | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  // The set as it was before "Run all on <model>", while that can be undone.
  const [before, setBefore] = useState<Pinned[] | null>(null);
  const wfs = useMemo(() => pins.map((p) => p.wf), [pins]);
  // What the price depends on: the set and each one's step models (Run all on <model> changes them).
  const shape = wfs.map((w) => `${w.id}:${w.steps.map((s) => s.model).join("/")}`).join(",");

  // The page has its own link, so a reload comes back here.
  useEffect(() => {
    if (!window.location.hash.startsWith("#/compare")) window.history.replaceState(null, "", "#/compare");
  }, []);
  useEffect(() => {
    api.lab().then(setLab, () => undefined);
    api.benches().then(setBenches, (e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);
  useEffect(() => {
    // A kept bench that is gone (an imported one removed) falls back like no choice at all.
    if (benches && !benches.some((b) => b.id === bid)) setBidState(defaultBench(benches, wfs[0]?.discipline ?? ""));
  }, [benches, bid, wfs]);
  const bench = benches?.find((b) => b.id === bid) ?? null;

  // Priced as soon as there is a set and a bench: no sign-in needed, no model call.
  useEffect(() => {
    if (wfs.length < 2 || !bid || budget <= 0) {
      setPlan(null);
      return;
    }
    let live = true;
    const t = window.setTimeout(() => {
      api.comparePlan({ workflows: wfs, bench: bid, budget, agent: agent?.id ?? "claude-code", size }).then(
        (p) => {
          if (!live) return;
          setPlan(p);
          setPlanError(null);
        },
        (e) => live && setPlanError(e instanceof ApiError ? e.message : String(e)),
      );
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shape, bid, budget, size, agent?.id]);

  const loadStanding = useCallback(() => {
    if (!bid || !wfs.length) {
      setStanding(null);
      return;
    }
    // Whole workflows: a result counts only on the session model each is on now.
    api.compareStanding(bid, wfs, agent?.id ?? "claude-code").then(setStanding, () => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bid, shape, agent?.id]);
  useEffect(loadStanding, [loadStanding]);

  // The run going: read every POLL_MS until it ends, then the standing again.
  const live = !!view && (view.status === "running" || view.status === "stopping");
  useEffect(() => {
    if (!job) return;
    let off = false;
    const tick = () =>
      api.compareGet(job).then(
        (v) => {
          if (off) return;
          setView(v);
          if (v.status === "done" || v.status === "stopped") {
            off = true;
            sessionStore(JOB, null);
            loadStanding();
          }
        },
        () => {
          // The server restarted: the run is gone, its finished results are in the standing.
          if (off) return;
          off = true;
          sessionStore(JOB, null);
          setJob(null);
        },
      );
    void tick();
    const t = window.setInterval(() => !off && void tick(), POLL_MS);
    return () => {
      off = true;
      window.clearInterval(t);
    };
  }, [job, loadStanding]);

  const start = async () => {
    setConfirm(false);
    setError(null);
    try {
      const r = await api.compareRun({ workflows: wfs, bench: bid, budget, agent: agent?.id ?? "claude-code", size });
      sessionStore(JOB, r.job);
      setJobShape(shape);
      setView(null);
      setJob(r.job);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  // What the columns and the summary show: the run on this bench, else each one's latest valid
  // result. A finished run whose workflows have since moved to another model (Run all on <model>)
  // isn't theirs any more: the standing, keyed by each one's model now, is shown instead.
  const runStale =
    !!view &&
    !live &&
    ((jobShape !== null && jobShape !== shape) ||
      (standing?.bench === bid && view.workflows.some((r) => r.model && standing.models?.[r.id] && standing.models[r.id] !== r.model)));
  const fromRun = view && view.bench === bid && !runStale ? view : null;
  const resultOf = (id: string): { result: CompareResult | null; status?: string; detail?: string | null } => {
    const r = fromRun?.workflows.find((x) => x.id === id);
    if (r && (r.result || live)) return { result: r.result, status: r.status, detail: r.detail };
    return { result: standing?.bench === bid ? (standing.workflows.find((x) => x.id === id)?.result ?? null) : null };
  };
  const rank = live ? null : (fromRun?.rank ?? (standing?.bench === bid ? standing.rank : null));
  const winner = rank?.winner ? pins.find((p) => p.wf.id === rank.winner) ?? null : null;

  const modelLabel = (m: string) => lab?.models[m]?.label ?? m;
  const ruleName = (r: string) => lab?.harness[r]?.name ?? r;
  const disciplineLabel = (d: string) => lab?.templates.find((t) => t.id === d)?.label ?? d;
  const diffs: DiffRow[] = useMemo(
    () => diffWorkflows(wfs, { model: modelLabel, rule: ruleName, discipline: disciplineLabel }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [wfs, lab],
  );
  const marked = useMemo(() => notShared(wfs), [wfs]);

  const remove = (id: string) => {
    setBefore(null);
    setPins(pins.filter((p) => p.wf.id !== id));
  };
  const alignAll = (a: CompareAlign) => {
    setBefore(pins);
    setPins(allOnModel(pins, a.model));
    setConfirm(false);
    setSaid(`All ${pins.length} run on ${a.label} now (each one's main steps), so they share one baseline. Only the copies pinned here changed.`);
  };
  const undoAlign = () => {
    if (before) setPins(before);
    setBefore(null);
    setSaid(null);
  };
  const named = (p: Pinned) => p.wf.name;

  const cols = pins.length;
  const colStyle = { ["--cmp-cols" as string]: String(Math.max(cols, 1)) };

  const row = (label: React.ReactNode, cell: (p: Pinned, i: number) => React.ReactNode, key: string) => (
    <tr key={key}>
      <th scope="row">{label}</th>
      {pins.map((p, i) => (
        <td key={p.wf.id}>{cell(p, i)}</td>
      ))}
    </tr>
  );
  const none = <span className="muted">None</span>;

  const measureBar = () => {
    if (cols < 2) return <p className="small muted">Pin at least two workflows to measure them together.</p>;
    const n = cols;
    return (
      <div className="cmp-measure" role="group" aria-label="Measure the set">
        <div className="cmp-measure__controls">
          <div className="field">
            <label htmlFor="cmp-bench">Bench</label>
            <select id="cmp-bench" className="select" value={bid} disabled={live} onChange={(e) => (setBid(e.target.value), setConfirm(false))}>
              {(benches ?? []).map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name} · {plural(b.scenarios.length, "task")}
                </option>
              ))}
            </select>
          </div>
          <RunSize size={size} onSize={(s) => (setSize(s), setConfirm(false))} full={planError ? null : plan?.full} disabled={live} />
          <div className="field">
            <label htmlFor="cmp-budget">Stop at (USD, in total)</label>
            <input
              id="cmp-budget"
              className="input num"
              type="number"
              min={0.5}
              step={0.5}
              value={budget}
              disabled={live}
              onChange={(e) => (setBudget(Number(e.target.value)), setConfirm(false))}
            />
          </div>
        </div>
        {planError ? (
          <p className="small muted">Couldn't price this: {planError}</p>
        ) : plan ? (
          <p className="small num" data-testid="compare-price">
            {plan.workflows.some((w) => w.pairs_in_budget < w.pairs) ? (
              <>
                <b>Stops at {usd(budget)}</b>, split evenly: {usd(plan.share)} each, which pays for about{" "}
                {plan.workflows.reduce((t, w) => t + w.pairs_in_budget, 0)} of {plan.pairs * n} pairs. All {n} in full would cost ≈{" "}
                {usd(plan.total_usd)} ({plural(plan.pairs, "pair")} each).
              </>
            ) : (
              <>
                <b>≈ {usd(plan.total_usd)}</b> for all {n} ({plural(plan.pairs, "pair")} each), split evenly: {usd(plan.share)} each.
              </>
            )}{" "}
            {plan.baselines === 1 ? "One shared baseline." : `${plan.baselines} baselines: one per session model.`}
          </p>
        ) : (
          <p className="small muted">Pricing the set…</p>
        )}
        {plan?.align && !planError ? <ModelsNotice align={plan.align} disabled={live} onAlign={() => alignAll(plan.align!)} /> : null}
        {live ? null : !agent?.ready ? (
          <div className="row" style={{ gap: 8 }}>
            <button type="button" className="btn btn--primary" onClick={onSignIn}>
              <LogIn size={14} aria-hidden="true" /> Sign In to Measure
            </button>
            <span className="small muted">Measuring needs {agent?.label ?? "an agent"} signed in; pricing it doesn't.</span>
          </div>
        ) : confirm && plan ? (
          <div className="card" role="group" aria-label="Confirm the comparison run">
            <strong>
              Measure All {n} on {bench?.name} with {agent.label}?
            </strong>
            <p className="small">
              One after another in the order shown, {plural(plan.pairs, "pair")} each on the same tasks, in Docker sandboxes on your
              sign-in. The first workflow on each model pays for the baseline (the agent with nothing added) and the rest reuse it.
            </p>
            <p className="small num" data-testid="compare-total">
              <b>≈ {usd(plan.total_usd)} in total</b>, predicted by the budget check. {usd(budget)} is split evenly: {usd(plan.share)} for each
              workflow, and what one doesn't spend isn't passed on, so they're measured alike.
            </p>
            <ul className="small num cmp-plan">
              {plan.workflows.map((w) => (
                <li key={w.id}>
                  <b>{w.name}</b>: ≈ {usd(w.predicted_usd)} · {w.pairs_in_budget < w.pairs ? `its share pays for about ${w.pairs_in_budget} of ${plural(w.pairs, "pair")}` : plural(w.pairs, "pair")}
                  {" · "}
                  {w.shared_baseline > 0 ? `reuses ${plural(w.shared_baseline, "baseline pair")}` : "pays for its baseline"}
                </li>
              ))}
            </ul>
            <p className="small">{budgetPromise(plan.share, agent.label, !!agent.budget_cap)} That holds for each workflow's share.</p>
            <div className="row" style={{ gap: 8 }}>
              <button type="button" className="btn btn--primary" onClick={() => void start()}>
                Start, up to {usd(budget)}
              </button>
              <button type="button" className="btn btn--quiet" onClick={() => setConfirm(false)}>
                Back
              </button>
            </div>
          </div>
        ) : (
          <div>
            <button type="button" className="btn btn--primary" disabled={!plan || !bench || budget <= 0} onClick={() => setConfirm(true)}>
              <FlaskConical size={14} aria-hidden="true" /> Measure All {n} on {bench?.name ?? "a Bench"}
            </button>
          </div>
        )}
        {live && view ? (
          <div className="row" style={{ gap: 8 }}>
            <span className="small num" role="status">
              {view.status === "stopping"
                ? "Stopping after the trial in progress… "
                : `Measuring ${Math.min(view.workflows.filter((w) => w.status !== "queued").length, view.workflows.length)} of ${view.workflows.length} on ${view.bench_name}… `}
              {usd(view.spent)} of {usd(view.budget)}
            </span>
            <button
              type="button"
              className="btn btn--small"
              disabled={view.status === "stopping"}
              onClick={() => api.compareStop(view.job).catch((e) => setError(e instanceof ApiError ? e.message : String(e)))}
            >
              Stop
            </button>
          </div>
        ) : null}
      </div>
    );
  };

  return (
    <main className="steppage cmp" id="main">
      <div className="steppage__inner cmp__inner">
        <div>
          <button type="button" className="linkish small" onClick={onBack}>
            <ArrowLeft size={14} aria-hidden="true" /> Back to the Lab
          </button>
        </div>
        <h1 className="steppage__title">
          Compare Workflows
        </h1>
        <p className="steppage__lead muted">
          Up to {COMPARE_MAX} side by side: what each one is, what differs between them, and how they do measured together on one bench.
        </p>
        {error ? (
          <p className="notice notice--error small" role="alert">
            {error}
          </p>
        ) : null}
        {said ? (
          <p className="notice small" role="status">
            <span style={{ flex: 1 }}>{said}</span>
            {before ? (
              <button type="button" className="btn btn--small" disabled={live} onClick={undoAlign}>
                <Undo2 size={14} aria-hidden="true" /> Undo
              </button>
            ) : null}
            <button type="button" className="btn btn--small btn--quiet" aria-label="Dismiss" onClick={() => (setSaid(null), setBefore(null))}>
              <X size={14} aria-hidden="true" />
            </button>
          </p>
        ) : null}

        {!cols ? (
          <div className="card">
            <strong>Nothing to Compare Yet</strong>
            <p className="small">In the Lab, open a workflow and press Compare under its details. Pin two to four, then come back here.</p>
            <div>
              <button type="button" className="btn btn--primary" onClick={onBack}>
                Back to the Lab
              </button>
            </div>
          </div>
        ) : (
          <>
            <section className="cmp-section" aria-labelledby="cmp-measure-h">
              <h2 id="cmp-measure-h" className="cmp-section__title">
                Measure Them Together
              </h2>
              {measureBar()}
              {live && view ? (
                <p className="small muted" data-testid="compare-rank">
                  Ranked once all {view.workflows.length} are measured; each column fills in as its run finishes.
                </p>
              ) : null}
              {rank && cols >= 2 ? (
                <div className={`cmp-rank cmp-rank--${rank.state}`} data-testid="compare-rank">
                  <p className="small" role="status">
                    {rank.state === "winner" ? <Star size={14} aria-hidden="true" /> : null} {rank.text}
                    {rank.order.length > 1 ? (
                      <span className="muted">
                        {" "}
                        {rank.by_text}:{" "}
                        {rank.order
                          .map((id) => pins.find((p) => p.wf.id === id))
                          .filter(Boolean)
                          .map((p) => named(p!))
                          .join(" · ")}
                        .
                      </span>
                    ) : null}
                  </p>
                  {winner ? (
                    <button type="button" className="btn btn--small btn--primary" onClick={() => onShip(winner)}>
                      <Rocket size={14} aria-hidden="true" /> Ship the Winner
                    </button>
                  ) : null}
                </div>
              ) : null}
            </section>

            <section className="cmp-section" aria-labelledby="cmp-side-h">
              <h2 id="cmp-side-h" className="cmp-section__title">
                Side by Side
              </h2>
              <div className="table-wrap cmp-wrap" tabIndex={0} role="region" aria-label="Workflows side by side">
                <table className="cmp-table" style={colStyle}>
                  <colgroup>
                    <col className="cmp-table__label" />
                    {pins.map((p) => (
                      <col key={p.wf.id} />
                    ))}
                  </colgroup>
                  <thead>
                    <tr>
                      <th scope="col">
                        <span className="visually-hidden">What</span>
                      </th>
                      {pins.map((p) => (
                        <th key={p.wf.id} scope="col" className={rank?.winner === p.wf.id ? "is-winner" : undefined}>
                          <div className="cmp-head">
                            <span className="cmp-head__name">{p.wf.name}</span>
                            <span className="row" style={{ gap: 6 }}>
                              {working === p.wf.id ? <span className="tag cmp-tag">Working Workflow</span> : null}
                              {rank?.winner === p.wf.id ? <span className="tag cmp-tag cmp-tag--win">Winner</span> : null}
                            </span>
                            <div className="cmp-head__actions">
                              <button type="button" className="btn btn--small" onClick={() => onOpen(p)} aria-label={`Open in Build: ${p.wf.name}`}>
                                <PenLine size={13} aria-hidden="true" /> Open in Build
                              </button>
                              <button
                                type="button"
                                className="btn btn--small"
                                onClick={() => {
                                  onWork(p);
                                  setBefore(null);
                                  setSaid(`${p.wf.name} is the working workflow now: Build, Measure and Ship open it.`);
                                }}
                                disabled={working === p.wf.id}
                                aria-label={`Make This the Working Workflow: ${p.wf.name}`}
                              >
                                Make This the Working Workflow
                              </button>
                              <button type="button" className="btn btn--small" onClick={() => onShip(p)} aria-label={`Ship This One: ${p.wf.name}`}>
                                <Rocket size={13} aria-hidden="true" /> Ship This One
                              </button>
                              <button
                                type="button"
                                className="btn btn--small btn--quiet"
                                disabled={live}
                                onClick={() => remove(p.wf.id)}
                                aria-label={`Remove from Compare: ${p.wf.name}`}
                              >
                                <X size={13} aria-hidden="true" /> Remove
                              </button>
                            </div>
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {row("Flow", (p, i) => <FlowMini wf={p.wf} marked={marked[i]} />, "flow")}
                    {row(
                      bench ? `Result on ${bench.name}` : "Result",
                      (p) => {
                        const r = resultOf(p.wf.id);
                        const across = rank?.by === "pass_with" ? { ranked: rank.ranked[p.wf.id], liftVs: rank.lift_vs[p.wf.id] } : null;
                        return <ResultCell result={r.result} status={r.status} detail={r.detail} bench={bench?.name ?? "this bench"} across={across} />;
                      },
                      "result",
                    )}
                    {row(
                      "Expected",
                      (p) => (
                        <span className="num">
                          {expectedText(p.wf)} pts{" "}
                          <span className={`cmp-prov cmp-prov--${provenance(p.wf).kind}`} title={provenance(p.wf).title} data-testid="compare-provenance">
                            {provenance(p.wf).text}
                          </span>
                        </span>
                      ),
                      "expected",
                    )}
                    {row("Relative cost", (p) => <span className="num">{p.wf.cost}×</span>, "cost")}
                    {row(
                      <>
                        Value <span className="muted cmp-unit">pts per 1× cost</span>
                      </>,
                      (p) => <span className="num">{p.wf.cost > 0 ? (expected(p.wf) / p.wf.cost).toFixed(1) : "–"}</span>,
                      "value",
                    )}
                    {row("Design", (p) => (p.design ? p.design.name : none), "design")}
                    {row("Started from", (p) => ORIGIN[p.wf.origin] ?? p.wf.origin, "origin")}
                    {row("Discipline", (p) => disciplineLabel(p.wf.discipline), "discipline")}
                    {row("Steps", (p) => <span className="num">{p.wf.steps.length}</span>, "steps")}
                    {row(
                      "Model per step",
                      (p) => (
                        <ul className="cmp-list">
                          {p.wf.steps.map((s) => (
                            <li key={s.id}>
                              <span>{s.name}</span> <span className="muted">· {modelLabel(s.model)}</span>
                            </li>
                          ))}
                        </ul>
                      ),
                      "models",
                    )}
                    {row(
                      "Loops",
                      (p) =>
                        p.wf.loops?.length ? (
                          <ul className="cmp-list">
                            {p.wf.loops.map(([a, b, n]) => (
                              <li key={`${a}>${b}`}>
                                {p.wf.steps.find((s) => s.id === a)?.name ?? a} ↺ back to {p.wf.steps.find((s) => s.id === b)?.name ?? b}, at most {n}×
                              </li>
                            ))}
                          </ul>
                        ) : (
                          none
                        ),
                      "loops",
                    )}
                    {row(
                      "Harness rules",
                      (p) => (p.wf.harness.length ? <ul className="cmp-list">{p.wf.harness.map((h) => <li key={h}>{ruleName(h)}</li>)}</ul> : none),
                      "rules",
                    )}
                    {row(
                      "Skills",
                      (p) => {
                        const withSkills = p.wf.steps.filter((s) => s.skills.length);
                        return withSkills.length ? (
                          <ul className="cmp-list">
                            {withSkills.map((s) => (
                              <li key={s.id}>
                                <span className="muted">{s.name}:</span> {s.skills.map((k) => k.name).join(", ")}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          none
                        );
                      },
                      "skills",
                    )}
                  </tbody>
                </table>
              </div>
              {cols < COMPARE_MAX ? (
                <p className="small muted">
                  {cols} of {COMPARE_MAX} pinned. Pin more from the Lab with Compare.
                </p>
              ) : null}
            </section>

            <section className="cmp-section" aria-labelledby="cmp-diff-h">
              <h2 id="cmp-diff-h" className="cmp-section__title">
                Differences
              </h2>
              {cols < 2 ? (
                <p className="small muted">Pin another workflow to see what differs.</p>
              ) : !diffs.length ? (
                <p className="small">They are the same workflow: same steps, models, skills, loops and rules.</p>
              ) : (
                <div className="table-wrap cmp-wrap" tabIndex={0} role="region" aria-label="Differences">
                  <p className="small muted cmp-diff__lead">
                    Only what differs, step by step. Steps are lined up by their id, then by name; – means that workflow hasn't got it.
                  </p>
                  <table className="cmp-table cmp-table--diff" style={colStyle}>
                    <colgroup>
                      <col className="cmp-table__label" />
                      {pins.map((p) => (
                        <col key={p.wf.id} />
                      ))}
                    </colgroup>
                    <thead>
                      <tr>
                        <th scope="col">What differs</th>
                        {pins.map((p) => (
                          <th key={p.wf.id} scope="col" className="cmp-diff__name">
                            {p.wf.name}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {diffs.map((d, k) => (
                        <tr key={`${d.kind}-${d.label}-${k}`} className={`cmp-diff cmp-diff--${d.kind}`} data-testid="compare-diff">
                          <th scope="row">{d.label}</th>
                          {d.cells.map((c, i) => (
                            <td key={pins[i]?.wf.id ?? i} className={c === null ? "muted" : undefined}>
                              {c ?? (d.kind === "rule" ? "off" : "–")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </main>
  );
}
