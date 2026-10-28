import { Columns3, Dices, FilePlus2, Pin, Plus, RotateCcw, Save, Trash2, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "../lib/api";
import { consumeDragClick, startSkillDrag } from "../lib/dragSkill";
import { changeNote, expected, expectedText, provenance, seenOf, type Seen } from "../lib/provenance";
import type { Contribution, Lab as LabData, LabMatrix, LabSkill, LabStep, LabWorkflow, LocalModel, LocalRepoWords, Proven, StepKind, StepTemplate } from "../lib/types";
import { usePanes } from "../lib/usePanes";
import { Canvas, type CanvasEdge, type CanvasNode } from "./Canvas";
import { BenchPanel } from "./BenchPanel";
import { TryIt } from "./TryIt";
import { BuildSpecButton } from "./BuildSpec";
import { Matrix } from "./Matrix";
import { ofWorkflow } from "../lib/evidence";
import { stages } from "../lib/compareDiff";
import { COMPARE_MAX, pin, pinState, useCompareSet } from "../lib/compareSet";
import { PaneResizer } from "./PaneResizer";
import { ProvenRig } from "./RigScore";
import { SkillPicker } from "./SkillPicker";
import { Term } from "./Term";
import { ShortcutsSheet, typing } from "./Shortcuts";

export const KIND: Record<StepKind, { label: string; color: string; what: string }> = {
  think: { label: "Think", color: "#6d28d9", what: "plans, decides or reviews" },
  do: { label: "Do", color: "#2f6bbf", what: "produces the work" },
  check: { label: "Check", color: "#15803d", what: "runs a check" },
  judge: { label: "Judge", color: "#b45309", what: "judges the quality" },
};
const W = 196;
const SKILLS_POLL_MS = 2000;
const SKILLS_POLLS = 30;
// The skill matcher's models download once (about a gigabyte): look again until they're ready or failed.
const MATCHER_POLL_MS = 5000;
const MATCHER_POLLS = 400;
const MATCHER_BUSY = new Set(["downloading", "loading", "warming"]);
const H = 128;
const GAP = 64;

/** Where a measured run executes: the agent on its sign-in, or a local model (`model`, with the
 * engine's words for a run on one and its time limit factor). */
type Runner = {
  agent: string;
  local: boolean;
  label: string;
  model: LocalModel | null;
  words: LocalRepoWords | null;
  factor: number;
};

/** "N skills (X from GitHub, Y yours)", or simpler when they all come from one side. */
function skillCount(d: LabData) {
  const n = d.skills.length;
  const gh = d.skills.filter((s) => s.source === "github").length;
  const words = `${n} skill${n === 1 ? "" : "s"}`;
  if (!n) return "no skills yet";
  if (!gh) return `your ${words}`;
  return gh < n ? `${words} (${gh} from GitHub, ${n - gh} yours)` : `${words} from GitHub`;
}

/** Where a step's skill comes from, with a link to read a GitHub one before keeping it. */
function SkillSource({ skill }: { skill: LabSkill }) {
  if (skill.source !== "github" || !skill.repo) return <span className="small muted">yours</span>;
  return (
    <span className="small muted">
      GitHub ·{" "}
      {skill.url ? (
        <a href={skill.url} target="_blank" rel="noreferrer" aria-label={`View ${skill.name} on GitHub (${skill.repo})`}>
          {skill.repo}
        </a>
      ) : (
        skill.repo
      )}
    </span>
  );
}

/** Points expected: from similar valid runs where there are enough, else the guess (lib/provenance). */
function est(wf: LabWorkflow) {
  return expected(wf);
}

function estNote(wf: LabWorkflow) {
  return provenance(wf).text;
}

function sign(n: number) {
  return `${n > 0 ? "+" : ""}${n}`;
}

/** A measured result, in words: replaces the guess once the workflow has been run. */
function measuredLabel(p: Proven) {
  const n = Math.round(p.diff_pts);
  if (p.verdict === "helps") return `${sign(n)} pts`;
  if (p.verdict === "hurts") return `${sign(n)} pts, hurts`;
  return "no effect";
}

/** Is there a path a → … → b along the forward connections? */
function reaches(wf: LabWorkflow, a: string, b: string): boolean {
  const seen = new Set<string>();
  const todo = [a];
  while (todo.length) {
    const x = todo.pop()!;
    if (x === b) return true;
    if (seen.has(x)) continue;
    seen.add(x);
    for (const [f, t] of wf.edges ?? []) if (f === x) todo.push(t);
  }
  return false;
}

function newId(prefix: string, taken: string[]): string {
  let n = 1;
  while (taken.includes(`${prefix}-${n}`)) n++;
  return `${prefix}-${n}`;
}

function Row({
  wf,
  selected,
  onPick,
  onRemove,
  removeLabel,
}: {
  wf: LabWorkflow;
  selected: boolean;
  onPick: () => void;
  /** Shown as an × on the row: things you added can be taken away again. */
  onRemove?: () => void;
  removeLabel?: string;
}) {
  return (
    <li className={`pal-item${selected ? " is-selected" : ""}`}>
      {onRemove ? (
        <button type="button" className="iconbtn pal-item__remove" aria-label={removeLabel ?? `Remove ${wf.name}`} title={removeLabel} onClick={onRemove}>
          <X size={14} aria-hidden="true" />
        </button>
      ) : null}
      <button
        type="button"
        className="pal-item__main"
        aria-pressed={selected}
        onClick={onPick}
        style={{ paddingRight: onRemove ? 36 : 10 }}
      >
        <span className="pal-item__name">{wf.name}</span>
        <span className="pal-item__sub">
          {/* Parallel steps shown together: "A → B + C → D". */}
          {stages(wf)
            .map((st) => st.map((id) => wf.steps.find((s) => s.id === id)?.name ?? id).join(" + "))
            .join(" → ")}
        </span>
        <span className="pal-item__meta">
          <ProvenRig proven={wf.proven} />
          {wf.proven ? (
            <span
              className="num"
              data-testid="proven-badge"
              title={provenance(wf).title}
            >
              {measuredLabel(wf.proven)} · {estNote(wf)}
            </span>
          ) : (
            <span className="num" data-testid="estimate-badge" title={provenance(wf).title}>
              {expectedText(wf)} pts · {estNote(wf)}
            </span>
          )}
          <span className="num">{wf.cost}× cost</span>
          <span>{wf.steps.length} steps</span>
        </span>
      </button>
    </li>
  );
}

function Group({ title, count, open, children }: { title: string; count: number; open?: boolean; children: React.ReactNode }) {
  return (
    <details className="pal-group" open={open}>
      <summary>
        <span className="pal-group__title">{title}</span>
        <span className="pal-group__count num">{count}</span>
      </summary>
      <ul className="pal-list">{children}</ul>
    </details>
  );
}

const DRAFT = "pg.lab.wf";
const SEEN = "pg.lab.seen"; // each workflow's number when last shown: to say why it moved
const DRAFTS = "pg.lab.drafts"; // edited workflows kept when another one is opened
const DISCIPLINE = "pg.lab.discipline";
const DRAFTS_MAX = 8; // until the engine says (starter-workflows: drafts_kept)

function stored<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function store(key: string, value: unknown): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Not remembered in a private window, or the browser's storage is full.
  }
}

/** The engine prices a workflow and checks it; it knows nothing of the design it came from, so
 * the link is put back on what comes back. */
async function priceKeepingDesign(w: LabWorkflow): Promise<LabWorkflow> {
  const priced = await api.labPrice(w);
  return w.design ? { ...priced, design: w.design } : priced;
}

/** A workflow as far as the browser can tell, before the engine checks it. */
function looksLikeWorkflow(x: unknown): x is LabWorkflow {
  const w = x as LabWorkflow | null;
  return !!w && typeof w.id === "string" && typeof w.name === "string" && Array.isArray(w.steps);
}

/** A workflow of your own with something in it: kept in "Your drafts" when another is opened. An
 * untouched blank one isn't worth keeping. */
function isDraft(w: LabWorkflow | null): w is LabWorkflow {
  if (!w || w.origin !== "custom") return false;
  const untouchedBlank = w.name === "My workflow" && w.steps.length === 1 && w.steps[0].name === "New step" && !w.steps[0].skills.length;
  return !untouchedBlank;
}

/** "Advanced: better skill matching": the skill matcher's download, offered in plain words with an
 * inline confirm. It sits under the skill picker, out of the way; while it downloads it stays open. */
