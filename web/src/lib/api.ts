import type {
  BeforeAfterCompare,
  BeforeAfterRefs,
  MetricId,
  SuiteView,
  ComparePlan,
  CompareJobView,
  CompareStanding,
  AblateJob,
  AgentInfo,
  Architecture,
  GarageBlueprint,
  GarageCatalog,
  GarageRecommendation,
  GarageWorkflow,
  RunForecast,
  BenchInfo,
  BenchMade,
  PublicBenches,
  Improvement,
  Lab,
  Forensics,
  LabMatrix,
  LabResult,
  LabStarted,
  ProbePrice,
  LabWorkflow,
  LocalModels,
  LocalTemplateFix,
  LocalTest,
  LoginJob,
  Placement,
  Proposal,
  BuildSource,
  DesignChoice,
  BuildSpec,
  CanvasAdded,
  Proposed,
  Recommendation,
  RigExplain,
  TokensTutorial,
  Tutorial,
  Suggestions,
  MapJob,
  CatalogCategory,
  CatalogPage,
  CatalogView,
  DoctorCheck,
  Estimate,
  RepoRef,
  RemoteJob,
  RemoteProvider,
  RemoteRepoRow,
  ActiveRun,
  RepoParts,
  RepoSkillRef,
  DryRun,
  ExperimentDetail,
  ExperimentRow,
  Generated,
  Project,
  RunEvent,
  ProveStatus,
  Scenario,
  Started,
  Treatments,
  TryJob,
  TryPrice,
  Workflow,
} from "./types";

/** Which bench and tier a baseline check runs, and on what: a workflow's session model, a model, or a local model. */
type ProbeBody = { bench: string; tier?: string; agent?: string; workflow?: LabWorkflow | null; model?: string | null; local_model?: string | null };

/** More for a brief: the design chosen in step 2, and (with nothing yet) the use case. */
export type BuildMore = { design?: DesignChoice; use_case?: string | null };

/** An error the API explained. `problems` lists each rejected part of a generated plan. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly problems: string[] = [],
  ) {
    super(message);
  }
}

let currentRepo: string | null = null;

/** Every per-repo request carries ?repo=<id> once a repo is chosen. */
export function setRepo(id: string | null): void {
  currentRepo = id;
}

function withRepo(path: string): string {
  if (!currentRepo || !path.startsWith("/api/") || GLOBAL.some((g) => path.startsWith(g)) || /[?&]repo=/.test(path)) return path;
  return `${path}${path.includes("?") ? "&" : "?"}repo=${encodeURIComponent(currentRepo)}`;
}

const GLOBAL = ["/api/runs/", "/api/repos", "/api/remotes", "/api/agents", "/api/credentials", "/api/catalog/", "/api/garage/", "/api/doctor", "/api/lab", "/api/local-models", "/api/tutorial"];

/** The server's own words for an error: FastAPI sends a string, or for a malformed request a
 * list of {loc, msg}. */
function detailText(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const where = (d.loc ?? []).filter((x) => x !== "body").join(".");
        return `${where ? `${where}: ` : ""}${d.msg ?? String(d)}`;
      })
      .join("; ");
  }
  return null;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  path = withRepo(path);
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["content-type"] = "application/json";
  }
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch (e) {
    // Only here did the request never reach the engine: every other failure has its answer.
    // Blocked or aborted on the way (a lost connection, an extension, a page leaving, a stopped
    // engine): say only what is known. Never blame the engine for a request that never left.
    if (e instanceof DOMException && e.name === "AbortError") throw new ApiError("The request didn't go through (cancelled).", 0);
    throw new ApiError("The request didn't go through (network).", 0);
  }
  let text = "";
  try {
    text = await res.text();
  } catch {
    throw new ApiError("The engine's answer was cut off. Try again.", res.status);
  }
  let data: { detail?: unknown; problems?: string[] } | null = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    // Not JSON: the engine crashed (a plain "Internal Server Error") or something else answered.
    throw new ApiError(
      res.ok
        ? "The engine sent a reply that isn't JSON."
        : res.status >= 500
          ? `The engine hit an error (HTTP ${res.status}) and couldn't finish this. Its terminal shows the details; reloading usually helps.`
          : `Request failed (HTTP ${res.status})${text.trim() ? `: ${text.trim().slice(0, 200)}` : "."}`,
      res.status,
    );
  }
  if (!res.ok) {
    throw new ApiError(detailText(data?.detail) ?? `Request failed (HTTP ${res.status}).`, res.status, data?.problems ?? []);
  }
  return data as T;
}

