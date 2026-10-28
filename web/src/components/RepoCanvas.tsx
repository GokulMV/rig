import {
  Anchor,
  BookOpen,
  Bot,
  ChevronDown,
  ChevronRight,
  Cloud,
  Code2,
  Database,
  Eye,
  FileText,
  FlaskConical,
  Package,
  Globe,
  ListChecks,
  MessagesSquare,
  Monitor,
  Palette as PaletteIcon,
  PenLine,
  Plug,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  Terminal,
  X,
} from "lucide-react";
import { type ReactNode, useMemo, useState, type MutableRefObject } from "react";

import type { CanvasStore } from "../lib/canvasState";
import type { DragMeta } from "../lib/dragSkill";
import { aboutTheAgent, laneLine, measureBadge, useRules } from "../lib/rules";
import type { ArchFlow, ArchKind, Architecture, Estimate, Project, Scenario, TreatmentItem, Workflow } from "../lib/types";
import { Canvas, type CanvasEdge, type CanvasNode, type Rect } from "./Canvas";
import { MeasureBadge } from "./MeasureBadge";

export const ARCH_STYLE: Record<ArchKind, { color: string; icon: ReactNode; label: string }> = {
  frontend: { color: "#be185d", icon: <Monitor size={14} />, label: "Frontend" },
  backend: { color: "#2f6fbb", icon: <Server size={14} />, label: "Backend" },
  database: { color: "#15803d", icon: <Database size={14} />, label: "Data store" },
  messagebus: { color: "#c2410c", icon: <MessagesSquare size={14} />, label: "Message bus" },
  // "cloud" covers hosting, gateways and model providers alike: named by what it is (archStyle).
  cloud: { color: "#0e7490", icon: <Cloud size={14} />, label: "Cloud service" },
  security: { color: "#b91c1c", icon: <ShieldCheck size={14} />, label: "Security" },
  external: { color: "#475569", icon: <Globe size={14} />, label: "External" },
};

const MODEL_WORDS = /\b(llm|llms|model|models|claude|anthropic|openai|gpt|gemini|bedrock|vertex|ollama|mistral|inference|embedding|embeddings|litellm|model gateway)\b/i;
const EDGE_WORDS = /\b(cdn|proxy|gateway|load balancer|nginx|edge|ingress|cloudflare)\b/i;
const MODEL_STYLE = { color: "#6d28d9", icon: <Bot size={14} />, label: "Model" };

/** A block's colour, icon and type label: by its type, but a model or model gateway is a Model,
 * and a proxy or CDN an Edge / proxy, whatever type the map gave it. */
export function archStyle(c: { type: ArchKind; label: string; sublabel?: string | null; role?: string | null }) {
  const text = `${c.label} ${c.sublabel ?? ""}`;
  if ((c.type === "cloud" || c.type === "external" || c.type === "backend") && MODEL_WORDS.test(text)) return MODEL_STYLE;
  if (c.type === "cloud" && EDGE_WORDS.test(text)) return { ...ARCH_STYLE.cloud, label: "Edge / proxy" };
  return ARCH_STYLE[c.type] ?? ARCH_STYLE.backend;
}

// A catalog blueprint's blocks are agent roles, not infrastructure: named by what each part
// does (its label and role), never "Cloud service". First match wins.
const BLUEPRINT_ROLES: [RegExp, string][] = [
  [/^(answer|result|output|response)$/i, "Output"],
  [/\b(tools?|web search)\b/i, "Tools"],
  [/\benvironment\b/i, "Environment"],
  [/\b(grader|critic|evaluator|scorer|judge|verifier|checker|reflection)\b/i, "Checker"],
  [/\bplanner\b/i, "Planner"],
  [/\b(router|classifier|triage|gate)\b/i, "Router"],
  [/\b(orchestrator|supervisor|lead)\b/i, "Coordinator"],
  [/\b(reranker|rewriter|embedder|extractor|retrieval|draft writer)\b/i, "Retrieval step"],
];

/** The header of a blueprint's block: its role in the design (Planner, Checker, Router ...),
 * else Agent for any other model-backed part; null where the type's own name fits. */
export function blueprintRole(c: { type: ArchKind; label: string; sublabel?: string | null }): string | null {
  if (c.type !== "cloud" && c.type !== "external") return null;
  if (archStyle(c) === MODEL_STYLE) return null; // already "Model"
  for (const [rx, name] of BLUEPRINT_ROLES) if (rx.test(c.label)) return name;
  return c.type === "cloud" ? "Agent" : null;
}

const SETUP_ICON: Record<string, ReactNode> = {
  "CLAUDE.md": <FileText size={14} />,
  "AGENTS.md": <FileText size={14} />,
  Hooks: <Anchor size={14} />,
  "MCP servers": <Plug size={14} />,
  "Test command": <Terminal size={14} />,
  Subagents: <Bot size={14} />,
};

