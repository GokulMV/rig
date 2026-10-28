import { CheckCircle2, KeyRound, LogIn } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import { budgetPromise, plural, usd } from "../lib/format";
import type {
  AgentInfo,
  BeforeAfterCompare,
  LoginJob,
  ExperimentDetail,
  ExperimentRow,
  FullSize,
  Kind,
  MetricId,
  Project,
  ProveStatus,
  RunExtends,
  Scenario,
  Started,
  TreatmentItem,
  Workflow,
} from "../lib/types";
import { KINDS } from "../lib/types";
import { Findings, Generate, Sources } from "./Generate";
import { LocalModels } from "./LocalModels";
import { RunEstimate } from "./RunEstimate";
import { CostOnLocal, costOnLocal as costOn, fill, useRunOn } from "./RunOn";
import { pairsFor, RunSize } from "./RunSize";
import { TryIt } from "./TryIt";
import { LiveRun, Result, Trials } from "./Results";
import { RigBadge } from "./RigScore";
import { humanName, modelText, verdictWord } from "../lib/evidence";
import {
  type BeforeAfterChoice,
  BeforeAfterPicker,
  type Change,
  ChangePicker,
  configChange,
  measuresNothing,
  useMetricChoice,
} from "./RunChoice";
import { useRules } from "../lib/rules";
import { ErrorNotice, KindChip, kindLabel, ReviewPill } from "./Bits";

function message(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

/* ---------------- Agent and sign-in ---------------- */

/** Text with `code` spans, as the engine writes its hints. */
function Hint({ text }: { text: string }) {
  return (
    <>
      {text.split(/(`[^`]+`)/).map((part, i) =>
        part.startsWith("`") ? <code key={i}>{part.slice(1, -1)}</code> : <span key={i}>{part}</span>,
      )}
    </>
  );
}

function agentState(x: AgentInfo): { text: string; tone: "ok" | "partial" | "muted" } {
  if (x.ready) return { text: "Ready to run", tone: "ok" };
  if (x.host) return { text: "Signed in on this Mac", tone: "partial" };
  return { text: "Not signed in", tone: "muted" };
}

const PROVIDER: Record<string, string> = {
  "claude-code": "Sign In with Claude",
  codex: "Sign In with ChatGPT",
  "gemini-cli": "Sign In with Google",
  opencode: "Sign In with OpenCode",
};

function SignInBox({ a, onChanged }: { a: AgentInfo; onChanged: () => void }) {
  const [job, setJob] = useState<LoginJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const running = job?.state === "running";

  useEffect(() => {
    setJob(null);
    setError(null);
    api.loginStatus(a.id).then(setJob, () => undefined);
  }, [a.id]);

  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(async () => {
      try {
        const j = await api.loginStatus(a.id);
        setJob(j);
        if (j.state === "done") onChanged();
      } catch {
        /* keep polling */
      }
    }, 1500);
    return () => window.clearInterval(t);
  }, [running, a.id, onChanged]);

  if (!a.login) return null;
  const how = a.sign_in.find((o) => !o.typed || o.id === "subscription");

  return (
    <div className="signbox">
      {running ? (
        <>
          <strong>{job?.manual ? "Waiting for you to sign in" : "Approve in your browser"}</strong>
          {job?.manual ? (
            <p className="small">
              <Hint text={job.manual} />
            </p>
          ) : (
            <p className="small muted">
              {job?.url ? (
                <>
                  A sign-in page should have opened.{" "}
                  <a href={job.url} target="_blank" rel="noreferrer">
                    Open it again
                  </a>
                  .
                </>
              ) : (
                "Starting the sign-in…"
              )}
            </p>
          )}
          <button
            type="button"
            className="btn btn--small btn--quiet"
            onClick={async () => setJob(await api.cancelLogin(a.id))}
          >
            Cancel
          </button>
        </>
      ) : (
        <>
          <button
            type="button"
            className="btn btn--primary btn--block"
            onClick={async () => {
              setError(null);
              try {
                setJob(await api.login(a.id));
              } catch (e) {
                setError(message(e));
              }
            }}
          >
            <LogIn size={14} aria-hidden="true" /> {PROVIDER[a.id] ?? "Sign In"}
          </button>
          <p className="small muted">
            {how?.help ? <Hint text={how.help} /> : null} Uses your plan; nothing is billed per call here.
          </p>
          {job?.state === "error" || error ? <ErrorNotice error={job?.error ?? error ?? ""} /> : null}
        </>
      )}
    </div>
  );
}

