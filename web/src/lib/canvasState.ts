import { useCallback, useEffect, useRef, useState } from "react";

import type { CanvasAdded } from "./types";

/** A card you placed: an installed skill, a catalog repo still to pick from, a suggestion, or one
 * part of a harness or workflow repo laid out on the canvas. */
export interface Card {
  id: string;
  kind: "skill" | "catalog" | "suggestion" | "part";
  ref: string; // skill folder path, "owner/repo", "<workflow>/<name>", or "owner/repo:path" for a part
  name: string;
  x: number;
  y: number;
  /** Why it was placed where it is, when "Add" chose the spot. */
  why?: string;
  /** Written for a language the repo has none of: "For Go; this repo has none." */
  fit?: string;
  /** A part: what kind (command, agent, skill, hook, ...), what it says it does, where to read it. */
  part?: { kind: string; label: string; description: string; url: string };
  /** A repo card laid out as its parts: how many are on the canvas. */
  parts?: number;
  /** A GitHub repo card: what the catalog calls it (harness, workflow, agent, hook, mcp, skill). */
  category?: string;
  /** A planned part of the agent setup (ref "setup/<item>"): what to put in it, for the brief. */
  plan?: string;
}

/** A connection you drew between any two blocks. */
export interface Link {
  id: string;
  from: string;
  to: string;
}

export interface CanvasState {
  positions: Record<string, { x: number; y: number }>;
  cards: Card[];
  links: Link[];
  notes: Record<string, string>;
  /** Blocks the repo already had, taken off this plan (the code is not touched). */
  removed: string[];
}

const EMPTY: CanvasState = { positions: {}, cards: [], links: [], notes: {}, removed: [] };

function key(repo: string) {
  return `pg.canvas.v2.${repo}`;
}

function read(repo: string): CanvasState {
  try {
    const raw = window.localStorage.getItem(key(repo));
    return raw ? { ...EMPTY, ...(JSON.parse(raw) as CanvasState) } : EMPTY;
  } catch {
    return EMPTY;
  }
}

const newId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

export interface CanvasStore {
  state: CanvasState;
  move: (id: string, x: number, y: number) => void;
  addCard: (card: Omit<Card, "id">, linkTo?: string[]) => string;
  updateCard: (id: string, patch: Partial<Card>) => void;
  removeCard: (id: string) => void;
  /** Take a block the repo already has off the plan, with every line to it. */
  removeBlock: (nodeId: string) => void;
  connect: (from: string, to: string) => void;
  disconnect: (linkId: string) => void;
  setNote: (nodeId: string, text: string) => void;
  /** Several changes made as one action (an Add with its links): one step for Undo. */
  group: (fn: () => void) => void;
  /** Back one change (kept for this visit, at most HISTORY of them). */
  undo: () => void;
  canUndo: boolean;
  /** Everything you placed, drew and moved, gone; undo brings it back. */
  reset: () => void;
  isEmpty: boolean;
}

const HISTORY = 50;

/** The canvas you built for one repo, kept in this browser. */
export function useCanvasState(repo: string): CanvasStore {
  const [state, setState] = useState<CanvasState>(() => read(repo));
  const past = useRef<CanvasState[]>([]);
  const [depth, setDepth] = useState(0);
  useEffect(() => {
    setState(read(repo));
    past.current = [];
    setDepth(0);
  }, [repo]);
  const write = useCallback(
    (next: CanvasState) => {
      try {
        window.localStorage.setItem(key(repo), JSON.stringify(next));
      } catch {
        // Storage can be unavailable (private window); the canvas then lasts for this visit.
      }
    },
    [repo],
  );
  // The latest state, so a change and its history entry are made once, outside React's updater.
  const now = useRef(state);
  now.current = state;
  const grouping = useRef<"off" | "open" | "recorded">("off");
  const save = useCallback(
    (fn: (s: CanvasState) => CanvasState) => {
      const cur = now.current;
      const next = fn(cur);
      if (next === cur) return;
      // Inside a group only the first change records where to undo back to.
      if (grouping.current !== "recorded") past.current = [...past.current.slice(-(HISTORY - 1)), cur];
      if (grouping.current === "open") grouping.current = "recorded";
      now.current = next;
      setDepth(past.current.length);
      write(next);
      setState(next);
    },
    [write],
  );
  return {
    state,
    move: (id, x, y) => save((s) => ({ ...s, positions: { ...s.positions, [id]: { x: Math.round(x), y: Math.round(y) } } })),
    addCard: (card, linkTo = []) => {
      const id = newId();
      save((s) => ({
        ...s,
        cards: [...s.cards, { ...card, id }],
        links: [...s.links, ...linkTo.map((to) => ({ id: newId(), from: `card:${id}`, to }))],
      }));
      return id;
    },
    updateCard: (id, patch) => save((s) => ({ ...s, cards: s.cards.map((c) => (c.id === id ? { ...c, ...patch } : c)) })),
    removeCard: (id) =>
      save((s) => ({
        ...s,
        cards: s.cards.filter((c) => c.id !== id),
        links: s.links.filter((l) => l.from !== `card:${id}` && l.to !== `card:${id}`),
      })),
    removeBlock: (nodeId) =>
      save((s) =>
        s.removed.includes(nodeId)
          ? s
          : {
              ...s,
              removed: [...s.removed, nodeId],
              links: s.links.filter((l) => l.from !== nodeId && l.to !== nodeId),
            },
      ),
    connect: (from, to) =>
      save((s) =>
        s.links.some((l) => l.from === from && l.to === to) ? s : { ...s, links: [...s.links, { id: newId(), from, to }] },
      ),
    disconnect: (linkId) => save((s) => ({ ...s, links: s.links.filter((l) => l.id !== linkId) })),
    setNote: (nodeId, text) => save((s) => ({ ...s, notes: { ...s.notes, [nodeId]: text } })),
    group: (fn) => {
      grouping.current = "open";
      try {
        fn();
      } finally {
        grouping.current = "off";
      }
    },
    undo: () => {
      const prev = past.current.pop();
      setDepth(past.current.length);
      if (!prev) return;
      now.current = prev;
      write(prev);
      setState(prev);
    },
    canUndo: depth > 0,
    reset: () => save(() => EMPTY),
    isEmpty:
      !state.cards.length &&
      !state.links.length &&
      !state.removed.length &&
      !Object.keys(state.positions).length &&
      !Object.keys(state.notes).length,
  };
}