const STEP_STYLE: Record<string, { color: string; icon: ReactNode }> = {
  research: { color: "#2f6fbb", icon: <Search size={14} /> },
  plan: { color: "#4f5bd5", icon: <ListChecks size={14} /> },
  code: { color: "#1b6c80", icon: <Code2 size={14} /> },
  test: { color: "#94590a", icon: <FlaskConical size={14} /> },
  review: { color: "#c2410c", icon: <Eye size={14} /> },
  write: { color: "#0e7490", icon: <PenLine size={14} /> },
  data: { color: "#6d28d9", icon: <Database size={14} /> },
  design: { color: "#be185d", icon: <PaletteIcon size={14} /> },
};
const SKILL = "#7c3aed";

export const BLOCK_W = 184;
// A harness repo's parts, one colour per kind (curate-catalog parts.kinds).
const PART_COLOR: Record<string, string> = {
  instructions: "#334155",
  command: "#0f766e",
  agent: "#2f6bbf",
  skill: "#7c3aed",
  hook: "#b45309",
  mcp: "#be185d",
};
export const BLOCK_H = 104;
const COL = 248; // the engine lays architecture out on 248 × 128
const ROW = 140;
const LANE_GAP = 90;
// The agent setup lane: five blocks a row, a little closer than other lanes (no flow runs
// between them), so a row fits a laptop's canvas at the 70% it opens at; more wrap.
export const SETUP_COLS = 5;
const SETUP_COL = 212;
// Between its rows: room for an "applies to" tag between a planned part and what it is for.
const SETUP_ROW_GAP = 48;

export type NodeInfo =
  | { kind: "arch"; c: Architecture["components"][number]; blueprint?: boolean }
  | {
      kind: "setup";
      label: string;
      detail: string;
      /** False for a placeholder: the repo doesn't have it yet (a CLAUDE.md to add). */
      present?: boolean;
      /** The repo's own test command, as the setup lane found it: what a CLAUDE.md should name. */
      tests?: string;
    }
  | { kind: "repo-skill"; t: TreatmentItem }
  | { kind: "step"; name: string; type: string; why: string; index: number }
  | { kind: "card"; card: CanvasStore["state"]["cards"][number] }
  | { kind: "lane"; label: string };

interface Props {
  repoName: string;
  project: Project;
  /** The goal in use (step 1, saved or not): whether it is about the coding agent. */
  goal?: string;
  architecture: Architecture | null;
  workflow: Workflow | null;
  scenarios: Scenario[];
  treatments: { repo: TreatmentItem[]; user: TreatmentItem[]; installed: TreatmentItem[] };
  store: CanvasStore;
  estimates: Record<string, Estimate | "loading">;
  selected: string | null;
  onSelect: (id: string | null, info: NodeInfo | null) => void;
  /** A drop: where its card goes (beside the block it landed on, or under the pointer), the
   * block it landed on, and the pointer itself with what the drag carried. */
  onDrop: (
    data: string,
    x: number,
    y: number,
    near: string | null,
    drop: { point: { x: number; y: number }; visible: Rect; meta?: DragMeta },
  ) => void;
  rates?: Record<string, { with: number | null; without: number | null }>;
  live?: boolean;
  overlays?: ReactNode;
  /** Set to a function that finds an open spot for a card added by click (not drag). */
  freeSlot?: MutableRefObject<(() => { x: number; y: number }) | null>;
  /** Open space under everything drawn: where a harness repo's parts are laid out. */
  belowAll?: MutableRefObject<(() => { x: number; y: number }) | null>;
  /** The top-left of a w × h area, as close to a point as it can be without covering a block:
   * where a dropped harness repo's parts are laid out. */
  clearArea?: MutableRefObject<((w: number, h: number, at: { x: number; y: number }) => { x: number; y: number }) | null>;
  /** A flow to highlight: its steps get numbers, everything else fades. */
  flow?: ArchFlow | null;
  /** Set to a function that finds a spot beside a block (for "Add" placing an item next to it). */
  besideSlot?: MutableRefObject<((id: string) => { x: number; y: number } | null) | null>;
  /** A catalog blueprint is drawn: just its parts and lines, fixed in place, not your repo's. */
  blueprint?: boolean;
  /** An area to bring into view: a dropped harness repo's parts. */
  reveal?: { key: string; rect: Rect } | null;
  /** The architecture drawn is one open suggestion, previewed: its parts say Preview, not New. */
  previewing?: boolean;
  /** A skill's last run, by block id, in the words Measure shows it (Rig score and verdict). */
  verdicts?: Record<string, MeasuredVerdict>;
}

/** A run's result as Measure shows it: the Rig score and the verdict word. */
export interface MeasuredVerdict {
  score: number | null;
  word: string;
  tone: "helps" | "hurts" | "inconclusive";
  run: number;
}

