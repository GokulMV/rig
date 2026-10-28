import { FolderGit2, MoreHorizontal, RotateCcw, ShieldCheck, Undo2, X } from "lucide-react";
import { type RefObject, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { Inspector } from "./components/Inspector";
import { Mark } from "./components/Mark";
import { RunPill } from "./components/RunPill";
import { type LibraryItem, Palette } from "./components/Palette";
import { ShortcutsSheet, typing } from "./components/Shortcuts";
import { ArchifyMap } from "./components/ArchifyMap";
import { Lab } from "./components/Lab";
import { LibraryDetail } from "./components/LibraryDetail";
import { PaneResizer } from "./components/PaneResizer";
import { BuildSpecView } from "./components/BuildSpec";
import { Term } from "./components/Term";
import { MeasureEmpty } from "./components/MeasureBadge";
import { ShipToggle } from "./components/ShipToggle";
import { Describe, Guide, type OffPath, StageHead, type Step, StepBar, StepNav, StepPage, STEPS, storedLabGoal, storeLabGoal } from "./components/Journey";
import { Home } from "./components/Home";
import { RecordedProof, TourEntry, TutorialPage } from "./components/Tutorial";
import { TokensTourSlot, TokensTutorialRoute } from "./components/TutorialTokens";
import { parseRoute, type Route, routeHash, routeOrder, type TourAt, type TourTrack } from "./lib/route";
import { useTutorial } from "./lib/tutorial";
import { RigExplainPage } from "./components/RigExplain";
import { RunsPage } from "./components/Runs";
import { Compare } from "./components/Compare";
import { SuggestionsPanel } from "./components/SuggestionsPanel";
import { PaneToggles } from "./components/PaneToggles";
import { AgentPanel, type Candidate, RunPanel, ScenariosPanel } from "./components/Panels";
import { GaragePanel } from "./components/Garage";
import { BLOCK_W, BLOCK_H, type MeasuredVerdict, type NodeInfo, RepoCanvas } from "./components/RepoCanvas";
import { aboutTheAgent, keptTemplate, measureBadge, useRules } from "./lib/rules";
import { verdictWord } from "./lib/evidence";
import type { Rect } from "./components/Canvas";
import { RemoteRepoForm } from "./components/RemoteRepo";
import { WorkflowPicker } from "./components/WorkflowPicker";
import { api, ApiError, setRepo } from "./lib/api";
import { canvasAdded, useCanvasState } from "./lib/canvasState";
import { designParams } from "./lib/designParams";
import { plural, notesOnly, suggestedTitle } from "./lib/format";
import type { DragMeta } from "./lib/dragSkill";
import type {
  AgentInfo,
  Architecture,
  DesignLink,
  Estimate,
  ExperimentRow,
  GarageBlueprint,
  LabResult,
  LabWorkflow,
  Project,
  Proposed,
  RepoParts,
  RepoRef,
  Scenario,
  Treatments,
  Workflow,
} from "./lib/types";
import { usePanes } from "./lib/usePanes";
import type { Pinned } from "./lib/compareSet";

function remembered(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function remember(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Not remembered in a private window.
  }
}

function rememberedJSON<T>(key: string): T | null {
  try {
    const raw = remembered(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

const PAGE_MS = 200;
const EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)"; // --ease-out (tokens.css)

/** A move between pages: the new page slides in a few pixels from the way you went (forward from
 * the right, back from the left) as it fades in, and focus goes to its heading. Only transform and
 * opacity; a move made mid-way starts from where the last one got to, so fast clicks never queue.
 * With reduced motion, no movement and no fade: the page just appears. */
function usePageMotion(app: RefObject<HTMLDivElement | null>, key: string, order: number) {
  const prev = useRef<{ key: string; order: number } | null>(null);
  const running = useRef<Animation[]>([]);
  useLayoutEffect(() => {
    const was = prev.current;
    prev.current = { key, order };
    const root = app.current;
    if (!was || was.key === key || !root) return; // the first page of a visit just appears
    const dir = order >= was.order ? 1 : -1;
    const reduce = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    root.dataset.transition = reduce ? "none" : dir > 0 ? "forward" : "back";

    // The new page's heading takes focus, unless something on it already did (a goal box).
    const active = document.activeElement;
    const typing = active instanceof HTMLElement && active.matches("input, textarea, select, [contenteditable]") && root.contains(active) && !active.closest(".topbar");
    const heading = Array.from(root.querySelectorAll<HTMLElement>("h1")).find((h) => !h.closest(".topbar, [hidden]") && h.getClientRects().length > 0);
    if (heading && !typing) {
      if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: true });
    }

    const from = new Map<Element, number>();
    for (const a of running.current) {
      const t = (a.effect as KeyframeEffect | null)?.target;
      if (t) from.set(t, Number(getComputedStyle(t).opacity));
      a.cancel();
    }
    running.current = [];
    if (reduce) return;
    // The page's parts: the Lab's host is its head, notices and panes, each on its own.
    const pages = Array.from(root.children)
      .flatMap((el) => (el.matches(".labhost") ? Array.from(el.children) : [el]))
      .filter(
        (el): el is HTMLElement => el instanceof HTMLElement && !el.matches(".topbar, .floating-notice, .goalbar, [hidden]") && typeof el.animate === "function",
      );
    for (const el of pages) {
      // A page of text slides; a work surface (canvas, panes, columns) only fades, so nothing you
      // might drag or measure moves under the pointer. Its head slides, so the direction still reads.
      const slide = el.matches(".steppage, .stagehead");
      const a = el.animate(
        [
          { opacity: from.get(el) ?? 0, transform: slide ? `translateX(${dir * 12}px)` : "none" },
          { opacity: 1, transform: "none" },
        ],
        { duration: PAGE_MS, easing: EASE_OUT },
      );
      a.id = "page-transition";
      a.onfinish = () => {
        running.current = running.current.filter((x) => x !== a);
      };
      running.current.push(a);
    }
  }, [key, order, app]);
}

/** Rough estimates asked in one request at most (the engine's bound is rough-estimate: batch_max). */
const ESTIMATE_BATCH = 50;

function message(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

function LocalForm({
  onAttached,
  compact,
}: {
  onAttached: (r: RepoRef, warning?: string) => void;
  compact?: boolean;
}) {
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = compact ? "attach-path-2" : "attach-path";
  return (
    <form
      className="attach"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!path.trim()) return;
        setBusy(true);
        setError(null);
        try {
          // The engine adds a warning when the repo sits outside the home folder.
          const added = (await api.addRepo(path.trim())) as RepoRef & { warning?: string };
          onAttached(added, added.warning);
          setPath("");
        } catch (err) {
          setError(message(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <label htmlFor={id} className="attach__label">
        Folder of the repo on this machine
      </label>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input
          id={id}
          className="input mono"
          placeholder="~/code/my-app"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          autoFocus={!compact}
        />
        <button type="submit" className="btn btn--primary" disabled={busy || !path.trim()}>
          {busy ? "Reading…" : "Attach"}
        </button>
      </div>
      {error ? (
        <p className="small" role="alert" style={{ color: "var(--negative)" }}>
          {error}
        </p>
      ) : null}
    </form>
  );
}

function AttachForm({
  onAttached,
  compact,
  onCancel,
}: {
  onAttached: (r: RepoRef, warning?: string) => void;
  compact?: boolean;
  onCancel?: () => void;
}) {
  const [way, setWay] = useState<"local" | "remote">("local");
  const body = (
    <>
      <div className="segmented" role="radiogroup" aria-label="Where the repo is">
        <button type="button" role="radio" aria-checked={way === "local"} onClick={() => setWay("local")}>
          On This Machine
        </button>
        <button type="button" role="radio" aria-checked={way === "remote"} onClick={() => setWay("remote")}>
          From GitHub or GitLab
        </button>
      </div>
      {way === "local" ? (
        <LocalForm onAttached={onAttached} compact={compact} />
      ) : (
        <RemoteRepoForm onAttached={onAttached} />
      )}
    </>
  );
  if (!compact) return <div className="attach-ways">{body}</div>;
  return (
    <div className="attach-pop" role="dialog" aria-label="Add a Repo">
      {body}
      <button type="button" className="btn btn--small btn--quiet" onClick={onCancel}>
        Cancel
      </button>
    </div>
  );
}

interface RepoData {
  /** The repo this was read for: never shown for another one while the next loads. */
  for: string | null;
  project: Project | null;
  architecture: Architecture | null;
  workflows: Workflow[];
  scenarios: Scenario[];
  treatments: Treatments | null;
  experiments: ExperimentRow[];
  error: string | null;
}

const EMPTY: RepoData = {
  for: null,
  project: null,
  architecture: null,
  workflows: [],
  scenarios: [],
  treatments: null,
  experiments: [],
  error: null,
};

function useRepoData(repoId: string | null) {
  const [data, setData] = useState<RepoData>(EMPTY);
  // The repo asked for last: a slower answer for a repo you've since left must not land on top of
  // the one you're on (it did, and the goal box then waited on "Reading…" for good).
  const latest = useRef<string | null>(null);
  const load = useCallback(async () => {
    if (!repoId) return;
    latest.current = repoId;
    setRepo(repoId);
    try {
      const [project, architecture, workflows, scenarios, treatments, experiments] = await Promise.all([
        api.project(),
        api.architecture(),
        api.workflows(),
        api.scenarios(),
        api.treatments(),
        api.experiments(),
      ]);
      if (latest.current !== repoId) return;
      setData({ for: repoId, project, architecture, workflows, scenarios, treatments, experiments, error: null });
    } catch (e) {
      if (latest.current !== repoId) return;
      setData((d) => ({ ...d, error: message(e) }));
    }
  }, [repoId]);
  useEffect(() => {
    setData(EMPTY);
    void load();
  }, [load]);
  // Until this repo's own data is in, nothing of the last one shows.
  return { ...(data.for === repoId || data.for === null ? data : EMPTY), reload: load };
}

export default function App() {
  const [repos, setRepos] = useState<RepoRef[] | null>(null);
  const [repoId, setRepoIdState] = useState<string | null>(null);
  const [repoWarning, setRepoWarning] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentInfo[] | null>(null);
  const [agentId, setAgentIdState] = useState(() => remembered("pg.agent") ?? "claude-code");
  // Build keeps two side tabs; running, scenarios and designs have steps of their own.
  const [tab, setTab] = useState<"selected" | "improve">("selected");
  // After a first full pass (or "Skip the guide") the path is a workspace: tabs, no Back/Next.
  const [workspace, setWorkspaceState] = useState(() => remembered("pg.workspace") === "1");
  // The hash picks the page (a reload or a link comes back to it); with no hash, Home. A step
  // page off the hash reopens the step you were on last.
  const initial = useRef(parseRoute(window.location.hash)).current;
  const [step, setStepState] = useState<Step>(() => {
    if (initial.page === null) return initial.step;
    const n = Number(remembered("pg.step"));
    return n >= 1 && n <= 5 ? (n as Step) : 1;
  });
  // The furthest step reached: its ticks stay whatever else changes (the repo, the "Start from").
  const [reached, setReached] = useState(() => Math.max(1, Math.min(5, Number(remembered("pg.reached")) || 1)));
  // Every page has a link, and every move adds to the browser's history, so Back and Forward
  // retrace it: #/home, the steps (#/describe … #/ship), #/runs (and each run,
  // #/runs/<repo|bench>/<place>/<id>), #/compare (the workflows pinned in the Lab) and #/rig-score.
  const [page, setPage] = useState<OffPath | null>(initial.page);
  // Where the tutorial is (#/tutorial/…): its own state, never the steps' (pg.step stays yours).
  const [tourAt, setTourAt] = useState<TourAt>(initial.page === "tutorial" ? initial.at : 1);
  // Which track: the first (no name) or the repo tutorial ("tokens", #/tutorial/tokens/…).
  const [tourTrack, setTourTrack] = useState<TourTrack | undefined>(initial.page === "tutorial" ? initial.track : undefined);
  const tour = useTutorial();
  useEffect(() => {
    if (!window.location.hash) window.history.replaceState(null, "", "#/home");
  }, []);
  const [passed, setPassed] = useState(false); // the guide just became a workspace, on step 5
  const setStepOnly = (n: Step) => {
    setPage(null);
    setStepState(n);
    remember("pg.step", String(n));
    setReached((r) => {
      const next = Math.max(r, n);
      remember("pg.reached", String(next));
      return next;
    });
    if (n === 5 && !workspace) {
      setWorkspace(true);
      setPassed(true);
    }
  };
  const setWorkspace = (on: boolean) => {
    setWorkspaceState(on);
    remember("pg.workspace", on ? "1" : "0");
  };
  const applyRoute = (r: Route) => {
    if (r.page === null) setStepOnly(r.step);
    else {
      if (r.page === "tutorial") {
        setTourAt(r.at);
        setTourTrack(r.track);
      }
      setPage(r.page);
    }
  };
  /** Go to a page: shown at once, and its hash pushed so Back comes back here. */
  const go = (r: Route) => {
    applyRoute(r);
    const h = routeHash(r);
    if (window.location.hash !== h) window.location.hash = h;
  };
  // Back, Forward, a typed link, or a plain <a href="#/…">.
  const applyLatest = useRef(applyRoute);
  applyLatest.current = applyRoute;
  useEffect(() => {
    const on = () => applyLatest.current(parseRoute(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const appRef = useRef<HTMLDivElement>(null);
  usePageMotion(appRef, page === "tutorial" ? `tutorial-${tourTrack ?? ""}${tourAt}` : (page ?? `step-${step}`), routeOrder(page, step, tourAt));
  const [agentOpen, setAgentOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => {
    if (!menuOpen) return;
    const down = (e: PointerEvent) => {
      if (!(e.target as Element | null)?.closest?.(".topmenu")) setMenuOpen(false);
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    document.addEventListener("pointerdown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", down);
      document.removeEventListener("keydown", key);
    };
  }, [menuOpen]);
  const [labWf, setLabWf] = useState<LabWorkflow | null>(null);
  // The design a "Nothing yet" workflow was built from: the link lives on the workflow itself
  // (id, parameter values, how it was set up), so edits, drafts, reloads and Compare keep it.
  // This is that design's catalog entry, read for its name and parts.
  const [labDesign, setLabDesign] = useState<GarageBlueprint | null>(null);
  // Said once after the link is dropped (Detach, or Start blank).
  const [designNote, setDesignNote] = useState<string | null>(null);
  const [labLoad, setLabLoad] = useState<{ key: string; wf: LabWorkflow | "blank" } | null>(null);
  // The design open in step 2's detail view: Next asks whether to use it.
  const [viewing, setViewing] = useState<GarageBlueprint | null>(null);
  // Design's catalog, for a repo: folded behind "Start from a blueprint instead" until opened.
  const [blueprintsOpen, setBlueprintsOpen] = useState<boolean | null>(null);
  const [asking, setAsking] = useState(false);
  useEffect(() => setAsking(false), [viewing?.id]);
  // Step 5 opens on "With the accepted suggestions" when there are some, until you choose.
  const [specPicked, setSpecSource] = useState<"repo" | "suggested" | null>(null);
  const [acceptedN, setAcceptedN] = useState(0);
  // What the accepted suggestions are, by name (never a preview): what Ship's "with" adds.
  const [acceptedDiff, setAcceptedDiff] = useState<NonNullable<Proposed["diff"]> | null>(null);
  const specSource = specPicked ?? (acceptedN > 0 ? "suggested" : "repo");
  // Repos: measure on your own code. Workflow Lab: build and compare workflows, no repo needed.
  // A first visit (no step history in this browser) chooses nothing: both "Start from" cards
  // show, and the goal box comes after the choice. After that, the last choice.
  const firstVisit = useRef(remembered("pg.step") === null && remembered("pg.reached") === null).current;
  const [chosenSpace, setSpaceState] = useState<"repo" | "lab" | null>(() => {
    const kept = remembered("pg.space");
    if (kept === "lab" || kept === "repo") return kept;
    return firstVisit ? null : "repo";
  });
  // Until a choice, the rest of the app works as "Nothing yet" (it needs no repo).
  const space = chosenSpace ?? "lab";
  const setSpace = (s: "repo" | "lab") => {
    setSpaceState(s);
    remember("pg.space", s);
  };
  // Two goals, never mixed. "Nothing yet": what you're building, kept in this browser as it's typed.
  const [labGoal, setLabGoalState] = useState(storedLabGoal);
  const setLabGoal = (t: string) => {
    setLabGoalState(t);
    storeLabGoal(t);
  };
  // Each repo's own goal is on the server; an edit is a draft, kept in this browser for that repo
  // only (across reloads), and is the goal every step uses until Save goal writes it to the repo.
  const [goalEdits, setGoalEditsState] = useState<Record<string, string>>(() => rememberedJSON<Record<string, string>>("pg.goal.drafts") ?? {});
  const setGoalEdits = (f: (m: Record<string, string>) => Record<string, string>) =>
    setGoalEditsState((m) => {
      const next = f(m);
      remember("pg.goal.drafts", JSON.stringify(next));
      return next;
    });
  // The one-click goal each repo's draft was picked from (repo-goals: templates), kept with the
  // draft in this browser and sent with Save goal, which keeps it while the box starts with it.
  const [goalPicks, setGoalPicksState] = useState<Record<string, string>>(() => rememberedJSON<Record<string, string>>("pg.goal.templates") ?? {});
  const setGoalPicks = (f: (m: Record<string, string>) => Record<string, string>) =>
    setGoalPicksState((m) => {
      const next = f(m);
      remember("pg.goal.templates", JSON.stringify(next));
      return next;
    });
  // The repo whose goal was just saved: the button says Saved.
  const [goalSaved, setGoalSaved] = useState<string | null>(null);
  // The canvas shows the architecture as it is, or as the suggestions would make it.
  const [mode, setMode] = useState<"current" | "suggested" | "blueprint">("current");
  // A catalog architecture opened from the Garage, drawn in place of the repo's own while it is open.
  const [blueprint, setBlueprint] = useState<GarageBlueprint | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [proposed, setProposed] = useState<Architecture | null>(null);
  const [diff, setDiff] = useState<NonNullable<Proposed["diff"]> | null>(null);
  // The suggestion each new or taken-away part came from (by component id).
  const [origins, setOrigins] = useState<NonNullable<Proposed["origins"]>>({});
  // The step "Add a task for <step>" asked for, for Measure's Add task form.
  const [taskPreset, setTaskPreset] = useState<{ step: string; key: number } | null>(null);
  const [decisions, setDecisions] = useState(0);
  const [flowName, setFlowName] = useState<string | null>(null);
  // Below 1024px one pane shows at a time; this picks which.
  const [view, setView] = useState<"library" | "canvas" | "details">("canvas");
  const [selected, setSelected] = useState<{ id: string; info: NodeInfo } | null>(null);
  // A library item opened in the details panel (not on the canvas yet).
  const [libItem, setLibItem] = useState<LibraryItem | null>(null);
  const [runFor, setRunFor] = useState<string | null>(null);
  // "Measure it" on a suggestion that changes the code: Measure opens on before and after, for it.
  const [codeFor, setCodeFor] = useState<{ title: string; key: number } | null>(null);
  const measureCode = (title: string) => {
    setCodeFor({ title, key: Date.now() });
    setStep(4);
  };
  const [estimates, setEstimates] = useState<Record<string, Estimate | "loading">>({});
  const [workflowId, setWorkflowId] = useState<string | null>(() => remembered("pg.workflow"));
  const panes = usePanes("main");

  const firstRepos = useRef(true);
  const loadRepos = useCallback(async () => {
    const list = await api.repos();
    // Only on opening, and not on a first visit (which chooses nothing): detaching the last repo
    // leaves "My repo" (and its Attach form) showing.
    if (firstRepos.current && !firstVisit && remembered("pg.space") === null && !list.length) setSpaceState("lab");
    firstRepos.current = false;
    setRepos(list);
    setRepoIdState((cur) => {
      const keep = cur ?? remembered("pg.repo");
      return list.find((r) => r.id === keep)?.id ?? list[0]?.id ?? null;
    });
  }, []);
  const loadAgents = useCallback(async () => setAgents(await api.agents()), []);
  useEffect(() => {
    void loadRepos();
    void loadAgents();
  }, [loadRepos, loadAgents]);

  const chooseRepo = (id: string) => {
    if (id === repoId) return;
    remember("pg.repo", id);
    setRepoIdState(id);
    setSelected(null);
    setEstimates({});
    asked.current.clear();
    setBlueprint(null);
    setMode((m) => (m === "blueprint" ? "current" : m));
  };
  const [pulling, setPulling] = useState<string | null>(null);
  const pull = async (r: RepoRef) => {
    setPulling(r.id);
    try {
      const done = await api.pullRepo(r.id);
      setRepoWarning(`Pulled ${r.name}: now at ${done.head}.`);
      if (r.id === repoId) void data.reload();
    } catch (e) {
      setRepoWarning(`Couldn't pull ${r.name}. ${message(e)}`);
    } finally {
      setPulling(null);
    }
  };
  const chooseAgent = (id: string) => {
    remember("pg.agent", id);
    setAgentIdState(id);
  };

  const data = useRepoData(repoId);
  // The chosen repo's saved goal ("" when it has none); null until that repo's project is read.
  const repoGoal = data.project ? (data.project.use_case ?? "") : null;
  const repoEdit = repoId !== null && repoId in goalEdits ? goalEdits[repoId] : null;
  const repoText = repoEdit ?? repoGoal ?? "";
  const repoDirty = repoGoal !== null && repoEdit !== null && repoEdit.trim() !== repoGoal.trim();
  // The effective goal, which every later step uses: the goal of the place you start from; for a
  // repo, the draft in this browser if there is one, else the saved goal.
  const useCase = space === "lab" ? labGoal : repoText;
  /** Save goal: the box becomes the chosen repo's goal. Nothing else writes it (Next never does). */
  const saveRepoGoal = async () => {
    const t = repoText.trim();
    if (!repoId || !repoDirty || !t) return;
    const id = repoId;
    await api.useCase(t, keptTemplate(t, goalPicks[id] ?? data.project?.goal_template, goalRules)?.id);
    await data.reload();
    setGoalEdits((m) => {
      const { [id]: _, ...rest } = m;
      return rest;
    });
    setGoalSaved(id);
  };
  const setStep = (n: Step) => go({ page: null, step: n });

  // The goal in use against the repo's languages (build-spec: stack_words), said on Design.
  const [stackWarnings, setStackWarnings] = useState<{ for: string; warnings: string[] } | null>(null);
  const checkKey = space === "repo" && repoId ? `${repoId}\n${repoText.trim()}` : null;
  useEffect(() => {
    if (!checkKey || !repoText.trim() || step !== 2) return;
    let live = true;
    const t = window.setTimeout(() => {
      api.goalCheck(repoText.trim()).then(
        (r) => live && setStackWarnings({ for: checkKey, warnings: r.warnings }),
        () => undefined,
      );
    }, 200);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkKey, step]);
  const mismatch = checkKey && repoText.trim() && stackWarnings?.for === checkKey ? stackWarnings.warnings : [];
  const [savingGoal, setSavingGoal] = useState(false);
  const saveFromBar = async () => {
    setSavingGoal(true);
    try {
      await saveRepoGoal();
    } catch (e) {
      setRepoWarning(`Couldn't save ${repos?.find((r) => r.id === repoId)?.name ?? "the repo"}'s goal. ${message(e)}`);
    } finally {
      setSavingGoal(false);
    }
  };

  // The open workflow's design link, and that design's entry (read again after a reload).
  const link: DesignLink | null = space === "lab" ? (labWf?.design ?? null) : null;
  useEffect(() => {
    if (!link) {
      setLabDesign(null);
      return;
    }
    if (labDesign?.id === link.id) return;
    let live = true;
    api.garageEntry(link.id).then(
      (b) => live && setLabDesign(b),
      () => undefined,
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [link?.id]);
  /** "Use this design" in "Nothing yet": its Lab workflow, set up for the use case, on the canvas,
   * carrying its link to the design (and the parameter values set in step 2). */
  const useDesign = async (b: GarageBlueprint) => {
    try {
      const got = await api.garageWorkflow(b.id, useCase);
      const { workflow, ...handoff } = got;
      const designLink: DesignLink = { id: b.id, name: b.name, parameters: { ...designParams(b.id) }, handoff };
      setLabDesign(b);
      setDesignNote(null);
      setLabLoad({ key: `${b.id}@${Date.now()}`, wf: { ...workflow, design: designLink } });
    } catch (e) {
      setRepoWarning(`Couldn't open ${b.name} as a workflow. ${message(e)}`);
      return;
    }
    setStep(3);
  };
  /** "Detach from design" (or "Stop using this design"): the workflow stays, the link goes. */
  const detachDesign = () => {
    if (!labWf?.design) return;
    const name = labWf.design.name;
    setLabLoad({ key: `detach@${Date.now()}`, wf: { ...labWf, design: null } });
    setLabDesign(null);
    setDesignNote(`Detached from ${name}: the workflow stays, but BUILD.md no longer has ${name}'s parts or parameters.`);
  };

  // A repo's view (As it is, With accepted, or a catalog blueprint) comes back after a reload.
  // Until you pick one, Build opens on "With accepted" whenever some suggestions were accepted,
  // so what you accepted is what you see.
  type View = { mode: "current" | "suggested" | "blueprint"; id: string | null; picked?: boolean };
  const [viewPicked, setViewPicked] = useState(false);
  // Which repo's view has been put back: until then, nothing is written over what was kept.
  const [restoredView, setRestoredView] = useState<string | null>(null);
  const asked_ = useRef<string | null>(null);
  useEffect(() => {
    if (!repoId || asked_.current === repoId) return;
    asked_.current = repoId;
    const v = rememberedJSON<Record<string, View>>("pg.view")?.[repoId];
    setViewPicked(Boolean(v?.picked));
    if (v?.mode === "blueprint" && v.id) {
      api.garageEntry(v.id).then(
        (b) => {
          setBlueprint(b);
          setMode("blueprint");
          setRestoredView(repoId);
        },
        () => setRestoredView(repoId),
      );
      return;
    }
    if (v?.mode === "suggested") setMode("suggested");
    setRestoredView(repoId);
  }, [repoId]);
  useEffect(() => {
    if (!repoId || restoredView !== repoId) return;
    const all = rememberedJSON<Record<string, View>>("pg.view") ?? {};
    all[repoId] = { mode: mode === "blueprint" && !blueprint ? "current" : mode, id: blueprint?.id ?? null, picked: viewPicked };
    remember("pg.view", JSON.stringify(all));
  }, [repoId, mode, blueprint, restoredView, viewPicked]);
  const store = useCanvasState(repoId ?? "none");
  // A selected card that Undo or Reset took away is no longer selected.
  useEffect(() => {
    if (selected?.id.startsWith("card:") && !store.state.cards.some((c) => `card:${c.id}` === selected.id)) setSelected(null);
  }, [store.state.cards, selected]);
  // Ctrl/Cmd+Z undoes a canvas change, except while typing in a field.
  useEffect(() => {
    if (space !== "repo") return;
    const key = (e: KeyboardEvent) => {
      if (typing(e)) return;
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === "z" && store.canUndo && mode !== "blueprint") {
        e.preventDefault();
        store.undo();
      } else if ((e.key === "Delete" || e.key === "Backspace") && selected && mode !== "blueprint" && !e.metaKey && !e.ctrlKey) {
        // Delete takes the selected block off the plan, as its × does; Undo brings it back.
        const { id, info } = selected;
        if (id.startsWith("card:")) store.removeCard(id.slice(5));
        else if (/^(arch|step|repo-skill|setup):/.test(id) && !(info?.kind === "setup" && info.present === false)) store.removeBlock(id);
        else return;
        e.preventDefault();
        setSelected(null);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [space, store, mode, selected]);
  const workflow = data.workflows.find((w) => w.id === workflowId) ?? data.workflows[0] ?? null;
  const agent = agents?.find((a) => a.id === agentId) ?? null;

  // Every skill on the canvas gets the rough estimate (no model) as soon as it lands, and again
  // when its links change. The model is asked only from "Sharpen with the model" in Details.
  const skillNodes = useMemo(() => {
    const out: { id: string; path: string; targets: string[] }[] = [];
    const targets = (id: string) =>
      store.state.links.filter((l) => l.from === id).map((l) => l.to.replace(/^(step|arch|setup):/, ""));
    for (const c of store.state.cards) {
      if (c.kind === "skill") out.push({ id: `card:${c.id}`, path: c.ref, targets: targets(`card:${c.id}`) });
    }
    for (const t of data.treatments?.repo ?? []) {
      const id = `repo-skill:${t.path}`;
      out.push({ id, path: t.path, targets: targets(id) });
    }
    return out;
  }, [store.state, data.treatments]);
  const asked = useRef(new Map<string, string>());
  const estimateKey = skillNodes.map((s) => `${s.id}=${s.targets.join(",")}`).join("|");
  useEffect(() => {
    if (!repoId) return;
    // Already asked with these links: nothing new to ask. The rest go in one request (rough
    // guesses only, never a model), a few dozen at most per request.
    const todo = skillNodes.filter((s) => asked.current.get(s.id) !== s.targets.join(","));
    if (!todo.length) return;
    for (const s of todo) asked.current.set(s.id, s.targets.join(","));
    setEstimates((m) => {
      const next = { ...m };
      for (const s of todo) if (!next[s.id]) next[s.id] = "loading";
      return next;
    });
    for (let i = 0; i < todo.length; i += ESTIMATE_BATCH) {
      const part = todo.slice(i, i + ESTIMATE_BATCH);
      api
        .estimateBatch(part.map((s) => ({ treatment_path: s.path, steps: s.targets })))
        .then((got) =>
          setEstimates((m) => {
            const next = { ...m };
            part.forEach((s, n) => {
              const cur = m[s.id];
              // A sharper number someone asked for stays until the links change.
              if (typeof cur === "object" && cur.basis === "estimate" && cur.steps === s.targets.join(",")) return;
              next[s.id] = got[n] ?? { basis: "none", reason: "No estimate came back." };
            });
            return next;
          }),
        )
        .catch((e) =>
          setEstimates((m) => {
            const next = { ...m };
            for (const s of part) next[s.id] = { basis: "none", reason: message(e) };
            return next;
          }),
        );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estimateKey, repoId]);
  /** "Sharpen with the model": one model call for one card, only on that click. */
  const sharpen = (id: string) => {
    const s = skillNodes.find((x) => x.id === id);
    if (!s) return;
    setEstimates((m) => {
      const cur = m[id];
      return typeof cur === "object" ? { ...m, [id]: { ...cur, refining: true } } : m;
    });
    api
      .estimate(s.path, s.targets, { model: true })
      .then((e) => setEstimates((m) => ({ ...m, [id]: { ...e, steps: s.targets.join(",") } })))
      .catch((e) =>
        setEstimates((m) => {
          const cur = m[id];
          if (typeof cur === "object") return { ...m, [id]: { ...cur, refining: false, note: message(e) } };
          return { ...m, [id]: { basis: "none", reason: message(e) } };
        }),
      );
  };

  const findSkillName = (path: string) =>
    [...(data.treatments?.repo ?? []), ...(data.treatments?.user ?? []), ...(data.treatments?.installed ?? [])].find(
      (t) => t.path === path,
    )?.name ??
    path.split("/").pop() ??
    path;

  // "Add": next to the block the item serves (asked of the engine), else in open space.
  const addFromLibrary = async (lib: LibraryItem) => {
    if (lib.from === "create" || lib.from === "improve") {
      // Not a thing to place yet: it has to be written first.
      setLibItem(lib);
      setTab("selected");
      setView("details");
      return;
    }
    setView("canvas");
    // A harness, workflow or agent repo is more than one skill: lay out its parts and how they link.
    if (lib.from === "github" && lib.item.category !== "skill" && (await addParts(lib.item.id, lib.name, { category: lib.item.category })))
      return;
    const query =
      lib.from === "github"
        ? { name: lib.name, description: lib.item.description, topics: lib.item.topics, category: lib.item.category, theme: lib.item.theme }
        : lib.from === "local"
          ? { name: lib.name, description: lib.t.description, category: "skill" }
          : { name: lib.name, description: lib.from === "suggested" ? lib.s.why : "", category: "skill" };
    let targets: { id: string; why: string }[] = [];
    let unlinked: string | undefined;
    let beside: string | null | undefined;
    let fit: string | undefined;
    try {
      const placed = await api.place(query);
      targets = placed.targets;
      fit = placed.note ?? undefined;
      // Unlinked, its reason is the whole line; the language note goes on the card on its own.
      unlinked = placed.targets.length ? undefined : fit ? placed.reason.replace(` ${fit}`, "") : placed.reason;
      beside = placed.beside;
    } catch {
      /* placed in open space instead */
    }
    const first = targets.find((t) => besideSlot.current?.(t.id));
    // Nothing it applies to: beside the agent setup, linked to nothing, never in among other cards.
    const at = (first && besideSlot.current?.(first.id)) || (beside && besideSlot.current?.(beside)) || freeSlot.current?.() || { x: 0, y: 0 };
    // The card and all its links are one action: one Undo takes them all back.
    store.group(() => {
      const id = place(lib.data, at.x, at.y, first?.id ?? null, lib.name, first?.why ?? unlinked, fit);
      for (const t of targets) if (t !== first && besideSlot.current?.(t.id)) store.connect(`card:${id}`, t.id);
    });
    // Where it lands may be out of view (open space, or beside a block at the edge): bring it in.
    setReveal({ key: `${lib.data}@${Date.now()}`, rect: { x0: at.x, y0: at.y, x1: at.x + 184, y1: at.y + 104 } });
  };
  /** Lay a repo out as its parts: under everything (Add), or where it was dropped, clear of what
   * is drawn (drag). `replace` is a card for it already on the canvas. */
  const addParts = async (
    repo: string,
    name: string,
    how: { replace?: string; category?: string; drop?: { x: number; y: number }; visible?: Rect; near?: string | null } = {},
  ): Promise<boolean> => {
    const { replace, category } = how;
    let got: RepoParts;
    try {
      got = await api.repoParts(repo);
    } catch (e) {
      setRepoWarning(`Couldn't read ${repo}'s parts${replace ? "" : ", so it is added as one card"}. ${message(e)}`);
      return false;
    }
    if (got.parts.length < 2) {
      if (replace) setRepoWarning(`${repo} has no commands, agents, hooks or MCP config to lay out, only ${got.parts.length} part.`);
      return false;
    }
    // One column per kind, in flow order (instructions, commands, agents, skills, hooks, MCP);
    // a kind with many parts wraps into more columns. The repo card is column 0.
    const COLW = 300;
    const ROWH = 140;
    const PER_COL = 5;
    const grid = new Map<string, { col: number; row: number }>();
    let col = 1;
    let last = "";
    let row = 0;
    let rows = 1;
    for (const part of got.parts) {
      if (part.kind !== last || row === PER_COL) {
        if (last) col += 1;
        row = 0;
        last = part.kind;
      }
      grid.set(part.id, { col, row });
      row += 1;
      rows = Math.max(rows, row);
    }
    // Dropped: the repo card under the pointer, pulled back as far as it takes for the layout to
    // stay in view (as much of it as fits), then moved only as far as it takes not to cover a
    // block. Added: under everything.
    const size = { w: col * COLW + BLOCK_W, h: (rows - 1) * ROWH + BLOCK_H };
    const v = how.visible;
    const fit = (at: number, len: number, lo?: number, hi?: number) =>
      lo === undefined || hi === undefined ? at : Math.max(lo, Math.min(at, hi - len));
    const want = how.drop && {
      x: fit(how.drop.x - BLOCK_W / 2, size.w, v?.x0, v?.x1),
      y: fit(how.drop.y - BLOCK_H / 2, size.h, v?.y0, v?.y1),
    };
    const o = want ? (clearArea.current?.(size.w, size.h, want) ?? want) : (belowAll.current?.() ?? { x: 0, y: 0 });
    const origin = { x: Math.round(o.x), y: Math.round(o.y) };
    // A drop can land the layout partly out of view: the canvas pans to show it.
    if (how.drop) setReveal({ key: `${repo}@${Date.now()}`, rect: { x0: origin.x, y0: origin.y, x1: origin.x + size.w, y1: origin.y + size.h } });
    const spots = new Map([...grid].map(([id, g]) => [id, { x: origin.x + g.col * COLW, y: origin.y + g.row * ROWH }]));
    const used = new Set(got.links.map((l) => l.to));
    store.group(() => {
      if (replace) store.removeCard(replace);
      const repoCard = store.addCard(
        { kind: "catalog", ref: repo, name, x: origin.x, y: origin.y, parts: got.parts.length, category },
        how.near && !how.near.startsWith("lane:") ? [how.near] : [],
      );
      const ids = new Map<string, string>();
      for (const part of got.parts) {
        const at = spots.get(part.id)!;
        const id = store.addCard({
          kind: "part",
          ref: `${repo}:${part.path}`,
          name: part.name,
          x: at.x,
          y: at.y,
          part: { kind: part.kind, label: part.label, description: part.description, url: part.url },
        });
        ids.set(part.id, id);
        // The repo links to the parts nothing else in it uses: where its flow starts.
        if (!used.has(part.id)) store.connect(`card:${repoCard}`, `card:${id}`);
      }
      for (const l of got.links) store.connect(`card:${ids.get(l.from)}`, `card:${ids.get(l.to)}`);
      setSelected({ id: `card:${repoCard}`, info: { kind: "card", card: { kind: "catalog", ref: repo, name, x: origin.x, y: origin.y, id: repoCard, parts: got.parts.length } } });
    });
    setLibItem(null);
    setTab("selected");
    if (got.more) setRepoWarning(`${repo} has ${got.more} more parts than fit; the first ${got.parts.length} are on the canvas.`);
    return true;
  };
  const belowAll = useRef<(() => { x: number; y: number }) | null>(null);
  const [reveal, setReveal] = useState<{ key: string; rect: Rect } | null>(null);
  const clearArea = useRef<((w: number, h: number, at: { x: number; y: number }) => { x: number; y: number }) | null>(null);
  /** A drop from the library: a harness, workflow, agent, hook or MCP repo is laid out as its
   * parts, like Add; anything else (or a repo whose parts can't be read) is one card. */
  const dropped = async (
    raw: string,
    x: number,
    y: number,
    near: string | null,
    drop: { point: { x: number; y: number }; visible: Rect; meta?: DragMeta },
  ) => {
    const category = drop.meta?.category;
    if (raw.startsWith("catalog:") && category && category !== "skill") {
      const repo = raw.slice("catalog:".length);
      if (await addParts(repo, drop.meta?.name || (repo.split("/")[1] ?? repo), { category, drop: drop.point, visible: drop.visible, near })) return;
    }
    place(raw, x, y, near, drop.meta?.name || undefined);
  };
  const besideSlot = useRef<((id: string) => { x: number; y: number } | null) | null>(null);
  const freeSlot = useRef<(() => { x: number; y: number }) | null>(null);
  const place = (raw: string, x: number, y: number, near: string | null, name?: string, why?: string, fit?: string) => {
    const [kind, ...rest] = raw.split(":");
    const ref = rest.join(":");
    const link = near && !near.startsWith("lane:") ? [near] : [];
    const k = kind === "skill" || kind === "catalog" ? kind : "suggestion";
    const label =
      name ?? (k === "skill" ? findSkillName(ref) : k === "catalog" ? (ref.split("/")[1] ?? ref) : (ref.split("/").pop() ?? ref));
    const id = store.addCard({ kind: k, ref, name: label, x, y, why, fit }, link);
    setSelected({ id: `card:${id}`, info: { kind: "card", card: { kind: k, ref, name: label, x, y, id, why, fit } } });
    setLibItem(null);
    setTab("selected");
    return id;
  };

  const names = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of data.architecture?.components ?? []) m.set(`arch:${c.id}`, c.label);
    for (const t of data.treatments?.repo ?? []) m.set(`repo-skill:${t.path}`, t.name);
    for (const s of workflow?.steps ?? []) m.set(`step:${s.name}`, s.name);
    for (const c of store.state.cards) m.set(`card:${c.id}`, c.name);
    return m;
  }, [data.architecture, workflow, store.state.cards, data.treatments]);
  const order = [...names.keys()];
  // The connections list names agent setup blocks too ("To CLAUDE.md", not "setup:CLAUDE.md").
  const linkNames = useMemo(() => new Map([...(data.project?.agent ?? []).map((s) => [s.id, s.label] as const), ...names]), [names, data.project]);
  // The plan as it is on the canvas, for the brief: what you placed, drew and noted.
  const planAdded = useMemo(() => {
    const every = [...(data.treatments?.repo ?? []), ...(data.treatments?.user ?? []), ...(data.treatments?.installed ?? [])];
    const cards = new Map(store.state.cards.map((c) => [`card:${c.id}`, c]));
    // Named with what each block is, so a link reads on its own: "skill tdd -> step fix".
    const label = (id: string): string | null => {
      const name = names.get(id);
      const c = cards.get(id);
      if (c)
        return c.kind === "part"
          ? `${c.part?.kind ?? "part"} ${c.name}`
          : c.kind === "catalog"
            ? `repo ${c.ref}`
            : `${c.kind === "skill" ? "skill" : "planned"} ${c.name}`;
      if (id.startsWith("setup:")) return `agent setup ${id.slice(6)}`;
      if (!name) return null;
      return id.startsWith("step:") ? `step ${name}` : id.startsWith("repo-skill:") ? `skill ${name}` : name;
    };
    return canvasAdded(store.state, label, (path) => every.find((t) => t.path === path) ?? null);
  }, [store.state, names, data.treatments]);
  // Only architecture parts are in the brief, so only those can be left out of it.
  const [nRemoved, nPlaced] = [store.state.removed.filter((id) => id.startsWith("arch:")).length, store.state.cards.length];
  const canvasNote =
    nRemoved && nPlaced
      ? `Leaves out ${plural(nRemoved, "part")} you removed and adds ${nPlaced} you placed on the canvas.`
      : nRemoved
        ? `Leaves out ${plural(nRemoved, "part")} you removed on the canvas.`
        : nPlaced
          ? `Adds ${plural(nPlaced, "part")} you placed on the canvas.`
          : "";

  const infoFor = (id: string): NodeInfo | null => {
    const kind = id.split(":")[0];
    const rest = id.slice(kind.length + 1);
    if (kind === "arch") {
      const c = data.architecture?.components.find((x) => x.id === rest);
      return c ? { kind: "arch", c } : null;
    }
    if (kind === "step" && workflow) {
      const i = workflow.steps.findIndex((s) => s.name === rest);
      const s = workflow.steps[i];
      return s ? { kind: "step", name: s.name, type: s.type, why: s.why, index: i } : null;
    }
    if (kind === "card") {
      const card = store.state.cards.find((c) => c.id === rest);
      return card ? { kind: "card", card } : null;
    }
    if (kind === "repo-skill") {
      const t = data.treatments?.repo.find((x) => x.path === rest);
      return t ? { kind: "repo-skill", t } : null;
    }
    return null;
  };

  const candidates: Candidate[] = [
    ...store.state.cards.filter((c) => c.kind === "skill").map((c) => ({ path: c.ref, name: c.name })),
    ...(data.treatments?.repo ?? []).map((t) => ({ path: t.path, name: `${t.name} (in repo)` })),
  ].filter((c, i, all) => all.findIndex((x) => x.path === c.path) === i);

  // A measured skill shows its last run as Measure does (Rig score and verdict), by block id.
  const verdicts = useMemo(() => {
    const out: Record<string, MeasuredVerdict> = {};
    const latest = (names: string[]) => data.experiments.find((e) => e.rig && names.includes(e.treatment_name)); // newest first
    const put = (id: string, names: string[]) => {
      const e = latest(names.filter(Boolean));
      if (!e?.rig) return;
      const v = verdictWord(e.rig, e.verdict);
      out[id] = { score: e.rig.band === "not_evidence" ? null : e.rig.score, word: v.word, tone: v.tone, run: e.id };
    };
    for (const t of data.treatments?.repo ?? []) put(`repo-skill:${t.path}`, [t.name, t.path.split("/").pop() ?? ""]);
    for (const c of store.state.cards) if (c.kind === "skill") put(`card:${c.id}`, [c.name, c.ref.split("/").pop() ?? ""]);
    return out;
  }, [data.experiments, data.treatments, store.state.cards]);
  const mrules = useRules("measurability");
  // Measure's mode, lifted from its run panel: the step lead and the run column's line follow it.
  const [measureMode, setMeasureMode] = useState<"agent" | "code">("agent");
  const goalRules = useRules("repo-goals");
  // What is on the canvas that Measure can't run, and why: for Measure's empty state.
  const notRunnable = useMemo(() => {
    const out: { name: string; b: ReturnType<typeof measureBadge> }[] = [];
    for (const x of data.project?.agent ?? [])
      if (x.present && x.label !== "Skills") out.push({ name: x.label, b: measureBadge({ kind: "setup", label: x.label, present: true }, mrules) });
    for (const c of store.state.cards) if (c.kind !== "skill") out.push({ name: c.name, b: measureBadge({ kind: "card", card: c }, mrules) });
    if (acceptedN)
      out.push({ name: plural(acceptedN, "accepted suggestion"), b: measureBadge({ kind: "arch", c: { source: "proposed" } }, mrules) });
    return out.filter((x) => x.b && x.b.id !== "runnable");
  }, [data.project, store.state.cards, acceptedN, mrules]);

  // The evidence card sums up the skills you added, not the ones already in the repo.
  const added = store.state.cards.filter((c) => c.kind === "skill");
  const known = added.flatMap((c) => {
    const e = estimates[`card:${c.id}`];
    return typeof e === "object" && e.basis !== "none" ? [{ name: c.name, e, v: verdicts[`card:${c.id}`] }] : [];
  });

  const flows = data.architecture?.flows ?? [];
  const flow = mode === "current" ? (flows.find((f) => f.name === flowName) ?? null) : null;
  // Fetched in both views: "As it is" shows how many changes are waiting in "Suggested".
  useEffect(() => {
    if (!repoId) return;
    let live = true;
    api.proposed(mode === "suggested" ? (preview ?? undefined) : undefined).then(
      (p) => {
        if (!live) return;
        setProposed(p.architecture);
        setDiff(p.diff ?? null);
        setOrigins(p.origins ?? {});
        if (!preview) {
          setAcceptedN(p.accepted?.length ?? 0);
          setAcceptedDiff(p.diff ?? null);
        }
      },
      () => undefined,
    );
    return () => {
      live = false;
    };
  }, [mode, preview, decisions, repoId]);
  // Until a view is picked, accepted suggestions are what Build opens on.
  useEffect(() => {
    if (repoId && restoredView === repoId && !viewPicked && acceptedN > 0 && mode === "current") setMode("suggested");
  }, [repoId, restoredView, viewPicked, acceptedN, mode]);

  if (repos === null) {
    return (
      <div className="boot">
        <Mark size={28} />
      </div>
    );
  }

  const attached = async (r: RepoRef, warning?: string) => {
    setRepoWarning(warning ?? null);
    await loadRepos();
    chooseRepo(r.id);
  };
  const repo = repos.find((r) => r.id === repoId) ?? null;
  const inRepo = space === "repo" && repo !== null;
  const openRuns = () => {
    go({ page: "runs" });
    setMenuOpen(false);
  };
  const skipGuide = () => {
    setWorkspace(true);
    setMenuOpen(false);
    setStep(3);
  };
  const showGuide = () => {
    setWorkspace(false);
    setPassed(false);
    setMenuOpen(false);
    setStep(1);
  };
  const openCompare = () => {
    setSpace("lab");
    go({ page: "compare" });
  };
  /** A workflow from Compare on the Lab's canvas; it carries its own design link. */
  const fromCompare = (p: Pinned) => {
    setSpace("lab");
    setLabLoad({ key: `compare:${p.wf.id}@${Date.now()}`, wf: p.wf });
  };
  /** A Lab run from the Runs page: the workflow it measured, on the Lab's Measure. */
  const openLabRun = async (r: LabResult) => {
    setSpace("lab");
    try {
      const wf = await api.labWorkflowOf(r.treatment);
      setLabLoad({ key: `run:${r.bench}:${r.id}`, wf });
    } catch (e) {
      setRepoWarning(`Couldn't open the workflow ${r.workflow} measured: ${message(e)} Its result is still under Results in the Lab.`);
    }
    setStep(4);
  };

  const topbar = (
    <header className="topbar topbar--one">
      <a className="brand" href="#/home" aria-label="Rig, home">
        <Mark />
        <span className="wordmark" aria-hidden="true">
          RIG
        </span>
      </a>
      <StepBar step={page ? null : step} onStep={setStep} reached={reached} page={page} onRuns={openRuns} />
      <div className="topbar__actions">
        <RunPill
          onOpen={(run) => {
            if (run.kind === "repo" && run.repo) {
              setSpace("repo");
              chooseRepo(run.repo);
            } else setSpace("lab");
            setStep(4);
          }}
          onRuns={workspace ? undefined : openRuns}
        />
        {step > 1 && !page ? (
          <button
            type="button"
            className="topbar__context"
            title="Change the goal or the repo"
            onClick={() => setStep(1)}
          >
            {inRepo ? <FolderGit2 size={14} aria-hidden="true" /> : null}
            <span>{inRepo ? repo.name : "No Repo"}</span>
          </button>
        ) : null}
        {inRepo && repo.remote ? (
          <button
            type="button"
            className="btn btn--small btn--quiet"
            title={`Pull the latest from ${repo.remote}`}
            aria-label={`Pull ${repo.name}`}
            disabled={pulling === repo.id}
            onClick={() => void pull(repo)}
          >
            {pulling === repo.id ? "Pulling…" : "Pull"}
          </button>
        ) : null}
        <button
          type="button"
          className={`agent-pill${agent?.ready ? " is-ready" : ""}`}
          aria-expanded={agentOpen}
          onClick={() => setAgentOpen((o) => !o)}
        >
          <ShieldCheck size={14} aria-hidden="true" />
          {agent?.label ?? "Agent"} · {agent?.ready ? "signed in" : agent?.host ? "finish sign-in" : "sign in"}
        </button>
        <div className="topmenu">
          <button
            type="button"
            className="btn btn--small btn--quiet"
            aria-label="Menu"
            aria-expanded={menuOpen}
            aria-controls="top-menu"
            onClick={() => setMenuOpen((o) => !o)}
          >
            <MoreHorizontal size={16} aria-hidden="true" />
          </button>
          {menuOpen ? (
            <div id="top-menu" className="topmenu__pop" role="group" aria-label="Menu">
              <button type="button" className="topmenu__item" onClick={openRuns}>
                Runs
              </button>
              {workspace ? (
                <button type="button" className="topmenu__item" onClick={showGuide}>
                  Show the Guide Again
                </button>
              ) : (
                <button type="button" className="topmenu__item" onClick={skipGuide}>
                  Skip the Guide
                </button>
              )}
            </div>
          ) : null}
        </div>
      </div>
      {agentOpen ? (
        <div className="agent-pop" role="dialog" aria-label="Agent">
          <div className="row row--between">
            <strong>Agent</strong>
            <button type="button" className="btn btn--small btn--quiet" aria-label="Close" onClick={() => setAgentOpen(false)}>
              <X size={14} aria-hidden="true" />
            </button>
          </div>
          <AgentPanel agents={agents} agentId={agentId} onAgent={chooseAgent} onChanged={loadAgents} />
        </div>
      ) : null}
    </header>
  );

  const notice = repoWarning ? (
    // Floats over the app so the fixed-height grid rows below stay as they are.
    <p className="notice notice--warning floating-notice" role="status">
      <span style={{ flex: 1 }}>{repoWarning}</span>
      <button type="button" className="btn btn--small btn--quiet" onClick={() => setRepoWarning(null)}>
        Dismiss
      </button>
    </p>
  ) : null;

  // Steps 3 and 4 fill the screen with panes: each opens with its own head (title, what it is
  // for, its forward action), so Build and Measure read as two pages, in a repo or the Lab.
  const scoreLink = (
    <a className="stagehead__link" href="#/rig-score">
      How Is This Scored?
    </a>
  );
  const stageHead =
    step === 3 ? (
      <StageHead
        step={3}
        title={space === "lab" ? "Build the Workflow" : inRepo ? `Change ${repo.name}'s Parts` : "Build"}
        lead={
          space === "lab"
            ? "Pick a workflow or make your own: its steps, models, skills and rules. Measure runs it next."
            : "Add, remove and connect skills, agents and tools on the canvas. Measure runs each change next."
        }
        action={{ label: space === "lab" ? "Measure This Workflow" : "Measure These Changes", to: 4 }}
        onStep={setStep}
      />
    ) : step === 4 ? (
      <StageHead
        step={4}
        title={space === "lab" ? "Measure the Workflow" : "Measure What It Changed"}
        lead={
          space === "lab"
            ? "Try it on one input, then run it on a bench with and without it. Each result gets a Rig score."
            : (mrules?.before_after?.stage_lead?.[measureMode] ??
              "Choose the tasks, then run the change on them with and without it. Each result gets a Rig score.")
        }
        extra={scoreLink}
        action={{ label: "Get the Build Brief", to: 5 }}
        onStep={setStep}
      />
    ) : null;
  // Where a returning visit left off, for Home's Continue.
  const resume =
    remembered("pg.step") === null
      ? null
      : {
          label: workspace ? STEPS[step - 1].label : `Step ${step} · ${STEPS[step - 1].label}`,
          where: chosenSpace === "repo" ? (repo ? `Rig a Repo, ${repo.name}` : "Rig a Repo") : chosenSpace === "lab" ? "Rig a Workflow" : "nothing chosen yet",
        };

  // Step 2's Next, with a design open: use it, keep browsing, or start without one.
  const usedId = space === "lab" ? labDesign?.id : mode === "blueprint" ? blueprint?.id : null;
  const showBlueprint = (b: GarageBlueprint) => {
    setBlueprint(b);
    setMode("blueprint");
    setSelected(null);
    setView("canvas");
    setStep(3);
  };
  // Only "Nothing yet" asks: a repo's Next keeps what is chosen (its own design, unless a blueprint was shown).
  const designFooter =
    asking && viewing ? (
      <div className="stepnav stepnav--ask" role="group" aria-label={`Use ${viewing.name}?`}>
        <span>
          Use <b>{viewing.name}</b>?
        </span>
        <span className="row" style={{ gap: 8 }}>
          <button type="button" className="btn btn--quiet" onClick={() => setAsking(false)}>
            Keep Browsing
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => {
              if (labWf?.design) setDesignNote(`Started blank: this workflow isn't linked to ${labWf.design.name}.`);
              setLabLoad({ key: `blank@${Date.now()}`, wf: "blank" });
              setStep(3);
            }}
          >
            Start Blank
          </button>
          <button type="button" className="btn btn--primary" onClick={() => void useDesign(viewing)}>
            Use It
          </button>
        </span>
      </div>
    ) : (
      <StepNav
        step={2}
        onStep={(n) => {
          if (n === 3 && space === "lab" && viewing && viewing.id !== usedId) setAsking(true);
          else setStep(n);
        }}
      />
    );

  let body: React.ReactNode;
  if (page === "home") {
    body = (
      <Home
        repos={repos}
        resume={resume}
        onResume={() => setStep(step)}
        onStart={(s) => {
          setSpace(s);
          setStep(1);
        }}
        onOpenRepo={(id) => {
          setSpace("repo");
          chooseRepo(id);
          setStep(1);
        }}
        tour={
          <>
            {tour.data ? <TourEntry data={tour.data} onStart={() => go({ page: "tutorial", at: 1 })} /> : null}
            <TokensTourSlot onStart={() => go({ page: "tutorial", at: 1, track: "tokens" })} />
          </>
        }
        proof={tour.data?.run ? <RecordedProof data={tour.data} run={tour.data.run} /> : undefined}
      />
    );
  } else if (page === "tutorial" && tourTrack === "tokens") {
    body = (
      <TokensTutorialRoute
        at={tourAt}
        onAt={(at) => go({ page: "tutorial", at, track: "tokens" })}
        onOption={(to) => {
          if (to === "home") go({ page: "home" });
          else if (to === "first") go({ page: "tutorial", at: 1 });
          else {
            setSpace("repo");
            setStep(1);
          }
        }}
      />
    );
  } else if (page === "tutorial") {
    body = (
      <TutorialPage
        data={tour.data}
        error={tour.error}
        at={tourAt}
        onAt={(at) => go({ page: "tutorial", at })}
        onOption={(to) => {
          if (to === "home") go({ page: "home" });
          else {
            setSpace(to);
            setStep(1);
          }
        }}
      />
    );
  } else if (page === "score") {
    body = <RigExplainPage onMeasure={() => setStep(4)} />;
  } else if (page === "runs") {
    body = (
      <RunsPage
        repos={repos}
        currentRepoId={space === "repo" ? repoId : null}
        onOpenRepo={(id) => {
          setSpace("repo");
          chooseRepo(id);
          setStep(4);
        }}
        onOpenLab={(r) => void openLabRun(r)}
      />
    );
  } else if (page === "compare") {
    body = (
      <Compare
        agent={agent ? { id: agent.id, label: agent.label, ready: agent.ready, budget_cap: agent.budget_cap } : null}
        working={space === "lab" ? (labWf?.id ?? null) : null}
        onBack={() => setStep(3)}
        onOpen={(p) => {
          fromCompare(p);
          setStep(3);
        }}
        onWork={fromCompare}
        onShip={(p) => {
          fromCompare(p);
          setStep(5);
        }}
        onSignIn={() => setAgentOpen(true)}
      />
    );
  } else if (step === 1) {
    body = (
      <Describe
        space={chosenSpace}
        onSpace={setSpace}
        repos={repos}
        repoId={repoId}
        onRepo={chooseRepo}
        onDetach={async (id) => {
          await api.removeRepo(id);
          await loadRepos();
        }}
        labText={labGoal}
        onLabText={setLabGoal}
        repoText={repoText}
        onRepoText={(t) => {
          if (!repoId) return;
          const id = repoId;
          // Typed back to the saved goal: no draft any more.
          setGoalEdits((m) => {
            if (repoGoal !== null && t.trim() === repoGoal.trim()) {
              const { [id]: _, ...rest } = m;
              return rest;
            }
            return { ...m, [id]: t };
          });
          setGoalSaved(null);
        }}
        repoReady={repoGoal !== null}
        repoDirty={repoDirty}
        repoHasGoal={!!repoGoal?.trim()}
        repoSaved={goalSaved === repoId}
        onSave={saveRepoGoal}
        attach={<AttachForm onAttached={attached} />}
        onStep={setStep}
        templates={goalRules?.templates ?? null}
        template={keptTemplate(repoText, (repoId && goalPicks[repoId]) || data.project?.goal_template, goalRules)?.id ?? null}
        onTemplate={(t) => {
          if (!repoId) return;
          const id = repoId;
          setGoalPicks((m) => ({ ...m, [id]: t.id }));
          setGoalEdits((m) => (repoGoal !== null && t.text.trim() === repoGoal.trim() ? (({ [id]: _, ...rest }) => rest)(m) : { ...m, [id]: t.text }));
          setGoalSaved(null);
          requestAnimationFrame(() => document.getElementById("describe-repo-goal")?.focus());
        }}
      />
    );
  } else if (step === 2) {
    const garage = (
      <GaragePanel
        key={`${space}:${repoId ?? ""}`}
        repoId={inRepo ? repoId : null}
        useCase={useCase.trim() || null}
        autoRun
        onEditUseCase={() => setStep(1)}
        blueprint={space === "lab" ? labDesign : blueprint}
        openLabel={inRepo ? "Show on the Canvas" : "Use This Design"}
        onViewing={setViewing}
        onOpen={(b) => {
          if (space === "repo") showBlueprint(b);
          else void useDesign(b);
        }}
        onClose={() => {
          if (space === "lab") detachDesign();
          else {
            setBlueprint(null);
            setMode("current");
          }
        }}
      />
    );
    // What the goal is about (repo-goals: agent_words); null until those words have loaded.
    const agentGoal = useCase.trim() ? aboutTheAgent(useCase, goalRules) : false;
    // The catalog stays folded unless opened, or the goal is about what the app does (where a
    // blueprint may fit): keeping the repo's design is still the first card either way.
    const printsOpen = blueprintsOpen ?? (mode === "blueprint" || (useCase.trim() !== "" && agentGoal === false));
    body = (
      <StepPage
        step={2}
        title={inRepo ? `Keep ${repo.name}'s Design, or Start from Another` : "Choose a Design"}
        lead={
          inRepo
            ? "A repo keeps its own design by default: Build changes the coding agent's setup on its real code. A catalog blueprint is there if you'd rather start from one."
            : useCase.trim()
              ? "Architectures ranked for what you described. Open one to see its parts, trade-offs and parameters."
              : "Describe what you're building first (Describe) to rank these; until then, browse them all."
        }
        footer={designFooter}
      >
        {inRepo
          ? mismatch.map((w) => (
              <p key={w} className="notice notice--warning small" role="status" data-testid="stack-mismatch">
                {w} Rig measures the agent on this repo's own code, so a goal about another stack won't be tested here.
              </p>
            ))
          : null}
        {inRepo ? (
          // A repo keeps its own design unless a blueprint is chosen: what the goal is about only
          // changes the words, never which way is the default.
          <div className={`keep-card${agentGoal ? " keep-card--first" : ""}`} data-testid="keep-card">
            <div>
              {agentGoal ? <span className="keep-card__tag small">Recommended</span> : null}
              <b>{agentGoal ? `Keep ${repo.name}'s Design and Improve Its Agent Setup` : `Keep ${repo.name}'s Design`}</b>
              <p className="small muted">
                {!useCase.trim()
                  ? "No goal yet, so nothing is recommended. Write one in Describe; Build then changes the agent's setup on this repo's own code."
                  : agentGoal
                    ? `Your goal is about how the coding agent works in ${repo.name} (its instructions, skills, checks and spend), not what the app is built from: change those parts on Build and measure each change.`
                    : agentGoal === false
                      ? `Your goal reads like what the app does rather than how the coding agent works. Keeping ${repo.name}'s design still measures the agent on its own code; a blueprint may fit better if you're reshaping the app.`
                      : "Reading your goal…"}
              </p>
            </div>
            <button
              type="button"
              className={`btn${mode !== "blueprint" ? " btn--primary" : ""}`}
              onClick={() => {
                setBlueprint(null);
                setMode("current");
                setStep(3);
              }}
            >
              Keep {repo.name}'s Design
            </button>
          </div>
        ) : null}
        {space === "lab" && labDesign ? (
          <p className="notice small">
            Using <b>{labDesign.name}</b>. Pick another below, or go on to Build to change its parts.
          </p>
        ) : null}
        {inRepo ? (
          // The catalog is folded away for a repo: open it to start from a blueprint instead.
          <details
            className="blueprints"
            open={printsOpen}
            onToggle={(e) => setBlueprintsOpen(e.currentTarget.open)}
            data-testid="blueprints"
          >
            <summary>
              <span className="blueprints__title">Start from a Blueprint Instead</span>
              <span className="small muted">
                {blueprint && mode === "blueprint"
                  ? ` · showing ${blueprint.name} on Build`
                  : agentGoal === false
                    ? " · architectures from the catalog, ranked for your goal: may fit better when the goal is about the app"
                    : " · architectures from the catalog, ranked for your goal"}
              </span>
            </summary>
            {printsOpen ? garage : null}
          </details>
        ) : (
          garage
        )}
      </StepPage>
    );
  } else if (step === 5) {
    body = (
      <StepPage
        step={5}
        title="Ship It to Any Agent"
        lead="BUILD.md is a brief any coding agent can follow. For a repo: the changes to make in it and how to check them. With nothing yet: a new project's parts, parameters and layout. rig.json has the same as data."
        footer={<StepNav step={5} onStep={setStep} />}
      >
        {passed ? (
          // Said once, when the guide becomes a workspace; quiet, so the brief stays the page.
          <p className="small muted shipnote">
            That's the whole path: from now on the steps are tabs at the top, and Rig reopens where you were. ⋯ → Show the Guide
            Again brings the numbered steps back.{" "}
            <button type="button" className="linkish small" onClick={() => setPassed(false)}>
              Got It
            </button>
          </p>
        ) : null}
        {space === "lab" ? (
          labWf ? (
            <BuildSpecView bare source="workflow" workflow={labWf} design={labWf.design ? { id: labWf.design.id, values: labWf.design.parameters } : null} useCase={useCase} saveLabel="Save to the Library" />
          ) : labDesign ? (
            <BuildSpecView bare source="design" design={labDesign} useCase={useCase} saveLabel="Save to the Library" />
          ) : (
            <p className="notice small">Choose or build a workflow in Build first; its brief appears here.</p>
          )
        ) : inRepo ? (
          <>
            <ShipToggle source={specSource} onSource={setSpecSource} accepted={acceptedN} diff={acceptedDiff} />
            {canvasNote ? <p className="small muted">{canvasNote}</p> : null}
            <BuildSpecView
              bare
              source={specSource}
              removed={store.state.removed.filter((id) => id.startsWith("arch:")).map((id) => id.slice(5))}
              added={planAdded}
              design={blueprint}
              useCase={useCase}
            />
          </>
        ) : (
          <p className="notice small">Add a repo in Describe, or choose "Nothing Yet" there.</p>
        )}
      </StepPage>
    );
  } else if (space === "lab") {
    body = null; // the Lab below stays mounted across steps 3 and 4, so its workflow is kept
  } else if (!inRepo) {
    body = (
      <StepPage step={step} title="Add a Repo First" lead="This step works on a repo's code. Add one in Describe, or choose Nothing Yet there." footer={<StepNav step={step} onStep={setStep} />}>
        <span />
      </StepPage>
    );
  } else if (step === 4) {
    body = (
      <>
        {stageHead}
        <main className="measure" id="main">
          <section className="measure__col" aria-label="Tasks">
            <h2 className="measure__title">Tasks to Measure On</h2>
            <p className="small muted">
              Each task
              <Term k="task" /> comes from your repo, with a check that decides pass or fail.
            </p>
            {data.project ? (
              <ScenariosPanel
                project={data.project}
                scenarios={data.scenarios}
                workflow={workflow}
                onChanged={data.reload}
                goal={useCase}
                onEditGoal={() => setStep(1)}
                preset={taskPreset}
                onPresetUsed={() => setTaskPreset(null)}
              />
            ) : (
              <p className="muted">Reading the repo…</p>
            )}
          </section>
          <section className="measure__col" aria-label="Run">
            <h2 className="measure__title">Rig &amp; Measure</h2>
            <p className="small muted" data-testid="measure-says">
              {mrules?.before_after?.run_says?.[measureMode] ?? "Every task runs twice, with and without the change, so the difference is the change's."}{" "}
              <button type="button" className="linkish" onClick={() => setStep(3)}>
                Change What's Measured on Build
              </button>
            </p>
            <RunPanel
              empty={<MeasureEmpty rules={mrules} notRunnable={notRunnable} onBuild={() => setStep(3)} />}
              candidates={candidates}
              configs={data.treatments?.configs ?? []}
              metricHint={data.project?.goal_metric}
              initial={runFor}
              codeFor={codeFor}
              onCodeForUsed={() => setCodeFor(null)}
              onMode={setMeasureMode}
              scenarios={data.scenarios}
              agent={agent}
              repoId={repoId}
              onSignIn={() => setAgentOpen(true)}
              goal={useCase}
              experiments={data.experiments}
              onChanged={async () => {
                await data.reload();
                setEstimates({});
                asked.current.clear();
              }}
            />
          </section>
        </main>
      </>
    );
  } else {
    body = (
      <>
        {stageHead}
        <div className="switch segmented" role="tablist" aria-label="View">
          {(
            [
              ["library", "Library"],
              ["canvas", "Canvas"],
              ["details", "Details"],
            ] as const
          ).map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={view === id} onClick={() => setView(id)}>
              {label}
            </button>
          ))}
        </div>
        <main className={`panes panes--one panes--view-${view}${panes.className}`} id="main" style={panes.style}>
          <Palette
            repoId={repoId ?? ""}
            treatments={data.treatments}
            selected={libItem ? `lib:${libItem.data}` : null}
            onAdd={addFromLibrary}
            onInspect={(lib) => {
              setLibItem(lib);
              setTab("selected");
              setView("details");
            }}
          />

          <section className="pane pane--canvas" aria-label="Canvas">
            {!panes.left ? (
              <PaneResizer
                side="left"
                width={panes.widths.left}
                min={panes.limits.left[0]}
                max={panes.limits.left[1]}
                label="Library width"
                onResize={(w) => panes.resize("left", w)}
                onReset={() => panes.reset("left")}
              />
            ) : null}
            {!panes.right ? (
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
            {data.error ? (
              <div className="pane__body">
                <p className="notice notice--error">{data.error}</p>
              </div>
            ) : !data.project ? (
              <div className="pane__body">
                <p className="muted">Reading the repo…</p>
              </div>
            ) : (
              <RepoCanvas
                repoName={data.project.name}
                project={data.project}
                goal={useCase}
                architecture={mode === "blueprint" && blueprint ? blueprint.architecture : mode === "suggested" && proposed ? proposed : data.architecture}
                blueprint={mode === "blueprint" && blueprint !== null}
                flow={flow}
                workflow={workflow}
                scenarios={data.scenarios}
                treatments={{
                  repo: data.treatments?.repo ?? [],
                  user: data.treatments?.user ?? [],
                  installed: data.treatments?.installed ?? [],
                }}
                store={store}
                freeSlot={freeSlot}
                belowAll={belowAll}
                clearArea={clearArea}
                reveal={reveal}
                besideSlot={besideSlot}
                estimates={estimates}
                verdicts={verdicts}
                previewing={mode === "suggested" && Boolean(preview)}
                selected={selected?.id ?? null}
                onSelect={(id, info) => {
                  if (mode === "blueprint") return;
                  setSelected(id && info ? { id, info } : null);
                  setLibItem(null);
                  setTab("selected");
                }}
                onDrop={(d, x, y, near, drop) => void dropped(d, Math.round(x), Math.round(y), near, drop)}
                overlays={
                  <>
                    <PaneToggles
                      left={panes.left}
                      right={panes.right}
                      onLeft={panes.toggleLeft}
                      onRight={panes.toggleRight}
                      leftName="library"
                      rightName="details panel"
                    />
                    {flow ? (
                      <div className="flowcard" aria-live="polite">
                        <div className="flowcard__head">
                          <strong>{flow.name}</strong>
                          <button type="button" className="linkish small" onClick={() => setFlowName(null)}>
                            Close
                          </button>
                        </div>
                        <ol>
                          {flow.steps.map((st, n) => (
                            <li key={n}>
                              <span className="flowcard__n num">{n + 1}</span>
                              <span>
                                <b>
                                  {names.get(`arch:${st.from}`) ?? st.from} → {names.get(`arch:${st.to}`) ?? st.to}
                                </b>
                                {st.what ? <span className="small muted"> · {st.what}</span> : null}
                              </span>
                            </li>
                          ))}
                        </ol>
                      </div>
                    ) : null}
                    {mode === "blueprint" && blueprint ? (
                      <div className="modebar small" role="status">
                        <span>
                          Blueprint from the catalog, not your repo. Undo and Reset don't apply to it. Choose "As It Is" to go back.
                        </span>
                      </div>
                    ) : null}
                    {mode === "suggested" ? (
                      <div className="modebar small" role="status">
                        {diff && diff.suggestions && !(diff.added.length + diff.removed.length + diff.connected + diff.disconnected) ? (
                          <span data-testid="diff-notes-only">{notesOnly(acceptedN, Boolean(preview))}</span>
                        ) : diff && diff.suggestions ? (
                          <div className="difflegend">
                            <span>
                              {preview
                                ? "Previewing one open suggestion (not accepted yet):"
                                : diff.drawn != null && diff.drawn < diff.suggestions
                                  ? `${diff.suggestions} accepted · ${diff.drawn} drawn here, ${diff.suggestions - diff.drawn} only in the brief:`
                                  : `${plural(diff.suggestions, "accepted suggestion")} applied:`}
                            </span>
                            <span className="difflegend__item">
                              <span className="block__flag block__flag--new">New</span> {plural(diff.added.length, "part")}
                            </span>
                            <span className="difflegend__item">
                              <span className="block__flag block__flag--removed">Removed</span> {plural(diff.removed.length, "part")}
                            </span>
                            <span className="difflegend__item">
                              <span className="difflegend__swatch" aria-hidden="true" /> {plural(diff.connected, "new link")}
                            </span>
                            <span className="difflegend__item">
                              <span className="difflegend__swatch difflegend__swatch--removed" aria-hidden="true" /> {diff.disconnected} cut
                            </span>
                          </div>
                        ) : (
                          <span>
                            Nothing accepted yet, so this is the same as "As It Is". Accept a suggestion on the right to draw it here; Preview
                            shows one without accepting it.
                          </span>
                        )}
                      </div>
                    ) : null}
                    <div className="canvas__top canvas__top--repo">
                      <div className="viewmode segmented" role="radiogroup" aria-label="Architecture">
                        <button
                          type="button"
                          role="radio"
                          aria-checked={mode === "current"}
                          onClick={() => {
                            setMode("current");
                            setPreview(null);
                            setBlueprint(null);
                            setViewPicked(true);
                          }}
                        >
                          As It Is
                        </button>
                        <button
                          type="button"
                          role="radio"
                          aria-checked={mode === "suggested"}
                          onClick={() => {
                            setMode("suggested");
                            setBlueprint(null);
                            setTab("improve");
                            setView("details");
                            setViewPicked(true);
                          }}
                        >
                          {/* Only what was accepted is drawn here; open ones and what the brief gets are in the title. */}
                          <span title={diff ? suggestedTitle(diff) : undefined} data-testid="suggested-count">
                            With Accepted · {acceptedN}
                          </span>
                        </button>
                        {blueprint ? (
                          <button type="button" role="radio" aria-checked={mode === "blueprint"} onClick={() => setMode("blueprint")}>
                            Blueprint: {blueprint.name}
                          </button>
                        ) : null}
                      </div>
                      <div className="editbar" role="group" aria-label="Canvas edits">
                        <button
                          type="button"
                          className="btn btn--small btn--quiet"
                          disabled={mode === "blueprint" || !store.canUndo}
                          onClick={store.undo}
                          aria-label="Undo"
                          title="Undo the last change (Ctrl+Z or Cmd+Z). Press ? for every shortcut."
                        >
                          <Undo2 size={14} aria-hidden="true" />
                          <span className="editbar__text">Undo</span>
                        </button>
                        <button
                          type="button"
                          className="btn btn--small btn--quiet"
                          disabled={mode === "blueprint" || store.isEmpty}
                          aria-label="Reset"
                          onClick={() => {
                            store.reset();
                            setSelected(null);
                          }}
                          title="Remove what you placed, drew and moved on this canvas. Undo brings it back."
                        >
                          <RotateCcw size={14} aria-hidden="true" />
                          <span className="editbar__text">Reset</span>
                        </button>
                        <ShortcutsSheet
                          button={false}
                          items={[
                            { keys: ["/", "+"], does: "Search the library, to add from it" },
                            { keys: ["Mod+Z"], does: "Undo the last change" },
                            { keys: ["Delete"], does: "Remove the selected block from the plan" },
                            { keys: ["Esc"], does: "Close a menu, clear the search, or close this sheet" },
                            { keys: ["?"], does: "Show these shortcuts" },
                          ]}
                        />
                      </div>
                      {/* One control for any number of flows, instead of a row of chips that wraps. */}
                      {flows.length && mode === "current" ? (
                        <label className="flowpick">
                          <span className="visually-hidden">Show a flow</span>
                          <select
                            className="select select--small"
                            value={flowName ?? ""}
                            onChange={(e) => setFlowName(e.target.value || null)}
                          >
                            <option value="">Flows · {flows.length}</option>
                            {flows.map((f) => (
                              <option key={f.name} value={f.name}>
                                {f.name}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : null}
                      {/* One line, so it never covers the canvas; the full list is in its title. */}
                      {mode !== "blueprint" && (known.length || added.length || store.state.removed.length) ? (
                      <div
                        className="layer"
                        title={
                          known.length
                            ? known
                                .map(({ name, e, v }) =>
                                  v ? `${name}: last run Rig ${v.score ?? "–"}, ${v.word}` : `${name}: estimated ${(e.likely ?? 0) > 0 ? "+" : ""}${e.likely} pts`,
                                )
                                .join("\n")
                            : "Drag a skill from the library to see its estimate"
                        }
                      >
                        <ShieldCheck size={13} aria-hidden="true" />
                        <span className="layer__line">
                          {[
                            added.length ? `${added.length} change${added.length === 1 ? "" : "s"} on the canvas` : "",
                          store.state.removed.length ? `${store.state.removed.length} removed from the plan` : "",
                            ...known.map(({ name, e, v }) => (v ? `${name} Rig ${v.score ?? "–"} · ${v.word}` : `${name} ≈${(e.likely ?? 0) > 0 ? "+" : ""}${e.likely}`)),
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </div>
                      ) : null}
                      <ArchifyMap
                        key={repoId}
                        architecture={data.architecture}
                        agent={agent ? { id: agent.id, label: agent.label } : null}
                        onMapped={data.reload}
                      />
                      {data.workflows.length > 1 ? (
                        <WorkflowPicker
                          workflows={data.workflows}
                          value={workflow?.id ?? null}
                          onChange={(wid) => {
                            remember("pg.workflow", wid);
                            setWorkflowId(wid);
                          }}
                        />
                      ) : null}
                    </div>
                  </>
                }
              />
            )}
          </section>

          <section className="pane" aria-label="Details">
            <div className="pane__head" style={{ paddingBottom: 0 }}>
              <div className="tabs tabs--boxed" role="tablist" style={{ width: "100%" }}>
                {(
                  [
                    ["selected", "Selected"],
                    ["improve", "Suggestions"],
                  ] as const
                ).map(([id, label]) => (
                  <button key={id} type="button" role="tab" className="tab" aria-selected={tab === id} onClick={() => setTab(id)}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="pane__body" role="tabpanel">
              {tab === "selected" && libItem ? (
                <LibraryDetail lib={libItem} onAdd={addFromLibrary} onSaved={() => void data.reload()} />
              ) : tab === "selected" ? (
                <Inspector
                  info={selected ? (infoFor(selected.id) ?? selected.info) : null}
                  nodeId={selected?.id ?? null}
                  order={order}
                  onGo={(id) => {
                    setLibItem(null);
                    const info = infoFor(id);
                    if (info) setSelected({ id, info });
                  }}
                  store={store}
                  scenarios={data.scenarios}
                  suggestions={data.treatments?.suggested ?? []}
                  estimate={selected ? estimates[selected.id] : undefined}
                  onSharpen={selected && skillNodes.some((s) => s.id === selected.id) ? () => sharpen(selected.id) : undefined}
                  names={linkNames}
                  flows={data.architecture?.connections ?? []}
                  onInstalled={async (cardId, path, name) => {
                    store.updateCard(cardId, { kind: "skill", ref: path, name });
                    await data.reload();
                  }}
                  onTest={(path) => {
                    setRunFor(path);
                    setStep(4);
                  }}
                  onParts={(cardId, repo, name) => void addParts(repo, name, { replace: cardId })}
                  placeBeside={(id) => besideSlot.current?.(id) ?? freeSlot.current?.() ?? null}
                  origins={origins}
                  verdict={selected ? verdicts[selected.id] : undefined}
                  onMeasureCode={measureCode}
                />
              ) : (
                <SuggestionsPanel
                  key={repoId}
                  agent={agent ? { id: agent.id, label: agent.label } : null}
                  preview={preview}
                  names={names}
                  onPreview={(id) => {
                    setPreview(id);
                    if (id) setMode("suggested");
                  }}
                  onChanged={() => setDecisions((n) => n + 1)}
                  onAddTask={(stepName) => {
                    setTaskPreset({ step: stepName, key: Date.now() });
                    setStep(4);
                  }}
                  onMeasure={(p) => measureCode(p.title)}
                />
              )}
            </div>
          </section>
      </main>
      </>
    );
  }

  const labShown = space === "lab" && !page && (step === 3 || step === 4);
  return (
    <Guide.Provider value={{ workspace, onSkip: skipGuide }}>
      <div ref={appRef} className={`app app--one app--step-${page ?? step}${workspace ? " app--workspace" : ""}`}>
        {notice}
        {topbar}
        {inRepo && repoDirty && step > 1 && !page ? (
          <div className="goalbar small" role="status" aria-label="Unsaved goal">
            {repoText.trim() ? (
              <span>
                <b>Unsaved goal</b> — only in this browser. Every step uses it; the repo still has its saved one.
              </span>
            ) : (
              <span>
                <b>Unsaved goal</b> — cleared, only in this browser: the steps go without one. Write one in Describe to save it.
              </span>
            )}
            <button type="button" className="btn btn--small btn--primary" disabled={savingGoal || !repoText.trim()} onClick={() => void saveFromBar()}>
              {savingGoal ? "Saving…" : "Save Goal"}
            </button>
          </div>
        ) : null}
        {body}
        {space === "lab" ? (
          <div className="labhost" hidden={!labShown}>
            {labShown ? stageHead : null}
            {link ? (
              <p className="labhost__design small" role="status">
                <span style={{ flex: 1 }}>
                  Design: <b>{link.name}</b>
                  {link.handoff && link.handoff.discipline !== "research"
                    ? ` · set up for ${link.handoff.discipline_label}${link.handoff.matched.length ? ` (your use case says '${link.handoff.matched.slice(0, 2).join("', '")}')` : ""}`
                    : ""}
                  {" · "}your edits stay linked to it, and BUILD.md has its parts and parameters.
                  {link.handoff?.note ? <span className="labhost__note"> {link.handoff.note}</span> : null}
                </span>
                <button type="button" className="btn btn--small btn--quiet" onClick={detachDesign}>
                  Detach from Design
                </button>
              </p>
            ) : designNote ? (
              <p className="labhost__design small" role="status">
                <span style={{ flex: 1 }}>{designNote}</span>
                <button type="button" className="btn btn--small btn--quiet" onClick={() => setDesignNote(null)}>
                  Dismiss
                </button>
              </p>
            ) : null}
            <Lab
              agentLabel={agent?.label ?? "your agent"}
              agent={agent ? { id: agent.id, label: agent.label, ready: agent.ready, budget_cap: agent.budget_cap } : null}
              stage={step === 4 ? "measure" : "build"}
              onBuild={() => setStep(3)}
              onWorkflow={setLabWf}
              load={labLoad}
              onLoaded={() => setLabLoad(null)}
              onSignIn={() => setAgentOpen(true)}
              useCase={useCase}
              onOpenCompare={openCompare}
            />
          </div>
        ) : null}
      </div>
    </Guide.Provider>
  );
}
