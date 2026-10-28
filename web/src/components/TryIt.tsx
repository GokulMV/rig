import { Check, LogIn, Plus, Save, Square, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import { plural, usd } from "../lib/format";
import type { LabWorkflow, LocalModel, LocalRepoWords, TryJob, TryPrice, TryResult } from "../lib/types";
import { ErrorNotice } from "./Bits";
import { fill } from "./RunOn";

const MAX_INPUTS = 5; // engine skill try-it: max_inputs
const MAX_CHARS = 8000; // try-it: max_input_chars
const MAX_BUDGET = 50; // try-it: max_budget_usd

type Agent = { id: string; label: string; ready: boolean; budget_cap?: boolean } | null;

/** The try going on (or last finished) for each target: switching tabs doesn't lose it. A reload
 * does, on purpose: the engine keeps inputs and answers only for the job's lifetime. */
const lastJob: Record<string, string> = {};

function message(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

const STATUS: Record<TryResult["status"], { label: string; tone: string }> = {
  waiting: { label: "Waiting", tone: "pill--outline" },
  running: { label: "Running…", tone: "" },
  done: { label: "Done", tone: "pill--positive" },
  capped: { label: "Cut Short at the Cap", tone: "pill--warning" },
  errored: { label: "Errored", tone: "pill--negative" },
  broken: { label: "Test Copy Didn't Build", tone: "pill--negative" },
  skipped: { label: "Not Run: Budget", tone: "pill--outline" },
  stopped: { label: "Stopped", tone: "pill--outline" },
};

/** Prose as paragraphs, fenced code (```) in monospace. */
function Answer({ text }: { text: string }) {
  const parts = text.split(/```[^\n]*\n?/);
  return (
    <div className="tryit__answer">
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <pre key={i} className="code mono small">
            {p.replace(/\n$/, "")}
          </pre>
        ) : p.trim() ? (
          <p key={i} className="tryit__prose">
            {p.trim()}
          </p>
        ) : null,
      )}
    </div>
  );
}

function stepsLine(r: TryResult): string | null {
  const s = r.steps;
  if (!s) return r.status === "done" ? "Steps: couldn't tell (no session logs)" : null;
  if (s.kind === "skill") return s.opened ? "Opened the skill" : "Didn't open the skill";
  const line = `Ran ${s.ran} of ${plural(s.steps, "step")}`;
  return s.missing.length ? `${line} · didn't run ${s.missing.join(", ")}` : line;
}

function ResultCard({ r, input, onSave }: { r: TryResult; input: string; onSave: (() => Promise<string>) | null }) {
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const st = STATUS[r.status];
  const steps = stepsLine(r);
  const ran = !["waiting", "running", "skipped", "stopped"].includes(r.status);
  return (
    <article className="card tryit__result" aria-label={`Answer ${r.index + 1}`} data-testid="try-result">
      <div className="tryit__head">
        <strong>Input {r.index + 1}</strong>
        <span className={`pill ${st.tone}`}>{st.label}</span>
        {r.grade && r.grade.followed !== undefined ? (
          <span className={`pill ${r.grade.followed ? "pill--positive" : "pill--negative"}`} data-testid="try-grade">
            {r.grade.followed ? "Followed the Goal ✓" : "Didn't Follow the Goal ✗"}
          </span>
        ) : null}
      </div>
      <details className="small">
        <summary className="muted">What You Pasted</summary>
        <p className="tryit__prose muted">{input}</p>
      </details>
      {r.answer ? <Answer text={r.answer} /> : r.status === "running" ? <p className="small muted">The agent is working in its test copy…</p> : null}
      {r.detail ? <p className="small muted">{r.detail}</p> : null}
      {r.grade?.reason ? (
        <p className="small">
          <b>Why:</b> {r.grade.reason} <span className="muted num">(check {usd(r.grade.cost_usd)})</span>
        </p>
      ) : r.grade?.error ? (
        <p className="small muted">{r.grade.error}</p>
      ) : null}
      {ran ? (
        <p className="small muted num">
          {steps ? `${steps} · ` : ""}
          {usd(r.cost_usd)} · {Math.round(r.duration_s)}s
        </p>
      ) : null}
      {onSave && r.status !== "waiting" ? (
        saved ? (
          <p className="small" role="status">
            Saved as the draft task <b>{saved}</b>. Give it a check in step 4, Measure, before it can run.
          </p>
        ) : (
          <div>
            <button
              type="button"
              className="btn btn--small"
              onClick={async () => {
                setError(null);
                try {
                  setSaved(await onSave());
                } catch (e) {
                  setError(message(e));
                }
              }}
            >
              <Save size={13} aria-hidden="true" /> Save as a Task
            </button>
            {error ? <ErrorNotice error={error} /> : null}
          </div>
        )
      ) : null}
    </article>
  );
}

/** Shown in the input box until the goal's own example is in (try-it: placeholders.default). */
const FALLBACK_EXAMPLE = "Paste one real input here: the kind of request this would get.";

/** Where the price comes from, in plain words (budget.estimate's sources). */
function priceBasis(source: string): string {
  if (source.startsWith("a first guess")) return "A first guess: nothing like it has been measured yet.";
  if (source.startsWith("a local model")) return "A local model: nothing is billed.";
  return `From what earlier runs cost (${source.replace(/^from /, "")}).`;
}

/**
 * Try it (engine skill try-it): paste a few real inputs, see what comes back. One run per input
 * in the same isolated test copy as a "with" trial; the price is on screen before the Run click.
 */
export function TryIt({
  workflow,
  skill,
  agent,
  onSignIn,
  onSaved,
  below = false,
  first = false,
  goal = "",
  local = null,
  localWords = null,
  timeoutFactor = 1,
}: {
  /** A Lab workflow, as on the canvas. */
  workflow?: LabWorkflow | null;
  /** Or a skill on the repo's canvas. */
  skill?: { path: string; name: string } | null;
  agent: Agent;
  onSignIn?: () => void;
  /** A tried input was kept as a draft scenario (the repo's list can refresh). */
  onSaved?: () => void | Promise<void>;
  /** Set apart from the panel above it (under Measure, rather than a tab of its own). */
  below?: boolean;
  /** First on Measure, set apart from the bench settings below it. */
  first?: boolean;
  /** The goal in use (step 1, saved or not): the input box's example is built from it. */
  goal?: string;
  /** Measure's "Run on" a local model: Claude Code on it, free, no sign-in (useRunOn). */
  local?: LocalModel | null;
  /** The engine's words for a try on one (local-models: repo). */
  localWords?: LocalRepoWords | null;
  /** A local model's time limit: this many times the try's own. */
  timeoutFactor?: number;
}) {
  const key = workflow ? `wf:${workflow.id}` : skill ? `skill:${skill.path}` : "";
  const [inputs, setInputs] = useState<string[]>([""]);
  const [budget, setBudget] = useState(2);
  const [autoBudget, setAutoBudget] = useState(true);
  const [grade, setGrade] = useState(false);
  const [policy, setPolicy] = useState("");
  const [acceptNoCap, setAcceptNoCap] = useState(false);
  const [price, setPrice] = useState<TryPrice | null>(null);
  const [priceError, setPriceError] = useState<string | null>(null);
  const [job, setJob] = useState<TryJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const agentId = local ? "claude-code" : (agent?.id ?? "claude-code");
  const localId = local?.id ?? null;
  const onLocal = !!local && !!localWords; // the words come with the models: both, or neither
  const ready = local ? true : !!agent?.ready;
  const runner = local ? local.label : (agent?.label ?? "the agent");
  const target = workflow ? { workflow, local_model: localId } : skill ? { skill_path: skill.path, local_model: localId } : null;
  const targetKey = workflow ? JSON.stringify(workflow) : (skill?.path ?? "");
  const n = inputs.length;
  // The example comes from the goal at once (no model, no debounce), not with the price.
  const discipline = workflow?.discipline ?? null;
  const [example, setExample] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api.tryExample(goal.trim(), discipline).then(
      (e) => live && setExample(e.example),
      () => undefined,
    );
    return () => {
      live = false;
    };
  }, [goal, discipline]);
  const shownExample = example ?? price?.placeholder ?? FALLBACK_EXAMPLE;

  // Back to the try already going for this target, after a tab switch.
  useEffect(() => {
    const id = lastJob[key];
    setJob(null);
    if (!id) return;
    api.tryGet(id).then(
      (j) => {
        setJob(j);
        setInputs(j.inputs);
      },
      () => delete lastJob[key],
    );
  }, [key]);

  // Follow a running try.
  const running = job?.status === "running";
  useEffect(() => {
    if (!running || !job) return;
    const t = window.setInterval(() => {
      api.tryGet(job.id).then(setJob, (e) => setError(message(e)));
    }, 1000);
    return () => window.clearInterval(t);
  }, [running, job?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Price first: the budget check's own prediction, asked again as the try changes.
  useEffect(() => {
    if (!target) return;
    let live = true;
    const t = window.setTimeout(() => {
      api
        .tryPrice({ ...target, agent: agentId, n, budget_usd: Math.min(MAX_BUDGET, Math.max(0.01, budget)), grade })
        .then(
          (p) => {
            if (!live) return;
            setPrice(p);
            setPriceError(null);
            if (autoBudget) {
              const fit = Math.min(MAX_BUDGET, Math.max(0.5, Math.ceil(p.total_usd * 2) / 2));
              if (fit !== budget) setBudget(fit);
            }
          },
          (e) => live && setPriceError(message(e)),
        );
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [targetKey, agentId, localId, n, budget, grade, autoBudget]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!target) return <p className="small muted">Put a skill or workflow on the canvas to try it.</p>;

  const gradable = !!price?.gradable;
  // Free on a local model, unless each answer is checked: that is a model call of its own, so
  // such a try is priced and capped as usual.
  const freeTry = onLocal && !(gradable && grade);
  const filled = inputs.every((x) => x.trim().length > 0);
  const tooLong = inputs.some((x) => x.length > MAX_CHARS);
  const needsAccept = !!price && !price.hard_cap && !price.free;
  const canRun = ready && filled && !tooLong && budget > 0 && budget <= MAX_BUDGET && !!price && (!needsAccept || acceptNoCap) && !running;
  const short = price && price.inputs_in_budget < n;

  const start = async () => {
    setError(null);
    setStarting(true);
    try {
      const j = await api.tryStart({
        ...target,
        agent: agentId,
        inputs,
        budget_usd: budget,
        grade: gradable && grade,
        goal: gradable && grade ? policy : "",
        accept_no_cap: acceptNoCap,
      });
      lastJob[key] = j.id;
      setJob(j);
    } catch (e) {
      setError(message(e));
    } finally {
      setStarting(false);
    }
  };

  const shownInputs = job ? job.inputs : inputs;

  return (
    <div className={`section tryit${below ? " tryit--below" : ""}${first ? " tryit--first" : ""}`} data-testid="try-it">
      <div className="insp__section">
        <div className="insp__label">Try it</div>
        <p className="small">
          Paste a few real inputs and see what {workflow ? "the workflow" : skill?.name} does with each. <b>One try shows what it does; Measure tells
          you whether it helps.</b>
        </p>
      </div>

      {!job ? (
        <>
          {inputs.map((text, i) => (
            <div className="field" key={i}>
              <div className="tryit__inputhead">
                <label htmlFor={`try-input-${i}`}>Input {i + 1}</label>
                {n > 1 ? (
                  <button
                    type="button"
                    className="btn btn--small btn--quiet"
                    aria-label={`Remove input ${i + 1}`}
                    onClick={() => setInputs((xs) => xs.filter((_, k) => k !== i))}
                  >
                    <X size={13} aria-hidden="true" />
                  </button>
                ) : null}
              </div>
              <textarea
                id={`try-input-${i}`}
                className="textarea"
                rows={4}
                value={text}
                placeholder={shownExample}
                onChange={(e) => setInputs((xs) => xs.map((x, k) => (k === i ? e.target.value : x)))}
              />
              {!text && example ? (
                <button
                  type="button"
                  className="linkish small"
                  style={{ justifySelf: "start" }}
                  onClick={() => setInputs((xs) => xs.map((x, k) => (k === i ? example : x)))}
                >
                  Use This Example
                </button>
              ) : null}
              {text.length > MAX_CHARS ? (
                <p className="small" style={{ color: "var(--negative)" }}>
                  {text.length.toLocaleString("en-US")} characters: at most {MAX_CHARS.toLocaleString("en-US")}.
                </p>
              ) : null}
            </div>
          ))}
          {n < MAX_INPUTS ? (
            <div>
              <button type="button" className="btn btn--small" onClick={() => setInputs((xs) => [...xs, ""])}>
                <Plus size={13} aria-hidden="true" /> Add Another ({n} of {MAX_INPUTS})
              </button>
            </div>
          ) : null}

          {gradable ? (
            <div className="insp__section">
              <label className="check-row small">
                <input type="checkbox" checked={grade} onChange={(e) => setGrade(e.target.checked)} />
                <span>
                  <b>Check each answer against the goal</b> · one quick model call per answer, about {usd(price?.judge_per_input || 0.01)} each. Off by
                  default.
                </span>
              </label>
              {grade ? (
                <div className="field">
                  <label htmlFor="try-goal">The goal or policy to check against</label>
                  <textarea
                    id="try-goal"
                    className="textarea"
                    rows={3}
                    value={policy}
                    maxLength={2000}
                    placeholder="e.g. Refunds within 30 days of purchase; after that, decline kindly and offer a credit. Leave empty to use the workflow's own steps."
                    onChange={(e) => setPolicy(e.target.value)}
                  />
                </div>
              ) : null}
            </div>
          ) : null}

          {freeTry ? null : (
          <div className="field">
            <label htmlFor="try-budget">Stop this try at (USD)</label>
            <input
              id="try-budget"
              className="input num"
              type="number"
              min={0.5}
              max={MAX_BUDGET}
              step={0.5}
              value={budget}
              onChange={(e) => {
                setAutoBudget(false);
                setBudget(Number(e.target.value));
              }}
            />
          </div>
          )}

          <div className="runest" aria-live="polite" data-testid="try-price">
            {priceError ? (
              <p className="small muted">Couldn't price this try: {priceError}</p>
            ) : !price ? (
              <p className="small muted">Pricing the try…</p>
            ) : freeTry && price.free ? (
              <p className="small" data-testid="try-price-local">
                {fill(localWords!.try_price, { label: local!.label, factor: timeoutFactor })}
              </p>
            ) : (
              <>
                <p className="small num">
                  <b>
                    ≈ {usd(price.total_usd)} for {plural(n, "input")}
                  </b>{" "}
                  (at most {usd(budget)}
                  {price.hard_cap ? ", hard cap" : ", no hard cap"})
                </p>
                <p className="small muted" data-testid="try-price-why">
                  {workflow
                    ? `Runs your ${price.steps ? `${price.steps}-step ` : ""}workflow once per input`
                    : `Runs ${runner} once per input with ${skill?.name ?? "the skill"}`}
                  , about {usd(price.per_input)} each{price.judge_per_input && grade ? ` + about ${usd(price.judge_per_input)} to check it` : ""}, priced as a
                  run on {price.model_label ?? price.model}{workflow ? ", the model its working steps use" : ""}. You pay for the model reading the task and{" "}
                  {workflow ? "the steps' instructions" : "the skill"} and writing its answer. {priceBasis(price.source)}{" "}
                  {price.hard_cap
                    ? `${agent?.label ?? "The agent"} stops itself at what is left (it can overrun by its last model call).`
                    : ""}
                </p>
                {short ? (
                  <p className="notice notice--warning small">
                    {usd(budget)} pays for about {plural(price.inputs_in_budget, "input")} of {n}; the rest won't run.
                  </p>
                ) : null}
              </>
            )}
          </div>
          {needsAccept ? (
            <label className="check-row small">
              <input type="checkbox" checked={acceptNoCap} onChange={(e) => setAcceptNoCap(e.target.checked)} />
              <span>
                <b>I accept no hard cap</b> · {agent?.label ?? "This agent"} can't stop itself at a dollar amount, so an input can cost more than
                predicted. Only the check before each input holds the budget.
              </span>
            </label>
          ) : null}

          {error ? <ErrorNotice error={error} /> : null}
          {!ready ? (
            <>
              <p className="small muted">Trying needs {agent?.label ?? "an agent"} signed in; pricing it doesn't.</p>
              <button type="button" className="btn btn--primary btn--block" onClick={onSignIn} disabled={!onSignIn}>
                <LogIn size={14} aria-hidden="true" /> Sign In to Try
              </button>
            </>
          ) : (
            <button type="button" className="btn btn--primary btn--block" disabled={!canRun || starting} onClick={() => void start()}>
              {starting
                ? "Starting…"
                : freeTry
                  ? fill(localWords!.try_start, { inputs: plural(n, "Input") })
                  : `Run ${plural(n, "Input")}, up to ${usd(budget)}`}
            </button>
          )}
          {freeTry ? (
            <p className="small muted">{fill(workflow ? localWords!.try_note_workflow : localWords!.try_note, { label: local!.label })}</p>
          ) : (
            <p className="small muted">
              Each input runs once, in an isolated test copy{workflow ? "" : " of the repo"}, never in your own files. Billed to your sign-in; nothing runs
              until you click.
            </p>
          )}
        </>
      ) : null}

      {job ? (
        <div className="insp__section" aria-live="polite">
          <div className="tryit__head">
            <span className="small num" data-testid="try-progress">
              {running
                ? `Running input ${Math.max(1, job.results.filter((r) => r.status !== "waiting").length)} of ${job.results.length}`
                : job.status === "done"
                  ? "Done"
                  : job.status === "stopped_budget"
                    ? "Stopped: the budget"
                    : job.status === "stopped"
                      ? "Stopped"
                      : "Stopped with an error"}{" "}
              · {job.model.startsWith("local:") && !job.grade ? `free, on ${local?.id === job.model ? local.label : "a local model"}` : `${usd(job.spent_usd)} spent of ${usd(job.budget_usd)}`}
            </span>
            {running ? (
              <button
                type="button"
                className="btn btn--small"
                disabled={job.stopping}
                onClick={async () => {
                  try {
                    await api.tryStop(job.id);
                    setJob(await api.tryGet(job.id));
                  } catch (e) {
                    setError(message(e));
                  }
                }}
              >
                <Square size={12} aria-hidden="true" /> {job.stopping ? "Stopping after this input…" : "Stop"}
              </button>
            ) : (
              <button
                type="button"
                className="btn btn--small btn--quiet"
                onClick={async () => {
                  await api.tryForget(job.id).catch(() => undefined);
                  delete lastJob[key];
                  setJob(null);
                }}
              >
                <Check size={12} aria-hidden="true" /> Clear the Answers and Edit the Inputs
              </button>
            )}
          </div>
          {job.detail ? <ErrorNotice error={job.detail} /> : null}
          {running && error ? <ErrorNotice error={error} /> : null}
          {job.results.map((r) => (
            <ResultCard
              key={`${job.id}-${r.index}`}
              r={r}
              input={shownInputs[r.index] ?? ""}
              onSave={async () => {
                const got = await api.draftScenario({ instruction: shownInputs[r.index] ?? "" });
                await onSaved?.();
                return got.id;
              }}
            />
          ))}
          <p className="small muted">One sample per input, not a measurement. Inputs and answers are kept in memory only until you clear them or start another try.</p>
        </div>
      ) : null}
    </div>
  );
}