/** A skill's badge: its last run's Rig score and verdict when it was measured (the same words as
 * Measure), else its estimate. A run's number never shows as an estimate's "Measured +17 pts". */
function Effect({ e, v }: { e: Estimate | "loading" | undefined; v?: MeasuredVerdict }) {
  if (v)
    return (
      <span className={`est est--verdict est--${v.tone}`} title={`Run #${v.run}: Rig ${v.score ?? "–"}, ${v.word}. The same result as on Measure.`}>
        Rig {v.score ?? "–"} · {v.word}
      </span>
    );
  return <EstimateBadge e={e} />;
}

function Block({
  color,
  icon,
  type,
  title,
  sub,
  subTitle,
  foot,
  selected,
  target,
  dashed,
  onRemove,
  removeLabel,
  onClick,
  flag,
  flagTone,
  dim,
  badge,
}: {
  color: string;
  icon: ReactNode;
  type: string;
  title: string;
  sub?: string | null;
  /** The whole of a sub line that two lines may cut short. */
  subTitle?: string;
  foot?: ReactNode;
  selected: boolean;
  target: boolean;
  dashed?: boolean;
  onRemove?: () => void;
  removeLabel?: string;
  onClick: () => void;
  /** A warning from checking the spec against the code, or "New" for a proposed block. */
  flag?: string;
  flagTone?: "new" | "removed";
  dim?: boolean;
  /** Whether Measure can test it (measurability), on its foot line. */
  badge?: ReactNode;
}) {
  return (
    <div
      className={`block${selected ? " is-selected" : ""}${target ? " is-over" : ""}${dashed ? " block--dashed" : ""}${dim ? " is-dim" : ""}${flagTone ? ` block--${flagTone}` : ""}`}
      style={{ ["--node" as string]: color }}
    >
      <div className="block__head">
        {icon}
        <span>{type}</span>
        {onRemove ? (
          <button type="button" className="node__remove" data-no-drag aria-label={removeLabel} onClick={onRemove}>
            <X size={14} />
          </button>
        ) : null}
      </div>
      <button type="button" className="block__body" onClick={onClick} aria-pressed={selected}>
        <strong>{title}</strong>
        {sub ? (
          <span className="block__sub" title={subTitle}>
            {sub}
          </span>
        ) : null}
        {foot || badge || flag ? (
          <span className="block__foot">
            {flag ? <span className={`block__flag${flagTone ? ` block__flag--${flagTone}` : ""}`}>{flag}</span> : null}
            {badge}
            {foot}
          </span>
        ) : null}
      </button>
    </div>
  );
}

export function EstimateBadge({ e }: { e: Estimate | "loading" | undefined }) {
  if (!e) return null;
  if (e === "loading") return <span className="est est--loading">Estimating…</span>;
  if (e.basis === "none") return <span className="est">No estimate</span>;
  const sign = (n: number) => `${n > 0 ? "+" : ""}${n}`;
  const word = e.basis === "measured" ? "Measured" : e.basis === "rough" ? "Rough" : "≈";
  return (
    <span
      className={`est est--${e.basis}${e.refining ? " est--refining" : ""}`}
      title={`${word} ${sign(e.low ?? 0)} to ${sign(e.high ?? 0)} pts (pass-rate points). ${e.reason ?? ""}`}
    >
      {word} {sign(e.likely ?? 0)} pts
    </span>
  );
}

