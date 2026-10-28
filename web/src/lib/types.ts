// Shapes returned by the engine's API (engine/src/proving_ground/api).

export type Kind = "typical" | "edge" | "adversarial" | "failure" | "overload" | "imaginary";
export const KINDS: Kind[] = ["typical", "edge", "adversarial", "failure", "overload", "imaginary"];
export type Verdict = "helps" | "hurts" | "inconclusive";

export interface Project {
  name: string;
  root: string;
  key_set: boolean;
  scanned: boolean;
  scan: {
    files: number;
    truncated: boolean;
    languages: Record<string, number>;
    stack: string[];
    agent_setup: string[];
    skills: { name: string; description: string; path: string }[];
  };
  graph: { name: string; nodes: number; edges: number; communities?: number; top?: string[] } | null;
  sources: { id: number; kind: string; name: string; chars: number }[];
  use_case: string | null;
  /** The one-click goal it was saved from (repo-goals: templates), and what it is about. */
  goal_template?: string | null;
  goal_metric?: GoalMetric | null;
  counts: {
    scenarios: number;
    approved: number;
    /** Approved with a check that is a command: the only ones a run uses. */
    runnable?: number;
    /** Approved ones left out: their check isn't a command. */
    not_command?: string[];
    workflows: number;
    experiments: number;
  };
  /** The coding agent's setup, as the canvas's first lane draws it (buildspec.setup_lane). */
  agent?: AgentSetupItem[];
  /** Placeholders for a new scenario, in this repo's own work. */
  example?: { title: string; instruction: string; check: string; use_case?: string };
}

export interface AgentSetupItem {
  id: string;
  label: string;
  present: boolean;
  detail: string;
  run?: string;
}

export interface Step {
  name: string;
  type: string;
  why: string;
}

export interface Workflow {
  id: string;
  name: string;
  success: string;
  steps: Step[];
}

export interface Fault {
  file?: { path: string; remove?: boolean; truncate?: boolean; corrupt?: boolean };
  command?: { match: string; exit: number; stderr: string };
  http?: { host: string; status: number };
}

export interface Scenario {
  id: string;
  title: string;
  kind: Kind;
  instruction: string;
  setup: string | null;
  check: string | null;
  timeout: number;
  step: string | null;
  faults: Fault[];
  load: { inputs?: { generate: string; count: number }; context_fill?: number; timeout?: number } | null;
  check_status: "unreviewed" | "approved";
  origin: "generated" | "user" | "bench";
  runnable: boolean;
  /** Why the check isn't a runnable command (evidence-validity); it can't be approved or run. */
  check_problem?: string | null;
  /** Generated for a different use case than the repo's current one. */
  goal_changed?: boolean;
  file: string;
  check_files: { path: string; content: string }[];
  fixtures: string[];
}

export interface ProveStatus {
  status: "idle" | "running" | "done" | "error";
  proven: boolean | null;
  detail: string;
}

export interface Evidence {
  experiment_id: number;
  status: string;
  verdict: Verdict;
  diff: number | null;
  ci_low: number | null;
  ci_high: number | null;
  n_pairs: number;
}

/** What a skill folder's PROVEN.md says, compactly: its best measured result. */
export interface Proven {
  verdict: Verdict;
  diff_pts: number;
  pairs: number;
  bench: string;
  /** The same run's Rig score (engine rig-score skill). */
  rig?: number;
  rig_band?: RigBand;
  rig_tone?: RigTone;
  rig_provisional?: boolean;
}

export type RigBand = "works" | "works_but" | "not_proven" | "helps_but" | "doesnt" | "none" | "not_evidence";

/** One count of a result's trials (engine rig_score.ledger): every line that cites a count uses it. */
export interface TrialLedger {
  total: number;
  with: number | null;
  without: number | null;
  /** Complete with/without pairs, as the interval counts them. */
  pairs: number;
  /** "With" trials whose session logs could be read; null when nothing reads them. */
  logs_read: number | null;
  clean: number;
  /** Fails because the agent ran out of the task's time limit (not counted as clean). */
  timed_out?: number;
  errored: number;
  broken: number;
}

/** Spent over the budget: by how much, and why (engine trial-budget). */
export interface OverBudget {
  by_usd: number;
  before_cap: boolean;
  note: string;
}
export type RigTone = "positive" | "neutral" | "warning" | "negative";

/** What a run is scored on (rig-score: Metric): the pass rate, or a saving per solved task. */
export type MetricId = "pass_rate" | "tokens" | "cost" | "time";

/** A run scored on a metric: its headline and the pass rate as the guard (engine metric_summary). */
export interface RigMetric {
  id: MetricId;
  name: string;
  n: number;
  margin_pts: number;
  /** "Pass rate: 32 of 40 passed with vs … (at worst -7 pts, within the 10-pt margin)". */
  guard: string | null;
  /** Shown to be no worse on the pass rate; null with nothing to compare. */
  noninferior: boolean | null;
  /** "Tokens per solved task: with 21.4k vs without 44.1k (-51%, 95% interval -58% to -45%)". */
  headline: string | null;
  missing?: "unsolved" | "unrecorded" | null;
  with?: number;
  without?: number;
  ratio?: number;
  low?: number | null;
  high?: number | null;
}

/** One number from 0 to 100 that says whether a rig works; the rules are the rig-score skill. */
export interface RigScore {
  score: number | null;
  band: RigBand;
  tone: RigTone;
  label: string;
  reason: string;
  provisional: boolean;
  pairs: number;
  parts: {
    id: string;
    name: string;
    weight: number;
    weight_used?: number;
    score: number | null;
    detail: string;
    /** In the sum: measured, and (for Cost and Reliable) a lift was shown. */
    counted?: boolean;
    /** Why a measured part earns nothing yet ("counts once a lift is shown"). */
    note?: string;
    /** Not scored because the metric is what it measures (Cost on a tokens or cost run): it is in Lift. */
    folded?: boolean;
  }[];
  gates: { id: string; cap: number | null; text: string; binding?: boolean }[];
  /** How the number is made, so a reader can rebuild it; null with no score. */
  formula?: { text: string; measured_weight: number; raw: number; not_measured: string[] } | null;
  ledger?: TrialLedger;
  ledger_text?: string;
  /** The plain answer (engine rig_score.verdict): the card's headline. */
  verdict?: RigVerdict;
  /** Present only on a run scored on tokens, cost or time. */
  metric?: RigMetric;
}