export interface ExperimentRequest {
  /** A skill, hook, MCP server or instructions file; left out with `before_after`. */
  treatment_path?: string;
  /** A code change measured before and after: the base commit and the after side (null: the
   * uncommitted working tree). */
  before_after?: { base: string; after: string | null };
  budget: number;
  n: number;
  model: string;
  agent: string;
  scenario_ids: string[];
  nudge_prompt?: boolean | null;
  /** The engine plans the pairs for this size (a full run grows with the budget), not n. */
  size?: "pilot" | "full";
  /** What the run is scored on (rig-score: Metric); left out, the goal's hint or the pass rate. */
  metric?: MetricId;
  /** Claude Code on a model served on this machine (its id in /api/local-models): free, no sign-in. */
  local_model?: string | null;
  /** "Keep going until it's decided": add pairs while it's undecided, up to the budget (judge-experiment: auto_extend). */
  auto?: boolean;
}

const ESTIMATES_AT_ONCE = 2;
let estimating = 0;
const waiting: (() => void)[] = [];

/** Run `fn` when fewer than ESTIMATES_AT_ONCE estimates are in flight. */
function inTurn<T>(fn: () => Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const go = () => {
      estimating += 1;
      fn()
        .then(resolve, reject)
        .finally(() => {
          estimating -= 1;
          waiting.shift()?.();
        });
    };
    if (estimating < ESTIMATES_AT_ONCE) go();
    else waiting.push(go);
  });
}