function MatcherAdvanced({
  m,
  busy,
  onTurn,
}: {
  m: NonNullable<LabData["matcher"]>;
  busy: boolean;
  onTurn: (on: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const going = MATCHER_BUSY.has(m.state) || m.state === "failed";
  const shown = open || going;
  return (
    <div className="matcher-adv">
      <button type="button" className="linkish small" aria-expanded={shown} aria-controls="matcher-adv" onClick={() => setOpen((o) => !o)}>
        Advanced: Better Skill Matching
      </button>
      {shown ? (
        <div id="matcher-adv" className="matcher-adv__box small" role="group" aria-label="Better skill matching">
          <p className="muted" role="status" data-testid="matcher-status">
            {m.note}
          </p>
          {m.offer ? (
            <>
              <p>
                Rig picks each step's skills by shared words now. The better matcher picks them by meaning, with two open-source
                models ({m.model} and an embedder) that run on this machine. Turning it on downloads them once (≈
                {m.mb.toLocaleString("en-US")} MB) and they use about {m.memory_gb ?? 2} GB of memory while Rig runs. Nothing is sent
                anywhere; you can turn it off again.
              </p>
              <div className="row" style={{ gap: 6 }}>
                <button type="button" className="btn btn--small btn--primary" disabled={busy} onClick={() => onTurn(true)}>
                  Download ≈{m.mb.toLocaleString("en-US")} MB and Turn It On
                </button>
                <button type="button" className="btn btn--small btn--quiet" onClick={() => setOpen(false)}>
                  Cancel
                </button>
              </div>
            </>
          ) : null}
          {m.can_turn_off ? (
            <button type="button" className="btn btn--small btn--quiet" disabled={busy} onClick={() => onTurn(false)}>
              Turn It Off
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** The goal the workflow is built for, whole and editable, and the rule lines found in it
 * (goal-rules): what the first step is told to follow. */
function GoalRules({
  wf,
  goal,
  onType,
  onDone,
}: {
  wf: LabWorkflow;
  goal: string;
  onType: (brief: string) => void;
  onDone: (brief: string) => void;
}) {
  const brief = wf.brief ?? "";
  const rules = wf.rules ?? [];
  const before = useRef(brief); // the text when the box got the focus: only a real edit is saved
  return (
    <div className="insp__section" aria-label="Goal and rules" role="group">
      <label className="insp__label" htmlFor="wf-brief">
        Goal &amp; rules
      </label>
      <textarea
        id="wf-brief"
        className="input"
        rows={3}
        value={brief}
        placeholder="What this workflow is for, with its rules: limits, deadlines, who must approve. The first step is told to follow them."
        onFocus={() => (before.current = brief)}
        onChange={(e) => onType(e.target.value)}
        onBlur={(e) => {
          if (e.target.value !== before.current) onDone(e.target.value);
        }}
      />
      {rules.length ? (
        <>
          <div className="small muted">The first step is told to follow {rules.length === 1 ? "this rule" : `these ${rules.length} rules`}:</div>
          <ul className="insp__points small" data-testid="goal-rules">
            {rules.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </>
      ) : brief.trim() ? (
        <p className="small muted">No rule lines found (a line with a number, a limit or must, never, only). The whole goal still goes to the agent.</p>
      ) : null}
      {goal && brief.trim() && brief.trim() !== goal ? (
        <button type="button" className="linkish small" style={{ justifySelf: "start" }} onClick={() => onDone(goal)}>
          Use the Goal from Step 1 Instead
        </button>
      ) : null}
    </div>
  );
}

/** The Workflow Lab: build, combine and compare agentic workflows, no repo needed. */
export function Lab({
  agentLabel,
  agent,
  stage,
  onWorkflow,
  load: incoming,
  onSignIn,
  onPicked,
  onLoaded,
  useCase,
  onOpenCompare,
  onBuild,
}: {
  agentLabel: string;
  agent: { id: string; label: string; ready: boolean; budget_cap?: boolean } | null;
  /** On the step path: "build" shapes the workflow, "measure" runs it; unset shows both. Build and
   * Measure are two pages: Measure has no Workflows list and no step editor, and opens on the bench
   * choice, then Try it. */
  stage?: "build" | "measure";
  /** The workflow on the canvas, for the Ship step. */
  onWorkflow?: (wf: LabWorkflow | null) => void;
  /** A workflow to put on the canvas (a design's, or a run's), or a blank one; once per key. */
  load?: { key: string; wf: LabWorkflow | "blank" } | null;
  /** Opens the agent sign-in, for "Sign in to run". */
  onSignIn?: () => void;
  /** You put another workflow on the canvas yourself (a pick, a random one, a blank one). */
  onPicked?: () => void;
  /** `load` is on the canvas: the parent drops it, so a remount doesn't put it back over edits. */
  onLoaded?: () => void;
  /** The design chosen in step 2: its parts and parameters go in the brief too. */
  design?: { id: string; name?: string } | null;
  /** Opens the Compare page with the pinned workflows. */
  onOpenCompare?: () => void;
  /** The goal in use (step 1): the brief's language, and Try it's example input. */
  useCase?: string;
  /** Measure's "Change it on Build": the workflow is edited on Build. */
  onBuild?: () => void;
}) {
  const [data, setData] = useState<LabData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [wf, setWf] = useState<LabWorkflow | null>(null);
  const [stepId, setStepId] = useState<string | null>(null);
  // The draft on the canvas survives a reload; one that no longer checks out is said once.
  const [lostDraft, setLostDraft] = useState(false);
  const restored = useRef(false);
  useEffect(() => onWorkflow?.(wf), [wf, onWorkflow]);
  useEffect(() => {
    if (wf) store(DRAFT, wf);
  }, [wf]);
  // The number moved since this workflow was last shown, and a new run explains it: said once.
  const [moved, setMoved] = useState<{ id: string; note: string } | null>(null);
  const seenKey = wf ? `${wf.id}:${expected(wf)}:${wf.learned?.runs ?? 0}` : "";
  useEffect(() => {
    if (!wf) return;
    const all = stored<Record<string, Seen>>(SEEN) ?? {};
    const note = changeNote(all[wf.id], wf);
    setMoved((cur) => (note ? { id: wf.id, note } : cur?.id === wf.id ? cur : null));
    const { [wf.id]: _, ...rest } = all;
    store(SEEN, Object.fromEntries([...Object.entries(rest).slice(-199), [wf.id, seenOf(wf)]]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seenKey]);
  // What each step contributes, from a slimming job on this workflow (colours the canvas).
  const [slim, setSlim] = useState<{ wfId: string; map: Record<string, Contribution> } | null>(null);
  // One Discipline choice: it filters the starters and is what a Random workflow is built for. Remembered.
  const [discipline, setDisciplineState] = useState<string>(() => stored<string>(DISCIPLINE) ?? "");
  const setDiscipline = (d: string) => {
    setDisciplineState(d);
    store(DISCIPLINE, d || null);
  };
  // Edited workflows are never lost by opening another: kept here, newest first.
  const [drafts, setDrafts] = useState<LabWorkflow[]>(() => {
    const got = stored<unknown[]>(DRAFTS);
    return Array.isArray(got) ? got.filter(looksLikeWorkflow) : [];
  });
  useEffect(() => store(DRAFTS, drafts.length ? drafts : null), [drafts]);
  // The last switch that kept a draft: said once, with Undo.
  const [switched, setSwitched] = useState<{ from: LabWorkflow; to: string } | null>(null);
  const [dropDraft, setDropDraft] = useState<string | null>(null); // a draft's id, being confirmed
  const [shown, setShown] = useState<string[]>([]);
  const [randoms, setRandoms] = useState<LabWorkflow[]>([]);
  // Pinned for Compare: up to four, kept in this browser, compared on their own page.
  const [compare, setCompare] = useCompareSet();
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const panes = usePanes("lab");
  const [drag, setDrag] = useState<{ id: string; x: number; y: number } | null>(null);
  const [runner, setRunner] = useState<Runner>({
    agent: agent?.id ?? "claude-code",
    local: false,
    label: agent?.label ?? "Claude Code",
    model: null,
    words: null,
    factor: 1,
  });
  const [view, setView] = useState<"library" | "canvas" | "details">("canvas");
  // On a phone, Measure opens on its panel (it has no Workflows list) and Build on the canvas.
  useEffect(() => {
    if (stage) setView(stage === "measure" ? "details" : "canvas");
  }, [stage]);
  const [adding, setAdding] = useState(false);
  // The centre pane shows the canvas, or the measured results of every workflow on one bench.
  const [centre, setCentre] = useState<"canvas" | "results">("canvas");
  const [matrices, setMatrices] = useState<Record<string, LabMatrix>>({});
  const [benchNames, setBenchNames] = useState<Record<string, string>>({});
  const [resultBench, setResultBench] = useState<string>("");
  // The bench picked in the Measure panel for this workflow: Results open on it.
  const [measureBench, setMeasureBench] = useState<string>("");
  const measureRef = useRef("");
  measureRef.current = measureBench;
  useEffect(() => {
    if (measureBench) setResultBench(measureBench);
  }, [measureBench]);
  const addRef = useRef<HTMLDivElement>(null);
  const addButton = useRef<HTMLButtonElement>(null);
  const version = useRef(0);
  // Undo: each workflow's earlier versions, newest last. Reset: what it was copied from.
  const pastBy = useRef<Record<string, LabWorkflow[]>>({});
  const baseOf = useRef<Record<string, LabWorkflow>>({});
  const [, bump] = useState(0);
  // Per-step models only apply on Claude Code with Claude models; OpenCode runs every step on its session model.
  const ignoresStepModels = runner.local || runner.agent !== "claude-code";
  // Codex and Gemini CLI do every step themselves, one after another.
  const sequential = !runner.local && (runner.agent === "codex" || runner.agent === "gemini-cli");
  /** A local change while typing: newer than any reply still on its way. */
  const type = (next: LabWorkflow) => {
    version.current++;
    setWf(next);
  };
  const draftsMax = data?.drafts_max ?? DRAFTS_MAX;
  const keepInDrafts = (w: LabWorkflow) => setDrafts((d) => [w, ...d.filter((x) => x.id !== w.id)].slice(0, draftsMax));
  /** Before another workflow goes on the canvas: an edited one is kept in Your drafts, and the
   * switch says so (with Undo). */
  const switchFrom = (toName: string, toId?: string) => {
    if (!isDraft(wf) || wf.id === toId) {
      setSwitched(null);
      return;
    }
    keepInDrafts(wf);
    setSwitched({ from: wf, to: toName });
  };
  const undoSwitch = () => {
    if (!switched) return;
    if (isDraft(wf) && wf.id !== switched.from.id) keepInDrafts(wf); // what you switched to, if you edited it
    version.current++;
    setWf(drafts.find((d) => d.id === switched.from.id) ?? switched.from);
    setStepId(null);
    setSwitched(null);
  };
  /** The forward connections, also for older workflows that are a plain list. */
  function currentEdges(w: LabWorkflow): [string, string][] {
    if (w.edges?.length) return w.edges;
    const ids = w.steps.map((s) => s.id);
    return ids.slice(1).map((b, i) => [ids[i], b] as [string, string]);
  }

  const load = async () => {
    let d: LabData;
    try {
      d = await api.lab();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      return;
    }
    setData(d);
    let back: LabWorkflow | null = null;
    if (!restored.current) {
      restored.current = true;
      const draft = stored<unknown>(DRAFT);
      if (draft !== null) {
        try {
          if (!looksLikeWorkflow(draft)) throw new ApiError("not a workflow", 422);
          back = await priceKeepingDesign(draft); // the engine checks it: steps, links, models
        } catch (e) {
          setLostDraft(true);
          // Only a draft the engine refused is dropped; one it couldn't be asked about is kept.
          if (!(e instanceof ApiError) || e.status === 422) store(DRAFT, null);
        }
      }
    }
    setWf((cur) => cur ?? back ?? d.disciplines[0]?.workflows[0] ?? null);
  };
  useEffect(() => {
    void load();
  }, []);
  // The GitHub skills are indexed in the background on the first visit: look again until they're in.
  const skillsPolls = useRef(0);
  const skillsState = data?.skills_status?.state;
  useEffect(() => {
    if (skillsState !== "loading" || skillsPolls.current >= SKILLS_POLLS) return;
    const t = window.setTimeout(() => {
      skillsPolls.current++;
      api.lab().then(setData, () => undefined);
    }, SKILLS_POLL_MS);
    return () => window.clearTimeout(t);
  }, [data, skillsState]);
  const matcherPolls = useRef(0);
  const matcherState = data?.matcher?.state;
  useEffect(() => {
    if (!matcherState || !MATCHER_BUSY.has(matcherState) || matcherPolls.current >= MATCHER_POLLS) return;
    const t = window.setTimeout(() => {
      matcherPolls.current++;
      api.lab().then(setData, () => undefined);
    }, MATCHER_POLL_MS);
    return () => window.clearTimeout(t);
  }, [data, matcherState]);
  // The skill matcher is off until asked for: on starts its download, off goes back to word rules.
  const [matcherBusy, setMatcherBusy] = useState(false);
  const turnMatcher = async (on: boolean) => {
    setMatcherBusy(true);
    try {
      const m = await api.labMatcher(on);
      matcherPolls.current = 0;
      setData((d) => (d ? { ...d, matcher: m } : d));
      if (!on) await api.lab().then(setData, () => undefined); // the page's skills, by word rules again
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setMatcherBusy(false);
    }
  };
  // Results are read again on each visit to the Lab's views and each workflow change, so a new measure shows up.
  const refreshResults = useCallback(async () => {
    let rows;
    try {
      rows = await api.labResults();
    } catch {
      return;
    }
    const names: Record<string, string> = {};
    for (const r of rows) names[r.bench] = r.bench_name;
    const got = await Promise.all(Object.keys(names).map((id) => api.labMatrix(id).catch(() => null)));
    const next: Record<string, LabMatrix> = {};
    for (const m of got) if (m && m.rows.length > 0) next[m.bench] = m;
    setBenchNames(names);
    setMatrices(next);
    // The bench chosen (or the Measure panel's), never an unrelated one: without results there,
    // the Results pane says so.
    setResultBench((cur) => cur || measureRef.current);
  }, []);
  useEffect(() => {
    void refreshResults();
  }, [refreshResults, view, wf?.id]);
  // An opened Add step menu (by click or "+") puts the focus on its first step.
  useEffect(() => {
    if (adding) addRef.current?.querySelector<HTMLButtonElement>(".labadd__item")?.focus();
  }, [adding]);
  useEffect(() => {
    if (!adding) return;
    const down = (e: PointerEvent) => {
      if (!addRef.current?.contains(e.target as Node)) setAdding(false);
    };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [adding]);

  // A workflow opened while step 1 has a goal is built for it: the goal becomes its Goal & rules
  // (once; cleared on purpose, it stays cleared), priced again for its rule lines.
  useEffect(() => {
    const goal = useCase?.trim();
    if (!wf || !goal || (wf.brief !== undefined && wf.brief !== null)) return;
    const withGoal = { ...wf, brief: goal };
    const ticket = ++version.current;
    setWf(withGoal);
    api.labPrice(withGoal).then(
      (priced) => ticket === version.current && setWf(priced),
      () => undefined,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wf?.id, wf?.brief, useCase]);

  // Any change makes it your own copy (the starters stay as they are), priced again by the engine.
  const edit = async (next: LabWorkflow) => {
    setSaved(null);
    const mine: LabWorkflow =
      next.origin === "custom"
        ? next
        : { ...next, origin: "custom", id: `c${Date.now().toString(36)}`, name: next.name.startsWith("My ") ? next.name : `My ${next.name}` };
    const ticket = ++version.current;
    if (wf) {
      pastBy.current[mine.id] = [...(pastBy.current[wf.id] ?? []).slice(-49), wf];
      if (!baseOf.current[mine.id]) baseOf.current[mine.id] = baseOf.current[wf.id] ?? wf;
      bump((n) => n + 1);
    }
    setWf(mine);
    try {
      const priced = await priceKeepingDesign(mine);
      // Only if nothing changed meanwhile: a reply must never undo newer typing.
      if (ticket === version.current) setWf(priced);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      void priceKeepingDesign(wf!).then(setWf, () => undefined); // back to the last valid shape
    }
  };

  const removeSteps = (sids: string[]) => {
    if (!wf) return;
    let steps = withPositions(wf);
    let edges = currentEdges(wf);
    let loops = wf.loops ?? [];
    for (const sid of sids) {
      // Never the last step, nor the last one that does the work.
      const gone = steps.find((s) => s.id === sid);
      if (!gone || steps.length <= 1) continue;
      if (gone.kind === "do" && steps.filter((s) => s.kind === "do").length === 1) continue;
      const ins = edges.filter(([, b]) => b === sid).map(([a]) => a);
      const outs = edges.filter(([a]) => a === sid).map(([, b]) => b);
      // Keep the flow joined: whatever led here now leads to whatever came after.
      edges = [
        ...edges.filter(([a, b]) => a !== sid && b !== sid),
        ...ins.flatMap((a) => outs.filter((b) => a !== b).map((b) => [a, b] as [string, string])),
      ];
      steps = steps.filter((s) => s.id !== sid);
      loops = loops.filter((l) => l[0] !== sid && l[1] !== sid);
    }
    if (steps.length === wf.steps.length) return;
    setStepId(null);
    void edit({ ...wf, steps, edges, loops, loop: null });
  };
  const removeStep = (sid: string) => wf && wf.steps.length > 1 && removeSteps([sid]);

  const undo = () => {
    if (!wf) return;
    const stack = pastBy.current[wf.id] ?? [];
    const prev = stack[stack.length - 1];
    if (!prev) return;
    pastBy.current[wf.id] = stack.slice(0, -1);
    // The earlier version keeps the rest of the history, so undo can keep going back.
    pastBy.current[prev.id] = pastBy.current[wf.id];
    version.current++;
    setWf(prev);
    setStepId(null);
    bump((n) => n + 1);
  };
  const reset = () => {
    if (!wf || !baseOf.current[wf.id]) return;
    const base = baseOf.current[wf.id];
    pastBy.current[base.id] = [...(pastBy.current[wf.id] ?? []), wf]; // undo brings your version back
    version.current++;
    setWf(base);
    setStepId(null);
    bump((n) => n + 1);
  };
  const canUndo = Boolean(wf && pastBy.current[wf.id]?.length);
  const canReset = Boolean(wf && baseOf.current[wf.id] && baseOf.current[wf.id] !== wf);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (typing(e)) return;
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === "z") {
        e.preventDefault();
        undo(); // on Measure too: it takes back a slimmed or improved version
      } else if (stage === "measure") {
        return; // steps are added and removed on Build
      } else if ((e.key === "Delete" || e.key === "Backspace") && stepId) {
        e.preventDefault();
        removeStep(stepId); // undo brings it back
      } else if (e.key === "+" && !e.metaKey && !e.ctrlKey && !e.altKey && wf && view === "canvas" && centre === "canvas") {
        e.preventDefault();
        setAdding(true); // the menu's first step takes the focus (below)
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });

  const blank = () => {
    switchFrom("a new blank workflow");
    const wfNew: LabWorkflow = {
      id: `c${Date.now().toString(36)}`,
      name: "My workflow",
      discipline: discipline || "development",
      origin: "custom",
      steps: [{ id: "step-1", name: "New step", does: "Describe what this step does.", kind: "do", model: "claude-sonnet-5-5", skills: [], pos: [0, 0] }],
      loop: null,
      edges: [],
      loops: [],
      harness: [],
      prior: 0,
      cost: 1,
      why: [],
    };
    setStepId("step-1");
    baseOf.current[wfNew.id] = wfNew; // reset goes back to the blank, not to what was open before
    void edit(wfNew);
  };

  // A workflow handed over (a design's, a run's) or a blank one: once per key.
  const loaded = useRef<string | null>(null);
  useEffect(() => {
    if (!incoming || loaded.current === incoming.key) return;
    loaded.current = incoming.key;
    setSaved(null);
    if (incoming.wf === "blank") blank();
    else {
      switchFrom(incoming.wf.name, incoming.wf.id);
      version.current++;
      setWf(incoming.wf);
      setStepId(null);
    }
    onLoaded?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incoming?.key]);

  const addStep = (t: StepTemplate, at?: { x: number; y: number }) => {
    if (!wf) return;
    const id = newId(t.id, wf.steps.map((s) => s.id));
    const last = wf.steps[wf.steps.length - 1];
    // Placed by hand: it joins the flow after the selected step (or the last one), so it runs.
    const after = stepId ?? last?.id;
    const base = wf.steps.find((s) => s.id === after);
    const [bx, by] = base ? posOf(base) : [0, 0];
    // To the right of the step it follows, below any steps that already follow it: siblings
    // run in parallel, so they're drawn one above the other.
    const siblings = currentEdges(wf).filter(([a]) => a === after).length;
    const pos: [number, number] = at ? [at.x, at.y] : [bx + W + GAP, by + siblings * (H + 48)];
    const step: LabStep = { id, name: t.name, does: t.does, kind: t.kind, model: t.model, skills: [], pos };
    const edges: [string, string][] = [...(currentEdges(wf) ?? [])];
    if (after) edges.push([after, id]);
    setStepId(id);
    void edit({ ...wf, steps: [...withPositions(wf), step], edges });
  };

  /** Another workflow on the canvas, chosen from the lists. */
  const pick = (w: LabWorkflow) => {
    switchFrom(w.name, w.id);
    version.current++; // a price still on its way for the last one must not land over this
    setWf(w);
    setStepId(null);
    onPicked?.();
  };

  const random = async () => {
    setBusy(true);
    try {
      const r = await api.labRandom(discipline || null, shown);
      setShown((s) => [...s, r.id]);
      setRandoms((x) => [r, ...x].slice(0, 12));
      switchFrom(r.name, r.id);
      setWf(r);
      setStepId(null);
      setSaved(null);
      onPicked?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const all = useMemo(
    () =>
      [...(data?.business ?? []), ...(data?.rag ?? []), ...(data?.disciplines.flatMap((d) => d.workflows) ?? []), ...randoms].filter(
        (w) => !discipline || w.discipline === discipline,
      ),
    [data, randoms, discipline],
  );
  // The starters of the chosen discipline (all of them with "Any discipline").
  const starterGroups = (data?.disciplines ?? []).filter((d) => !discipline || d.id === discipline);
  const disciplineLabel = data?.templates.find((d) => d.id === discipline)?.label ?? null;
  // The open draft is listed as it is now, not as it was when it was last kept.
  const draftRows = drafts.map((d) => (wf && d.id === wf.id ? wf : d));
  const bestResult = [...all].sort((a, b) => est(b) - est(a)).slice(0, 3);
  const bestValue = [...all].sort((a, b) => est(b) / b.cost - est(a) / a.cost).slice(0, 3);
  const patternGroups = useMemo(() => {
    const m = new Map<string, LabWorkflow[]>();
    for (const p of data?.patterns ?? []) m.set(p.group ?? "Patterns", [...(m.get(p.group ?? "Patterns") ?? []), p]);
    return [...m.entries()];
  }, [data]);

  const order = wf ? stages(wf) : [];
  const autoPos = new Map<string, [number, number]>();
  // Each stage is a column, its parallel steps stacked and centred; a loop note makes a step taller.
  const tall = (id: string) => H + 48 + 28 * (wf?.loops ?? []).filter((l) => l[0] === id).length;
  order.forEach((stage, x) => {
    const total = stage.reduce((t, id) => t + tall(id), 0);
    let y = -total / 2;
    for (const id of stage) {
      autoPos.set(id, [x * (W + GAP), Math.round(y)]);
      y += tall(id);
    }
  });
  const posOf = (st: LabStep): [number, number] => (st.pos as [number, number] | null | undefined) ?? autoPos.get(st.id) ?? [0, 0];
  const number = new Map(order.flat().map((id, n) => [id, n + 1]));
  const loopsFrom = (id: string) => (wf?.loops ?? []).filter((l) => l[0] === id);
  const name = (id: string) => wf?.steps.find((s) => s.id === id)?.name ?? id;

  const slimOf = (id: string): Contribution | undefined =>
    slim && wf && slim.wfId === wf.id && slim.map[id]?.kind === "drop" ? slim.map[id] : undefined;
  // Measure shows the workflow as a read-only map beside the run: it is changed on Build.
  const readOnly = stage === "measure";
  // Measure's bench choice is shown at the top of its pane (BenchPanel renders it there).
  const [benchAt, setBenchAt] = useState<HTMLDivElement | null>(null);
  const nodes: CanvasNode[] = (wf?.steps ?? []).map((st) => {
    const [x, y] = drag?.id === st.id ? [drag.x, drag.y] : posOf(st);
    const sc = slimOf(st.id);
    return {
      id: st.id,
      x,
      y,
      w: W,
      h: H,
      draggable: !readOnly,
      label: `Step ${number.get(st.id)}: ${st.name}`,
      render: ({ target }) => (
        <div
          className={`block labstep${stepId === st.id ? " is-selected" : ""}${target ? " is-over" : ""}${sc ? ` slim slim--${sc.verdict.replace(" ", "-")}` : ""}`}
          style={{ ["--node" as string]: KIND[st.kind].color }}
        >
          <div className="block__head">
            <span>
              {number.get(st.id)} · {KIND[st.kind].label}
            </span>
            {wf && wf.steps.length > 1 && !readOnly ? (
              <button
                type="button"
                className="node__remove"
                data-no-drag
                aria-label={`Remove the step ${st.name}`}
                onClick={() => removeStep(st.id)}
              >
                <X size={14} aria-hidden="true" />
              </button>
            ) : null}
          </div>
          <button type="button" className="block__body" onClick={() => setStepId(st.id)} aria-pressed={stepId === st.id}>
            <strong>{st.name}</strong>
            {sc ? (
              <span className="slim__flag">
                {sc.verdict === "neutral" ? "no effect" : sc.verdict}
                {sc.marginal_pts != null ? ` · ${sc.marginal_pts > 0 ? "+" : ""}${sc.marginal_pts} pts` : ""}
              </span>
            ) : null}
            <span className="block__sub">{st.does}</span>
            <span className="labstep__chips">
              <span
                className={`labchip labchip--model${ignoresStepModels ? " chip--ignored" : ""}`}
                title={ignoresStepModels ? `Ignored on ${runner.label}: every step runs on the session model` : undefined}
              >
                {data?.models[st.model]?.label ?? st.model}
              </span>
              {st.skills.map((s) => (
                <span
                  key={s.path}
                  className="labchip"
                  title={[s.why, s.source === "github" ? `From GitHub · ${s.repo}` : ""].filter(Boolean).join(" · ") || undefined}
                >
                  {s.name}
                </span>
              ))}
            </span>
            {loopsFrom(st.id).map((l) => (
              <span key={l[1]} className="labloop">
                ↺ back to {name(l[1])} until it passes, at most {l[2]}×
              </span>
            ))}
          </button>
        </div>
      ),
    };
  });
  const edges: CanvasEdge[] = (wf ? currentEdges(wf) : []).map(([a, b], i) => ({
    id: `e${i}`,
    from: a,
    to: b,
    ...(readOnly
      ? {}
      : {
          onRemove: () => wf && void edit({ ...wf, steps: withPositions(wf), edges: currentEdges(wf).filter(([x, y]) => !(x === a && y === b)) }),
          removeLabel: `Remove the connection from ${name(a)} to ${name(b)}`,
        }),
  }));

  /** Positions as drawn now, so a change never jumps the layout. */
  function withPositions(w: LabWorkflow): LabStep[] {
    return w.steps.map((st) => ({ ...st, pos: posOf(st) }));
  }

  const connect = (from: string, to: string) => {
    if (!wf || from === to) return;
    const es = currentEdges(wf);
    // Back to a step that already leads here: that's a loop (fix and try again), not a circle.
    if (reaches(wf, to, from)) {
      if (!(wf.loops ?? []).some((l) => l[0] === from && l[1] === to))
        void edit({ ...wf, steps: withPositions(wf), edges: es, loops: [...(wf.loops ?? []), [from, to, 2]] });
      return;
    }
    if (!es.some(([a, b]) => a === from && b === to)) void edit({ ...wf, steps: withPositions(wf), edges: [...es, [from, to]] });
  };

  const hasResults = Object.keys(matrices).length > 0;
  const showResults = centre === "results" && hasResults;
  const matrix = matrices[resultBench] ?? null;
  // In the canvas header, or above the results: switch between the two.
  const centreToggle = hasResults ? (
    <div className="segmented centre-switch" role="radiogroup" aria-label="Centre pane">
      {(
        [
          ["canvas", "Canvas"],
          ["results", "Results"],
        ] as const
      ).map(([id, label]) => (
        <button
          key={id}
          type="button"
          role="radio"
          aria-checked={centre === id}
          onClick={() => setCentre(id)}
        >
          {label}
        </button>
      ))}
    </div>
  ) : null;

  const step = wf?.steps.find((s) => s.id === stepId) ?? null;
  const setStep = (patch: Partial<LabStep>) => wf && step && void edit({ ...wf, steps: wf.steps.map((s) => (s.id === step.id ? { ...s, ...patch } : s)) });
  if (error) return <p className="notice notice--error" style={{ margin: 24 }}>{error}</p>;
  if (!data || !wf) return <p className="muted" style={{ margin: 24 }}>Loading…</p>;
  const dataRef = data;

  return (
    <>
      <div className="switch segmented" role="tablist" aria-label="View">
        {(
          [
            ["library", "Workflows"],
            ["details", "Measure"],
            ["canvas", stage === "measure" ? "Workflow Map" : "Canvas"],
            ["details", "Details"],
          ] as const
        )
          // Build: Workflows, Canvas, Details. Measure: the run first, then the workflow's map.
          .filter(([id, label], i) => (stage === "measure" ? id !== "library" && label !== "Details" : i !== 1))
          .map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={view === id} onClick={() => setView(id)}>
            {label}
          </button>
        ))}
      </div>
      <main
        className={`panes panes--one panes--view-${view}${stage === "measure" ? " panes--no-left panes--measure" : panes.className}`}
        id="main"
        style={panes.style}
      >
        <section className="pane palette" aria-label="Workflows" inert={stage === "measure"}>
          <div className="palette__top">
            <div className="palette__head">
              <h2>Workflows</h2>
            </div>
            <div className="palette__controls">
              <label className="small lab-discipline__label" htmlFor="lab-discipline">
                Discipline
              </label>
              <div className="row" style={{ gap: 8, flexWrap: "nowrap", marginTop: -6 }}>
                <select
                  id="lab-discipline"
                  className="select select--small lab-discipline"
                  value={discipline}
                  aria-describedby="lab-discipline-note"
                  onChange={(e) => setDiscipline(e.target.value)}
                >
                  <option value="">Any Discipline</option>
                  {data.templates.filter((d) => d.id !== "generic").map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.label}
                    </option>
                  ))}
                </select>
                <button type="button" className="btn btn--small btn--primary" onClick={random} disabled={busy}>
                  <Dices size={14} aria-hidden="true" /> Random
                </button>
              </div>
              <p id="lab-discipline-note" className="small muted" style={{ margin: 0 }}>
                {disciplineLabel ? `Showing ${disciplineLabel} starters; Random builds a ${disciplineLabel} workflow. ` : ""}
                Built from the discipline's steps, {skillCount(data)} and {Object.keys(data.models).length} models.
              </p>
              {switched ? (
                <p className="notice small lab-switched" role="status">
                  <span style={{ flex: 1 }}>
                    Switched to {switched.to}. Your draft <b>{switched.from.name}</b> is in Your Drafts.
                  </span>
                  <button type="button" className="btn btn--small" onClick={undoSwitch}>
                    Undo
                  </button>
                  <button type="button" className="btn btn--small btn--quiet" aria-label="Dismiss" onClick={() => setSwitched(null)}>
                    <X size={14} aria-hidden="true" />
                  </button>
                </p>
              ) : null}
              {data.skills_status?.note ? (
                <p className="small muted" style={{ margin: 0 }} role="status">
                  {data.skills_status.note}
                </p>
              ) : null}
            </div>
          </div>
          <div className="palette__body">
            {drafts.length ? (
              <div className="pal-section">
                <div className="pal-section__title">Your Drafts</div>
                <ul className="pal-list" aria-label="Your Drafts">
                  {draftRows.map((w) =>
                    dropDraft === w.id ? (
                      <li key={w.id} className="pal-item pal-item--confirm" role="group" aria-label={`Remove ${w.name}?`}>
                        <p className="small" style={{ margin: 0 }}>
                          Remove the draft <b>{w.name}</b>? It isn't saved anywhere else.
                        </p>
                        <span className="row" style={{ gap: 6 }}>
                          <button
                            type="button"
                            className="btn btn--small btn--primary"
                            onClick={() => {
                              setDrafts((d) => d.filter((x) => x.id !== w.id));
                              if (switched?.from.id === w.id) setSwitched(null);
                              setDropDraft(null);
                            }}
                          >
                            Remove
                          </button>
                          <button type="button" className="btn btn--small btn--quiet" onClick={() => setDropDraft(null)}>
                            Cancel
                          </button>
                        </span>
                      </li>
                    ) : (
                      <Row
                        key={w.id}
                        wf={w}
                        selected={wf.id === w.id}
                        onPick={() => pick(w)}
                        onRemove={() => setDropDraft(w.id)}
                        removeLabel={`Remove the draft ${w.name}`}
                      />
                    ),
                  )}
                </ul>
              </div>
            ) : null}
            <div className="pal-section">
              <div className="pal-section__title">Build Your Own</div>
              <button
                type="button"
                className="btn btn--small"
                style={{ margin: "0 8px 6px" }}
                onClick={() => {
                  blank();
                  onPicked?.();
                }}
              >
                <FilePlus2 size={14} aria-hidden="true" /> New Blank Workflow
              </button>
              <p className="small muted" style={{ margin: "0 8px 4px" }}>
                Drag a step onto the canvas, or press +. Connect steps from their right-hand handle; connecting back to an earlier
                step makes a loop.
              </p>
              {data.templates.map((g, gi) => (
                <Group key={g.id} title={`Steps · ${g.label}`} count={g.steps.length} open={gi === 0}>
                  {g.steps.map((t) => (
                    <li key={t.id} className="pal-item">
                      <button
                        type="button"
                        className="pal-item__main item--draggable"
                        onPointerDown={(e) => startSkillDrag(e, `tpl:${g.id}/${t.id}`, t.name)}
                        onClick={() => consumeDragClick()}
                        title="Drag onto the canvas"
                      >
                        <span className="pal-item__name">{t.name}</span>
                        <span className="pal-item__sub">
                          {KIND[t.kind].label} · {t.does}
                        </span>
                      </button>
                      <button type="button" className="pal-item__add" aria-label={`Add the step ${t.name}`} onClick={() => addStep(t)}>
                        <Plus size={14} />
                      </button>
                    </li>
                  ))}
                </Group>
              ))}
            </div>
            <div className="pal-section">
              <div className="pal-section__title">Suggested</div>
              <Group title="Best expected result" count={bestResult.length} open>
                {bestResult.map((w) => (
                  <Row key={`r-${w.id}`} wf={w} selected={wf.id === w.id} onPick={() => pick(w)} />
                ))}
              </Group>
              <Group title="Best value for the cost" count={bestValue.length}>
                {bestValue.map((w) => (
                  <Row key={`v-${w.id}`} wf={w} selected={wf.id === w.id} onPick={() => pick(w)} />
                ))}
              </Group>
            </div>
            {randoms.length ? (
              <div className="pal-section">
                <div className="pal-section__title row row--between">
                  <span>Random</span>
                  <button type="button" className="linkish small" onClick={() => setRandoms([])}>
                    Clear
                  </button>
                </div>
                <ul className="pal-list">
                  {randoms.map((w) => (
                    <Row
                      key={w.id}
                      wf={w}
                      selected={wf.id === w.id}
                      onPick={() => pick(w)}
                      onRemove={() => setRandoms((x) => x.filter((y) => y.id !== w.id))}
                      removeLabel={`Remove ${w.name} from this list`}
                    />
                  ))}
                </ul>
              </div>
            ) : null}
            {data.business?.length ? (
              <div className="pal-section">
                <div className="pal-section__title">Business Processes</div>
                <Group title="Real procedures, parallel and looping" count={data.business.length}>
                  {data.business.map((w) => (
                    <Row key={w.id} wf={w} selected={wf.id === w.id} onPick={() => pick(w)} />
                  ))}
                </Group>
                {data.rag?.length ? (
                  <Group title="RAG architectures" count={data.rag.length}>
                    {data.rag.map((w) => (
                      <Row key={w.id} wf={w} selected={wf.id === w.id} onPick={() => pick(w)} />
                    ))}
                  </Group>
                ) : null}
              </div>
            ) : null}
            <div className="pal-section">
              <div className="pal-section__title">{disciplineLabel ? `Starters · ${disciplineLabel}` : "Starters by Discipline"}</div>
              {starterGroups.map((d) => (
                <Group key={d.id} title={d.label} count={d.workflows.length} open={!!discipline}>
                  {d.workflows.map((w) => (
                    <Row key={w.id} wf={w} selected={wf.id === w.id} onPick={() => pick(w)} />
                  ))}
                </Group>
              ))}
            </div>
            <div className="pal-section">
              <div className="pal-section__title">Agentic Patterns</div>
              {patternGroups.map(([g, list]) => (
                <Group key={g} title={g} count={list.length}>
                  {list.map((w) => (
                    <Row key={w.id} wf={w} selected={wf.id === w.id} onPick={() => pick(w)} />
                  ))}
                </Group>
              ))}
            </div>
            {data.saved.length ? (
              <div className="pal-section">
                <div className="pal-section__title">Saved in Your Library</div>
                <ul className="pal-list">
                  {data.saved.map((w) => (
                    <Row
                      key={w.id}
                      wf={w}
                      selected={wf.id === w.id}
                      onPick={() => pick(w)}
                      onRemove={async () => {
                        try {
                          await api.unsave(w.id);
                          void load();
                        } catch (e) {
                          setError(e instanceof ApiError ? e.message : String(e));
                        }
                      }}
                      removeLabel={`Take ${w.name} off your saved list`}
                    />
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </section>

        <section className="pane pane--canvas" aria-label="Workflow">
          {!panes.left && stage !== "measure" ? (
            <PaneResizer
              side="left"
              width={panes.widths.left}
              min={panes.limits.left[0]}
              max={panes.limits.left[1]}
              label="Workflows width"
              onResize={(w) => panes.resize("left", w)}
              onReset={() => panes.reset("left")}
            />
          ) : null}
          {!panes.right && stage !== "measure" ? (
            <PaneResizer
              side="right"
              width={panes.widths.right}
              min={panes.limits.right[0]}
              max={panes.limits.right[1]}
              label="Details panel width"
              onResize={(w) => panes.resize("right", w)}
              onReset={() => panes.reset("right")}
            />
          ) : null}
          {showResults ? (
            <div className="matrix__page">
              <div className="matrix__head">
                {centreToggle}
                <label className="small matrix__pick">
                  Results from{" "}
                  <select
                    className="select select--small"
                    value={resultBench}
                    onChange={(e) => setResultBench(e.target.value)}
                  >
                    {!matrix ? <option value={resultBench}>{benchNames[resultBench] ?? (resultBench || "Choose a bench")}</option> : null}
                    {Object.keys(matrices).map((id) => (
                      <option key={id} value={id}>
                        {benchNames[id] ?? id}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {matrix && wf && !matrix.rows.some((r) => ofWorkflow({ treatment: r.treatment }, wf.id)) ? (
                <p className="small muted" data-testid="results-not-measured">
                  Not measured yet: {wf.name} has no result on {benchNames[matrix.bench] ?? matrix.bench}; measure it to see it here.
                </p>
              ) : null}
              {matrix ? (
                <Matrix key={matrix.bench} data={matrix} benchName={benchNames[matrix.bench] ?? matrix.bench} />
              ) : (
                <p className="muted" data-testid="results-not-measured">
                  Not measured yet: measure it to see results here.
                </p>
              )}
            </div>
          ) : (
            <Canvas
              nodes={nodes}
              edges={edges}
              label={`${wf.name} workflow`}
              fitKey={`${wf.id}:${wf.steps.length}:${view}:${stage ?? ""}`}
              overview={readOnly}
              onMove={readOnly ? undefined : (id, x, y) => setDrag({ id, x, y })}
              onMoveEnd={readOnly ? undefined : (id) => {
                if (drag && drag.id === id) {
                  const d = drag;
                  setDrag(null);
                  void edit({ ...wf, steps: withPositions(wf).map((s) => (s.id === id ? { ...s, pos: [d.x, d.y] } : s)) });
                }
              }}
              onConnect={readOnly ? undefined : connect}
              onDropAt={readOnly ? undefined : (data, x, y) => {
                const [gid, tid] = data.replace(/^tpl:/, "").split("/");
                const t = data.startsWith("tpl:") ? (dataRef.templates.find((g) => g.id === gid)?.steps.find((st) => st.id === tid) ?? null) : null;
                if (t) addStep(t, { x: x - W / 2, y: y - H / 2 });
              }}
              overlays={
                <>
                {slim && wf && slim.wfId === wf.id ? (
                  <ul className="slim__legend small" aria-label="What each step contributes">
                    <li><i className="slim__swatch slim__swatch--essential" /> Essential</li>
                    <li><i className="slim__swatch slim__swatch--dead-weight" /> Dead Weight</li>
                    <li><i className="slim__swatch slim__swatch--harmful" /> Harmful</li>
                    <li><i className="slim__swatch slim__swatch--unclear" /> Unclear or No Effect</li>
                  </ul>
                ) : null}
                <div className="canvas__top">
                  {centreToggle}
                  <div
                    className="labadd"
                    ref={addRef}
                    onKeyDown={(e) => {
                      if (e.key === "Escape" && adding) {
                        setAdding(false);
                        addButton.current?.focus();
                      }
                    }}
                  >
                    <button
                      ref={addButton}
                      type="button"
                      hidden={stage === "measure"}
                      className="btn btn--small btn--primary"
                      aria-expanded={adding}
                      aria-controls="lab-add-menu"
                      aria-keyshortcuts="+"
                      title="Add a step (+)"
                      onClick={() => setAdding((a) => !a)}
                    >
                      <Plus size={14} aria-hidden="true" /> Add Step
                    </button>
                    {/* The map on Measure is read-only: no Reset, and Undo only once a slimmed or improved version was applied here. */}
                    {readOnly ? (
                      canUndo ? (
                        <span className="editbar" role="group" aria-label="Workflow edits">
                          <button type="button" className="btn btn--small btn--quiet" onClick={undo} aria-label="Undo" title="Take back the applied version (Ctrl+Z or Cmd+Z)">
                            <Undo2 size={14} aria-hidden="true" />
                            <span className="editbar__text">Undo</span>
                          </button>
                        </span>
                      ) : null
                    ) : (
                    <span className="editbar" role="group" aria-label="Workflow edits">
                      <button type="button" className="btn btn--small btn--quiet" disabled={!canUndo} onClick={undo} aria-label="Undo" title="Undo the last change (Ctrl+Z or Cmd+Z)">
                        <Undo2 size={14} aria-hidden="true" />
                          <span className="editbar__text">Undo</span>
                      </button>
                      <button
                        type="button"
                        className="btn btn--small btn--quiet"
                        disabled={!canReset}
                        onClick={reset}
                        aria-label="Reset"
                        title="Back to the workflow this one was made from. Undo brings your version back."
                      >
                        <RotateCcw size={14} aria-hidden="true" />
                          <span className="editbar__text">Reset</span>
                      </button>
                      <ShortcutsSheet
                        items={[
                          { keys: ["+"], does: "Add a step" },
                          { keys: ["Mod+Z"], does: "Undo the last change" },
                          { keys: ["Delete"], does: "Remove the selected step" },
                          { keys: ["Esc"], does: "Close a menu or this sheet" },
                          { keys: ["?"], does: "Show these shortcuts" },
                        ]}
                      />
                    </span>
                    )}
                    {adding && stage !== "measure" ? (
                      <div id="lab-add-menu" className="labadd__menu" role="group" aria-label="Steps to add">
                        {[dataRef.templates[0], dataRef.templates.find((g) => g.id === wf.discipline && g.id !== dataRef.templates[0]?.id)]
                          .filter((g): g is NonNullable<typeof g> => !!g)
                          .map((g) => (
                            <div key={g.id} className="labadd__group">
                              <div className="labadd__title">{g.label}</div>
                              {g.steps.map((t) => (
                                <button
                                  key={t.id}
                                  type="button"
                                  className="labadd__item"
                                  onClick={() => {
                                    addButton.current?.focus();
                                    setAdding(false);
                                    addStep(t);
                                  }}
                                >
                                  <span>{t.name}</span>
                                  <span className="small muted">{KIND[t.kind].label}</span>
                                </button>
                              ))}
                            </div>
                          ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="canvas__title">{wf.name}</div>
                  {readOnly ? (
                    <div className="labsum labsum--map small">
                      <span className="muted">Workflow map, read-only here.</span>
                      {onBuild ? (
                        <button type="button" className="linkish" onClick={onBuild} aria-label="Edit the workflow on Build">
                          Edit on Build
                        </button>
                      ) : null}
                    </div>
                  ) : (
                  <div className="labsum">
                    <span className="num">{expectedText(wf)} pts</span>
                    <span className="muted" title={provenance(wf).title}>
                      {estNote(wf)}
                    </span>
                    <span className="num">{wf.cost}× cost</span>
                    <span className="muted">vs one Sonnet pass</span>
                  </div>
                  )}
                </div>
                </>
              }
            />
          )}
        </section>

        <section className="pane" aria-label={stage === "measure" ? "Measure" : "Details"}>
          {stage === "measure" ? <h2 className="visually-hidden">Measure {wf.name}</h2> : null}
          <div className="pane__body">
            {lostDraft ? (
              <p className="notice notice--warning small" role="status">
                <span style={{ flex: 1 }}>Your earlier draft couldn't be restored, so a starter workflow is open instead.</span>
                <button type="button" className="btn btn--small btn--quiet" onClick={() => setLostDraft(false)}>
                  Dismiss
                </button>
              </p>
            ) : null}
            <div className="insp">
              <div className="insp__band" style={{ ["--node" as string]: "#1b6c80" }}>
                {stage === "measure" ? "Measuring" : wf.origin === "rag" ? "RAG architecture" : wf.origin === "business" ? "Business process" : wf.origin === "pattern" ? "Agentic pattern" : wf.origin === "random" ? "Random workflow" : wf.origin === "custom" ? "Your workflow" : "Starter workflow"}
              </div>
              <div className="insp__body">
                {wf.origin === "custom" && stage !== "measure" ? (
                  <div className="labedit-head">
                    <label className="visually-hidden" htmlFor="wf-name">
                      Workflow name
                    </label>
                    <input
                      id="wf-name"
                      className="input insp__title-input"
                      value={wf.name}
                      onChange={(e) => type({ ...wf, name: e.target.value })}
                      onBlur={() => void edit(wf)}
                    />
                    <label htmlFor="wf-discipline" className="small muted">
                      For
                    </label>
                    <select id="wf-discipline" className="select select--small" value={wf.discipline} onChange={(e) => void edit({ ...wf, discipline: e.target.value })}>
                      {data.templates.filter((d) => d.id !== "generic").map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.label}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <h3 className="insp__title">{wf.name}</h3>
                )}
                <div className="insp__subtitle">
                  {data.disciplines.find((d) => d.id === wf.discipline)?.label ?? "Pattern"} · {wf.steps.length} steps
                  {stages(wf).some((x) => x.length > 1) ? (
                    sequential ? (
                      <>
                        {" · "}
                        <span className="pill pill--warning">parallel steps run one after another on {runner.label}</span>
                      </>
                    ) : (
                      " · runs steps in parallel"
                    )
                  ) : (
                    ""
                  )}
                </div>
                {stage === "measure" ? (
                  <p className="labmeasure__guess small muted">
                    Before any run: <b className="num">{expectedText(wf)} pts</b>
                    <Term k="pts" /> expected ({estNote(wf)}), <b className="num">{wf.cost}×</b> the cost per task. A run replaces the guess.{" "}
                    {onBuild ? (
                      <button type="button" className="linkish" onClick={onBuild}>
                        Change It on Build
                      </button>
                    ) : null}
                  </p>
                ) : (
                <div className="labnums">
                  <div>
                    <b className="num">{expectedText(wf)}</b>
                    <span title={provenance(wf).title}>
                      pts
                      <Term k="pts" /> expected · {estNote(wf)}
                    </span>
                    {moved?.id === wf.id ? (
                      <span className="small muted" data-testid="guess-updated">
                        {moved.note}
                      </span>
                    ) : null}
                  </div>
                  <div>
                    <b className="num">{wf.cost}×</b>
                    <span>relative cost per task</span>
                  </div>
                </div>
                )}
                {/* Measure opens on where it is measured (the bench choice, in view without scrolling), then
                    Try it: one input, seen working, before the rest of the bench settings. */}
                {stage === "measure" ? (
                  <div className="labmeasure__bench" ref={setBenchAt} role="group" aria-label="Where it's measured" />
                ) : null}
                {stage === "measure" ? (
                  // Try it runs where the measure would: on the bench panel's "Run on" choice.
                  <TryIt
                    workflow={wf}
                    agent={agent}
                    onSignIn={onSignIn}
                    goal={useCase}
                    first
                    local={runner.model}
                    localWords={runner.words}
                    timeoutFactor={runner.factor}
                  />
                ) : null}
                {stage !== "measure" ? (
                  <GoalRules
                    wf={wf}
                    goal={useCase?.trim() || ""}
                    onType={(brief) => type({ ...wf, brief })}
                    onDone={(brief) => void edit({ ...wf, brief })}
                  />
                ) : null}
                {stage !== "measure" ? (
                <div className="insp__section">
                  <div className="insp__label">Why this shape</div>
                  <ul className="insp__points small">
                    {wf.why.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </div>
                ) : null}

                {step && stage !== "measure" ? (
                  <div className="insp__section labedit">
                    <div className="insp__label">
                      Step: {step.name}{" "}
                      <span className="muted" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 400 }}>
                        ({KIND[step.kind].label.toLowerCase()}: {KIND[step.kind].what})
                      </span>
                    </div>
                    <div className="field">
                      <label htmlFor="step-name">Name</label>
                      <input
                        id="step-name"
                        className="input"
                        value={step.name}
                        onChange={(e) => type({ ...wf, steps: wf.steps.map((x) => (x.id === step.id ? { ...x, name: e.target.value } : x)) })}
                        onBlur={() => void edit(wf)}
                      />
                    </div>
                    <div className="field">
                      <label htmlFor="step-does">What it does</label>
                      <textarea
                        id="step-does"
                        className="input"
                        rows={3}
                        value={step.does}
                        onChange={(e) => type({ ...wf, steps: wf.steps.map((x) => (x.id === step.id ? { ...x, does: e.target.value } : x)) })}
                        onBlur={() => void edit(wf)}
                      />
                    </div>
                    {wf.rules?.length && stages(wf)[0]?.includes(step.id) ? (
                      <p className="small muted" data-testid="step-rules-note">
                        This step is also told: "Follow these rules", with the {wf.rules.length} rule{wf.rules.length === 1 ? "" : "s"} in Goal &amp; rules. Later
                        steps are told to keep to them.
                      </p>
                    ) : null}
                    <div className="field">
                      <label htmlFor="step-kind">Kind</label>
                      <select id="step-kind" className="select" value={step.kind} onChange={(e) => setStep({ kind: e.target.value as StepKind })}>
                        {(Object.keys(KIND) as StepKind[]).map((k) => (
                          <option key={k} value={k}>
                            {KIND[k].label}: {KIND[k].what}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="field">
                      <label htmlFor="lab-model">Model</label>
                      <select
                        id="lab-model"
                        className="select"
                        value={step.model}
                        aria-describedby={ignoresStepModels ? "lab-model-note" : undefined}
                        onChange={(e) => setStep({ model: e.target.value })}
                      >
                        {Object.entries(data.models).map(([id, m]) => (
                          <option key={id} value={id}>
                            {m.label} · {m.tier} · {m.cost}× cost
                          </option>
                        ))}
                      </select>
                      {ignoresStepModels ? (
                        <p id="lab-model-note" className="notice notice--warning small">
                          Runs on {runner.label}: every step uses that one model, so this choice is ignored there.
                        </p>
                      ) : null}
                    </div>
                    <div className="field">
                      <label htmlFor="lab-skill">Add a skill</label>
                      <SkillPicker
                        id="lab-skill"
                        skills={data.skills}
                        chosen={step.skills.map((x) => x.path)}
                        why={Object.fromEntries(step.skills.filter((x) => x.why).map((x) => [x.path, x.why as string]))}
                        onPick={(s) => {
                          const { path, name, source, repo, url } = s;
                          setStep({ skills: [...step.skills, { path, name, source, repo, url }] });
                        }}
                      />
                      {data.matcher && data.matcher.state !== "disabled" ? (
                        <MatcherAdvanced m={data.matcher} busy={matcherBusy} onTurn={(on) => void turnMatcher(on)} />
                      ) : null}
                    </div>
                    {step.skills.length ? (
                      <ul className="labskills">
                        {step.skills.map((s) => (
                          <li key={s.path}>
                            <button
                              type="button"
                              className="tag tag--x"
                              aria-label={`Remove ${s.name} from this step`}
                              onClick={() => setStep({ skills: step.skills.filter((x) => x.path !== s.path) })}
                            >
                              {s.name} ×
                            </button>
                            <SkillSource skill={s} />
                            {s.why ? <span className="small muted labskills__why">{s.why}</span> : null}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    <div className="insp__label">Connections</div>
                    <ul className="labconns small">
                      {currentEdges(wf)
                        .filter(([a, b]) => a === step.id || b === step.id)
                        .map(([a, b]) => (
                          <li key={`${a}>${b}`}>
                            {a === step.id ? `→ then ${name(b)}` : `← after ${name(a)}`}
                            <button
                              type="button"
                              className="btn btn--small btn--quiet"
                              aria-label={`Remove the connection from ${name(a)} to ${name(b)}`}
                              onClick={() => void edit({ ...wf, steps: withPositions(wf), edges: currentEdges(wf).filter(([x, y]) => !(x === a && y === b)) })}
                            >
                              ×
                            </button>
                          </li>
                        ))}
                      {(wf.loops ?? [])
                        .filter((l) => l[0] === step.id)
                        .map((l) => (
                          <li key={`loop-${l[1]}`}>
                            ↺ back to {name(l[1])}, at most{" "}
                            <input
                              className="input input--tiny num"
                              type="number"
                              min={1}
                              max={5}
                              value={l[2]}
                              aria-label={`Times back to ${name(l[1])}`}
                              onChange={(e) =>
                                void edit({ ...wf, steps: withPositions(wf), loops: (wf.loops ?? []).map((x) => (x[0] === l[0] && x[1] === l[1] ? [x[0], x[1], Number(e.target.value)] : x)) })
                              }
                            />
                            ×
                            <button
                              type="button"
                              className="btn btn--small btn--quiet"
                              aria-label={`Remove the loop back to ${name(l[1])}`}
                              onClick={() => void edit({ ...wf, steps: withPositions(wf), loops: (wf.loops ?? []).filter((x) => !(x[0] === l[0] && x[1] === l[1])) })}
                            >
                              ×
                            </button>
                          </li>
                        ))}
                    </ul>
                    <div className="field">
                      <label htmlFor="step-connect">Connect to</label>
                      <select
                        id="step-connect"
                        className="select"
                        value=""
                        onChange={(e) => e.target.value && connect(step.id, e.target.value)}
                      >
                        <option value="">Choose a step (earlier steps make a loop)…</option>
                        {wf.steps
                          .filter((x) => x.id !== step.id)
                          .map((x) => (
                            <option key={x.id} value={x.id}>
                              {x.name}
                            </option>
                          ))}
                      </select>
                    </div>
                    <button
                      type="button"
                      className="btn btn--small btn--quiet"
                      disabled={wf.steps.length <= 1}
                      onClick={() => removeStep(step.id)}
                    >
                      <Trash2 size={13} aria-hidden="true" /> Remove This Step
                    </button>
                  </div>
                ) : (
                  stage !== "measure" ? (
                    <p className="small muted">Select a step on the canvas to edit it: name, what it does, model, skills and connections.</p>
                  ) : null
                )}

                {stage !== "measure" ? (
                <>
                <div className="insp__section">
                  <div className="insp__label">Harness rules</div>
                  {Object.entries(data.harness).map(([id, h]) => (
                    <label key={id} className="check-row small">
                      <input
                        type="checkbox"
                        checked={wf.harness.includes(id)}
                        onChange={(e) =>
                          void edit({ ...wf, harness: e.target.checked ? [...wf.harness, id] : wf.harness.filter((x) => x !== id) })
                        }
                      />
                      <span>
                        <b>{h.name}</b> · {wf.harness_text?.[id] ?? h.does}
                      </span>
                    </label>
                  ))}
                </div>

                <div className="row" style={{ gap: 8 }}>
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={async () => {
                      try {
                        const r = await api.labSave(wf);
                        setSaved(r.name);
                        void load();
                      } catch (e) {
                        setError(e instanceof ApiError ? e.message : String(e));
                      }
                    }}
                  >
                    <Save size={14} aria-hidden="true" /> Save to My Library
                  </button>
                  {stage ? null : <BuildSpecButton source="workflow" workflow={wf} design={wf.design ? { id: wf.design.id, values: wf.design.parameters } : null} useCase={useCase} className="btn" saveLabel="Save to the Library" />}
                  {(() => {
                    const state = pinState(compare, wf);
                    const full = state === "out" && compare.length >= COMPARE_MAX;
                    return (
                      <button
                        type="button"
                        className="btn"
                        disabled={state === "same" || full}
                        title={full ? `Compare holds ${COMPARE_MAX}: remove one first` : state === "older" ? "Replace the pinned copy with this version" : undefined}
                        onClick={() => {
                          const next = pin(compare, wf, wf.design?.name ? { id: wf.design.id, name: wf.design.name } : null);
                          if (next) setCompare(next);
                        }}
                      >
                        <Pin size={14} aria-hidden="true" /> {state === "same" ? "In Compare" : state === "older" ? "Update in Compare" : "Compare"}
                      </button>
                    );
                  })()}
                </div>
                </>
                ) : null}
                {saved ? (
                  <p className="notice small">
                    Saved as a runnable skill with a subagent per step, in your library. Measure it below, or from a repo's Run
                    tab, on {agentLabel}.
                  </p>
                ) : null}

                {stage !== "build" ? (
                <BenchPanel
                  key={wf.id}
                  wf={wf}
                  chooserAt={stage === "measure" ? benchAt : undefined}
                  onBench={setMeasureBench}
                  agent={agent}
                  onRunOn={setRunner}
                  onUseVersion={(next) => void edit(next)}
                  onSlim={(map) => setSlim(map ? { wfId: wf.id, map } : null)}
                  onSignIn={onSignIn}
                  onApplySlim={(ids) => {
                    setSlim(null); // the slimmed workflow is a new shape: the colours no longer describe it
                    removeSteps(ids);
                  }}
                />
                ) : null}

                {compare.length ? (
                  <div className="insp__section">
                    <div className="insp__label row row--between">
                      <span>
                        Compare · {compare.length} of {COMPARE_MAX}
                      </span>
                      <button type="button" className="linkish small" aria-label="Clear the pinned set" onClick={() => setCompare([])}>
                        Clear
                      </button>
                    </div>
                    <div role="region" aria-label="Compared workflows">
                      <ul className="labcmp-list small">
                        {compare.map((c) => (
                          <li key={c.wf.id}>
                            <button type="button" className="linkish labcmp-list__name" onClick={() => pick(c.wf)} title={c.wf.name}>
                              {c.wf.name}
                            </button>
                            <button
                              type="button"
                              className="btn btn--small btn--quiet"
                              aria-label={`Stop comparing ${c.wf.name}`}
                              onClick={() => setCompare(compare.filter((y) => y.wf.id !== c.wf.id))}
                            >
                              <X size={13} aria-hidden="true" />
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                    {onOpenCompare ? (
                      <button type="button" className="btn btn--small" onClick={onOpenCompare}>
                        <Columns3 size={14} aria-hidden="true" /> Open the Comparison
                      </button>
                    ) : null}
                    <p className="small muted">
                      {compare.length < 2 ? "Pin one more to compare them side by side." : "Side by side, what differs, and measured together on one bench."}
                    </p>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </section>
      </main>
    </>
  );
}