/** The Rig score's definition, for its explainer page (engine GET /api/rig-score, the rig-score skill). */
export interface RigExplain {
  intro: string;
  parts: { id: string; name: string; weight: number; measures: string; scale: string; needs_lift: boolean }[];
  missing: string;
  no_credit: string;
  gates: { id: string; cap: number; text: string }[];
  min_pairs: number;
  bands: { id: string; tone: RigTone; label: string; min: number | null; when: string }[];
  verdict: { id: string; word: string; tone: RigTone }[];
  /** What a run can be scored on, for Measure's choice. */
  metric?: {
    text: string;
    default: MetricId;
    margin_pts: number;
    guard_note: string;
    options: { id: MetricId; name: string; describe: string }[];
    /** "Keep going until it's decided", per metric: what it waits for (judge-experiment: auto_extend). */
    keep_going?: Record<MetricId, string>;
  };
  example: {
    title: string;
    note: string;
    evidence: { n_pairs: number; diff: number; ci_low: number; ci_high: number; pass_with: number; pass_without: number };
    /** rig_score() on the evidence: the real formula, never one of the page's own. */
    result: RigScore;
  };
}

/** Helps / Doesn't Help / Can't Tell Yet, why (with the numbers), and one next step. */
export interface RigVerdict {
  id: "helps" | "doesnt" | "cant";
  word: string;
  tone: RigTone;
  reason: string;
  /** "Next: …" */
  next: string;
  /** Quality, cost, time and reliability, one line each. */
  facts: string[];
}

export interface TreatmentItem {
  name: string;
  description: string;
  path: string;
  evidence: Evidence | null;
  proven?: Proven | null;
  source?: string | null;
  /** Installed from GitHub: the skill's folder in `source`. */
  folder?: string;
  kind?: "skill" | "hook" | "mcp" | "instructions";
  /** Written for a language the repo has none of: "For Go; this repo has none." */
  fit_note?: string;
  /** A hook, MCP server or instructions: what the two arms of a run get. "same": nothing to measure. */
  compare?: "hook" | "mcp" | "edited" | "new" | "same" | "replaces" | "adds";
  compare_text?: string;
  /** Instructions: the file it writes and its text, for an edited copy. */
  file?: string;
  text?: string;
}

export interface Suggestion {
  name: string;
  kind: "skill" | "loop" | "config";
  why: string;
  step?: string;
  workflow: string;
}

export interface Treatments {
  repo: TreatmentItem[];
  user: TreatmentItem[];
  installed: TreatmentItem[];
  created?: TreatmentItem[];
  configs?: TreatmentItem[];
  suggested: Suggestion[];
}

export interface ArmStats {
  n_pairs: number;
  pass_with: number;
  pass_without: number;
  diff: number;
  ci_low: number;
  ci_high: number;
}

/** Partial credit (RIG_ITEMS): each trial scores right/total; present only when every pair counted. */
export interface ItemScore {
  with: number;
  without: number;
  diff: number;
  ci_low: number;
  ci_high: number;
  n: number;
  right_with: number;
  total_with: number;
  right_without: number;
  total_without: number;
}

export interface Summary {
  headline: ArmStats | null;
  verdict: Verdict;
  mde: number | null;
  required_pairs: number | null;
  by_kind: Record<string, ArmStats>;
  synthetic: ArmStats | null;
  errored: number;
  broken: number;
  total: number;
  unreliable: boolean;
  cost_with: number;
  cost_without: number;
  items?: ItemScore;
}

export interface Trial {
  scenario_id: string;
  kind: Kind;
  arm: "with" | "without";
  repeat: number;
  outcome: "pass" | "fail" | "errored" | "broken";
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  duration_s: number;
  /** The check's RIG_ITEMS count, when it printed one. */
  items_right?: number | null;
  items_total?: number | null;
  /** "timed out after 600 s", an error, or null. */
  detail?: string | null;
  /** A fail because the agent ran out of the task's time limit: shown as "timed out". */
  timed_out?: boolean;
}

export interface ExperimentRow {
  id: number;
  treatment_name: string;
  treatment_kind: string;
  treatment_hash: string;
  model: string;
  repeats: number;
  budget_usd: number;
  status: string;
  /** The status in words (trial-budget: status_words). */
  status_text?: string;
  created_at: string;
  spent_usd: number;
  verdict?: Verdict;
  rig?: RigScore;
  agent?: string;
  n_pairs?: number;
  validity?: Validity;
  ledger?: TrialLedger;
  over_budget?: OverBudget | null;
  items?: ItemScore;
  /** What the run is scored on; older runs read as the pass rate. */
  metric?: MetricId;
  /** A code change measured before and after: "with" is the after side, "without" the base. */
  before_after?: BeforeAfterMeta | null;
  /** The local model it ran on, or null on the signed-in agent. */
  local_model?: LocalRun | null;
}

/** The local model a run ran on: its id (the run's model) and its label. */
export interface LocalRun {
  id: string;
  label: string;
}

export interface ExperimentDetail extends ExperimentRow {
  summary: Summary;
  trials: Trial[];
  /** A workflow handed over: did the "with" trials follow it. */
  adherence?: LabResult["adherence"];
}

export interface DryRun {
  included: string[];
  dropped: string[];
  tokens_est: number;
  model: string;
  mix: Record<string, number>;
}

export interface Generated {
  workflow: Workflow;
  scenarios: Scenario[];
  treatments: Suggestion[];
  tokens: { in: number; out: number };
  written: number;
}

export interface Started {
  id: number;
  repeats: number;
  scenarios: string[];
  trials: number;
  model: string;
  budget: number;
  commit: string | null;
  dirty: boolean;
  metric?: MetricId;
  before_after?: BeforeAfterMeta | null;
  local_model?: LocalRun | null;
}

export type RunEvent =
  | { type: "trial"; scenario_id: string; arm: string; repeat: number; outcome: string; timed_out?: boolean; spent_usd: number }
  | { type: "broken"; scenario_id: string; log?: string }
  | { type: "stopped_budget"; spent_usd: number; predicted_usd?: number; left_usd?: number; reason?: string }
  | { type: "stopped"; spent_usd: number }
  | { type: "done"; spent_usd: number }
  | { type: "finished"; status: string; summary: Summary }
  | { type: "error"; detail: string }
  | { type: "idle" }
  | { type: string; [k: string]: unknown };

export interface DoctorCheck {
  name: string;
  ok: boolean;
  detail: string;
}

export interface RepoRef {
  id: string;
  root: string;
  name: string;
  /** Where a cloned repo came from (never holds a login). */
  remote?: string | null;
  provider?: "github" | "gitlab" | null;
}

export interface RemoteProvider {
  id: "github" | "gitlab";
  label: string;
  cli: string;
  installed: boolean;
  cli_account: string | null;
  token_set: boolean;
  signed_in: boolean;
  via: "cli" | "token" | null;
  hint: string;
}

export interface RemoteRepoRow {
  owner: string;
  name: string;
  full_name: string;
  description: string;
  private: boolean;
  updated: string | null;
  url: string;
}

export interface RemoteJob {
  id: string;
  url: string;
  state: "running" | "done" | "error";
  stage: string;
  error: string | null;
  repo?: RepoRef;
  warning?: string;
}

export type ArchKind = "frontend" | "backend" | "database" | "cloud" | "security" | "messagebus" | "external";