export const api = {
  // `removed`: architecture component ids taken off the canvas, left out of the brief.
  buildSpec: (source: BuildSource, workflow?: unknown, removed: string[] = [], added?: CanvasAdded, more: BuildMore = {}) =>
    request<BuildSpec>("POST", "/api/buildspec", { source, workflow, removed, added, ...more }),
  buildSpecSave: (source: BuildSource, workflow?: unknown, removed: string[] = [], added?: CanvasAdded, more: BuildMore = {}) =>
    request<{ dir: string; markdown: string; json: string }>("POST", "/api/buildspec/save", { source, workflow, removed, added, ...more }),
  project: () => request<Project>("GET", "/api/project"),
  intake: () => request<Project>("POST", "/api/intake"),
  upload: (files: File[]) => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    return request<{ added: [string, string][]; skipped: string[] }>("POST", "/api/sources", form);
  },
  /** A goal (saved or a draft) against the chosen repo: a language it names that the repo has no files in. */
  goalCheck: (use_case: string) => request<{ warnings: string[] }>("POST", "/api/goal/check", { use_case }),
  useCase: (text: string, template?: string | null) =>
    request<{ use_case: string; goal_template: string | null; goal_metric: string | null }>("PUT", "/api/usecase", template ? { text, template } : { text }),
  rules: <T,>(name: "measurability" | "repo-goals") => request<T>("GET", `/api/rules/${name}`),
  /** `useCase`: an unsaved draft goal to write from instead of the saved one (never saved by this). */
  dryRun: (mix: string, model: string, useCase?: string) =>
    request<DryRun>("POST", "/api/generate", { mix, model, dry_run: true, use_case: useCase }),
  generate: (mix: string, model: string, useCase?: string) =>
    request<Generated>("POST", "/api/generate", { mix, model, use_case: useCase }),
  workflows: () => request<Workflow[]>("GET", "/api/workflows"),
  scenarios: () => request<Scenario[]>("GET", "/api/scenarios"),
  approve: (id: string) => request<Scenario>("POST", `/api/scenarios/${encodeURIComponent(id)}/approve`),
  setCheck: (id: string, check: string) => request<Scenario>("PUT", `/api/scenarios/${encodeURIComponent(id)}/check`, { check }),
  prove: (id: string) => request<{ status: string }>("POST", `/api/scenarios/${encodeURIComponent(id)}/prove`),
  proveStatus: (id: string) => request<ProveStatus>("GET", `/api/scenarios/${encodeURIComponent(id)}/prove`),
  treatments: () => request<Treatments>("GET", "/api/treatments"),
  experiments: () => request<ExperimentRow[]>("GET", "/api/experiments"),
  experiment: (id: number) => request<ExperimentDetail>("GET", `/api/experiments/${id}`),
  start: (body: ExperimentRequest) => request<Started>("POST", "/api/experiments", body),
  beforeAfterRefs: () => request<BeforeAfterRefs>("GET", "/api/before-after/refs"),
  beforeAfterCompare: (base: string, after: string | null) =>
    request<BeforeAfterCompare>("POST", "/api/before-after/compare", { base, after }),
  /** Save an edited copy of the repo's CLAUDE.md (or AGENTS.md) to measure against the committed one. */
  saveInstructions: (body: { text: string; file?: "CLAUDE.md" | "AGENTS.md"; name?: string }) =>
    request<{ path: string; name: string; file: string }>("POST", "/api/treatments/instructions", body),
  doctor: () => request<DoctorCheck[]>("GET", "/api/doctor"),
  repos: () => request<RepoRef[]>("GET", "/api/repos"),
  addRepo: (path: string) => request<RepoRef>("POST", "/api/repos", { path }),
  remotesStatus: () => request<RemoteProvider[]>("GET", "/api/remotes/status"),
  setRemoteToken: (provider: string, value: string) =>
    request<{ account: string | null }>("PUT", `/api/remotes/${provider}/token`, { value }),
  clearRemoteToken: (provider: string) => request<unknown>("DELETE", `/api/remotes/${provider}/token`),
  remoteRepos: (provider: string, q: string) =>
    request<RemoteRepoRow[]>("GET", `/api/remotes/${provider}/repos?q=${encodeURIComponent(q)}`),
  cloneRepo: (url: string) => request<{ job: string }>("POST", "/api/repos/remote", { url }),
  cloneJob: (job: string) => request<RemoteJob>("GET", `/api/repos/remote/${job}`),
  pullRepo: (id: string) => request<{ head: string }>("POST", `/api/repos/${id}/pull`),
  removeRepo: (id: string) => request<{ removed: string }>("DELETE", `/api/repos/${id}`),
  mapStatus: () => request<MapJob>("GET", "/api/architecture/map"),
  mapArchitecture: (agent: string) => request<MapJob>("POST", "/api/architecture/map", { agent }),
  architecture: (refresh = false) => request<Architecture>("GET", `/api/architecture${refresh ? "?refresh=true" : ""}`),
  agents: () => request<AgentInfo[]>("GET", "/api/agents"),
  signIn: (agent: string, option: string, value: string) =>
    request<{ ready: boolean }>("PUT", "/api/credentials", { agent, option, value }),
  login: (agent: string) => request<LoginJob>("POST", `/api/agents/${agent}/login`),
  loginStatus: (agent: string) => request<LoginJob>("GET", `/api/agents/${agent}/login`),
  cancelLogin: (agent: string) => request<LoginJob>("DELETE", `/api/agents/${agent}/login`),
  signOut: (agent: string) => request<{ ready: boolean }>("DELETE", `/api/credentials/${agent}`),
  /** "all": every kind at once, to search from the Library's home. */
  catalog: (category: CatalogCategory | "all", view: CatalogView, q: string) =>
    request<CatalogPage>(
      "GET",
      `/api/catalog?category=${category}&view=${view}&q=${encodeURIComponent(q)}`,
    ),
  suggestions: () => request<Suggestions>("GET", "/api/suggestions"),
  decide: (id: string, state: Proposal["state"]) => request<{ id: string }>("PUT", `/api/suggestions/${id}`, { state }),
  garageCatalog: () => request<GarageCatalog>("GET", "/api/garage/catalog"),
  rigExplain: () => request<RigExplain>("GET", "/api/rig-score"),
  /** The tutorial's example space: never carries ?repo=, and reads nothing of yours. */
  tutorial: () => request<Tutorial>("GET", "/api/tutorial"),
  /** The repo tutorial (fewer tokens): the same, for its own example. */
  tutorialTokens: () => request<TokensTutorial>("GET", "/api/tutorial/tokens"),
  glossary: () => request<{ terms: Record<string, { term: string; short: string }> }>("GET", "/api/glossary"),
  garageEntry: (id: string) => request<GarageBlueprint>("GET", `/api/garage/catalog/${encodeURIComponent(id)}`),
  garageRecommend: (use_case: string, repo: string | null, explain: boolean) =>
    request<GarageRecommendation>("POST", "/api/garage/recommend", { use_case, repo, explain }),
  proposed: (preview?: string) =>
    request<Proposed>("GET", `/api/architecture/proposed${preview ? `?preview=${encodeURIComponent(preview)}` : ""}`),
  review: (agent: string) => request<MapJob>("POST", "/api/suggestions/review", { agent }),
  reviewStatus: () => request<MapJob & { count?: number }>("GET", "/api/suggestions/review"),
  place: (item: { name: string; description?: string; topics?: string[]; category?: string; theme?: string }) =>
    request<Placement>("POST", "/api/place", item),
  /** Rough picks by default; `model: true` asks the model to pick (a paid call). */
  recommend: (category: CatalogCategory, refresh = false, model = false) =>
    request<Recommendation>("GET", `/api/recommend?category=${category}${refresh ? "&refresh=true" : ""}${model ? "&model=true" : ""}`),
  draft: (body: { name: string; need: string; what: string; improves?: string | null }) =>
    request<{ name: string; text: string; improves: string | null }>("POST", "/api/draft", body),
  saveDraft: (body: { name: string; text: string; improves?: string | null }) =>
    request<{ path: string; name: string }>("POST", "/api/draft/save", body),
  lab: () => request<Lab>("GET", "/api/lab"),
  benches: () => request<BenchInfo[]>("GET", "/api/lab/benches"),
  calibrate: (bench: string) => request<NonNullable<BenchInfo["calibration"]>>("POST", `/api/lab/benches/${bench}/calibrate`),
  labRun: (body: {
    workflow: LabWorkflow;
    bench: string;
    size: "pilot" | "full";
    budget: number;
    agent: string;
    auto: boolean;
    local_model?: string | null;
    reuse_baseline?: boolean;
    nudge_prompt?: boolean | null;
    improved_from?: number | null;
    tier?: string;
    /** What the run is scored on (rig-score: Metric); left out, the pass rate. */
    metric?: MetricId;
  }) =>
    request<LabStarted>("POST", "/api/lab/run", body),
  /** A baseline check's price: the agent alone on each task once (no sign-in, no model call). */
  probePrice: (body: ProbeBody) => request<ProbePrice>("POST", "/api/lab/probe/price", body),
  /** Start a baseline check, capped at its price. */
  probe: (body: ProbeBody & { budget?: number }) => request<LabStarted & { price: ProbePrice }>("POST", "/api/lab/probe", body),
  suiteRun: (body: { workflow: LabWorkflow; budget: number; agent: string; size: "pilot" | "full"; metric?: MetricId }) =>
    request<{ job: string; benches: string[]; metric: MetricId }>("POST", "/api/lab/suite", body),
  suiteGet: (job: string) => request<SuiteView>("GET", `/api/lab/suite/${job}`),
  suiteStop: (job: string) => request<{ stopping: boolean }>("POST", `/api/lab/suite/${job}/stop`),
  /** Measuring 2 to 4 workflows on one bench, priced (no sign-in, no model call). */
  comparePlan: (body: { workflows: LabWorkflow[]; bench: string; budget: number; agent: string; size: "pilot" | "full" }) =>
    request<ComparePlan>("POST", "/api/lab/compare/plan", body),
  compareRun: (body: { workflows: LabWorkflow[]; bench: string; budget: number; agent: string; size: "pilot" | "full" }) =>
    request<{ job: string; workflows: string[] }>("POST", "/api/lab/compare", body),
  compareGet: (job: string) => request<CompareJobView>("GET", `/api/lab/compare/${job}`),
  compareStop: (job: string) => request<{ stopping: boolean }>("POST", `/api/lab/compare/${job}/stop`),
  /** Each workflow's latest valid result on a bench, and the ranking. */
  /** Whole workflows (with steps) count only results on their current session model. */
  compareStanding: (bench: string, workflows: LabWorkflow[] | { id: string; name: string }[], agent = "claude-code") =>
    request<CompareStanding>("POST", "/api/lab/compare/standing", { bench, workflows, agent }),
  ablatePreview: (wf: LabWorkflow) =>
    request<{ count: number; of: number; variants: string[] }>("POST", "/api/lab/ablate/preview", wf),
  ablate: (body: { workflow: LabWorkflow; bench: string; budget: number; agent: string; size: "pilot" | "full"; auto: boolean; local_model?: string | null }) =>
    request<AblateJob>("POST", "/api/lab/ablate", body),
  ablateGet: (id: string) => request<AblateJob>("GET", `/api/lab/ablate/${id}`),
  ablateStop: (id: string) => request<{ stopping: boolean }>("POST", `/api/lab/ablate/${id}/stop`),
  labImprove: (body: { workflow: LabWorkflow; bench: string; experiment: number }) =>
    request<Improvement>("POST", "/api/lab/improve", body),
  labResults: () => request<LabResult[]>("GET", "/api/lab/results"),
  /** The workflow a measured Lab run ran, to open it again in the Lab. */
  labWorkflowOf: (treatment: string) => request<LabWorkflow>("GET", `/api/lab/workflow?treatment=${encodeURIComponent(treatment)}`),
  /** The Lab workflow that runs a catalog design, set up for the use case. */
  garageWorkflow: (entry: string, use_case: string) => request<GarageWorkflow>("POST", "/api/garage/workflow", { entry, use_case }),
  /** The budget check's prediction for a run, before it starts (no sign-in, no model call). */
  runEstimate: (body: {
    pairs: number;
    agent: string;
    model?: string | null;
    bench?: string | null;
    repo?: string | null;
    workflow?: LabWorkflow | null;
    treatment_path?: string | null;
    local?: boolean;
    budget?: number;
    pilot_pairs?: number | null;
    tier?: string | null;
  }) => request<RunForecast>("POST", "/api/runs/estimate", body),
  // Any repo's runs, not only the open one's.
  /** One repo run, read without switching the active repo (the Runs page's link). */
  experimentOf: (repo: string, id: number) => request<ExperimentDetail>("GET", `/api/experiments/${id}?repo=${encodeURIComponent(repo)}`),
  /** One Lab run, read-only: its result row, summary and trials. */
  labResult: (bench: string, id: number) =>
    request<ExperimentDetail & LabResult>("GET", `/api/lab/results/${encodeURIComponent(bench)}/${id}`),
  experimentsOf: (repo: string) => request<ExperimentRow[]>("GET", `/api/experiments?repo=${encodeURIComponent(repo)}`),
  forgetExperiment: (id: number, repo: string) =>
    request<{ removed: number }>("DELETE", `/api/experiments/${id}?repo=${encodeURIComponent(repo)}`),
  labForensics: (bench: string, id: number) => request<Forensics>("GET", `/api/lab/results/${bench}/${id}/forensics`),
  labMatrix: (bench: string) => request<LabMatrix>("GET", `/api/lab/matrix?bench=${encodeURIComponent(bench)}`),
  activeRun: () => request<{ running: ActiveRun | null }>("GET", "/api/runs/active"),
  // The run's own repo, which needn't be the one open now.
  stopExperiment: (id: number, repo: string) =>
    request<{ stopping: boolean }>("POST", `/api/experiments/${id}/stop?repo=${encodeURIComponent(repo)}`),
  labStop: (bench: string, id: number) => request<{ stopping: boolean }>("POST", `/api/lab/runs/${bench}/${id}/stop`),
  labForget: (bench: string, id: number) => request<{ removed: number }>("DELETE", `/api/lab/results/${bench}/${id}`),
  removeBench: (bench: string) => request<{ removed: string }>("DELETE", `/api/lab/benches/${encodeURIComponent(bench)}`),
  unsave: (id: string) => request<{ removed: string }>("DELETE", `/api/lab/saved/${encodeURIComponent(id)}`),
  makeBench: (workflow: LabWorkflow) => request<BenchMade>("POST", "/api/lab/benches/generate", { workflow }),
  importSuite: (body: { path: string; name: string; disciplines: string[] }) =>
    request<BenchInfo>("POST", "/api/lab/benches/import", body),
  publicBenches: () => request<PublicBenches>("GET", "/api/lab/public-benches"),
  addPublicBench: (key: string, sample: number) =>
    request<{ bench: BenchInfo; dropped: string[] }>("POST", "/api/lab/public-benches", { key, sample }),
  localModels: (scan = false) => request<LocalModels>("GET", `/api/local-models${scan ? "?scan=true" : ""}`),
  scanLocal: (base: string) => request<LocalModels["models"]>("POST", "/api/local-models/scan", { base }),
  addLocal: (m: { base: string; model: string; kind: string; label?: string }) =>
    request<LocalModels>("POST", "/api/local-models", m),
  removeLocal: (id: string) => request<LocalModels>("DELETE", `/api/local-models/${encodeURIComponent(id)}`),
  testLocal: (id: string) => request<LocalTest>("POST", `/api/local-models/${encodeURIComponent(id)}/test`),
  localTemplateFix: (id: string) =>
    request<LocalTemplateFix>("POST", `/api/local-models/${encodeURIComponent(id)}/template-fix`),
  localHelper: (id: string | null) => request<LocalModels>("POST", "/api/local-models/helper", { id }),
  labRandom: (discipline: string | null, shown: string[]) =>
    request<LabWorkflow>("POST", "/api/lab/random", { discipline, shown, seed: Math.floor(Math.random() * 1e9) }),
  labMatcher: (on: boolean) => request<NonNullable<Lab["matcher"]>>("POST", "/api/lab/matcher", { on }),
  labPrice: (wf: LabWorkflow) => request<LabWorkflow>("POST", "/api/lab/price", wf),
  labSave: (wf: LabWorkflow) => request<{ path: string; id: string; name: string }>("POST", "/api/lab/save", wf),
  readme: (name: string) =>
    request<{ name: string; text: string; url: string }>("GET", `/api/catalog/readme?name=${encodeURIComponent(name)}`),
  skillText: (path: string) =>
    request<{ path: string; text: string; files: string[] }>("GET", `/api/skill?path=${encodeURIComponent(path)}`),
  repoParts: (name: string) => request<RepoParts>("GET", `/api/catalog/parts?name=${encodeURIComponent(name)}`),
  repoSkills: (name: string) => request<RepoSkillRef[]>("GET", `/api/catalog/skills?name=${encodeURIComponent(name)}`),
  install: (repo: string, path: string) => request<{ path: string; name: string }>("POST", "/api/catalog/install", { repo, path }),
  // Estimates wait their turn: a browser keeps only six requests open per site, and a repo with
  // many skills must not starve the rest of the page.
  /** The rough estimate; `model: true` asks the model (a paid call, only when someone clicks). */
  estimate: (treatment_path: string, steps: string[], opts: { model?: boolean } = {}) =>
    inTurn(() => request<Estimate>("POST", "/api/estimate", { treatment_path, steps, model: !!opts.model })),
  /** Rough guesses for many skills in one request (never a model): a repo's own skills on opening. */
  estimateBatch: (items: { treatment_path: string; steps: string[] }[]) =>
    request<{ estimates: Estimate[] }>("POST", "/api/estimate/batch", { items }).then((r) => r.estimates),
  addScenario: (body: { id: string; title: string; kind: string; instruction: string; check: string; step?: string }) =>
    request<Scenario>("POST", "/api/scenarios", body),
  /** Try it: the price first (no sign-in, no model call), then one run per input. */
  tryPrice: (body: TryTarget & { n: number; budget_usd: number }) => request<TryPrice>("POST", "/api/try/price", body),
  tryStart: (body: TryTarget & { inputs: string[]; budget_usd: number; goal?: string; accept_no_cap?: boolean }) =>
    request<TryJob>("POST", "/api/try", body),
  /** The input box's example, from the goal in use (try-it: goal_examples). No model. */
  tryExample: (goal: string, discipline: string | null) =>
    request<{ kind: string; example: string }>("POST", "/api/try/example", { goal, discipline }),
  tryGet: (id: string) => request<TryJob>("GET", `/api/try/${id}`),
  tryStop: (id: string) => request<{ stopping: boolean }>("POST", `/api/try/${id}/stop`),
  tryForget: (id: string) => request<{ forgotten: string }>("DELETE", `/api/try/${id}`),
  /** Keep a tried input: a draft scenario with no check yet. */
  draftScenario: (body: { instruction: string; title?: string }) =>
    request<{ id: string; title: string; file: string }>("POST", "/api/scenarios/draft", body),
};

/** What Try it runs: a Lab workflow, or a skill on a repo's canvas. */
export type TryTarget = {
  workflow?: LabWorkflow;
  skill_path?: string;
  agent: string;
  model?: string | null;
  grade?: boolean;
  /** Claude Code on a local model (its id): free, no sign-in. */
  local_model?: string | null;
};

/**
 * Follow an experiment's live events. The server replays every event from the start on each
 * connection, so `onOpen` fires before each replay and the caller starts its log afresh.
 * Returns a function that stops listening.
 */
export function follow(id: number, onEvent: (e: RunEvent) => void, onOpen: () => void, url?: string): () => void {
  const source = new EventSource(url ?? `/api/experiments/${id}/events`);
  source.onopen = onOpen;
  source.onmessage = (m) => {
    const e = JSON.parse(m.data) as RunEvent;
    onEvent(e);
    if (e.type === "finished" || e.type === "error" || e.type === "idle") source.close();
  };
  return () => source.close();
}