const GITHUB_REPO = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;

/** What the plan has beyond the repo, for the brief: the skills, GitHub repos and parts, and
 * planned skills you placed, the links you drew and your notes. Only what is on the canvas now:
 * a link to a block that isn't drawn (another workflow, a removed block) is left out. */
export function canvasAdded(
  state: CanvasState,
  label: (nodeId: string) => string | null,
  skillSource: (path: string) => { repo?: string | null; folder?: string } | null,
): CanvasAdded {
  const out: CanvasAdded = { skills: [], repos: [], planned: [], links: [], notes: [] };
  const repos = new Map<string, CanvasAdded["repos"][number]>();
  const repoOf = (repo: string, name?: string, category?: string) => {
    let r = repos.get(repo);
    if (!r) {
      r = { repo, name: name ?? repo.split("/")[1] ?? repo, category: category ?? "", parts: [] };
      repos.set(repo, r);
    }
    if (name) r.name = name;
    if (category) r.category = category;
    return r;
  };
  for (const c of state.cards) {
    if (c.kind === "skill") {
      const src = skillSource(c.ref);
      const gh = src?.repo && GITHUB_REPO.test(src.repo) ? { repo: src.repo, folder: src.folder ?? "" } : {};
      out.skills.push({ name: c.name, path: c.ref, ...gh });
    } else if (c.kind === "catalog" && GITHUB_REPO.test(c.ref)) {
      repoOf(c.ref, c.name, c.category);
    } else if (c.kind === "part" && c.part) {
      const at = c.ref.indexOf(":");
      const repo = c.ref.slice(0, at);
      if (at < 0 || !GITHUB_REPO.test(repo)) continue;
      repoOf(repo).parts.push({
        kind: c.part.kind,
        name: c.name,
        path: c.ref.slice(at + 1),
        url: c.part.url,
        description: c.part.description,
      });
    } else if (c.kind === "suggestion") {
      out.planned.push(c.plan ? { name: c.name, ref: c.ref, do: c.plan } : { name: c.name, ref: c.ref });
    }
  }
  out.repos = [...repos.values()];
  const kind = new Map(state.cards.map((c) => [`card:${c.id}`, c.kind]));
  for (const l of state.links) {
    const [from, to] = [label(l.from), label(l.to)];
    if (!from || !to) continue;
    const [fk, tk] = [kind.get(l.from), kind.get(l.to)];
    // A repo holding its own parts is said by listing the parts under it.
    if (fk === "catalog" && tk === "part") continue;
    const relation =
      fk === "part" && tk === "part"
        ? "uses"
        : (fk && fk !== "part") || l.from.startsWith("repo-skill:")
          ? "applies to"
          : "connects to";
    out.links.push({ from, to, relation });
  }
  for (const [id, text] of Object.entries(state.notes)) {
    const on = label(id);
    // The brief takes a note of up to 2000 characters (build-spec added_limits.text).
    const t = text.trim();
    if (on && t) out.notes.push({ on, text: t.length > 2000 ? `${t.slice(0, 1999)}…` : t });
  }
  return out;
}