export interface ArchComponent {
  id: string;
  type: ArchKind;
  label: string;
  sublabel: string | null;
  pos: [number, number] | null;
  source: string | null;
  evidence?: string[];
  /** What it really is ("Surface driver"); `type` only picks the colour. */
  role?: string | null;
  /** Set when a spec was checked against the code. */
  check?: "found" | "weak" | "missing" | null;
  why?: string | null;
}

export interface ArchCheck {
  found: number;
  weak: number;
  missing: number;
  total: number;
  missed: string[];
  no_input?: string[];
  planned?: string[];
  lines_found: number;
  lines_total: number;
  summary: string;
}

export interface Architecture {
  title: string;
  source: "archify" | "mapped" | "inferred";
  spec_path: string | null;
  components: ArchComponent[];
  connections: { from: string; to: string; label: string | null; variant: string | null; check?: "found" | "unchecked" | null }[];
  boundaries: { kind: string; label: string; wraps: string[] }[];
  flows?: ArchFlow[];
  check?: ArchCheck | null;
}

export interface ArchFlow {
  name: string;
  steps: { from: string; to: string; what: string }[];
}

export type Impact = "reliability" | "speed" | "agent" | "clarity";

export interface Proposal {
  id: string;
  title: string;
  kind: "split" | "merge" | "add" | "reconnect" | "move" | "remove" | "check";
  targets: string[];
  why: string;
  what: string;
  impact: Partial<Record<Impact, string>>;
  effort: "S" | "M" | "L";
  evidence: string[];
  delta: {
    add?: { id: string; type: ArchKind; label: string; sublabel?: string }[];
    remove?: string[];
    connect?: [string, string, string?][];
    disconnect?: [string, string][];
  };
  source: "rules" | "review";
  state: "open" | "accepted" | "dismissed";
  /** What it adds to the coding agent rather than the app: a treatment kind, "task" or "step". */
  adds?: string;
  /** Whether Measure can test it: a state of the measurability skill. */
  measure?: string;
}

export interface Suggestions {
  proposals: Proposal[];
  review: MapJob & { count?: number };
}

export interface Proposed {
  architecture: Architecture;
  archify: Record<string, unknown>;
  accepted: string[];
  /** Every suggestion drawn: the accepted ones (or the one being previewed). */
  shown?: string[];
  /** The suggestion each new or taken-away part came from, by component id. */
  origins?: Record<string, { id: string; title: string; state: Proposal["state"] }>;
  /** What the suggestions change, for the legend. */
  diff?: {
    added: string[];
    removed: string[];
    connected: number;
    disconnected: number;
    suggestions: number;
    /** How many of them change the diagram (the rest are only in the brief). */
    drawn?: number;
    /** In the brief's unit: accepted suggestions that are tasks, ones that only fix the diagram, and open ones. */
    tasks?: number;
    notes?: number;
    open?: number;
    /** The same, by name: what "With the accepted suggestions" adds to the brief. */
    task_items?: { id: string; title: string; measure?: string }[];
    note_items?: { id: string; title: string; measure?: string }[];
  };
}

/** One state of the measurability skill: the badge, its line, its colour. */
export interface MeasureState {
  label: string;
  says: string;
  tone: "positive" | "neutral" | "warning";
}

/** The measurability skill's values (/api/rules/measurability). */
export interface MeasureRules {
  states: Record<string, MeasureState>;
  treatments: Record<string, string>;
  kind_names: Record<string, string>;
  setup_kinds: Record<string, string>;
  code_kinds: string[];
  adds: Record<string, string>;
  lanes: { setup: string; flow: string; arch: string };
  empty: { title: string; lead: string; go: string };
  /** A code change measured before and after: Measure's words for it. */
  before_after: BeforeAfterWords;
}

export interface BeforeAfterWords {
  mode: string;
  mode_agent: string;
  lead: string;
  base: string;
  after: string;
  working_tree: string;
  compare: string;
  files: string;
  file: string;
  same: string;
  not_git: string;
  unknown_ref: string;
  name: string;
  arms: { with: string; without: string };
  /** Beside the Rig score's title: "before vs after". */
  card: string;
  key: string;
  /** Build's link to Measure on a suggestion that changes the code. */
  measure_it: string;
  /** Measure's note naming that suggestion: "Measuring “{title}”: ...". */
  for: string;
  /** Measure's step lead and its run column's line, by mode: an agent change or a code change. */
  stage_lead: { agent: string; code: string };
  run_says: { agent: string; code: string };
}

/** One side of a before/after run: a commit, or the working tree (sha null). */
export interface BeforeAfterSide {
  sha: string | null;
  short: string | null;
  ref: string | null;
  label: string;
  subject: string;
  working_tree: boolean;
}

/** A before/after run's two sides, as its meta.json keeps them. */
export interface BeforeAfterMeta {
  base: BeforeAfterSide;
  after: BeforeAfterSide;
  files: string[];
  n_files: number;
}

/** POST /api/before-after/compare: what a run would compare, and whether it would measure nothing. */
export interface BeforeAfterCompare extends BeforeAfterMeta {
  name: string;
  same: boolean;
  says: string;
  files_text: string;
}

/** GET /api/before-after/refs: what Measure offers to pick from. */
export type BeforeAfterRefs =
  | { git: false; says: string }
  | {
      git: true;
      head: { sha: string; short: string; branch: string | null; subject: string };
      branches: { name: string; sha: string; short: string; subject: string; current: boolean }[];
      commits: { sha: string; short: string; subject: string }[];
      dirty: boolean;
    };

/** A metric a goal can be about (repo-goals: metrics). */
export type GoalMetric = "pass_rate" | "tokens" | "cost" | "time";

/** The repo-goals skill's values (/api/rules/repo-goals). */
export interface GoalRules {
  agent_words: string[];
  templates: { id: string; label: string; text: string; metric: GoalMetric }[];
  metrics: GoalMetric[];
}

export interface Placement {
  targets: { id: string; why: string }[];
  reason: string;
  /** The block it goes beside: its first target, else the agent setup (linked to nothing). */
  beside?: string | null;
  /** Written for a language the repo has none of (also at the end of `reason`). */
  note?: string | null;
}

export interface Recommendation {
  needs: { text: string; source: string }[];
  picks: { id: string; need: string; why: string; item: CatalogItem | null }[];
  create: { name: string; need: string; what: string; why: string }[];
  improve: { path: string; need: string; how: string; why: string }[];
  basis: "model" | "rough";
  note?: string;
  creatable: boolean;
  /** Roughly what "Ask the model to pick" costs (recommend-for-repo: model_pick_usd). */
  model_pick_usd?: number;
}

export interface SignInStatus {
  id: string;
  label: string;
  ready: boolean;
  how: string;
  help: string;
  typed: boolean;
}

