import { useSyncExternalStore } from "react";

import { api } from "./api";
import type { GoalRules, MeasureRules, MeasureState, Proposal } from "./types";

/** Skills whose values the app shows as they are (/api/rules/<name>): their words and rules live
 * in engine/src/proving_ground/skills/<name>/SKILL.md, not here. Each is fetched once a page load. */
type Names = { measurability: MeasureRules; "repo-goals": GoalRules };
type Name = keyof Names;

const got: { [K in Name]?: Names[K] } = {};
const asked = new Set<Name>();
const listeners = new Set<() => void>();

function ask(name: Name) {
  if (asked.has(name)) return;
  asked.add(name);
  api.rules<Names[typeof name]>(name).then(
    (v) => {
      (got as Record<Name, unknown>)[name] = v;
      listeners.forEach((f) => f());
    },
    () => asked.delete(name), // asked again by the next page that needs it
  );
}

/** A skill's values, or null until they have loaded. */
export function useRules<K extends Name>(name: K): Names[K] | null {
  return useSyncExternalStore(
    (f) => {
      listeners.add(f);
      ask(name);
      return () => listeners.delete(f);
    },
    () => (got[name] as Names[K] | undefined) ?? null,
  );
}

/** For tests: set a skill's values without a request (null forgets them). */
export function setRules<K extends Name>(name: K, v: Names[K] | null) {
  if (v === null) {
    delete got[name];
    asked.delete(name);
  } else {
    (got as Record<Name, unknown>)[name] = v;
    asked.add(name);
  }
  listeners.forEach((f) => f());
}

/* ---------------- What a goal is about (repo-goals) ---------------- */

const escape = (w: string) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Whether a goal is about the coding agent (its instructions, skills, checks, spend) rather than
 * what the app does: any of the skill's agent_words, as a whole word. null until the words load. */
export function aboutTheAgent(goal: string | null | undefined, rules: GoalRules | null): boolean | null {
  if (!rules) return null;
  const text = goal ?? "";
  if (!text.trim()) return false;
  const words = [...rules.agent_words].sort((a, b) => b.length - a.length).map(escape);
  return new RegExp(`(?<![\\w.])(${words.join("|")})(?![\\w])`, "i").test(text);
}

/** The template a goal still comes from: picked, and the box still starts with its text. */
export function keptTemplate(goal: string, id: string | null | undefined, rules: GoalRules | null): GoalRules["templates"][number] | null {
  if (!id || !rules) return null;
  const t = rules.templates.find((x) => x.id === id);
  return t && goal.trim().startsWith(t.text.trim()) ? t : null;
}

/* ---------------- Whether Measure can test it (measurability) ---------------- */

/** Anything that can carry a badge: a suggestion, a kind of change, or a block on the canvas. */
export type Measurable =
  | { kind: "proposal"; p: Pick<Proposal, "measure"> }
  | { kind: "treatment"; treatment: string }
  | { kind: "setup"; label: string; present?: boolean }
  | { kind: "repo-skill" }
  | { kind: "step" }
  | { kind: "arch"; c: { source?: string | null } }
  | { kind: "card"; card: { kind: string; ref: string } }
  | { kind: "lane" };

/**
 * The one place that says whether Measure can test something: a state of the measurability skill.
 * A kind of change reads its state from the skill's `treatments`, so making Measure run hooks, MCP
 * servers or CLAUDE.md is one value there (`hook: runnable`) and every badge follows.
 */
export function measureState(item: Measurable, r: MeasureRules): string | null {
  const kind = (t: string) => r.treatments[t] ?? (t in r.states ? t : "not_yet");
  switch (item.kind) {
    case "proposal":
      return item.p.measure ?? "brief";
    case "treatment":
      return kind(item.treatment);
    case "repo-skill":
      return kind("skill");
    case "setup":
      if (item.present === false) return "absent";
      return kind(r.setup_kinds[item.label] ?? "not_yet");
    case "step":
      return "step";
    case "arch":
      return item.c.source === "proposed" || item.c.source === "removed" ? "before_after" : "app";
    case "card":
      if (item.card.kind === "skill") return kind("skill");
      if (item.card.kind === "suggestion") return item.card.ref.startsWith("setup/") ? "planned" : "not_installed";
      return "not_installed"; // a GitHub repo, or one of its parts: nothing installed to run
    case "lane":
      return null;
  }
}

/** The state's badge and line, or null when there is none (a lane, or rules not loaded yet). */
export function measureBadge(item: Measurable, r: MeasureRules | null): (MeasureState & { id: string }) | null {
  if (!r) return null;
  const id = measureState(item, r);
  const s = id ? r.states[id] : undefined;
  return s && id ? { ...s, id } : null;
}

/** "skills", or "skills and hooks": the kinds Measure runs today, as a line says them. */
export function runnableKinds(r: MeasureRules): string {
  const names = Object.entries(r.treatments)
    .filter(([, v]) => v === "runnable")
    .map(([k]) => r.kind_names[k] ?? k);
  if (names.length <= 1) return names[0] ?? "nothing yet";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** A canvas row's line: what Measure tests there. */
export function laneLine(lane: keyof MeasureRules["lanes"], r: MeasureRules | null): string | null {
  return r ? r.lanes[lane].replace("{kinds}", runnableKinds(r)) : null;
}