export function AgentPanel({
  agents,
  agentId,
  onAgent,
  onChanged,
}: {
  agents: AgentInfo[] | null;
  agentId: string;
  onAgent: (id: string) => void;
  onChanged: () => void;
}) {
  const [value, setValue] = useState("");
  const [option, setOption] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const a = agents?.find((x) => x.id === agentId) ?? null;
  const typedReady = a?.sign_in.some((o) => o.typed && o.ready && o.how === "Entered in this session");
  useEffect(() => {
    setValue("");
    setOption(a?.sign_in.find((o) => o.typed)?.id ?? null);
  }, [agentId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="section">
      <div className="insp__label">Agent that runs the tasks</div>
      <div className="agent-grid" role="radiogroup" aria-label="Agent">
        {(agents ?? []).map((x) => {
          const st = agentState(x);
          return (
            <button
              key={x.id}
              type="button"
              role="radio"
              aria-checked={x.id === agentId}
              className="agent-card"
              onClick={() => onAgent(x.id)}
            >
              <strong>{x.label}</strong>
              <span className={`small agent-card__state agent-card__state--${st.tone}`}>{st.text}</span>
            </button>
          );
        })}
      </div>

      {a ? (
        <>
          {a.ready ? (
            <div className="signbox signbox--ok">
              <strong>
                <CheckCircle2 size={16} className="ok" aria-hidden="true" /> {a.label} is ready to run
              </strong>
              <span className="small muted">{a.sign_in.find((o) => o.ready)?.label}: {a.sign_in.find((o) => o.ready)?.how}</span>
              {typedReady ? (
                <button
                  type="button"
                  className="btn btn--small btn--quiet"
                  onClick={async () => {
                    await api.signOut(a.id);
                    onChanged();
                  }}
                >
                  Sign Out
                </button>
              ) : null}
            </div>
          ) : (
            <>
              {a.host ? (
                <p className="notice small">
                  Signed in on this Mac{a.host.email ? ` as ${a.host.email}` : ""}
                  {a.host.plan ? ` (${a.host.plan} plan)` : ""}. That's enough for Map with Archify. Runs happen in
                  Docker sandboxes, which can't use this Mac's keychain, so they need one more click:
                </p>
              ) : null}
              <SignInBox a={a} onChanged={onChanged} />
            </>
          )}

          {a.sign_in.some((o) => o.typed) && !a.ready ? (
            <details className="keybox">
              <summary>Use an API Key Instead</summary>
              <form
                className="section"
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (!option || !value.trim()) return;
                  setError(null);
                  try {
                    await api.signIn(a.id, option, value.trim());
                    setValue("");
                    onChanged();
                  } catch (err) {
                    setError(message(err));
                  }
                }}
              >
                <div className="field">
                  <label htmlFor="cred-kind">Paste a key or token</label>
                  <select id="cred-kind" className="select" value={option ?? ""} onChange={(e) => setOption(e.target.value)}>
                    {a.sign_in
                      .filter((o) => o.typed)
                      .map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.label}
                        </option>
                      ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="cred-value" className="visually-hidden">
                    Value
                  </label>
                  <input
                    id="cred-value"
                    className="input"
                    type="password"
                    autoComplete="off"
                    placeholder="Pasted here, kept in memory only"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                  />
                </div>
                <p className="small muted">
                  <KeyRound size={12} aria-hidden="true" /> Kept in the local server's memory only: never written to disk,
                  never shown again, gone when the server stops.
                </p>
                {error ? <ErrorNotice error={error} /> : null}
                <button type="submit" className="btn btn--primary" disabled={!value.trim()}>
                  Use This Key
                </button>
              </form>
            </details>
          ) : null}
        </>
      ) : null}
      <details className="keybox">
        <summary>Local Models</summary>
        <LocalModels />
      </details>
    </div>
  );
}

/* ---------------- Scenarios ---------------- */

function slug(text: string): string {
  return (
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60) || "scenario"
  );
}