export interface AgentInfo {
  id: string;
  label: string;
  default_model: string | null;
  sign_in: SignInStatus[];
  ready: boolean;
  /** Claude Code's own login on this machine (enough for Map with Archify, not for sandboxes). */
  host: { email: string | null; plan: string | null; method: string | null } | null;
  /** Signing in through the agent's CLI: `auto` drives it; otherwise the person runs it. */
  login: { auto: boolean; install: string } | null;
  /** Stops itself mid-trial at the budget (Claude Code); else only pairs predicted to go over are held back. */
  budget_cap?: boolean;
}

export interface LoginJob {
  state: "idle" | "running" | "done" | "error";
  url: string | null;
  error: string | null;
  manual: string;
}

export type CatalogCategory = "skill" | "agent" | "mcp" | "hook" | "harness" | "workflow" | "eval";
export type CatalogView = "recommended" | "stars" | "latest" | "relevant";

export interface CatalogItem {
  id: string;
  name: string;
  owner: string;
  url: string;
  description: string;
  stars: number;
  pushed_at: string;
  topics: string[];
  category: CatalogCategory;
  theme: string;
  relevance: number;
  /** Hand-picked canonical repository (curate-catalog `pinned`). */
  pinned?: boolean;
  /** A weak search match (only a topic, a theme or scattered words): folded under "Weaker matches". */
  weak?: boolean;
  /** Written for a language the repo has none of: "For Go; this repo has none." */
  fit_note?: string;
}

export interface CatalogKind {
  id: CatalogCategory;
  label: string;
  /** One plain line: what it is and why you'd add one (curate-catalog `blurb`). */
  blurb: string;
}

export interface CatalogPage {
  loading: boolean;
  partial?: boolean;
  items: CatalogItem[];
  themes: Record<string, number>;
  terms?: string[];
  /** Items of each kind in the catalog, and how many of each match the search. */
  counts?: Partial<Record<CatalogCategory, number>>;
  matches?: Partial<Record<CatalogCategory, number>>;
  /** Of the matches, how many are weak (shown folded away). */
  weak?: Partial<Record<CatalogCategory, number>>;
  kinds?: CatalogKind[];
  error: string | null;
}

export interface RepoSkillRef {
  path: string;
  name: string;
  description: string;
}

export interface Estimate {
  /** measured: a run; estimate: a model's judgement; rough: a model-free guess. */
  basis: "measured" | "estimate" | "rough" | "none";
  low?: number;
  high?: number;
  likely?: number;
  confidence?: string;
  reason: string;
  note?: string;
  /** Roughly what "Sharpen with the model" costs (estimate-effect: model_call_usd). */
  sharpen_usd?: number;
  /** UI only: a rough number on screen while the model estimate is on its way. */
  refining?: boolean;
  /** UI only: the links a sharpened estimate was asked for. */
  steps?: string;
}

export interface MapJob {
  state: "idle" | "running" | "done" | "error";
  agent?: string;
  started_at?: number;
  error?: string;
}

export type StepKind = "think" | "do" | "check" | "judge";

/** A skill the Lab can put on a step: yours (local), or preloaded from GitHub (starter-skills).
 * A GitHub skill's path is "github:<repo>/<folder>" until saving or running downloads it. */
export interface LabSkill {
  path: string;
  name: string;
  description?: string;
  source?: "local" | "github";
  repo?: string;
  folder?: string;
  url?: string;
  label?: string;
  /** Why the Lab attached it to a step, e.g. "matched: failing test; name 1/1". */
  why?: string;
}

export interface LabStep {
  id: string;
  name: string;
  does: string;
  kind: StepKind;
  model: string;
  skills: LabSkill[];
  pos?: [number, number] | null;
}

export interface LabWorkflow {
  /** The guess moved by similar valid measured runs (learned-priors), when there are any.
   * basis "shape": too few valid pairs (need_pairs), so prior is still the guess. */
  learned?: {
    prior: number;
    guess: number;
    runs: number;
    pairs: number;
    basis?: "learned" | "shape";
    need_pairs?: number;
    ignored?: number;
  } | null;
  /** The best measured result kept in a saved workflow's PROVEN.md. */
  proven?: Proven | null;
  id: string;
  name: string;
  discipline: string;
  origin: "starter" | "business" | "rag" | "random" | "pattern" | "custom";
  steps: LabStep[];
  loop: [string, string, number] | null;
  /** What follows what: several outs run in parallel, several ins join. */
  edges: [string, string][];
  /** Back to an earlier step to fix it, at most N times. */
  loops: [string, string, number][];
  harness: string[];
  /** Every harness rule as this workflow's discipline says it. */
  harness_text?: Record<string, string>;
  /** The Garage design this workflow was built from ("Use this design"), kept through edits,
   * drafts, reloads and Compare; only Start blank or Detach drops it. The engine ignores it. */
  design?: DesignLink | null;
  /** The goal it is built for, whole ("Goal & rules"); null or absent when none. */
  brief?: string | null;
  /** The goal's rule lines (goal-rules skill), given to the first step. */
  rules?: string[];
  prior: number;
  cost: number;
  why: string[];
  /** The pattern it was made from: while unedited it keeps the pattern's guess. */
  pattern?: string | null;
  group?: string;
  path?: string;
}

export interface StepTemplate {
  id: string;
  name: string;
  does: string;
  kind: StepKind;
  model: string;
}

export interface Lab {
  disciplines: { id: string; label: string; workflows: LabWorkflow[] }[];
  /** Complex workflows modelled on published procedures: parallel branches, joins, loops. */
  business: LabWorkflow[];
  /** RAG architectures as runnable workflows, measured on the rag-qa bench. */
  rag?: LabWorkflow[];
  local_models: LocalModel[];
  templates: { id: string; label: string; steps: StepTemplate[] }[];
  patterns: LabWorkflow[];
  models: Record<string, { label: string; tier: string; cost: number; prior: number }>;
  harness: Record<string, { name: string; does: string; prior: number }>;
  skills: (LabSkill & { description: string })[];
  /** The GitHub index behind the preloaded skills, and how many skills come from each side. */
  skills_status?: { state: "ready" | "loading" | "partial" | "offline"; note: string | null; github: number; local: number };
  /** The skill matcher's open-source models: fetched once, then they pick each step's skills (word rules until then). */
  matcher?: {
    state: "disabled" | "off" | "idle" | "downloading" | "loading" | "warming" | "ready" | "failed";
    note: string;
    mb: number;
    /** Memory the models use while Rig runs, once on. */
    memory_gb?: number;
    model: string;
    /** Off by default: the button that asks for the download (nothing heavy happens unasked). */
    offer: string | null;
    can_turn_off: boolean;
  };
  saved: LabWorkflow[];
  /** How many edited workflows "Your drafts" keeps (starter-workflows: drafts_kept). */
  drafts_max?: number;
}

/** One task of a bench, as the Lab lists it. */
export interface BenchTask {
  id: string;
  kind: string;
  title: string;
  judged: boolean;
  held_out?: boolean;
  /** "standard", or "hard" for the hard tier's tasks. */
  tier?: string;
}

/** The agent alone on one tier of a bench, one session model: from trials already recorded
 * (bench-difficulty). Too easy: every one of at least min_trials passed, on every task. */
