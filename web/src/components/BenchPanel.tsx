import { FlaskConical, LogIn, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { api, ApiError } from "../lib/api";
import type { AblateJob, BenchInfo, BenchMade, Contribution, FullSize, Improvement, LabResult, LabStarted, LabWorkflow, LocalModel, LocalModels as LocalData, PublicBench, PublicBenches, RunExtends, Started } from "../lib/types";
import { budgetPromise } from "../lib/format";
import { isEvidence } from "../lib/provenance";
import { adhered, adherenceText, modelText, ofWorkflow, spentText, statusText, verdictWord } from "../lib/evidence";
import { RigBadge } from "./RigScore";
import { LocalModels } from "./LocalModels";
import { LiveRun, MetricHeadline } from "./Results";
import { RigScore } from "./RigScore";
import { Forensics } from "./Forensics";
import { useMetricChoice } from "./RunChoice";
import { CostOnLocal, costOnLocal, fill } from "./RunOn";
import { RunEstimate } from "./RunEstimate";
import { pairsFor, RunSize } from "./RunSize";
import { SuiteRun } from "./SuiteRun";
import { BaselineCheck, baselineOf, TierChoice, tierTasks } from "./BenchTier";
import { sessionModel } from "../lib/compareSet";
import { Term } from "./Term";

const SUITE = "__suite__";
const PUB = "pub:"; // a public benchmark not downloaded yet: "pub:<name>@<version>"
const MORE = "more:public"; // the Bench list's one entry for every public benchmark

/** The bench a workflow starts on: one made for its discipline, else one it also fits, else the first. */
function defaultBench(list: BenchInfo[], discipline: string): string {
  return (list.find((x) => x.discipline === discipline) ?? list.find((x) => x.disciplines.includes(discipline)) ?? list[0])?.id ?? "";
}

const HEAVY = "Large Docker images: each task pulls or builds a whole repository and its tools, often several GB.";

function tasks(n: number) {
  return `${n} task${n === 1 ? "" : "s"}`;
}

/** "Accounts payable · 5 tasks + 2 hard · too easy for Sonnet 5.5": the hard tier, and the agent
 * alone passing every standard task on the session model (bench-difficulty). */
function benchLabel(x: BenchInfo, model: string | null = null) {
  const kind = x.public ? " · public" : x.imported ? " · imported" : x.generated ? " · generated" : "";
  const hard = x.hard?.length ? ` + ${x.hard.length} hard` : "";
  const easy = baselineOf(x, "standard", model);
  return `${x.name} · ${tasks(x.scenarios.length)}${hard}${x.judged ? " · judged" : ""}${kind}${
    easy?.too_easy ? ` · too easy for ${easy.model_label}` : ""
  }`;
}

function pct(x: number | null | undefined) {
  return x == null ? "–" : `${Math.round(x * 100)}%`;
}

function pts(x: number | null | undefined) {
  if (x == null) return "–";
  const v = Math.round(x * 100);
  return `${v > 0 ? "+" : ""}${v}`;
}

const VERDICT_TEXT: Record<Contribution["verdict"], string> = {
  essential: "essential",
  "dead weight": "dead weight",
  harmful: "harmful",
  unclear: "unclear",
  neutral: "no effect, no saving",
};

function SlimProgress({
  job,
  applied,
  onStop,
  onApply,
}: {
  job: AblateJob;
  applied: boolean;
  onStop: () => void;
  onApply: (stepIds: string[]) => void;
}) {
  const con = job.contributions ?? null;
  const dead = con ? job.variants.filter((v) => v.kind === "drop" && con[v.key]?.verdict === "dead weight").map((v) => v.key) : [];
  return (
    <div className="card slim" role="status" aria-live="polite">
      <div className="result__top">
        <strong>
          {job.status === "running" ? "Measuring Variants" : job.status === "stopped" ? "Stopped" : "Slimming Done"}
        </strong>
        <span className="small muted num">
          ${job.spent_usd.toFixed(2)} of ${job.budget.toFixed(2)}
        </span>
      </div>
      <ul className="slim__list small">
        {job.variants.map((v) => {
          const c = con?.[v.key];
          return (
            <li key={v.key} className="slim__row">
              <span>{v.label}</span>
              <span className="num muted">
                {c
                  ? `${c.marginal_pts == null ? "–" : `${c.marginal_pts > 0 ? "+" : ""}${c.marginal_pts} pts if kept`}${
                      c.saved_cost_usd != null ? ` · saves $${c.saved_cost_usd.toFixed(3)}/task` : ""
                    } · ${VERDICT_TEXT[c.verdict]}`
                  : v.status === "error"
                    ? `failed: ${v.detail}`
                    : v.status}
              </span>
            </li>
          );
        })}
      </ul>
      {job.note ? <p className="small muted">{job.note}</p> : null}
      {job.status === "running" ? (
        <button type="button" className="btn btn--small btn--quiet" onClick={onStop}>
          Stop (finishes the trial in progress, skips the rest)
        </button>
      ) : con ? (
        <>
          <p className="small muted">
            Each number is the workflow's change minus the variant's, so it is what keeping the part adds. Small runs have wide
            intervals: where they overlap heavily, it says “unclear”.
          </p>
          <button type="button" className="btn btn--small btn--primary" disabled={!dead.length || applied} onClick={() => onApply(dead)}>
            {applied ? "Applied (Cmd+Z or Ctrl+Z takes it back)" : `Apply the Slimmed Workflow${dead.length ? ` (Remove ${dead.length} Dead-Weight Step${dead.length === 1 ? "" : "s"})` : ""}`}
          </button>
          {!dead.length ? <span className="small muted"> No step is dead weight.</span> : null}
        </>
      ) : null}
    </div>
  );
}

/** Measure a workflow on a built-in bench: with it against without it, on the same agent and model. */
export function BenchPanel({
  wf,
  agent,
  onRunOn,
  onSlim,
  onApplySlim,
  onUseVersion,
  onSignIn,
  onBench,
  chooserAt,
}: {
  wf: LabWorkflow;
  /** Where the bench choice itself is shown, when not here: Measure puts it at the top of the
   * pane, so it is in view without scrolling. The rest of the bench settings stay here. */
  chooserAt?: HTMLElement | null;
  /** The bench picked here: the Lab's Results open on it. */
  onBench?: (bench: string) => void;
  /** Opens the agent sign-in (the top bar's): a run can be priced before, but not started. */
  onSignIn?: () => void;
  agent: { id: string; label: string; ready: boolean; budget_cap?: boolean } | null;
  /** Where the next measure runs: the agent on its sign-in, or a local model (`model`, with the
   * engine's words for a run on one and its time limit factor: Try it runs there too). */
  onRunOn?: (r: {
    agent: string;
    local: boolean;
    label: string;
    model: LocalModel | null;
    words: NonNullable<LocalData["repo"]> | null;
    factor: number;
  }) => void;
  /** Colours the canvas by what each step contributes (null clears it). */
  onSlim?: (map: Record<string, Contribution> | null) => void;
  /** Removes these steps from the workflow, as one edit that Undo takes back. */
  onApplySlim?: (stepIds: string[]) => void;
  /** Load an edited workflow into the Lab as the person's own (so Undo works). */
  onUseVersion?: (next: LabWorkflow) => void;
}) {
  const [benches, setBenches] = useState<BenchInfo[] | null>(null);
  const [bid, setBid] = useState<string>("");
  const [size, setSize] = useState<"pilot" | "full">("pilot");
  const [full, setFull] = useState<FullSize | null>(null);
  const [budget, setBudget] = useState(5);
  const [auto, setAuto] = useState(true);
  const [grows, setGrows] = useState<RunExtends | null>(null); // what "Keep going" may grow it to
  const [reuse, setReuse] = useState(true);
  const [nudge, setNudge] = useState(true);
  const [confirm, setConfirm] = useState(false);
  const [running, setRunning] = useState<LabStarted | null>(null);
  const [tier, setTier] = useState("standard");
  const [suiteJob, setSuiteJob] = useState<string | null>(null);
  const [results, setResults] = useState<LabResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [locals, setLocals] = useState<LocalModel[]>([]);
  const [localWords, setLocalWords] = useState<LocalData | null>(null); // the engine's words for runs on one
  const [suitePath, setSuitePath] = useState("");
  const [forget, setForget] = useState<string | null>(null); // "bench:id" being confirmed
  const [dropBench, setDropBench] = useState(false);
  const [suiteName, setSuiteName] = useState("");
  const [runOn, setRunOn] = useState<string>(""); // "" = the workflow's Claude models; else a local model id
  const [helper, setHelper] = useState<string | null>(null);
  const [making, setMaking] = useState<"ask" | "running" | null>(null);
  const [made, setMade] = useState<BenchMade | null>(null);
  const [pubs, setPubs] = useState<PublicBenches | null>(null);
  const [pubSize, setPubSize] = useState(0); // 0: the default sample
  const [pubBusy, setPubBusy] = useState<number | null>(null); // tasks being downloaded
  const [pubDone, setPubDone] = useState<string | null>(null);
  const [pubOpen, setPubOpen] = useState(false); // "More: public benchmarks" chosen, none picked yet
  // Slim this workflow: ask (confirm) -> a job whose progress is polled -> contributions.
  const [slimAsk, setSlimAsk] = useState<{ rid: string; count: number; of: number; labels: string[]; budget: number } | null>(null);
  const [job, setJob] = useState<AblateJob | null>(null);
  const [applied, setApplied] = useState(false);
  // "Improve from failures" on one result card: ask first, then show the proposed edits.
  const [improve, setImprove] = useState<{ key: string; stage: "ask" | "running" | "done"; got?: Improvement } | null>(null);
  // What a run is scored on, as on a repo's Measure; a suite pools it over every bench's pairs.
  const { metric, onPlan, picker: metricPicker, confirm: metricConfirm, keepGoing } = useMetricChoice();
  const onLocals = useCallback((d: LocalData) => {
    setLocals(d.models);
    setLocalWords(d);
    setHelper(d.helper);
    setRunOn((cur) => (cur && !d.models.some((m) => m.id === cur) ? "" : cur));
  }, []);
  const local = locals.find((m) => m.id === runOn) ?? null;
  const ready = local ? true : !!agent?.ready;
  // As a repo's Measure: cost can't be the metric on a local model (refused by the engine too).
  const costLocal = costOnLocal(local, metric);
  useEffect(() => {
    const l = locals.find((m) => m.id === runOn) ?? null;
    onRunOn?.({
      agent: l ? "claude-code" : (agent?.id ?? "claude-code"),
      local: !!l,
      label: l ? l.label : (agent?.label ?? "Claude Code"),
      model: l,
      words: localWords?.repo ?? null,
      factor: localWords?.timeout_factor ?? 1,
    });
  }, [runOn, agent, locals, localWords, onRunOn]);

  const loadResults = useCallback(() => api.labResults().then(setResults, () => undefined), []);
  useEffect(() => {
    api.benches().then((b) => {
      setBenches(b);
      // A bench made for the workflow's discipline (support: "Answer support tickets by policy"),
      // not merely one that lists it among others; kept once you choose one yourself.
      setBid((cur) => cur || defaultBench(b, wf.discipline));
    }, (e) => setError(e instanceof ApiError ? e.message : String(e)));
    void loadResults();
  }, [wf.discipline, loadResults]);
  useEffect(() => {
    api.publicBenches().then(setPubs, () => undefined);
  }, []);

  // Calibrations belong to one judge, so a new helper means a fresh look at each bench.
  useEffect(() => {
    api.benches().then(setBenches, () => undefined);
  }, [helper]);

  const isSuite = bid === SUITE;
  const benchRef = useRef(onBench);
  benchRef.current = onBench;
  useEffect(() => {
    if (bid) benchRef.current?.(bid);
  }, [bid]);
  // This workflow's own results; every other workflow's runs are kept apart, by name.
  // A version improved from one of its results ("Improve from failures") counts as its own too.
  const mineKeys = new Set(results.filter((r) => ofWorkflow(r, wf.id)).map((r) => `${r.bench}:${r.id}`));
  for (let grew = true; grew; ) {
    grew = false;
    for (const r of results)
      if (r.improved_from != null && mineKeys.has(`${r.bench}:${r.improved_from}`) && !mineKeys.has(`${r.bench}:${r.id}`)) {
        mineKeys.add(`${r.bench}:${r.id}`);
        grew = true;
      }
  }
  const mine = results.filter((r) => mineKeys.has(`${r.bench}:${r.id}`));
  const otherRuns = results.filter((r) => !mineKeys.has(`${r.bench}:${r.id}`));
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setInterval(() => {
      api.ablateGet(job.id).then(setJob, () => undefined);
    }, 1500);
    return () => clearInterval(t);
  }, [job]);
  // The parent's callbacks change every render: keep them in a ref so these effects run on the job alone.
  const slimRef = useRef(onSlim);
  slimRef.current = onSlim;
  const colours = job?.status !== "running" && job?.contributions ? job.contributions : null;
  useEffect(() => {
    slimRef.current?.(colours);
  }, [colours]);
  useEffect(() => () => slimRef.current?.(null), []);

  const b = benches?.find((x) => x.id === bid) ?? null;
  // The tier picked here, if this bench has it (a bench without a hard tier is standard only).
  const tierNow = b?.tiers?.some((t) => t.id === tier) ? tier : "standard";
  const runTasks = b ? tierTasks(b, tierNow) : [];
  // The model a run is recorded under: the workflow's session model, or the local model.
  const modelKey = runOn ? runOn : (agent?.id ?? "claude-code") === "claude-code" ? sessionModel(wf) : null;
  const easy = isSuite ? null : baselineOf(b, tierNow, modelKey);
  const warn = easy?.too_easy ? (easy.warn ?? null) : null;
  // Those made for this discipline first, then those that also fit it.
  const fits = (benches ?? [])
    .filter((x) => x.disciplines.includes(wf.discipline))
    .sort((x, y) => Number(y.discipline === wf.discipline) - Number(x.discipline === wf.discipline));
  // A suite is the built-in benches that fit; imported and generated ones are picked one by one.
  const suiteBenches = fits.filter((x) => !x.imported && !x.generated);
  const suiteTasks = suiteBenches.reduce((a, x) => a + x.scenarios.length, 0);
  const perBench = suiteBenches.length ? budget / suiteBenches.length : 0;
  const others = (benches ?? []).filter((x) => !x.disciplines.includes(wf.discipline));
  // Public benchmarks not added yet; an added one is listed with the benches above.
  const pubFree = (pubs?.datasets ?? []).filter((d) => !d.added);
  const pubGroups: [string, PublicBench[]][] = [
    ["Public Benchmarks for This Workflow", pubFree.filter((d) => d.disciplines.includes(wf.discipline))],
    ["Other Public Benchmarks", pubFree.filter((d) => !d.disciplines.includes(wf.discipline))],
  ];
  const pubCount = pubFree.length;
  // The public benchmarks sit behind one entry; picking it shows them in a list of their own.
  const pubShown = pubOpen || bid.startsWith(PUB);
  const pick = bid.startsWith(PUB) ? (pubs?.datasets.find((d) => d.key === bid.slice(PUB.length)) ?? null) : null;
  const pickN = pick ? Math.min(pubSize || pubs!.default_sample, pick.tasks, pubs!.max_sample) : 0;
  const judgeBlocked = !!b?.judged && !!helper && b.calibration?.trustworthy !== true;
  const [calibrating, setCalibrating] = useState<"ask" | "running" | null>(null);
  const hiddenN = runTasks.filter((s) => s.held_out).length;
  // Pairs of a pilot or a full run: the suite's are every bench's added up.
  const pairsOf = (s: "pilot" | "full") =>
    isSuite ? suiteBenches.reduce((a, x) => a + pairsFor(s, x.scenarios.length), 0) : b ? pairsFor(s, runTasks.length) : 0;
  // One bench's full run grows with the budget up to the sizing: the engine plans it (full).
  const planned = !isSuite && b && size === "full" && full ? full.planned_pairs : pairsOf(size);
  const repeats = b && runTasks.length ? planned / runTasks.length : 0;
  const trials = 2 * planned;
  /** A result of this very workflow that helped: the one a slimming job can start from. */
  const slimTarget = (r: LabResult): { agent: string } | null => {
    const stem = `workflow-${wf.id}`;
    if (r.status !== "done" || r.verdict !== "helps" || !isEvidence(r.validity)) return null;
    if (r.treatment === stem) return { agent: "claude-code" };
    return r.treatment.startsWith(`${stem}-`) ? { agent: r.treatment.slice(stem.length + 1) } : null;
  };
  const improveModel = locals.find((m) => m.id === helper)?.label ?? "Claude Sonnet";
  const onDone = useCallback(() => {
    setRunning(null);
    void loadResults();
    // A baseline check (or any run) changes what the agent alone is known to do here.
    api.benches().then(setBenches, () => undefined);
  }, [loadResults]);

  // The bench choice: here, or at the top of Measure's pane (chooserAt), with its state kept here.
  const chooser = benches ? (
    <>
          <div className="field">
            <label htmlFor="bench">Bench</label>
            <select
              id="bench"
              className="select"
              value={pubShown ? MORE : bid}
              onChange={(e) => {
                const v = e.target.value;
                setConfirm(false);
                setPubDone(null);
                if (v === MORE) {
                  setPubOpen(true);
                  setBid("");
                } else {
                  setPubOpen(false);
                  setBid(v);
                }
              }}
            >
              {fits.length ? (
                <optgroup label="Fits This Workflow">
                  {suiteBenches.length >= 2 ? (
                    <option value={SUITE}>
                      All {suiteBenches.length} Matching Benches ({tasks(suiteTasks)})
                    </option>
                  ) : null}
                  {fits.map((x) => (
                    <option key={x.id} value={x.id}>
                      {benchLabel(x, modelKey)}
                    </option>
                  ))}
                </optgroup>
              ) : null}
              <optgroup label="Other Benches">
                {others.map((x) => (
                  <option key={x.id} value={x.id}>
                    {benchLabel(x, modelKey)}
                  </option>
                ))}
              </optgroup>
              {pubCount ? <option value={MORE}>More: Public Benchmarks ({pubCount})…</option> : null}
            </select>
          </div>
          {pubShown ? (
            <div className="field">
              <label htmlFor="pub-bench">Public benchmark</label>
              <select
                id="pub-bench"
                className="select"
                value={bid.startsWith(PUB) ? bid : ""}
                onChange={(e) => (setBid(e.target.value), setConfirm(false), setPubDone(null))}
              >
                <option value="" disabled>
                  Choose one of {pubCount}…
                </option>
                {pubGroups.map(([label, list]) =>
                  list.length ? (
                    <optgroup key={label} label={label}>
                      {list.map((d) => (
                        <option key={d.key} value={PUB + d.key}>
                          {d.name} {d.version} · {tasks(d.tasks)} · public
                        </option>
                      ))}
                    </optgroup>
                  ) : null,
                )}
              </select>
            </div>
          ) : null}
          {pubs?.note ? <p className="small muted">{pubs.note}</p> : null}
          {pubDone ? (
            <p className="small" role="status">
              {pubDone}
            </p>
          ) : null}
    </>
  ) : null;

  return (
    <div className="insp__section">
      <div className="insp__label">Measure on a test bench</div>
      {error ? <p className="notice notice--error small">{error}</p> : null}
      {suiteJob ? (
        <SuiteRun job={suiteJob} onDone={loadResults} onClose={() => setSuiteJob(null)} />
      ) : running ? (
        <LiveRun
          started={{ ...running, repeats: running.probe ? 1 : repeats, commit: null, dirty: false } as Started}
          title={running.probe ? `Checking the bench: the agent alone (#${running.id})` : undefined}
          eventsUrl={`/api/lab/runs/${running.bench}/${running.id}/events`}
          onDone={onDone}
          onStop={async () => {
            await api.labStop(running.bench, running.id);
          }}
        />
      ) : benches ? (
        <>
          {chooserAt ? createPortal(chooser, chooserAt) : chooser}
          {pick ? (
            <>
              <p className="small muted">
                {pick.description}
                {pick.source ? (
                  <>
                    {" "}
                    <a href={pick.source} target="_blank" rel="noreferrer">
                      Source
                    </a>
                  </>
                ) : null}
              </p>
              {!pick.disciplines.includes(wf.discipline) ? (
                <p className="notice notice--warning small">This benchmark is for other kinds of work, so its result says little about this workflow.</p>
              ) : null}
              <div className="field">
                <label htmlFor="pub-size">Tasks to download</label>
                <input
                  id="pub-size"
                  className="input num"
                  type="number"
                  min={1}
                  max={Math.min(pick.tasks, pubs!.max_sample)}
                  value={pickN}
                  onChange={(e) => setPubSize(Math.max(1, Math.round(Number(e.target.value)) || 1))}
                />
              </div>
              <p className="small muted">
                {pickN} of its {tasks(pick.tasks)}, picked at random but the same each time. Every task runs with and without the
                workflow on your sign-in, so each one costs money: start small.
              </p>
              {pick.heavy ? (
                <p className="notice notice--warning small">{HEAVY}</p>
              ) : null}
              {pubBusy ? (
                <p className="small" role="status">
                  Downloading {tasks(pubBusy)}…
                </p>
              ) : (
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={async () => {
                    setError(null);
                    setPubDone(null);
                    setPubBusy(pickN);
                    try {
                      const got = await api.addPublicBench(pick.key, pickN);
                      setBenches((cur) => [...(cur ?? []).filter((x) => x.id !== got.bench.id), got.bench]);
                      setPubs((cur) =>
                        cur ? { ...cur, datasets: cur.datasets.map((d) => (d.key === pick.key ? { ...d, added: got.bench.id } : d)) } : cur,
                      );
                      setBid(got.bench.id);
                      setPubOpen(false);
                      setPubDone(
                        `Added ${got.bench.name}: ${tasks(got.bench.scenarios.length)}.` +
                          (got.dropped.length ? ` Left out ${got.dropped.join(", ")}: not Harbor tasks.` : ""),
                      );
                    } catch (e) {
                      setError(e instanceof ApiError ? e.message : String(e));
                    } finally {
                      setPubBusy(null);
                    }
                  }}
                >
                  Download {pickN} {pickN === 1 ? "Task" : "Tasks"}
                </button>
              )}
            </>
          ) : (
            <>
          {isSuite ? (
            <p className="small muted">
              One total budget, split evenly over {suiteBenches.map((x) => x.name).join("; ")}, with one pooled verdict at the end.
            </p>
          ) : null}
          {b ? (
            <p className="small muted">
              {b.summary} Tasks:{" "}
              {runTasks
                .filter((s) => !s.held_out)
                .map((s) => (s.tier === "hard" ? `${s.title} (hard)` : s.title))
                .join("; ")}
              .
              {hiddenN
                ? ` Plus ${hiddenN} held-out task${hiddenN === 1 ? "" : "s"}: run, but not shown here, so a workflow can't be tuned to ${hiddenN === 1 ? "it" : "them"}.`
                : ""}
              {b.public?.source ? (
                <>
                  {" "}
                  <a href={b.public.source} target="_blank" rel="noreferrer">
                    Source
                  </a>
                </>
              ) : null}
            </p>
          ) : null}
          {b && !isSuite ? <TierChoice bench={b} tier={tierNow} onTier={(t) => (setTier(t), setConfirm(false))} /> : null}
          {b && !isSuite ? (
            <BaselineCheck
              bench={b}
              tier={tierNow}
              model={modelKey}
              ready={ready}
              probe={{ agent: local ? "claude-code" : (agent?.id ?? "claude-code"), workflow: wf, local_model: local?.id ?? null }}
              onStarted={setRunning}
            />
          ) : null}
          {b?.public?.heavy ? (
            <p className="notice notice--warning small">{HEAVY}</p>
          ) : null}
          {b && (b.imported || b.generated) ? (
            <p className="small">
              {dropBench ? (
                <>
                  Remove {b.name} and its results?{" "}
                  <button
                    type="button"
                    className="linkish"
                    onClick={async () => {
                      setDropBench(false);
                      try {
                        await api.removeBench(b.id);
                        // A public benchmark is offered for download again.
                        setPubs((cur) => (cur ? { ...cur, datasets: cur.datasets.map((d) => (d.added === b.id ? { ...d, added: null } : d)) } : cur));
                        const rest = (benches ?? []).filter((x) => x.id !== b.id);
                        setBenches(rest);
                        setBid(defaultBench(rest, wf.discipline));
                        void loadResults();
                      } catch (e) {
                        setError(e instanceof ApiError ? e.message : String(e));
                      }
                    }}
                  >
                    Remove
                  </button>{" "}
                  <button type="button" className="linkish" onClick={() => setDropBench(false)}>
                    Keep It
                  </button>
                </>
              ) : (
                <button type="button" className="linkish" onClick={() => setDropBench(true)}>
                  Remove This {b.public ? "Public Benchmark" : b.imported ? "Imported Suite" : "Generated Bench"}
                </button>
              )}
            </p>
          ) : null}
          {b && !b.disciplines.includes(wf.discipline) ? (
            <p className="notice notice--warning small">This bench is for other kinds of work, so its result says little about this workflow.</p>
          ) : null}
          {b?.judged ? (
            <div className="small judgebox">
              Graded in two layers: rule checks in the sandbox, then a judge (Opus, on this machine, blind to which arm) scores the
              document against a rubric.{" "}
              {b.calibration && calibrating !== "ask" && calibrating !== "running" ? (
                <>
                <b className={b.calibration.trustworthy ? "ok" : "adh"}>
                  {b.calibration.trustworthy ? "Judge checked: it tells good from bad." : "Judge check failed: treat these grades with care."}
                </b>
                {!b.calibration.trustworthy ? (
                  <>
                    {" "}
                    <button type="button" className="linkish" onClick={() => setCalibrating("ask")}>
                      Check Again
                    </button>
                  </>
                ) : null}
                </>
              ) : calibrating === "ask" ? (
                <span>
                  Run the judge on a known-good and a known-bad example of each task (2 calls per task, your sign-in)?{" "}
                  <button
                    type="button"
                    className="linkish"
                    onClick={async () => {
                      setCalibrating("running");
                      try {
                        const cal = await api.calibrate(b.id);
                        setBenches((cur) => cur?.map((x) => (x.id === b.id ? { ...x, calibration: cal } : x)) ?? cur);
                      } catch (e) {
                        setError(e instanceof ApiError ? e.message : String(e));
                      } finally {
                        setCalibrating(null);
                      }
                    }}
                  >
                    Check It
                  </button>{" "}
                  <button type="button" className="linkish" onClick={() => setCalibrating(null)}>
                    Cancel
                  </button>
                </span>
              ) : calibrating === "running" ? (
                <span>Checking the judge…</span>
              ) : (
                <button type="button" className="linkish" onClick={() => setCalibrating("ask")}>
                  Check the Judge First
                </button>
              )}
              {judgeBlocked ? (
                <p className="adh">
                  Local model selected for judging: run 'Check the Judge First' and pass it before measuring.
                </p>
              ) : null}
            </div>
          ) : null}
          <div className="field">
            <label htmlFor="run-on">Run on</label>
            <select id="run-on" className="select" value={runOn} onChange={(e) => (setRunOn(e.target.value), setConfirm(false))}>
              <option value="">{agent?.label ?? "Claude Code"} · your sign-in</option>
              {locals.length ? (
                <optgroup label="Local Models (Free, on This Machine)">
                  {locals.map((m) => (
                    <option key={m.id} value={m.id} disabled={!m.anthropic}>
                      {m.label}
                      {m.anthropic ? "" : " · can't run Claude Code"}
                    </option>
                  ))}
                </optgroup>
              ) : null}
            </select>
          </div>
          {local ? (
            <p className="notice small">
              Claude Code runs in the sandbox with every model it asks for (subagents too) served by {local.label}, reached as
              host.docker.internal. Small local models often can't hold an agent loop: a run full of errors says that, not that
              the workflow is bad.
            </p>
          ) : null}
          {metricPicker}
          <CostOnLocal show={costLocal} words={localWords?.repo} />
          <div className="row" style={{ gap: 6, alignItems: "center" }}>
          <RunSize size={size} onSize={setSize} full={full} />
          <Term k="pilot-vs-full" />
          </div>
          <div className="field">
            <label htmlFor="bench-budget">Stop at (USD{isSuite ? ", in total" : ""})</label>
            <input
              id="bench-budget"
              className="input num"
              type="number"
              min={0.5}
              step={0.5}
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
            />
          </div>
          <RunEstimate
            budget={budget}
            onSetBudget={setBudget}
            canExtend={!isSuite && auto}
            onFull={setFull}
            onMetricPlan={onPlan}
            onExtends={setGrows}
            request={
              isSuite || b
                ? {
                    pairs: pairsOf(size),
                    agent: local ? "claude-code" : (agent?.id ?? "claude-code"),
                    bench: isSuite ? null : bid,
                    workflow: wf,
                    local: !!local,
                    // One bench: the engine plans the pairs from its tasks. A suite: fixed sizes,
                    // the pilot running each task once (a full run stopped within that is no better),
                    // and on a saving the guard is judged on all of them pooled.
                    ...(isSuite
                      ? { pilot_pairs: pairsOf("pilot"), full_pairs: pairsOf("full"), metric }
                      : { size, tasks: runTasks.length, tier: tierNow, metric, auto }),
                  }
                : null
            }
          />
          {isSuite ? null : (
            <>
          <label className="check-row small">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
            <span>
              <b>Keep going until it's decided</b> <span data-testid="keep-going">· {keepGoing}</span>
            </span>
          </label>
          <label className="check-row small">
            <input type="checkbox" checked={reuse} onChange={(e) => setReuse(e.target.checked)} />
            <span>
              <b>Reuse matching baseline trials</b>
              <Term k="baseline" />
              <span data-testid="reuse-state">
                {reuse
                  ? " · on: earlier baseline trials that match (same tasks, model and agent) are used again instead of paid for twice"
                  : " · off: the baseline runs fresh, and both arms are paid for"}
              </span>
            </span>
          </label>
          <label className="check-row small">
            <input type="checkbox" checked={nudge} onChange={(e) => setNudge(e.target.checked)} />
            <span>
              <b>Tell the agent to open the workflow in the prompt</b>
              <span data-testid="nudge-state">
                {nudge ? " · on: the prompt tells the agent to open it" : " · off: the workflow has to be found, as in real use"}
              </span>
            </span>
          </label>
            </>
          )}
          {!ready ? (
            <>
              <p className="small muted">Running needs {agent?.label ?? "an agent"} signed in; pricing it doesn't.</p>
              <button type="button" className="btn btn--primary" onClick={onSignIn} disabled={!onSignIn}>
                <LogIn size={14} aria-hidden="true" /> Sign In to Run
              </button>
            </>
          ) : isSuite && local ? (
            <p className="notice notice--warning small" data-testid="suite-local">
              {localWords?.suite_local ? fill(localWords.suite_local, { agent: agent?.label ?? "Claude Code" }) : null}
            </p>
          ) : confirm && isSuite ? (
            <div className="card">
              <strong>
                Run {trials} Trials on {agent?.label} across {suiteBenches.length} Benches?
              </strong>
              <p className="small">
                {suiteBenches.map((x) => x.name).join("; ")}. Each bench runs the workflow with and without it, one bench after
                another, in Docker sandboxes on your sign-in. ${budget.toFixed(2)} in total is split evenly: ${perBench.toFixed(2)} per
                bench, and what a bench doesn't spend carries over to the next. Each bench runs its {size === "full" ? "full" : "pilot"}{" "}
                pairs and no more: the verdict is pooled at the end, not decided bench by bench.
              </p>
              <p className="small">{budgetPromise(budget, agent?.label ?? "The agent", !!agent?.budget_cap)}</p>
              {metricConfirm}
              <div className="row" style={{ gap: 8 }}>
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={async () => {
                    setError(null);
                    setConfirm(false);
                    try {
                      const r = await api.suiteRun({ workflow: wf, budget, agent: agent?.id ?? "claude-code", size, metric });
                      setSuiteJob(r.job);
                    } catch (e) {
                      setError(e instanceof ApiError ? e.message : String(e));
                    }
                  }}
                >
                  Start, up to ${budget.toFixed(2)}
                </button>
                <button type="button" className="btn btn--quiet" onClick={() => setConfirm(false)}>
                  Back
                </button>
              </div>
            </div>
          ) : confirm ? (
            <div className="card">
              <strong>
                Run {trials} Trials on {local ? local.label : agent?.label}?
              </strong>
              <p className="small">
                Every {tierNow === "standard" ? "" : `${tierNow === "hard" ? "hard" : "standard and hard"} `}task in {b?.name} runs {repeats}× with this workflow and {repeats}× without it, in Docker sandboxes
                <Term k="sandbox" />,{" "}
                {local ? "on your local model (no API cost)" : "on your sign-in"}
                {auto ? ", then more while it's undecided" : ""}. {reuse
                  ? '"Without" trials from earlier runs on this bench are reused where they match.'
                  : "The baseline runs fresh."}
              </p>
              {auto && grows ? (
                <p className="small num" data-testid="confirm-extends">
                  {grows.line}
                </p>
              ) : null}
              <p className="small">
                {budgetPromise(budget, local ? local.label : (agent?.label ?? "The agent"), !local && !!agent?.budget_cap, !!local)}
              </p>
              {metricConfirm}
              {warn ? <p className="notice notice--warning small">{easy!.text}. {warn}</p> : null}
              <div className="row" style={{ gap: 8 }}>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={costLocal}
                  onClick={async () => {
                    setError(null);
                    setConfirm(false);
                    try {
                      setRunning(
                        await api.labRun({
                          workflow: wf,
                          bench: bid,
                          size,
                          budget,
                          agent: local ? "claude-code" : (agent?.id ?? "claude-code"),
                          auto,
                          reuse_baseline: reuse,
                          nudge_prompt: nudge,
                          local_model: local?.id ?? null,
                          tier: tierNow,
                          metric,
                        }),
                      );
                    } catch (e) {
                      setError(e instanceof ApiError ? e.message : String(e));
                    }
                  }}
                >
                  Start, up to ${budget.toFixed(2)}
                </button>
                <button type="button" className="btn btn--quiet" onClick={() => setConfirm(false)}>
                  Back
                </button>
              </div>
            </div>
          ) : (
            <>
              {warn ? (
                <p className="notice notice--warning small" data-testid="too-easy-warn">
                  {warn}
                </p>
              ) : null}
              <button
                type="button"
                className="btn btn--primary"
                disabled={(!b && !isSuite) || budget <= 0 || judgeBlocked || costLocal}
                onClick={() => setConfirm(true)}
              >
                <FlaskConical size={14} aria-hidden="true" /> Rig &amp; Measure · {trials} trials
              </button>
            </>
          )}
            </>
          )}
          <div className="small judgebox">
            {making === "ask" ? (
              <span>
                {helper
                  ? `${locals.find((m) => m.id === helper)?.label ?? "Your local model"} writes a project and tasks for this workflow (free, on this machine).`
                  : "Claude writes a project and tasks for this workflow: one model call on your sign-in."}{" "}
                Each task is then proven in a Docker container with no network: it must fail untouched and pass on its
                reference solution, or it's dropped.{" "}
                <button
                  type="button"
                  className="linkish"
                  onClick={async () => {
                    setMaking("running");
                    setError(null);
                    try {
                      const r = await api.makeBench(wf);
                      setMade(r);
                      if (r.bench) {
                        const nb = r.bench;
                        setBenches((cur) => [...(cur ?? []).filter((x) => x.id !== nb.id), nb]);
                        setBid(nb.id);
                      }
                    } catch (e) {
                      setError(e instanceof ApiError ? e.message : String(e));
                    } finally {
                      setMaking(null);
                    }
                  }}
                >
                  Make It
                </button>{" "}
                <button type="button" className="linkish" onClick={() => setMaking(null)}>
                  Cancel
                </button>
              </span>
            ) : making === "running" ? (
              <span role="status">Writing the bench and proving each task in Docker…</span>
            ) : (
              <button type="button" className="linkish" onClick={() => (setMade(null), setMaking("ask"))}>
                Make a Bench for This Workflow
              </button>
            )}
            {made ? (
              <div role="status">
                {made.bench
                  ? `Made "${made.bench.name}": ${made.kept.length} task${made.kept.length === 1 ? "" : "s"} proven both ways.`
                  : "No task survived the proofs, so no bench was made."}
                {Object.keys(made.dropped).length
                  ? ` Dropped ${Object.entries(made.dropped)
                      .map(([k, v]) => `${k} (${v.split(":")[0]})`)
                      .join("; ")}.`
                  : ""}
              </div>
            ) : null}
          </div>
          <details className="keybox">
            <summary>Import an Eval Suite</summary>
            <form
              className="localm"
              onSubmit={async (e) => {
                e.preventDefault();
                setError(null);
                try {
                  const got = await api.importSuite({ path: suitePath.trim(), name: suiteName.trim(), disciplines: [wf.discipline] });
                  setBenches((cur) => [...(cur ?? []).filter((x) => x.id !== got.id), got]);
                  setBid(got.id);
                  setSuitePath("");
                  setSuiteName("");
                } catch (err) {
                  setError(err instanceof ApiError ? err.message : String(err));
                }
              }}
            >
              <p className="small muted" style={{ margin: 0 }}>
                A folder of tasks in Harbor's format (task.toml, instruction.md, environment/, tests/test.sh), like a
                downloaded benchmark. Each task builds its own Docker image from its own Dockerfile: import only suites you
                trust.
              </p>
              <label htmlFor="suite-path" className="small">
                Folder
              </label>
              <input id="suite-path" className="input input--small" placeholder="~/evals/my-suite" value={suitePath} onChange={(e) => setSuitePath(e.target.value)} />
              <label htmlFor="suite-name" className="small">
                Name
              </label>
              <input id="suite-name" className="input input--small" value={suiteName} onChange={(e) => setSuiteName(e.target.value)} />
              <button type="submit" className="btn btn--small" disabled={!suitePath.trim() || !suiteName.trim()}>
                Import
              </button>
            </form>
          </details>
          <details className="keybox">
            <summary>Local Models{locals.length ? ` · ${locals.length}` : ""}</summary>
            <LocalModels onChanged={onLocals} />
          </details>
        </>
      ) : (
        <p className="small muted">Loading the benches…</p>
      )}

      {results.length ? (
        <>
          <div className="insp__label" style={{ marginTop: 12 }}>
            Measured
          </div>
          <section aria-label="Measured workflows">
          {mine.length === 0 ? <p className="small muted">Not measured yet: {wf.name} has no runs. Measure it above.</p> : null}
          <ul className="results">
            {[...mine]
              // Results that aren't evidence go last, whatever their number.
              .sort((x, y) => Number(isEvidence(y.validity)) - Number(isEvidence(x.validity)) || (y.diff ?? -9) - (x.diff ?? -9))
              .map((r) => (
                <li key={`${r.bench}-${r.id}`} className="result">
                  <div className="result__top">
                    <b>{r.workflow}</b>
                    <span className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
                      {r.status === "running" ? (
                        <span className={`verdict-pill verdict-pill--${r.verdict}`}>Running</span>
                      ) : (
                        <span className={`verdict-pill verdict-pill--${verdictWord(r.rig, r.verdict).tone}`}>{verdictWord(r.rig, r.verdict).word}</span>
                      )}
                      {r.overfit && r.status !== "running" ? (
                        <span className={`verdict-pill overfit-pill overfit-pill--${r.overfit.verdict}`}>
                          {r.overfit.verdict === "generalises"
                            ? "Generalises"
                            : r.overfit.verdict === "overfit"
                              ? "Overfit: Better on Visible Tasks, Not on Held-Out"
                              : "Held-Out Tasks Don't Settle It"}
                        </span>
                      ) : null}
                      {r.status !== "running" ? (
                        forget === `${r.bench}:${r.id}` ? (
                          <span className="small">
                            Forget it?{" "}
                            <button
                              type="button"
                              className="linkish"
                              onClick={async () => {
                                setForget(null);
                                try {
                                  await api.labForget(r.bench, r.id);
                                  void loadResults();
                                } catch (e) {
                                  setError(e instanceof ApiError ? e.message : String(e));
                                }
                              }}
                            >
                              Yes
                            </button>{" "}
                            <button type="button" className="linkish" onClick={() => setForget(null)}>
                              No
                            </button>
                          </span>
                        ) : (
                          <button
                            type="button"
                            className="iconbtn"
                            aria-label={`Forget the result for ${r.workflow} on ${r.bench_name}`}
                            title="Forget this result: its trials are deleted"
                            onClick={() => setForget(`${r.bench}:${r.id}`)}
                          >
                            <X size={14} aria-hidden="true" />
                          </button>
                        )
                      ) : null}
                    </span>
                  </div>
                  <div className="small muted">{r.bench_name}</div>
                  {!isEvidence(r.validity) ? (
                    <p className="notice notice--warning small" data-testid="validity-badge">
                      <b>{r.validity?.badge}</b> {r.validity?.reason} Not used for estimates or the frontier.
                    </p>
                  ) : null}
                  {/* Scored on tokens, cost or time: the saving and its guard lead; the numbers below are the pass rate. */}
                  {r.rig?.metric ? <MetricHeadline m={r.rig.metric} /> : null}
                  <div className="result__nums num">
                    <span
                      className="result__diff"
                      title={r.ci_low != null ? `95% interval ${pts(r.ci_low)} to ${pts(r.ci_high)} pts` : undefined}
                    >
                      {r.rig?.metric ? "Pass rate " : null}
                      {pts(r.diff)} pts
                    </span>
                    <span>
                      {pct(r.pass_with)} with · {pct(r.pass_without)} without
                    </span>
                    <span>{r.local_model ? "Free (local)" : `$${r.spent_usd.toFixed(2)}`}</span>
                  </div>
                  {r.over_budget ? <div className="small muted num">{spentText(r.spent_usd, r.budget_usd, r.over_budget)}</div> : null}
                  {r.ci_low != null ? (
                    <div className="small muted num">
                      95% interval {pts(r.ci_low)} to {pts(r.ci_high)} pts · {r.n_pairs} complete {r.n_pairs === 1 ? "pair" : "pairs"} · {modelText(r)}
                    </div>
                  ) : null}
                  {r.rig && r.status !== "running" ? <RigScore rig={r.rig} compact name={`Rig score for ${r.workflow} on ${r.bench_name}`} /> : null}
                  {r.held_out ? (
                    <div className="small muted num">
                      Held-out {r.held_out.tasks === 1 ? "task" : "tasks"}:{" "}
                      {r.held_out.diff != null ? `${pts(r.held_out.diff)} pts over ${r.held_out.n_pairs} pairs` : "no pairs yet"}
                      {r.held_out.diff != null && r.diff != null && r.held_out.diff < r.diff - 0.2
                        ? " · much less than on the visible tasks"
                        : ""}
                    </div>
                  ) : null}
                  {r.costs ? (
                    <div className="small muted num">
                      {r.costs.with.per_solved_usd != null ? `$${r.costs.with.per_solved_usd.toFixed(2)}` : "–"} per solved task with
                      {" · "}
                      {r.costs.without.per_solved_usd != null ? `$${r.costs.without.per_solved_usd.toFixed(2)}` : "–"} without
                      {" · "}
                      {r.costs.per_extra_solved_usd == null
                        ? "solved no more tasks"
                        : r.costs.per_extra_solved_usd <= 0.005
                          ? "extra tasks solved at no extra cost"
                          : `$${r.costs.per_extra_solved_usd.toFixed(2)} per extra task solved`}
                    </div>
                  ) : null}
                  {r.reused ? (
                    <div className="small muted num">
                      {r.reused} baseline trials reused · ${r.saved_usd.toFixed(2)} saved
                    </div>
                  ) : null}
                  {r.overfit && r.status !== "running" ? (
                    <div className="small muted num">
                      Against the result it was improved from: {r.overfit.visible_gain_pts != null ? `${r.overfit.visible_gain_pts >= 0 ? "+" : ""}${r.overfit.visible_gain_pts}` : "–"} pts on visible tasks
                      {" · "}
                      {r.overfit.held_out_gain_pts != null ? `${r.overfit.held_out_gain_pts >= 0 ? "+" : ""}${r.overfit.held_out_gain_pts} pts on held-out tasks` : "no held-out pairs"}
                    </div>
                  ) : null}
                  {r.status !== "running" && (r.visible?.failing ?? 0) > 0 && !running ? (
                    <div className="improve">
                      {improve?.key !== `${r.bench}:${r.id}` ? (
                        <button
                          type="button"
                          className="btn btn--small btn--quiet"
                          onClick={() => setImprove({ key: `${r.bench}:${r.id}`, stage: "ask" })}
                        >
                          Improve from Failures
                        </button>
                      ) : improve.stage === "ask" ? (
                        <div className="card">
                          <strong>Improve {r.workflow} from Its Failures?</strong>
                          <p className="small">
                            One call to {improveModel}; only visible tasks are shown to it. Held-out tasks stay hidden, so you can check
                            afterwards whether the edit generalises. Nothing is changed until you pick a version.
                          </p>
                          <div className="row" style={{ gap: 8 }}>
                            <button
                              type="button"
                              className="btn btn--primary btn--small"
                              onClick={async () => {
                                setError(null);
                                setImprove({ key: `${r.bench}:${r.id}`, stage: "running" });
                                try {
                                  const got = await api.labImprove({ workflow: wf, bench: r.bench, experiment: r.id });
                                  setImprove({ key: `${r.bench}:${r.id}`, stage: "done", got });
                                } catch (e) {
                                  setError(e instanceof ApiError ? e.message : String(e));
                                  setImprove(null);
                                }
                              }}
                            >
                              Ask {improveModel}
                            </button>
                            <button type="button" className="btn btn--quiet btn--small" onClick={() => setImprove(null)}>
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : improve.stage === "running" ? (
                        <p className="small muted" role="status">
                          Reading the failures…
                        </p>
                      ) : improve.got ? (
                        <div className="card" aria-label="Proposed improvement">
                          <strong>Proposed Changes</strong>
                          {improve.got.proposal.summary ? <p className="small">{improve.got.proposal.summary}</p> : null}
                          <ul className="improve__changes">
                            {improve.got.proposal.changes.map((c, i) => (
                              <li key={i} className="small">
                                <b>
                                  {c.field === "harness_add"
                                    ? "Add Rule"
                                    : `${improve.got?.workflow.steps.find((s) => s.id === c.step_id)?.name ?? c.step_id} · ${c.field}`}
                                </b>
                                <div>
                                  {c.old ? <del>{c.old}</del> : null}
                                  {c.old ? " → " : ""}
                                  <ins>{c.new}</ins>
                                </div>
                                <div className="muted">{c.why}</div>
                              </li>
                            ))}
                          </ul>
                          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                            <button
                              type="button"
                              className="btn btn--small"
                              onClick={() => {
                                onUseVersion?.(improve.got!.workflow);
                                setImprove(null);
                              }}
                            >
                              Use This Version
                            </button>
                            <button
                              type="button"
                              className="btn btn--primary btn--small"
                              disabled={!ready || costOnLocal(local, r.metric)}
                              title={
                                !ready
                                  ? "Sign in first"
                                  : costOnLocal(local, r.metric)
                                    ? localWords?.repo?.cost_metric
                                    : "Run it on this bench, held-out tasks included, and compare with this result"
                              }
                              onClick={async () => {
                                const got = improve.got!;
                                setError(null);
                                setImprove(null);
                                try {
                                  setRunning(
                                    await api.labRun({
                                      workflow: got.workflow,
                                      bench: r.bench,
                                      size,
                                      budget,
                                      agent: local ? "claude-code" : (agent?.id ?? "claude-code"),
                                      auto,
                                      reuse_baseline: reuse,
                                      nudge_prompt: nudge,
                                      local_model: local?.id ?? null,
                                      improved_from: r.id,
                                      tier: r.tier ?? "standard",
                                      // Scored as the result it is compared with.
                                      metric: r.metric ?? "pass_rate",
                                    }),
                                  );
                                } catch (e) {
                                  setError(e instanceof ApiError ? e.message : String(e));
                                }
                              }}
                            >
                              Measure It, up to ${budget.toFixed(2)}
                            </button>
                            <button type="button" className="btn btn--quiet btn--small" onClick={() => setImprove(null)}>
                              Dismiss
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {r.adherence ? (
                    <div className={`small adh${adhered(r.adherence) ? " adh--ok" : ""}`}>{adherenceText(r.adherence)}</div>
                  ) : null}
                  {r.discordant ? <Forensics bench={r.bench} id={r.id} pairs={r.discordant} /> : null}
                  {slimTarget(r) ? (
                    <div>
                      {slimAsk?.rid === `${r.bench}:${r.id}` ? (
                        <div className="card slim">
                          <strong>
                            Measure {slimAsk.count} Slimmer Variant{slimAsk.count === 1 ? "" : "s"}?
                          </strong>
                          <ul className="small slim__list">
                            {slimAsk.labels.map((l) => (
                              <li key={l}>{l}</li>
                            ))}
                          </ul>
                          <p className="small">
                            {slimAsk.of > slimAsk.count ? `${slimAsk.of} are possible; the first ${slimAsk.count} are measured. ` : ""}
                            One after another on {r.bench_name}. Each runs only its "with" arm: the baseline from this result is reused.
                          </p>
                          <label className="small" htmlFor="slim-budget">
                            Total budget cap (USD)
                          </label>{" "}
                          <input
                            id="slim-budget"
                            type="number"
                            min={0.5}
                            max={500}
                            step={0.5}
                            className="input input--small"
                            value={slimAsk.budget}
                            onChange={(e) => setSlimAsk({ ...slimAsk, budget: Math.max(0.5, Number(e.target.value) || 0.5) })}
                          />
                          <div className="row" style={{ gap: 8, marginTop: 8 }}>
                            <button
                              type="button"
                              className="btn btn--primary btn--small"
                              onClick={async () => {
                                setError(null);
                                const ask = slimAsk;
                                setSlimAsk(null);
                                setApplied(false);
                                try {
                                  setJob(
                                    await api.ablate({
                                      workflow: wf,
                                      bench: r.bench,
                                      budget: ask.budget,
                                      agent: slimTarget(r)!.agent,
                                      size: b && r.n_pairs > b.scenarios.length ? "full" : "pilot",
                                      auto,
                                      local_model: locals.find((m) => m.id === r.model)?.id ?? null,
                                    }),
                                  );
                                } catch (e) {
                                  setError(e instanceof ApiError ? e.message : String(e));
                                }
                              }}
                            >
                              Start, up to ${slimAsk.budget.toFixed(2)}
                            </button>
                            <button type="button" className="btn btn--quiet btn--small" onClick={() => setSlimAsk(null)}>
                              Back
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          type="button"
                          className="btn btn--small"
                          disabled={job?.status === "running"}
                          onClick={async () => {
                            setError(null);
                            try {
                              const pre = await api.ablatePreview(wf);
                              if (!pre.count) return setError("There is nothing to take out of this workflow.");
                              setSlimAsk({
                                rid: `${r.bench}:${r.id}`,
                                count: pre.count,
                                of: pre.of,
                                labels: pre.variants,
                                budget: Math.min(500, Math.max(1, Math.round((pre.count * r.spent_usd) / 2))),
                              });
                            } catch (e) {
                              setError(e instanceof ApiError ? e.message : String(e));
                            }
                          }}
                        >
                          Find the Slimmest Version
                        </button>
                      )}
                    </div>
                  ) : null}
                  {job && job.bench === r.bench && slimTarget(r) ? (
                    <SlimProgress
                      job={job}
                      applied={applied}
                      onStop={() => void api.ablateStop(job.id).catch(() => undefined)}
                      onApply={(ids) => {
                        onApplySlim?.(ids);
                        setApplied(true);
                      }}
                    />
                  ) : null}
                  {r.adherent ? (
                    <div className="small muted num">
                      {`When followed (${r.adherent.n_pairs} of ${r.adherent.of_pairs} pairs): ${r.adherent.diff >= 0 ? "+" : ""}${(r.adherent.diff * 100).toFixed(0)} pts (95% interval ${(r.adherent.ci_low * 100).toFixed(0)} to ${(r.adherent.ci_high * 100).toFixed(0)}) · selection-biased: leaves out trials that ignored the workflow`}
                    </div>
                  ) : null}
                </li>
              ))}
          </ul>
          {otherRuns.length ? (
            <details className="results__others" data-testid="other-runs">
              <summary className="small">Other Runs ({otherRuns.length})</summary>
              <ul className="list small">
                {otherRuns.map((r) => (
                  <li key={`${r.bench}-${r.id}`} className="row row--between" style={{ gap: 6 }}>
                    <span>
                      <b>{r.workflow}</b> <span className="muted">· {r.bench_name}</span>
                      {!isEvidence(r.validity) && r.status !== "running" ? (
                        <span className="pill pill--warning" title={r.validity?.reason ?? undefined}>
                          {r.validity?.badge}
                        </span>
                      ) : null}
                    </span>
                    <span className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                      {r.rig && r.status !== "running" ? (
                        <RigBadge score={r.rig.score} tone={r.rig.tone} provisional={r.rig.provisional} label={r.rig.label} band={r.rig.band} />
                      ) : null}
                      <span className="muted">
                        {r.status === "running" ? "running" : r.probe ? (r.probe_result?.text ?? statusText(r.status, r.status_text)) : verdictWord(r.rig, r.verdict).word}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          </section>
          <p className="small muted">Change: pass rate with the workflow minus without it, same agent and model. Hover for the 95% interval.</p>
        </>
      ) : null}
    </div>
  );
}