/** Runs a generated check on the untouched repo with no agent ($0); it should fail. */
function ProveCheck({ id }: { id: string }) {
  const [st, setSt] = useState<ProveStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const running = st?.status === "running";

  useEffect(() => {
    let live = true;
    const look = () =>
      api
        .proveStatus(id)
        .then((r) => live && setSt(r))
        .catch((e) => live && setError(message(e)));
    if (st === null) void look();
    if (!running) return () => void (live = false);
    const t = setInterval(() => void look(), 2000);
    return () => {
      live = false;
      clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, running, st === null]);

  const badge = (() => {
    if (!st || st.status === "idle" || st.status === "running") return null;
    if (st.status === "error") return <span className="pill pill--warning">Couldn’t run: {st.detail}</span>;
    return st.proven ? (
      <span className="pill pill--positive">Fails Untouched (Proven)</span>
    ) : (
      <span className="pill pill--warning">Broken: Passes without Any Work</span>
    );
  })();

  return (
    <>
      <button
        type="button"
        className="btn btn--small"
        disabled={running}
        onClick={async () => {
          setError(null);
          try {
            await api.prove(id);
            setSt({ status: "running", proven: null, detail: "" });
          } catch (e) {
            setError(message(e));
          }
        }}
      >
        Prove Check
      </button>
      {running ? (
        <span className="small muted" role="status">
          Building the sandbox and running the check with no agent…
        </span>
      ) : null}
      {badge}
      {error ? <ErrorNotice error={error} /> : null}
    </>
  );
}

/** One count of the tasks wherever they are counted (evidence-validity): approved with prose for a
 * check is approved but never runnable, and says so. */
export function taskCount(scenarios: Scenario[]): string {
  const approved = scenarios.filter((s) => s.runnable);
  const runnable = approved.filter((s) => !s.check_problem).length;
  const prose = approved.length - runnable;
  if (!prose) return `Tasks · ${approved.length} of ${scenarios.length} approved`;
  return `Tasks · ${approved.length} approved, ${runnable} runnable — ${prose === 1 ? (approved.length === 1 ? "its check isn't" : "1 check isn't") : `${prose} checks aren't`} a command`;
}

/** A check that never runs (prose), rewritten as a command in place. */
function FixCheck({ s, example, onChanged }: { s: Scenario; example: string; onChanged: () => Promise<void> }) {
  const [check, setCheck] = useState("");
  const [error, setError] = useState<string | null>(null);
  const id = `fix-check-${s.id}`;
  return (
    <form
      className="fixcheck"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          await api.setCheck(s.id, check);
          await onChanged();
        } catch (err) {
          setError(message(err));
        }
      }}
    >
      <label htmlFor={id} className="small">
        <b>Write it as a command</b>
      </label>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input id={id} className="input mono" required placeholder={example} value={check} onChange={(e) => setCheck(e.target.value)} />
        <button type="submit" className="btn btn--small btn--primary" disabled={!check.trim()}>
          Save Check
        </button>
      </div>
      {error ? <ErrorNotice error={error} /> : null}
    </form>
  );
}

/** What a runnable check is, with this repo's own example, where a check is written. */
function CheckHelp({ example }: { example: string }) {
  return (
    <p className="small muted hint" data-testid="check-help">
      A shell command Rig runs in the repo after the agent finishes: exit code 0 is a pass, anything else a fail. For example{" "}
      <code>{example}</code>. A sentence such as “the agent should use fewer tokens” never runs, so the task is left out of every run.
    </p>
  );
}