export interface BenchBaseline {
  passed: number;
  total: number;
  tasks_seen: number;
  tasks: number;
  too_easy: boolean;
  model_label: string;
  /** "Too easy for Sonnet 5.5: the agent alone passed 5 of 5", or the measured rate. */
  text: string;
  /** Too easy: what Measure says before Rig & Measure. */
  warn?: string;
}

export interface BenchInfo {
  id: string;
  name: string;
  discipline: string;
  summary: string;
  /** A held-out task runs but isn't shown, so a workflow can't be tuned to it. The standard tier. */
  scenarios: BenchTask[];
  /** The hard tier's tasks (none on most benches). */
  hard?: BenchTask[];
  /** The tiers a run can pick: standard, and with hard tasks hard and all. */
  tiers?: { id: string; label: string; tasks: number }[];
  /** By tier, then by session model. */
  baseline?: Record<string, Record<string, BenchBaseline>>;
  disciplines: string[];
  judged: boolean;
  /** An existing eval suite (Harbor tasks) imported from a folder. */
  imported?: boolean;
  /** Made for a workflow by a model, every check proven in Docker. */
  generated?: { by: string; workflow: string } | null;
  /** A seeded sample of a public benchmark from the Harbor registry. */
  public?: { key: string; total: number; source: string | null; heavy: boolean } | null;
  calibration: { trustworthy: boolean; scenarios: Record<string, { good?: number; bad?: number; gap?: number; trustworthy?: boolean; reason?: string; error?: string }> } | null;
}

export interface LabStarted {
  id: number;
  bench: string;
  workflow: string;
  trials: number;
  scenarios: string[];
  model: string;
  budget: number;
  tier?: string;
  /** A baseline check: the agent alone, no "with" arm. */
  probe?: boolean;
  metric?: MetricId;
  /** The local model it runs on, or null on the signed-in agent. */
  local_model?: LocalRun | null;
}

/** What a baseline check would run and cost (POST /api/lab/probe/price). */
export interface ProbePrice {
  trials: number;
  per_trial: number;
  source: string;
  total_usd: number;
  /** The cap it runs under: the price rounded up to the budget step. */
  budget: number;
  free: boolean;
  bench: string;
  tier: string;
  model: string;
  model_label: string;
  offer: string;
}

export interface SuiteBench {
  bench: string;
  name: string;
  tasks: number;
  experiment: number | null;
  status: "queued" | "running" | "done" | "stopped" | "skipped" | "error";
  budget: number | null;
  spent: number;
  detail: string | null;
  diff: number | null;
  ci_low: number | null;
  ci_high: number | null;
  n_pairs: number;
  rig?: RigScore | null;
}

export interface SuiteView {
  job: string;
  workflow: string;
  /** What every bench's run and the pooled result are scored on (rig-score: Metric, Suites). */
  metric?: MetricId;
  status: "running" | "stopping" | "done" | "stopped";
  budget: number;
  spent: number;
  benches: SuiteBench[];
  pooled: {
    verdict: string;
    diff: number | null;
    ci_low: number | null;
    ci_high: number | null;
    n_pairs: number;
    pass_with: number | null;
    pass_without: number | null;
    rig?: RigScore;
  };
}

export interface Contribution {
  kind: "drop" | "loop" | "model";
  marginal_pts: number | null;
  saved_cost_usd: number | null;
  verdict: "essential" | "dead weight" | "harmful" | "unclear" | "neutral";
}

export interface AblateJob {
  id: string;
  workflow: string;
  bench: string;
  budget: number;
  spent_usd: number;
  status: "running" | "done" | "stopped";
  note: string;
  variants: {
    key: string;
    kind: "drop" | "loop" | "model";
    label: string;
    experiment_id: number | null;
    status: "pending" | "running" | "done" | "stopped" | "skipped" | "error";
    detail: string;
  }[];
  contributions?: Record<string, Contribution> | null;
}

export interface LabResult {
  /** The local model it ran on, or null on the signed-in agent. */
  local_model?: LocalRun | null;
  rig?: RigScore;
  /** What the run is scored on; older runs read as the pass rate. */
  metric?: MetricId;
  /** Partial credit, when every pair's check counted items (RIG_ITEMS). */
  items?: ItemScore;
  bench: string;
  bench_name: string;
  id: number;
  workflow: string;
  treatment: string;
  agent?: string;
  date?: string;
  budget_usd?: number;
  /** The Lab workflow's id, when the run recorded it. */
  workflow_id?: string | null;
  /** Null for a baseline check, which has no "with" arm. */
  verdict: string | null;
  /** A baseline check (the agent alone), and what it found. */
  probe?: boolean;
  probe_result?: { passed: number; total: number; text: string } | null;
  /** The bench tier it ran: standard, hard or all. */
  tier?: string;
  status: string;
  /** The status in words (trial-budget: status_words). */
  status_text?: string;
  model: string;
  spent_usd: number;
  pass_with: number | null;
  pass_without: number | null;
  diff: number | null;
  ci_low: number | null;
  ci_high: number | null;
  n_pairs: number;
  reused: number;
  saved_usd: number;
  /** The visible tasks alone, and how many "with" trials failed on them. */
  visible?: { diff: number | null; n_pairs: number; failing: number };
  /** The result this workflow was improved from, and whether the edit generalised. */
  improved_from?: number | null;
  overfit?: { visible_gain_pts: number | null; held_out_gain_pts: number | null; verdict: "generalises" | "overfit" | "unclear" } | null;
  /** The same comparison on the held-out tasks alone. */
  held_out?: { tasks: number; diff: number | null; pass_with?: number; pass_without?: number; n_pairs: number } | null;
  /** What a solved task cost on each arm, and each extra one the workflow solved. */
  costs?: {
    with: { spent_usd: number; solved: number; tasks: number; per_solved_usd: number | null };
    without: { spent_usd: number; solved: number; tasks: number; per_solved_usd: number | null };
    per_extra_solved_usd: number | null;
  };
  adherence: {
    trials: number;
    read: number;
    followed: number;
    steps_run: number | null;
    models_ok: number | null;
    loop_broken: number;
    /** "With" trials that never opened the workflow skill at all. */
    not_opened?: number;
    /** "With" trials that never got the workflow: not opened, or (where that can't be told) no step run. */
    not_applied?: number;
    missing: string[];
    /** Each skipped step and in how many of the `read` trials ("missing" is only their union). */
    skipped?: { step: string; trials: number }[];
    wrong_model: string[];
  } | null;
  /** The change on pairs whose "with" trial followed the workflow; selection-biased. */
  adherent?: { diff: number; ci_low: number; ci_high: number; n_pairs: number; of_pairs: number } | null;
  /** Pairs of the same task that ended differently with and without the workflow. */
  discordant?: number;
  /** Whether this result is evidence at all (evidence-validity). */
  validity?: Validity;
  ledger?: TrialLedger;
  over_budget?: OverBudget | null;
}