export function RepoCanvas(p: Props) {
  const { state } = p.store;
  const goals = useRules("repo-goals");
  const mr = useRules("measurability");
  const [drafts, setDrafts] = useState<Record<string, { x: number; y: number }>>({});
  // The app's architecture is folded away when the goal is about the coding agent; your choice wins.
  const archKey = `pg.arch-open:${p.repoName}`;
  const [archOpen, setArchOpenState] = useState<boolean | null>(() => {
    try {
      const v = localStorage.getItem(archKey);
      return v === null ? null : v === "1";
    } catch {
      return null;
    }
  });
  // Toggled on this canvas since it opened: that choice wins even over a suggestion's parts.
  const [toggledHere, setToggledHere] = useState(false);
  const setArchOpen = (open: boolean) => {
    setToggledHere(true);
    setArchOpenState(open);
    try {
      localStorage.setItem(archKey, open ? "1" : "0");
    } catch {
      // Storage blocked: the choice lasts for this visit.
    }
  };
  // Parts a suggestion adds or takes away are what "With accepted" is for: the row opens to show
  // them, whatever the goal folds it to, until you fold it here.
  const archChanged = (p.architecture?.components ?? []).some((c) => c.source === "proposed" || c.source === "removed");
  const archShown = archChanged && !toggledHere ? true : (archOpen ?? !aboutTheAgent(p.goal ?? p.project.use_case, goals));

  const { nodes, edges, info } = useMemo(() => {
    const nodes: CanvasNode[] = [];
    const edges: CanvasEdge[] = [];
    const info = new Map<string, NodeInfo>();
    const pos = (id: string, x: number, y: number) =>
      p.blueprint ? { x, y } : (drafts[id] ?? state.positions[id] ?? { x, y });
    // Blocks the repo has that you took off this plan; a blueprint is read-only.
    const gone = new Set(p.blueprint ? [] : (state.removed ?? []));
    const drop = (id: string, title: string) =>
      p.blueprint ? {} : { onRemove: () => p.store.removeBlock(id), removeLabel: `Remove ${title} from the plan` };
    const add = (id: string, x: number, y: number, i: NodeInfo, render: CanvasNode["render"], extra: Partial<CanvasNode> = {}) => {
      if (gone.has(id)) return;
      info.set(id, i);
      nodes.push({ id, ...pos(id, x, y), w: BLOCK_W, h: BLOCK_H, render, draggable: !p.blueprint, label: labelOf(i), ...extra });
    };
    // Each row says what Measure tests in it (measurability: lanes), beside its title.
    const lane = (id: string, y: number, label: string, measure?: string | null) => {
      info.set(id, { kind: "lane", label });
      nodes.push({
        id,
        x: 0,
        y,
        w: 400,
        h: 24,
        ports: false,
        draggable: false,
        label: measure ? `${label} · ${measure}` : label,
        render: () => (
          <div className="lane">
            {label}
            {measure ? <span className="lane__measure">{measure}</span> : null}
          </div>
        ),
      });
    };
    const badge = (i: NodeInfo) => <MeasureBadge b={measureBadge(i, mr)} />;
    const sel = (id: string) => p.selected === id;
    const pick = (id: string) => () => p.onSelect(id, info.get(id) ?? null);

    // A blueprint is only its own parts and lines.
    const archLane = (top: number, label: string, toggle: boolean) => {
      let y = top;
      const comps = p.architecture?.components ?? [];
      if (!comps.length) return y;
      const check = p.architecture?.check;
      const inFlow = new Set((p.flow?.steps ?? []).flatMap((st) => [st.from, st.to]));
      const head =
        label +
        (check ? ` · checked: ${check.found} of ${check.total} found in the code` : "");
      const archMeasure = toggle ? laneLine("arch", mr) : null;
      if (toggle) {
        info.set("lane:arch", { kind: "lane", label: head });
        nodes.push({
          id: "lane:arch",
          x: 0,
          y,
          w: 520,
          h: 28,
          ports: false,
          draggable: false,
          label: archMeasure ? `${head} · ${archMeasure}` : head,
          render: () => (
            // The row's line sits beside the toggle, not in it: the button stays the title's size.
            <div className="lane-row">
              <button
                type="button"
                className="lane lane--toggle"
                data-no-drag
                aria-expanded={archShown}
                onClick={() => setArchOpen(!archShown)}
              >
                {archShown ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />} {head}
              </button>
              {archMeasure ? <span className="lane lane__measure">{archMeasure}</span> : null}
            </div>
          ),
        });
        if (!archShown) return y + 28 + LANE_GAP / 2;
      } else lane("lane:arch", y, head);
      const xs = comps.map((c) => c.pos?.[0] ?? 0);
      const ys = comps.map((c) => c.pos?.[1] ?? 0);
      const [x0, y0] = [Math.min(...xs), Math.min(...ys)];
      let maxY = 0;
      for (const c of comps) {
        const st = archStyle(c);
        const cx = ((c.pos?.[0] ?? 0) - x0) * (COL / 248);
        const cy = top + 40 + ((c.pos?.[1] ?? 0) - y0) * (ROW / 128);
        maxY = Math.max(maxY, cy);
        const id = `arch:${c.id}`;
        const isNew = c.source === "proposed";
        const isGone = c.source === "removed";
        // A suggestion's part says whether it is only being previewed (else it was accepted).
        // Kept short: the flag and the badge share one line, so the block keeps its height.
        const noInput = check?.no_input?.includes(c.label);
        add(id, cx, cy, { kind: "arch", c, blueprint: p.blueprint }, ({ target }) => (
          <Block
            color={st.color}
            icon={st.icon}
            type={c.role || (p.blueprint ? blueprintRole(c) : null) || st.label}
            title={c.label}
            sub={c.sublabel}
            selected={sel(id)}
            target={target}
            onClick={pick(id)}
            dashed={isNew || isGone || c.check === "weak" || c.check === "missing"}
            {...drop(id, c.label)}
            dim={Boolean(p.flow) && !inFlow.has(c.id)}
            flag={
              isGone
                ? p.previewing
                  ? "Preview"
                  : "Removed"
                : isNew
                  ? p.previewing
                    ? "Preview"
                    : "New"
                : c.check === "missing"
                  ? "Not Found in the Code"
                  : c.check === "weak"
                    ? "Weak Evidence"
                    : noInput
                      ? "No Input Shown"
                      : undefined
            }
            flagTone={isGone ? "removed" : isNew ? "new" : undefined}
            // Only a suggestion's parts carry a badge here: the row's line covers the app's own.
            badge={isNew || isGone ? badge({ kind: "arch", c }) : undefined}
          />
        ));
      }
      const added = new Set(comps.filter((c) => c.source === "proposed").map((c) => c.id));
      const stepOf = new Map((p.flow?.steps ?? []).map((st, n) => [`${st.from}>${st.to}`, n + 1]));
      for (const [i, conn] of (p.architecture?.connections ?? []).entries()) {
        // What flows on a line ("SQL", "HTTPS") is in the details panel: pills would cover the blocks.
        // Planned lines say so on the line: they are the gaps.
        const planned = conn.variant === "planned";
        const step = stepOf.get(`${conn.from}>${conn.to}`);
        edges.push({
          id: `a${i}`,
          from: `arch:${conn.from}`,
          to: `arch:${conn.to}`,
          live: p.live || Boolean(step),
          variant:
            conn.variant === "removed"
              ? "removed"
              : planned
                ? "planned"
                : conn.variant === "added" || added.has(conn.from) || added.has(conn.to)
                  ? "new"
                  : "flow",
          // New and cut links are told apart by colour (see the legend): labels would cover blocks.
          // A short tag: long "planned: ..." sentences covered the blocks. The sentence is its title.
          label: planned ? "planned" : undefined,
          title: planned ? `Planned, not built yet${conn.label ? `: ${conn.label}` : ""}` : undefined,
          dim: Boolean(p.flow) && !step,
          step,
        });
      }
      return maxY + BLOCK_H + LANE_GAP;
    };

    if (p.blueprint) {
      archLane(0, `Blueprint · ${p.architecture?.title ?? ""}`, false);
      return { nodes, edges, info };
    }
    const keptEdges = () => edges.filter((e) => !gone.has(e.from) && !gone.has(e.to));

    // Lane 1: the coding agent's setup, first: what an agent working here reads and runs.
    let y = 0;
    lane("lane:setup", y, "Agent setup · what the coding agent reads and runs here", laneLine("setup", mr));
    // Wrapped at SETUP_COLS a row, so the lane fits the canvas at the zoom it opens at.
    let col = 0;
    const slot = () => {
      const n = col++;
      return [(n % SETUP_COLS) * SETUP_COL, y + 40 + Math.floor(n / SETUP_COLS) * (BLOCK_H + SETUP_ROW_GAP)] as const;
    };
    const setupItems = p.project.agent ?? [];
    const repoSkills = p.treatments.repo;
    const tests = setupItems.find((x) => x.id === "setup:Test command" && x.present)?.run;
    for (const s of setupItems) {
      if (s.label === "Skills" && repoSkills.length) {
        // The repo's skills are drawn one by one, in this slot.
        for (const t of repoSkills) {
          const id = `repo-skill:${t.path}`;
          add(id, ...slot(), { kind: "repo-skill", t }, ({ target }) => (
            <Block
              color={SKILL}
              icon={<Sparkles size={14} />}
              type="Skill · in repo"
              title={t.name}
              sub={t.description}
              foot={<Effect e={p.estimates[id]} v={p.verdicts?.[id]} />}
              // A measured skill's Rig score says it is measurable; until then the badge does.
              badge={p.verdicts?.[id] ? undefined : badge({ kind: "repo-skill", t })}
              selected={sel(id)}
              target={target}
              onClick={pick(id)}
              {...drop(id, t.name)}
            />
          ));
        }
        continue;
      }
      const id = s.id;
      const icon = SETUP_ICON[s.label] ?? <FileText size={14} />;
      add(id, ...slot(), { kind: "setup", label: s.label, detail: s.detail, present: s.present, tests }, ({ target }) => (
        <Block
          color="#334155"
          icon={icon}
          type="Agent setup"
          // The header says missing and the line under it what to do: the title stays readable.
          title={s.present || s.label === "CLAUDE.md" || s.label === "AGENTS.md" ? s.label : `${s.label}: none yet`}
          sub={s.label === "Test command" && s.run ? s.run : s.detail}
          dashed={!s.present}
          badge={badge({ kind: "setup", label: s.label, detail: s.detail, present: s.present, tests })}
          selected={sel(id)}
          target={target}
          onClick={pick(id)}
          {...(s.present ? drop(id, s.label) : {})}
        />
      ));
    }
    if (!setupItems.length) {
      // An older engine: what the scan found, as before.
      for (const s of p.project.scan.agent_setup.filter((x) => x !== "Skills")) {
        const id = `setup:${s}`;
        add(id, ...slot(), { kind: "setup", label: s, detail: "", present: true }, ({ target }) => (
          <Block color="#334155" icon={SETUP_ICON[s] ?? <FileText size={14} />} type="Agent setup" title={s} badge={badge({ kind: "setup", label: s, detail: "", present: true })} selected={sel(id)} target={target} onClick={pick(id)} {...drop(id, s)} />
        ));
      }
    }
    // A part planned for the agent setup (a CLAUDE.md to add) sits in this lane, after the rest.
    const inLane = new Map<string, readonly [number, number]>();
    for (const c of state.cards) if (c.ref.startsWith("setup/") && c.kind === "suggestion") inLane.set(c.id, slot());
    y += 40 + Math.max(1, Math.ceil(col / SETUP_COLS)) * (BLOCK_H + SETUP_ROW_GAP) - SETUP_ROW_GAP + LANE_GAP;

    // Lane 2: the agent workflow
    if (p.workflow) {
      lane("lane:flow", y, `Workflow · ${p.workflow.name}`, laneLine("flow", mr));
      let prev: string | null = null;
      p.workflow.steps.forEach((st, i) => {
        const style = STEP_STYLE[st.type] ?? { color: "#5d5f60", icon: <BookOpen size={14} /> };
        const id = `step:${st.name}`;
        const own = p.scenarios.filter((s) => s.step === st.name);
        const r = p.rates?.[st.name];
        add(id, i * COL, y + 40, { kind: "step", name: st.name, type: st.type, why: st.why, index: i }, ({ target }) => (
          <Block
            color={style.color}
            icon={style.icon}
            type={`${i + 1} · ${st.type}`}
            title={st.name}
            sub={st.why}
            foot={
              r ? (
                <span className="num">
                  with {r.with == null ? "–" : `${r.with}%`} · without {r.without == null ? "–" : `${r.without}%`}
                </span>
              ) : (
                <span>{own.length ? stepTasks(own) : "No tasks"}</span>
              )
            }
            selected={sel(id)}
            target={target}
            onClick={pick(id)}
            {...drop(id, st.name)}
          />
        ));
        // A removed step is bridged: the steps either side of it run one after the other.
        if (gone.has(id)) return;
        if (prev) edges.push({ id: `w${i}`, from: prev, to: id, live: p.live || false });
        prev = id;
      });
      y += 40 + BLOCK_H + LANE_GAP;
    }

    // Lane 3: the app's architecture, below the agent's setup, folded away when the goal is
    // about the coding agent rather than the app.
    const n = p.architecture?.components.length ?? 0;
    const src =
      p.architecture?.source === "archify"
        ? "Archify spec in the repo"
        : p.architecture?.source === "mapped"
          ? "mapped with Archify"
          : "read from the code";
    archLane(y, `Architecture of ${p.repoName} · ${n} part${n === 1 ? "" : "s"} · ${src}`, true);

    // Cards you placed
    for (const c of state.cards) {
      const id = `card:${c.id}`;
      const dashed = c.kind !== "skill" && c.kind !== "part";
      const type =
        c.kind === "skill"
          ? "Skill"
          : c.kind === "part"
            ? (c.part?.label ?? "Part")
            : c.kind === "catalog"
              ? c.parts
                ? `From GitHub · ${c.parts} parts`
                : "From GitHub · pick a skill"
              : c.ref.startsWith("setup/")
                ? "Planned · agent setup"
                : "Suggested skill";
      const lanePos = inLane.get(c.id);
      add(
        id,
        lanePos?.[0] ?? c.x,
        lanePos?.[1] ?? c.y,
        { kind: "card", card: c },
        ({ target }) => (
          <Block
            color={c.kind === "part" ? (PART_COLOR[c.part?.kind ?? ""] ?? "#24292f") : c.kind === "catalog" ? "#24292f" : SKILL}
            icon={c.kind === "catalog" || c.kind === "part" ? <Package size={14} /> : <Sparkles size={14} />}
            type={type}
            title={c.name}
            // Added from the library: the one line on why it's here, on the card itself.
            sub={c.kind === "part" ? c.part?.description || c.ref.split(":")[1] : c.plan ? "Not written yet: in BUILD.md" : (c.why ?? (c.kind === "catalog" ? c.ref : null))}
            subTitle={c.why}
            flag={c.fit}
            foot={c.kind === "skill" ? <Effect e={p.estimates[id]} v={p.verdicts?.[id]} /> : null}
            badge={c.kind === "skill" && p.verdicts?.[id] ? undefined : badge({ kind: "card", card: c })}
            dashed={dashed}
            selected={sel(id)}
            target={target}
            onRemove={() => p.store.removeCard(c.id)}
            removeLabel={`Remove ${c.name} from the canvas`}
            onClick={pick(id)}
          />
        ),
        lanePos ? { draggable: false } : {},
      );
    }

    // Connections you drew (and skill links)
    const names = new Map(nodes.map((n) => [n.id, n.label ?? n.id]));
    const cardKind = new Map(state.cards.map((c) => [`card:${c.id}`, c.kind]));
    const cardWhy = new Map(state.cards.filter((c) => c.why).map((c) => [`card:${c.id}`, c.why]));
    for (const l of state.links) {
      // Inside a harness repo: the repo holds its parts, and one part uses another.
      if (cardKind.get(l.to) === "part") {
        const uses = cardKind.get(l.from) === "part";
        edges.push({
          id: l.id,
          from: l.from,
          to: l.to,
          variant: uses ? "flow" : "link",
          // No tag on the line: at a harness's density tags cover the cards. It's in the title.
          title: uses ? `${names.get(l.from)} uses ${names.get(l.to)}` : undefined,
          onRemove: () => p.store.disconnect(l.id),
          removeLabel: `Remove the link from ${names.get(l.from)} to ${names.get(l.to)}`,
        });
        continue;
      }
      const fromCard = l.from.startsWith("card:") || l.from.startsWith("repo-skill:");
      edges.push({
        id: l.id,
        from: l.from,
        to: l.to,
        variant: fromCard ? "link" : "flow",
        label: fromCard ? "applies to" : undefined,
        title: cardWhy.get(l.from),
        onRemove: () => p.store.disconnect(l.id),
        removeLabel: `Remove the link from ${names.get(l.from)} to ${names.get(l.to)}`,
      });
    }
    return { nodes, edges: keptEdges(), info };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.architecture, p.workflow, p.scenarios, p.treatments, p.project, state, drafts, p.selected, p.estimates, p.rates, p.live, p.blueprint, archShown, mr, p.verdicts, p.previewing]);

  // Dropped onto (or just beside) a block: link to it. Dropped in open space: a free card to wire by hand.
  const near = (x: number, y: number) => {
    const PAD = 24;
    for (const n of nodes) {
      const i = info.get(n.id);
      if (!i || i.kind === "lane" || i.kind === "card") continue;
      if (x >= n.x - PAD && x <= n.x + n.w + PAD && y >= n.y - PAD && y <= n.y + n.h + PAD) return n.id;
    }
    return null;
  };

  // A card linked on drop sits next to its target, never on top of a block.
  const beside = (id: string) => {
    const t = nodes.find((n) => n.id === id)!;
    // Room for the link's "applies to" tag between the two, clear of both: the tag keeps its
    // size when zoomed out, so the gap is wider than it.
    const TAG_GAP = 170;
    const GAP = 36;
    // Above or below, room for the link's "applies to" tag between the two, clear of both.
    const GAP_V = 48;
    // Lane titles count: a card on one hides it.
    const free = (x: number, y: number) =>
      !nodes.some((n) => x < n.x + n.w + 12 && x + BLOCK_W + 12 > n.x && y < n.y + n.h + 12 && y + BLOCK_H + 12 > n.y);
    // Best to its left, a tag's width away: a link runs out of a card's right edge into a
    // block's left one, so there the tag sits in the gap. Else the nearest free side.
    const left = { x: t.x - BLOCK_W - TAG_GAP, y: t.y };
    if (free(left.x, left.y)) return left;
    const tries = [
      { x: t.x, y: t.y + t.h + GAP_V },
      { x: t.x, y: t.y - BLOCK_H - GAP_V },
      // To the right, a tag's width away too, so the tag sits in the gap, not on the card's title.
      { x: t.x + t.w + TAG_GAP, y: t.y },
      { x: t.x - BLOCK_W - GAP, y: t.y },
    ];
    for (let k = 1; k <= 4; k++) for (const c of tries) {
      const at = { x: c.x + (c.x - t.x) * (k - 1), y: c.y + (c.y - t.y) * (k - 1) };
      if (free(at.x, at.y)) return at;
    }
    return tries[0];
  };

  if (p.belowAll)
    p.belowAll.current = () => {
      const blocks = nodes.filter((n) => info.get(n.id)?.kind !== "lane");
      if (!blocks.length) return { x: 0, y: 0 };
      return { x: Math.min(...blocks.map((n) => n.x)), y: Math.max(...blocks.map((n) => n.y + n.h)) + LANE_GAP };
    };

  if (p.clearArea)
    p.clearArea.current = (w, h, at) => {
      // Lanes count too: their titles sit above each lane.
      const hit = (x: number, y: number) =>
        nodes.some((n) => x < n.x + n.w + 24 && x + w + 24 > n.x && y < n.y + n.h + 24 && y + h + 24 > n.y);
      if (!hit(at.x, at.y) || !nodes.length) return at;
      // Rings of 40px cells around the point, nearest first; past everything drawn there is room.
      const minX = Math.min(...nodes.map((n) => n.x)) - w - 48;
      const minY = Math.min(...nodes.map((n) => n.y)) - h - 48;
      const maxX = Math.max(...nodes.map((n) => n.x + n.w)) + 48;
      const maxY = Math.max(...nodes.map((n) => n.y + n.h)) + 48;
      const cells: { x: number; y: number }[] = [];
      for (let x = minX; x <= maxX; x += 40) for (let y = minY; y <= maxY; y += 40) cells.push({ x, y });
      cells.sort((a, b) => Math.hypot(a.x - at.x, a.y - at.y) - Math.hypot(b.x - at.x, b.y - at.y));
      return cells.find((c) => !hit(c.x, c.y)) ?? { x: at.x, y: maxY };
    };

  // Click-to-add: the open grid cell closest to the middle of everything already drawn.
  if (p.besideSlot) p.besideSlot.current = (id) => (nodes.some((n) => n.id === id) ? beside(id) : null);
  if (p.freeSlot)
    p.freeSlot.current = () => {
      const blocks = nodes.filter((n) => info.get(n.id)?.kind !== "lane");
      if (!blocks.length) return { x: 0, y: 0 };
      const minX = Math.min(...blocks.map((n) => n.x));
      const minY = Math.min(...blocks.map((n) => n.y));
      const maxX = Math.max(...blocks.map((n) => n.x + n.w));
      const maxY = Math.max(...blocks.map((n) => n.y + n.h));
      const cx = (minX + maxX) / 2;
      const cy = (minY + maxY) / 2;
      const hit = (x: number, y: number) =>
        nodes.some((n) => x < n.x + n.w + 24 && x + BLOCK_W + 24 > n.x && y < n.y + n.h + 24 && y + BLOCK_H + 24 > n.y);
      const cells: { x: number; y: number }[] = [];
      for (let x = minX; x <= maxX + BLOCK_W; x += 40) for (let y = minY; y <= maxY + BLOCK_H; y += 40) cells.push({ x, y });
      cells.sort((a, b) => Math.hypot(a.x + BLOCK_W / 2 - cx, a.y + BLOCK_H / 2 - cy) - Math.hypot(b.x + BLOCK_W / 2 - cx, b.y + BLOCK_H / 2 - cy));
      return cells.find((c) => !hit(c.x, c.y)) ?? { x: maxX + 48, y: minY };
    };

  return (
    <Canvas
      label={`${p.repoName} canvas`}
      nodes={nodes}
      edges={edges}
      // Refit when the architecture is redrawn (mapped, or a spec added), not on every edit.
      fitKey={`${p.repoName}:${p.blueprint ? `blueprint:${p.architecture?.title}` : p.architecture?.source}:${p.architecture?.components.length ?? 0}:${archShown ? "arch" : "setup"}`}
      onMove={(id, x, y) => !p.blueprint && setDrafts((d) => ({ ...d, [id]: { x, y } }))}
      onMoveEnd={(id) => {
        if (p.blueprint) return;
        const d = drafts[id];
        if (!d) return;
        if (id.startsWith("card:")) p.store.updateCard(id.slice(5), { x: Math.round(d.x), y: Math.round(d.y) });
        else p.store.move(id, d.x, d.y);
        setDrafts(({ [id]: _, ...rest }) => rest);
      }}
      onConnect={(from, to) => !p.blueprint && p.store.connect(from, to)}
      canConnect={(from, to) => !p.blueprint && from !== to && !from.startsWith("lane:") && !to.startsWith("lane:")}
      onDropAt={(data, x, y, visible: Rect, meta) => {
        if (p.blueprint) return;
        const target = near(x, y);
        const at = target ? beside(target) : { x: x - BLOCK_W / 2, y: y - BLOCK_H / 2 };
        p.onDrop(data, at.x, at.y, target, { point: { x, y }, visible, meta });
      }}
      dropSize={{ w: BLOCK_W, h: BLOCK_H }}
      reveal={p.blueprint ? null : p.reveal}
      overlays={p.overlays}
    />
  );
}

function labelOf(i: NodeInfo): string {
  switch (i.kind) {
    case "arch":
      return `${archStyle(i.c).label} ${i.c.label}`;
    case "setup":
      return `Agent setup ${i.label}`;
    case "repo-skill":
      return `Skill in repo ${i.t.name}`;
    case "step":
      return `Step ${i.index + 1}: ${i.name}`;
    case "card":
      return `${i.card.kind === "skill" ? "Skill" : i.card.kind === "part" ? (i.card.part?.label ?? "Part") : i.card.kind === "catalog" ? "GitHub repo" : i.card.ref.startsWith("setup/") ? "Planned" : "Suggested skill"} ${i.card.name}`;
    case "lane":
      return i.label;
  }
}

/** A step's tasks on its card, as short as before: approved, or runnable when an approved one's
 * check is prose and so never runs (evidence-validity). */
function stepTasks(own: { runnable: boolean; check_problem?: string | null }[]): string {
  const approved = own.filter((s) => s.runnable);
  const runnable = approved.filter((s) => !s.check_problem).length;
  return runnable < approved.length ? `${runnable}/${own.length} runnable` : `${approved.length}/${own.length} approved`;
}