export function ScenariosPanel({
  project,
  scenarios,
  workflow,
  onChanged,
  goal,
  onEditGoal,
  preset,
  onPresetUsed,
}: {
  project: Project;
  scenarios: Scenario[];
  workflow: Workflow | null;
  onChanged: () => Promise<void>;
  /** The goal in use (step 1, saved or not): tasks are written from it. */
  goal?: string;
  /** Opens Describe, where the goal is edited. */
  onEditGoal?: () => void;
  /** Opens Add task for this step (from the "Add a task for <step>" suggestion); a new key reopens it. */
  preset?: { step: string; key: number } | null;
  /** The preset was opened: it isn't opened again on the next visit. */
  onPresetUsed?: () => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const draftGoal = goal !== undefined && goal.trim() !== (project.use_case ?? "").trim();
  // A cleared box sends nothing: the server writes from the saved goal.
  const draft = draftGoal && goal.trim() ? goal : undefined;
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ title: "", kind: "typical" as Kind, step: "", instruction: "", check: "" });
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  // An example in this repo's own work (generate-scenarios: examples): its language and test command.
  const ex = project.example ?? {
    title: "Fix the failing date parsing",
    instruction: 'The date parser rejects "2024-02-29". Make it accept leap days without breaking the other formats.',
    check: "make test",
  };
  // "Add a task for <step>", accepted on Build: the form opens with that step chosen.
  useEffect(() => {
    if (!preset) return;
    setAdding(true);
    setForm((f) => ({ ...f, step: workflow?.steps.some((st) => st.name === preset.step) ? preset.step : f.step }));
    requestAnimationFrame(() => document.getElementById("sc-title")?.focus());
    onPresetUsed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset?.key]);
  const stale = scenarios.filter((s) => s.goal_changed).length;
  const regenerate = () => {
    setGenerating(true);
    requestAnimationFrame(() => document.getElementById("generate-tasks")?.scrollIntoView({ block: "start", behavior: "smooth" }));
  };

  return (
    <div className="section">
      <div className="row row--between">
        <div className="insp__label" data-testid="task-count">
          {taskCount(scenarios)}
        </div>
        <button type="button" className="btn btn--small" onClick={() => setAdding(!adding)} aria-expanded={adding}>
          {adding ? "Close" : "+ Add Task"}
        </button>
      </div>
      {adding ? (
        <form
          className="card enter"
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            try {
              await api.addScenario({
                id: slug(form.title),
                title: form.title,
                kind: form.kind,
                instruction: form.instruction,
                check: form.check,
                step: form.step || undefined,
              });
              setForm({ title: "", kind: "typical", step: "", instruction: "", check: "" });
              setAdding(false);
              await onChanged();
            } catch (err) {
              setError(message(err));
            }
          }}
        >
          <div className="field">
            <label htmlFor="sc-title">What should the agent do?</label>
            <input
              id="sc-title"
              className="input"
              required
              placeholder={ex.title}
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </div>
          <div className="row" style={{ alignItems: "end" }}>
            <div className="field" style={{ flex: 1 }}>
              <label htmlFor="sc-kind">Kind</label>
              <select id="sc-kind" className="select" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as Kind })}>
                {KINDS.filter((k) => k !== "failure" && k !== "overload").map((k) => (
                  <option key={k} value={k}>
                    {kindLabel(k)}
                  </option>
                ))}
              </select>
            </div>
            {workflow ? (
              <div className="field" style={{ flex: 1 }}>
                <label htmlFor="sc-step">Step</label>
                <select
                  id="sc-step"
                  className="select"
                  aria-describedby="sc-step-hint"
                  value={form.step}
                  onChange={(e) => setForm({ ...form, step: e.target.value })}
                >
                  <option value="">Any</option>
                  {workflow.steps.map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
          </div>
          {workflow ? (
            <p id="sc-step-hint" className="small muted hint">
              The step of {workflow.name} this task tests. A skill linked to that step on Build is measured on it; “Any” tests the whole flow.
            </p>
          ) : null}
          <div className="field">
            <label htmlFor="sc-instr">Instruction the agent gets</label>
            <textarea
              id="sc-instr"
              className="textarea"
              required
              placeholder={ex.instruction}
              value={form.instruction}
              onChange={(e) => setForm({ ...form, instruction: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="sc-check">Check: a shell command</label>
            <CheckHelp example={ex.check} />
            <input
              id="sc-check"
              className="input mono"
              required
              placeholder={ex.check}
              value={form.check}
              onChange={(e) => setForm({ ...form, check: e.target.value })}
            />
          </div>
          {error ? <ErrorNotice error={error} /> : null}
          <button type="submit" className="btn btn--primary">
            Add Task
          </button>
        </form>
      ) : null}
      {error && !adding ? <ErrorNotice error={error} /> : null}
      {stale && onEditGoal ? (
        <div className="notice notice--warning small stale-tasks" role="note" data-testid="stale-tasks">
          <span style={{ flex: 1 }}>
            {stale === scenarios.length ? "Every task was" : `${plural(stale, "task")} ${stale === 1 ? "was" : "were"}`} written for a different goal than
            the one in Describe, so {stale === 1 ? "it may" : "they may"} not measure what you want now.
          </span>
          <button type="button" className="btn btn--small btn--primary" onClick={regenerate}>
            Regenerate Tasks for This Goal
          </button>
        </div>
      ) : null}
      <ul className="list">
        {scenarios.map((s) => (
          <li key={s.id}>
            <button type="button" className="item" aria-expanded={open === s.id} onClick={() => setOpen(open === s.id ? null : s.id)}>
              <span className="item__top">
                <span className="item__name">{s.title || s.id}</span>
                <ReviewPill s={s} />
              </span>
              <span className="item__top">
                <span className="mono small item__id">{s.id}</span>
                <KindChip kind={s.kind} />
              </span>
            </button>
            {open === s.id ? (
              <div className="section enter" style={{ padding: "0 8px 12px" }}>
                <p style={{ whiteSpace: "pre-wrap" }}>{s.instruction}</p>
                {s.check ? (
                  <pre className="code" tabIndex={0}>
                    {s.check}
                  </pre>
                ) : null}
                {s.check_files.map((f) => (
                  <pre key={f.path} className="code" tabIndex={0} aria-label={f.path}>
                    {`# ${f.path}\n${f.content}`}
                  </pre>
                ))}
                {s.check_problem ? (
                  <div className="notice notice--warning small" role="note">
                    <p>
                      <Hint text={s.check_problem} /> Runs leave this task out until its check is a command.
                    </p>
                    <FixCheck s={s} example={ex.check} onChanged={onChanged} />
                  </div>
                ) : null}
                {s.goal_changed ? (
                  <div className="notice notice--warning small row" role="note">
                    <span style={{ flex: 1 }}>Written for a different goal: it was generated for an earlier one. Regenerate the tasks for the goal in Describe, or check this one still fits.</span>
                    <button type="button" className="btn btn--small btn--primary" onClick={regenerate}>
                      Regenerate Tasks for This Goal
                    </button>
                  </div>
                ) : null}
                {!s.runnable && s.check ? (
                  <div className="row" style={{ flexWrap: "wrap" }}>
                    <ProveCheck id={s.id} />
                    <button
                      type="button"
                      className="btn btn--small btn--primary"
                      disabled={!!s.check_problem}
                      title={s.check_problem ?? undefined}
                      onClick={async () => {
                        setError(null);
                        try {
                          await api.approve(s.id);
                          await onChanged();
                        } catch (e) {
                          setError(message(e));
                        }
                      }}
                    >
                      Approve Check
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
      <details id="generate-tasks" className="pal-group" open={generating || scenarios.length === 0} onToggle={(e) => setGenerating((e.target as HTMLDetailsElement).open)}>
        <summary>
          <span className="pal-group__title">Generate tasks from the repo and docs</span>
        </summary>
        <div className="gen">
          {draftGoal ? (
            <p className="small muted" data-testid="generate-goal">
              {draft
                ? "Tasks are written from your unsaved goal."
                : `Your goal box is empty, so tasks are written from ${project.name}'s saved goal.`}
            </p>
          ) : null}
          <Findings project={project} onChanged={onChanged} />
          <Sources project={project} onChanged={onChanged} goal={goal} onEditGoal={onEditGoal} />
          <Generate project={project} scenarios={scenarios} onChanged={onChanged} draft={draft} />
        </div>
      </details>
    </div>
  );
}

/* ---------------- Runs ---------------- */

export interface Candidate {
  path: string;
  name: string;
}

export function RunPanel({
  candidates,
  initial,
  scenarios,
  agent,
  experiments,
  onChanged,
  repoId,
  onSignIn,
  goal,
  configs = [],
  metricHint,
  empty,
  codeFor,
  onCodeForUsed,
  onMode,
}: {
  candidates: Candidate[];
  /** The repo's hooks, MCP servers and instructions (/api/treatments configs): measurable too. */
  configs?: TreatmentItem[];
  /** The goal's metric hint (project goal_metric): the metric picked until you pick one. */
  metricHint?: MetricId | null;
  initial: string | null;
  scenarios: Scenario[];
  agent: AgentInfo | null;
  experiments: ExperimentRow[];
  onChanged: () => Promise<void>;
  /** The repo the run is priced on (its earlier runs are the evidence). */
  repoId?: string | null;
  /** Opens the agent sign-in: a run can be priced before, but not started. */
  onSignIn?: () => void;
  /** The goal in use (step 1, saved or not): Try it's example input. */
  goal?: string;
  /** What shows while there is nothing to run (the page says why, and where to add something). */
  empty?: ReactNode;
  /** "Measure it" on Build's suggestion that changes the code: open on before and after, for it. */
  codeFor?: { title: string; key: number } | null;
  /** codeFor was applied (the page can forget it). */
  onCodeForUsed?: () => void;
  /** The mode picked (an agent change, or a code change): the page's words follow it. */
  onMode?: (mode: "agent" | "code") => void;
}) {
  const changes: Change[] = [...candidates.map((c) => ({ ...c, kind: "skill" as const })), ...configs.map(configChange)];
  const [path, setPath] = useState(initial ?? changes[0]?.path ?? "");
  const { metric, onPlan, picker, confirm, keepGoing } = useMetricChoice(metricHint);
  // "Keep going until it's decided", as the Lab's: the estimate says what the run may grow to.
  const [auto, setAuto] = useState(true);
  const [grows, setGrows] = useState<RunExtends | null>(null);
  const [size, setSize] = useState<"pilot" | "full">("pilot");
  const [full, setFull] = useState<FullSize | null>(null);
  const [budget, setBudget] = useState(5);
  const [nudge, setNudge] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [running, setRunning] = useState<Started | null>(null);
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  // What is measured: an agent change with and without, or a code change before and after.
  const baWords = useRules("measurability")?.before_after ?? null;
  const [mode, setMode] = useState<"agent" | "code">("agent");
  const [ba, setBa] = useState<BeforeAfterChoice | null>(null);
  const [baCmp, setBaCmp] = useState<BeforeAfterCompare | null>(null);
  const code = mode === "code";
  useEffect(() => onMode?.(mode), [mode, onMode]);
  // Run on: the signed-in agent, or Claude Code on a local model (free: no sign-in, no budget).
  const { local, words: localWords, select: runOnSelect, manage: runOnManage, factor } = useRunOn(agent);
  const runAgent = local ? "claude-code" : (agent?.id ?? "claude-code");
  const runLabel = local ? local.label : (agent?.label ?? "the agent");
  const canRun = local ? true : !!agent?.ready;
  const costOnLocal = costOn(local, metric); // nothing to compare: refused by the engine too
  // A small local model never opens a skill it is only offered: on it starts ticked, off unticked.
  const localId = local?.id;
  useEffect(() => setNudge(!!localId), [localId]);
  // The suggestion a code change is measured for, named until another mode is picked.
  const [forTitle, setForTitle] = useState<string | null>(null);
  useEffect(() => {
    if (!initial) return;
    setPath(initial);
    setMode("agent"); // "Confirm with a run" on Build picks an agent change
    setForTitle(null);
  }, [initial]);
  useEffect(() => {
    if (!codeFor) return;
    setMode("code"); // "Measure it" on a suggestion that changes the code
    setForTitle(codeFor.title);
    onCodeForUsed?.();
  }, [codeFor?.key]);
  // The skills arrive after the panel opens: until one is picked, the first is the one shown (and priced).
  const first = changes[0]?.path;
  const known = changes.some((c) => c.path === path);
  useEffect(() => {
    if (!known && first) setPath(first);
  }, [known, first]);

  // A check that isn't a command fails both arms every time: never part of a run (evidence-validity).
  const ready = scenarios.filter((s) => s.runnable && !s.check_problem);
  const leftOut = scenarios.filter((s) => s.runnable && s.check_problem);
  // A full run grows with the budget up to the sizing: the engine plans it (full).
  const n = size === "full" && full ? full.planned_pairs : pairsFor(size, ready.length);
  const repeats = ready.length ? n / ready.length : 0;
  const trials = 2 * n;
  const chosen = code ? undefined : changes.find((c) => c.path === path);
  const codeReady = code && !!ba && !!baCmp && !baCmp.same;
  const runName = code ? (codeReady ? baCmp.name : undefined) : chosen?.name;

  return (
    <div className="section">
      <div className="insp__label">Confirm with a run</div>
      {baWords && !running && !confirming ? (
        <div className="segmented" role="radiogroup" aria-label="What to measure" data-testid="measure-mode" style={{ justifySelf: "start" }}>
          <button
            type="button"
            role="radio"
            aria-checked={!code}
            onClick={() => {
              setMode("agent");
              setForTitle(null);
            }}
          >
            {baWords.mode_agent}
          </button>
          <button type="button" role="radio" aria-checked={code} onClick={() => setMode("code")}>
            {baWords.mode}
          </button>
        </div>
      ) : null}
      {!code && changes.length === 0 ? (
        (empty ?? <p className="small muted">Add a skill to the canvas first, or a CLAUDE.md, hook or MCP server to the repo; then measure it here.</p>)
      ) : running ? (
        <LiveRun
          started={running}
          onDone={async (ok) => {
            if (ok) setDetail(await api.experiment(running.id));
            setRunning(null);
            await onChanged();
          }}
        />
      ) : confirming && runName ? (
        <div className="card enter">
          <strong>Run {runName}?</strong>
          <p className="small num">
            {plural(trials, "trial")}: {plural(ready.length, "task")} × {plural(repeats, "repeat")} × {code ? "before and after" : "with and without"}, on{" "}
            {runLabel}.
          </p>
          {auto && grows ? (
            <p className="small num" data-testid="confirm-extends">
              {grows.line}
            </p>
          ) : null}
          {confirm}
          {local && localWords ? (
            <p className="small" data-testid="confirm-free">
              {fill(localWords.confirm, { label: local.label })}
            </p>
          ) : (
            <>
              <p className="small">{budgetPromise(budget, agent?.label ?? "The agent", !!agent?.budget_cap)}</p>
              <p className="small muted">Real agent runs in Docker sandboxes, billed to your sign-in.</p>
            </>
          )}
          {error ? <ErrorNotice error={error} /> : null}
          <div className="row">
            <button
              type="button"
              className="btn btn--primary"
              onClick={async () => {
                setError(null);
                try {
                  const s = await api.start({
                    ...(code && ba ? { before_after: ba } : { treatment_path: chosen?.path }),
                    n,
                    size,
                    budget: local && budget <= 0 ? 1 : budget, // a local run costs nothing either way
                    model: agent?.default_model?.split("/").pop() ?? "claude-sonnet-5-5",
                    agent: runAgent,
                    scenario_ids: ready.map((x) => x.id),
                    // Unticked: the default (workflows are handed over, skills found); on a local model, said outright.
                    nudge_prompt: chosen?.kind === "skill" ? (nudge ? true : local ? false : null) : null,
                    metric,
                    local_model: local?.id ?? null,
                    auto,
                  });
                  setConfirming(false);
                  setDetail(null);
                  setRunning(s);
                } catch (e) {
                  setError(message(e));
                }
              }}
            >
              {local && localWords ? localWords.start : `Start, up to ${usd(budget)}`}
            </button>
            <button type="button" className="btn btn--quiet" onClick={() => setConfirming(false)}>
              Back
            </button>
          </div>
        </div>
      ) : (
        <>
        <form
          className="section"
          onSubmit={(e) => {
            e.preventDefault();
            setConfirming(true);
          }}
        >
          {code && baWords && forTitle ? (
            <p className="small" data-testid="ba-for">
              {baWords.for.replace("{title}", forTitle)}
            </p>
          ) : null}
          {code && baWords ? (
            <BeforeAfterPicker words={baWords} value={ba} onChange={setBa} onCompare={setBaCmp} />
          ) : (
            <ChangePicker
              changes={changes}
              value={path}
              onChange={setPath}
              onSaved={async (saved) => {
                await onChanged();
                setPath(saved);
              }}
            />
          )}
          {runOnSelect}
          {picker}
          <CostOnLocal show={costOnLocal} words={localWords} />
          <RunSize size={size} onSize={setSize} full={full} />
          {local ? null : (
          <div className="field">
            <label htmlFor="run-budget">Stop at (USD)</label>
            <input
              id="run-budget"
              className="input num"
              type="number"
              min={0.5}
              step={0.5}
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
            />
          </div>
          )}
          <RunEstimate
            budget={budget}
            onSetBudget={setBudget}
            canExtend={auto}
            onFull={setFull}
            onMetricPlan={onPlan}
            onExtends={setGrows}
            request={
              (chosen || codeReady) && ready.length
                ? {
                    pairs: pairsFor(size, ready.length),
                    agent: runAgent,
                    model: agent?.default_model?.split("/").pop() ?? "claude-sonnet-5-5",
                    repo: repoId ?? null,
                    treatment_path: chosen?.path ?? null,
                    local: !!local,
                    size,
                    tasks: ready.length,
                    metric,
                    auto,
                  }
                : null
            }
          />
          <label className="check-row small">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
            <span>
              <b>Keep going until it's decided</b> <span data-testid="keep-going">· {keepGoing}</span>
            </span>
          </label>
          {chosen?.kind !== "skill" ? null : (
          <label className="check-row small">
            <input type="checkbox" checked={nudge} onChange={(e) => setNudge(e.target.checked)} />
            <span>
              <b>Tell the agent to open the skill in the prompt</b>
              <span data-testid="nudge-state">
                {nudge
                  ? " · on: the prompt tells the agent to open it"
                  : " · off: a skill has to be found, as in real use (a workflow is always handed over)"}
              </span>
              {local && localWords ? (
                <span className="muted" style={{ display: "block" }} data-testid="nudge-local">
                  {localWords.nudge}
                </span>
              ) : null}
            </span>
          </label>
          )}
          <p className="small muted num">
            {ready.length
              ? `${plural(ready.length, "runnable task")} · ${plural(trials, "trial")}`
              : leftOut.length
                ? `No runnable tasks: fix the check of ${leftOut.map((s) => s.title || s.id).join(", ")}.`
                : "No runnable tasks yet: add or approve one in Tasks to measure on."}
          </p>
          {leftOut.length ? (
            <p className="notice notice--warning small" data-testid="left-out">
              Left out: {leftOut.map((s) => s.title || s.id).join(", ")}. {leftOut.length === 1 ? "Its check isn't" : "Their checks aren't"} a command, so every trial would fail both ways.
            </p>
          ) : null}
          {!canRun ? (
            <>
              <p className="small muted">Running needs {agent?.label ?? "an agent"} signed in; pricing it doesn't.</p>
              <button type="button" className="btn btn--primary btn--block" onClick={onSignIn} disabled={!onSignIn}>
                <LogIn size={14} aria-hidden="true" /> Sign In to Run
              </button>
            </>
          ) : (
            <button
              type="submit"
              className="btn btn--primary btn--block"
              disabled={!runName || !ready.length || (!local && budget <= 0) || costOnLocal || measuresNothing(chosen)}
            >
              Review the Run
            </button>
          )}
        </form>
        {runOnManage}
        </>
      )}
      {detail ? (
        <>
          <Result detail={detail} />
          <Trials detail={detail} />
        </>
      ) : null}
      {chosen?.kind === "skill" && !running && !confirming ? (
        // Try it runs where the run would: on the "Run on" choice above.
        <TryIt skill={chosen} agent={agent} onSignIn={onSignIn} onSaved={onChanged} goal={goal} below local={local} localWords={localWords} timeoutFactor={factor} />
      ) : null}
      {experiments.length ? (
        <>
          <div className="insp__label">Earlier runs</div>
          <ul className="list">
            {experiments.slice(0, 8).map((e) => (
              <li key={e.id}>
                <button type="button" className="item" onClick={async () => setDetail(await api.experiment(e.id))}>
                  <span className="item__top">
                    <span className="item__name">
                      #{e.id} {humanName(e.treatment_name)}
                    </span>
                    <span className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                      {e.rig ? <RigBadge score={e.rig.score} tone={e.rig.tone} provisional={e.rig.provisional} label={e.rig.label} band={e.rig.band} /> : null}
                      {e.verdict && e.rig?.band !== "not_evidence"
                        ? (() => {
                            const v = verdictWord(e.rig, e.verdict);
                            return <span className={`pill ${v.tone === "helps" ? "pill--positive" : v.tone === "hurts" ? "pill--negative" : ""}`}>{v.word}</span>;
                          })()
                        : null}
                    </span>
                  </span>
                  <span className="small muted">
                    {modelText(e)} · {e.local_model ? "free" : `${usd(e.spent_usd)} spent`}
                    {e.metric && e.metric !== "pass_rate" ? ` · scored on ${e.metric}` : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