/** valid, or why a result isn't evidence: the treatment wasn't applied, a check is broken, or
 * no task could be won or lost. Only valid results feed estimates and the frontier. */
export interface Validity {
  status: "valid" | "invalid" | "uninformative";
  badge: string | null;
  reason: string | null;
}

/** One workflow measured on a bench: its change against the baseline and what a trial costs. */
export interface LabMatrixRow {
  experiment_id: number;
  workflow: string;
  treatment: string;
  model: string;
  agent: string;
  validity?: Validity;
  n_pairs: number;
  /** Fractions: 0.18 is 18 points. Null until there are complete pairs. */
  diff: number | null;
  ci_low: number | null;
  ci_high: number | null;
  pass_with: number | null;
  pass_without: number | null;
  /** Mean spend per finished trial on the workflow's arm; 0 on local models. */
  cost_per_trial_usd: number | null;
  mean_duration_s: number | null;
  /** Pass rates per task (keyed by task id), with the trial count on the workflow's arm. */
  per_task: Record<string, { with: number | null; without: number | null; n: number }>;
  /** The local model it ran on, or null on the signed-in agent. */
  local_model?: LocalRun | null;
}

export interface LabMatrix {
  bench: string;
  /** When the newest measurement on this bench was started (ISO time), or null. */
  latest: string | null;
  rows: LabMatrixRow[];
  tasks: { id: string; title: string }[];
}

/** A model served on this machine or the local network (Ollama, LM Studio, llama.cpp, vLLM, Jan). */
export interface LocalModel {
  id: string;
  label: string;
  base: string;
  model: string;
  kind: string;
  /** Also speaks Anthropic's Messages API, so Claude Code can run on it. */
  anthropic: boolean;
}

export interface LocalModels {
  models: LocalModel[];
  /** The one that answers estimates, picks and the judge, if any. */
  helper: string | null;
  notes: Record<string, string>;
  found?: LocalModel[];
  /** Measure's words for a repo run on a local model (local-models skill: repo). */
  repo?: LocalRepoWords;
  /** A local model's time limit: this many times each task's own. */
  timeout_factor?: number;
  /** The Lab's words for a suite asked for on a local model ({agent}: the signed-in agent's). */
  suite_local?: string;
}

export interface LocalRepoWords {
  sign_in: string;
  group: string;
  cant_run: string;
  none: string;
  notice: string;
  nudge: string;
  confirm: string;
  start: string;
  cost_metric: string;
  /** Try it on a local model: its price line, its button ({inputs}) and its note. */
  try_price: string;
  try_start: string;
  try_note: string;
  try_note_workflow: string;
}

export interface LocalStage {
  name: string;
  ok: boolean;
  why: string;
}

export interface LocalTest {
  /** Same as helper_ok, kept for older callers. */
  ok: boolean;
  why: string;
  seconds: number;
  helper_ok: boolean;
  /** null when the server doesn't speak the Anthropic API. */
  claude_code_ok: boolean | null;
  context_tokens: number | null;
  warnings: string[];
  /** Set when a saved template would fix it. */
  fix_command: string | null;
  stages: LocalStage[];
}

export interface LocalTemplateFix {
  path: string;
  command: string;
}

/** A benchmark in the Harbor registry, not downloaded yet (or already added: `added`). */
export interface PublicBench {
  key: string;
  name: string;
  version: string;
  description: string;
  tasks: number;
  disciplines: string[];
  /** Big Docker images per task (a whole repo and toolchain). */
  heavy: boolean;
  source: string | null;
  added: string | null;
}

export interface PublicBenches {
  datasets: PublicBench[];
  note: string | null;
  default_sample: number;
  max_sample: number;
}

export interface BenchMade {
  bench: BenchInfo | null;
  kept: string[];
  dropped: Record<string, string>;
  model: string;
}

export interface ForensicsSide {
  outcome: "pass" | "fail" | "errored" | "broken";
  bucket: string;
  why: string;
}

export interface ForensicsStep {
  tool: string;
  summary: string;
}

/** One task and repeat whose with and without trials ended differently. */
export interface ForensicsPair {
  scenario_id: string;
  repeat: number;
  with: ForensicsSide;
  without: ForensicsSide;
  /** First position where the two runs' tool calls differ; null when they never do. */
  diverged_at: number | null;
  timeline_with: ForensicsStep[];
  timeline_without: ForensicsStep[];
}

export interface Forensics {
  pairs: ForensicsPair[];
  /** Failing trials in these pairs, by what went wrong. */
  counts: Record<string, number>;
}

export interface ImproveChange {
  step_id: string;
  field: "does" | "name" | "harness_add";
  old: string;
  new: string;
  why: string;
}

export interface Improvement {
  proposal: { changes: ImproveChange[]; summary: string; model: string; failures: number; from: number };
  workflow: LabWorkflow;
}

export type BuildSource = "repo" | "suggested" | "workflow" | "design";
/** The Garage design chosen in step 2, with the parameter values edited there. */
export interface DesignChoice {
  id: string;
  parameters: Record<string, string>;
}
/** What was placed on the canvas, sent with a build spec request so the brief describes it. */
export interface CanvasAdded {
  skills: { name: string; path: string; repo?: string; folder?: string }[];
  repos: {
    repo: string;
    name: string;
    category: string;
    parts: { kind: string; name: string; path: string; url: string; description: string }[];
  }[];
  planned: { name: string; ref: string; do?: string }[];
  links: { from: string; to: string; relation: "applies to" | "uses" | "connects to" }[];
  notes: { on: string; text: string }[];
}
export interface BuildTask {
  id: string;
  title: string;
  files: { path: string; new: boolean }[];
  effort: string;
}
export interface BuildSpec {
  json: {
    name: string;
    /** "change": the changes to make in a repo; "new": a new project, with a layout. */
    kind: "change" | "new";
    layout?: { path: string; note: string }[];
    changes?: BuildTask[];
    [k: string]: unknown;
  };
  markdown: string;
  /** The newest result of what is being shipped (this workflow, or the parts on the canvas). */
  shipped?: { name: string; where: string | null; rig: RigScore } | null;
}

// ---------- Garage: the architecture catalog ----------

export type Level = "low" | "medium" | "high";

export interface GarageEntry {
  id: string;
  family: "rag" | "agent";
  name: string;
  summary: string;
  when_to_use: string;
  when_not_to_use: string;
  components: { id: string; label: string; type: string; role: string }[];
  connections: [string, string, string][];
  parameters: { name: string; default: string | number | boolean; range?: [number, number]; options?: (string | number | boolean)[]; what: string }[];
  tradeoffs: { latency: Level; cost: Level; accuracy: Level; complexity: Level };
  signals: string[];
  sources: { title: string; url: string }[];
}

export interface GarageBlueprint extends GarageEntry {
  architecture: Architecture;
}

export interface GarageCatalog {
  families: { id: string; entries: GarageEntry[] }[];
  count: number;
}

export interface GarageRecommendation {
  picks: {
    id: string;
    score: number;
    /** A plain label for how well it fits, never the points. */
    fit?: "strong" | "good" | "possible";
    fit_label?: string;
    reasons: string[];
    entry: GarageEntry;
    explanation: string | null;
    weak?: boolean;
  }[];
  note: string | null;
  /** With no picks: why, the designs its words came close to (never picks), and what to add
   * (architecture-catalog: empty_state). Null when there are picks. */
  empty: GarageEmpty | null;
  /** Roughly what one "Explain the top three with the model" call costs (architecture-catalog: explain_usd). */
  explain_usd?: number;
}

export interface GarageEmpty {
  /** The section's heading in place of "Best fits": "No fits yet". */
  title: string;
  /** "Only 'support' matched, too little to rank on." or that no word matched. */
  matched: string;
  /** "Close, not a fit yet", when there are close designs. */
  heading: string | null;
  near: { id: string; name: string; matched: string[] }[];
  asks_lead: string | null;
  asks: string[];
  words: string | null;
  browse: string;
}

/** A harness or workflow repository as its parts (GET /api/catalog/parts). */
export interface RepoPart {
  id: string;
  kind: string;
  label: string;
  name: string;
  path: string;
  description: string;
  url: string;
}

export interface RepoParts {
  parts: RepoPart[];
  links: { from: string; to: string }[];
  more: number;
}

/** The run going now, anywhere (GET /api/runs/active). */
export interface ActiveRun {
  kind: "repo" | "bench";
  id: number;
  repo?: string | null;
  repo_name?: string;
  bench?: string;
  treatment: string;
  /** A baseline check on a bench. */
  probe?: boolean;
  model: string;
  spent_usd: number;
  budget_usd: number;
  trials: number;
}

/** The Lab workflow a catalog design opens as (POST /api/garage/workflow). */
/** A Lab workflow's link to the design it came from: which one, its parameter values when it
 * was used, and how it was set up for the goal. */
export interface DesignLink {
  id: string;
  name: string;
  parameters: Record<string, string>;
  handoff?: Omit<GarageWorkflow, "workflow"> | null;
}

export interface GarageWorkflow {
  workflow: LabWorkflow;
  discipline: string;
  discipline_label: string;
  /** The use case's words that picked the discipline; empty when it fell back to the default. */
  matched: string[];
  /** What the Lab leaves out of this design, when it can't run all of it. */
  note: string | null;
}

/** What "Full" buys at this budget (trial-budget: full_label): the pairs it reaches, the smallest
 * change those tell from noise, and the run-size choice's label. "conclusive" only when they
 * reach the pairs sized for the target change. */
export interface FullSize {
  state: "conclusive" | "detects" | "like_pilot" | "nothing";
  pairs: number;
  planned_pairs: number;
  pts: number | null;
  text: string;
}

/** The budget check's prediction for a run that hasn't started (POST /api/runs/estimate). */
/** What a planned run on a saving metric can show, before it is paid for (engine rig_score.metric_plan). */
export interface MetricPlan {
  metric: MetricId;
  need_pairs: number;
  planned_pairs: number;
  /** The planned pairs can meet the pass-rate guard (if the pass rate holds). */
  enough: boolean;
  /** Short of the guard, but "Keep going until it's decided" adds pairs toward it (the Lab or a repo's Measure). */
  extends?: boolean;
  need_usd: number | null;
  /** What Measure says: what the guard needs, then whether this run gets there. */
  lines: string[];
}

export interface RunForecast {
  /** Present when the run is scored on tokens, cost or time. */
  metric_plan?: MetricPlan;
  pairs: number;
  trials: number;
  per_trial: { with: number; without: number };
  source: { with: string; without: string };
  per_pair: number;
  total_usd: number;
  free: boolean;
  pairs_in_budget?: number;
  /** With the pairs it will reach, an effect smaller than ±pts can't be told from noise. */
  detect?: { pairs: number; pts: number; base_rate: number } | null;
  /** Earlier trials the prediction was measured on, per arm (0: the prior). */
  measured_trials?: { with: number; without: number };
  /** What it takes to tell a ±target_pts change from noise: pairs, and the budget that pays for them. */
  sizing?: {
    target_pts: number;
    pairs: number;
    usd: number | null;
    planned_pairs: number;
    planned_pts: number | null;
    enough_planned: boolean;
    enough_budget: boolean;
  };
  /** A full run the budget stops within the pilot's pairs: said plainly. */
  no_better_than_pilot?: string | null;
  /** Asked for with full_pairs: what a full run buys at this budget, whatever size is chosen. */
  full?: FullSize;
  /** "Keep going until it's decided" on: the most pairs it may grow to while undecided. */
  extends?: RunExtends;
  model: string;
}

/** What a run with "Keep going until it's decided" may grow to (judge-experiment: auto_extend):
 * the caps' pairs, what they cost (null: free), the pairs the budget stops it at, and the line. */
export interface RunExtends {
  max_pairs: number;
  usd: number | null;
  pairs_in_budget: number;
  line: string;
}

/** Try it (engine skill try-it): what a try is predicted to cost, before it starts. */
export interface TryPrice {
  inputs: number;
  per_input: number;
  judge_per_input: number;
  total_usd: number;
  cap_usd: number;
  /** The agent stops itself at the cap (Claude Code); else only the checks before each input hold it. */
  hard_cap: boolean;
  source: string;
  free: boolean;
  inputs_in_budget: number;
  model: string;
  /** Grading is offered (support and research workflows). */
  gradable: boolean;
  placeholder: string;
  discipline: string | null;
  /** The model it runs on, as people say it ("Sonnet 5.5"), and a workflow's step count. */
  model_label?: string;
  steps?: number | null;
}

export type TryStatus = "waiting" | "running" | "done" | "capped" | "errored" | "broken" | "skipped" | "stopped";

export interface TryResult {
  index: number;
  status: TryStatus;
  answer: string | null;
  steps: { kind: "workflow"; steps: number; ran: number; missing: string[] } | { kind: "skill"; opened: boolean } | null;
  cost_usd: number;
  duration_s: number;
  detail: string;
  grade: { followed?: boolean; reason?: string; error?: string; cost_usd: number } | null;
}

export interface TryJob {
  id: string;
  status: "running" | "done" | "stopped" | "stopped_budget" | "error";
  detail: string;
  label: string;
  agent: string;
  model: string;
  budget_usd: number;
  hard_cap: boolean;
  grade: boolean;
  spent_usd: number;
  stopping: boolean;
  inputs: string[];
  results: TryResult[];
}

/** Measuring a compare set, priced before it starts (engine judge-experiment: compare). */
export interface ComparePlan {
  bench: string;
  bench_name: string;
  size: "pilot" | "full";
  pairs: number;
  budget: number;
  /** Each workflow's even share of the budget. */
  share: number;
  total_usd: number;
  total_in_budget: number;
  /** How many baselines get paid for: one per session model. */
  baselines: number;
  /** What "Full" buys at this budget, whatever size is chosen: the least-paid workflow's pairs. */
  full?: FullSize;
  workflows: {
    id: string;
    name: string;
    model: string;
    pairs: number;
    pairs_in_budget: number;
    /** "Without" pairs reused from an earlier workflow in the set. */
    shared_baseline: number;
    per_trial: { with: number; without: number };
    source: string | null;
    budget: number;
    predicted_usd: number;
    predicted_in_budget: number;
    /** What it pays for "without" trials in full: 0 when it reuses them all. */
    baseline_usd: number;
  }[];
  /** On more than one session model: the extra baselines' cost and the offer to run all on one. */
  align: CompareAlign | null;
}

/** Running every workflow in the set on one session model, so one baseline is shared. */
export interface CompareAlign {
  model: string;
  label: string;
  /** The session models the set is on now, in pinned order. */
  models: string[];
  extra_baseline_usd: number;
  total_usd: number;
  total_in_budget: number;
  pairs_in_budget: number;
  /** Now minus all on `model`; negative when that model costs more. */
  saving_usd: number;
  notice: string;
  action: string;
  result: string;
}

/** One workflow's result on the compare bench. */
export interface CompareResult {
  id: number;
  bench: string;
  status: string;
  verdict: string;
  diff: number | null;
  ci_low: number | null;
  ci_high: number | null;
  n_pairs: number;
  pass_with: number | null;
  pass_without: number | null;
  spent_usd: number;
  reused: number;
  rig?: RigScore;
  validity?: Validity;
  treatment: string;
  date?: string;
  /** The session model it ran on. */
  model?: string | null;
  /** The "with" arm's spend per trial. */
  cost_with?: number | null;
  /** Measured on another session model than the workflow is on now: shown marked, never ranked. */
  other_model?: { model: string; label: string; text: string } | null;
}

/** The ranking: a winner only when its interval clears every other one's. On one session model by
 * Rig score; across models by the pass rate with the workflow, then cost. */
export interface CompareRank {
  state: "winner" | "not_proven" | "too_few";
  by: "rig" | "pass_with";
  by_text: string;
  /** The session models the ranked results ran on. */
  models: string[];
  /** Each ranked one's figure and its interval: the change, or the pass rate with it. */
  ranked: Record<string, { value: number; lo: number; hi: number }>;
  /** Across models, what each one's lift is against: "vs Direct on Haiku 5.5". Empty otherwise. */
  lift_vs: Record<string, string>;
  order: string[];
  winner: string | null;
  close: [string, string] | null;
  more_pairs: number | null;
  text: string;
}

export interface CompareStanding {
  bench: string;
  bench_name: string;
  workflows: { id: string; name: string; result: CompareResult | null }[];
  /** Each workflow's session model now (when sent with its steps). */
  models?: Record<string, string | null>;
  rank: CompareRank;
}

export interface CompareJobView {
  job: string;
  bench: string;
  bench_name: string;
  status: "running" | "stopping" | "done" | "stopped";
  budget: number;
  share: number;
  spent: number;
  workflows: {
    id: string;
    name: string;
    experiment: number | null;
    status: "queued" | "running" | "done" | "stopped" | "skipped" | "error";
    budget: number | null;
    spent: number;
    detail: string | null;
    /** The session model it ran on in this job. */
    model?: string | null;
    result: CompareResult | null;
  }[];
  rank: CompareRank;
}

/** One tutorial step's words (tutorial skill), filled in with the example's and the run's facts. */
export interface TutorialStep {
  id: "describe" | "design" | "build" | "measure" | "ship";
  title: string;
  lead: string;
  note: string;
  [key: string]: string | string[];
}

/** The tutorial's example space (engine GET /api/tutorial): its words, the example and one recorded run. */
export interface Tutorial {
  text: {
    home: { title: string; title_done: string; lead: string; start: string; replay: string };
    proof: { pill: string; caption: string; without: string; with: string };
    eyebrow: string;
    leave: string;
    stepper: string;
    steps: TutorialStep[];
    finish: { eyebrow: string; title: string; lead: string; options: { id: "repo" | "lab" | "home"; label: string; text: string; to: "repo" | "lab" | "home" }[] };
    stale: string;
    recorded_note: string;
    settings_title: string;
    settings: string[];
  };
  example: {
    name: string;
    files: { path: string; text: string }[];
    skill: { name: string; description: string; path: string; text: string; body: string };
    tasks: { id: string; title: string; kind: string; instruction: string; check: string }[];
  };
  run: TutorialRun | null;
}

export interface TutorialArm {
  passed: number;
  trials: number;
  outcomes: string[];
  seconds: number[];
  /** Why a trial didn't pass, as the engine said it ("timed out after 900 s"); "" when it did. */
  details: string[];
}

export interface TutorialRun {
  recorded: string;
  model: { file: string; id: string; server: string; agent: string; nudge: boolean; label: string };
  skill: string;
  tasks: { id: string; title: string; with: TutorialArm; without: TutorialArm }[];
  n: number;
  with: number;
  without: number;
  diff: number | null;
  ci_low: number | null;
  ci_high: number | null;
  verdict: Verdict;
  rig: RigScore;
  stale: boolean;
}

/** One step of the repo tutorial (tutorial-tokens skill): the example's words, then `yours`, what to
 * do on your own repo. */
export type TokensTourStep = TutorialStep & { yours: string[] };

/** A row of the repo tutorial's Build step: a kind of thing on your canvas, where it shows, its badge. */
export interface TokensTourPlace {
  what: string;
  where: string;
  badge: string;
  tone: "positive" | "neutral" | "warning";
}

/** The repo tutorial: Rig your own repo for fewer tokens (engine GET /api/tutorial/tokens). */
export interface TokensTutorial {
  text: {
    home: { title: string; title_done: string; lead: string; start: string; replay: string };
    eyebrow: string;
    leave: string;
    stepper: string;
    yours_title: string;
    steps: TokensTourStep[];
    finish: { eyebrow: string; title: string; lead: string; options: { id: string; label: string; text: string; to: "repo" | "first" | "home" }[] };
    stale: string;
    not_recorded: string;
    recorded_note: string;
    settings_title: string;
    settings: string[];
  };
  example: Tutorial["example"];
  run: TokensTutorialRun | null;
}

export interface TokensTutorialArm extends TutorialArm {
  /** Each trial's tokens, in + out as the agent reported them. */
  tokens: number[];
}

export interface TokensTutorialRun {
  recorded: string;
  model: TutorialRun["model"];
  skill: string;
  repeats: number;
  took_s: number | null;
  tasks: { id: string; title: string; with: TokensTutorialArm; without: TokensTutorialArm }[];
  n: number;
  with: number;
  without: number;
  verdict: Verdict;
  metric: RigMetric | null;
  rig: RigScore;
  stale: boolean;
}
