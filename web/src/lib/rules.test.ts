import RULES from "../fixtures/rules.json";
import { aboutTheAgent, keptTemplate, laneLine, measureBadge, measureState, runnableKinds } from "./rules";
import type { GoalRules, MeasureRules } from "./types";

const M = RULES.measurability as MeasureRules;
const G = RULES["repo-goals"] as GoalRules;

test("a goal about tokens, cost or speed is about the coding agent, not the app", () => {
  expect(aboutTheAgent("Reduce the token usage", G)).toBe(true);
  expect(aboutTheAgent("Reduce the agent's token consumption in this repo", G)).toBe(true);
  expect(aboutTheAgent("Lower our spend per task", G)).toBe(true);
  expect(aboutTheAgent("Cut latency; keep the context small", G)).toBe(true);
  expect(aboutTheAgent("Bug fixing in my repo", G)).toBe(true);
  expect(aboutTheAgent("Review Java pull requests", G)).toBe(true);
  expect(aboutTheAgent("Keep CLAUDE.md short", G)).toBe(true);
  expect(aboutTheAgent("Answer support tickets from our refund policy", G)).toBe(false);
  expect(aboutTheAgent("Answer billing questions in three languages.", G)).toBe(false);
  // Whole words only: "prefix" is not "fix", "contest" is not "test".
  expect(aboutTheAgent("A prefix tree for the contest", G)).toBe(false);
  expect(aboutTheAgent(null, G)).toBe(false);
  expect(aboutTheAgent("tokens", null)).toBeNull();
});

test("every goal template is short, about the agent, and names a metric", () => {
  expect(G.templates.length).toBeGreaterThanOrEqual(4);
  expect(G.templates.length).toBeLessThanOrEqual(6);
  for (const t of G.templates) {
    expect(G.metrics).toContain(t.metric);
    expect(aboutTheAgent(t.text, G)).toBe(true);
  }
  const tokens = G.templates.find((t) => t.id === "fewer-tokens")!;
  expect(keptTemplate(tokens.text, "fewer-tokens", G)?.metric).toBe("tokens");
  expect(keptTemplate(`${tokens.text} Mostly in refunds.`, "fewer-tokens", G)?.id).toBe("fewer-tokens");
  expect(keptTemplate("Something else entirely.", "fewer-tokens", G)).toBeNull();
  expect(keptTemplate(tokens.text, null, G)).toBeNull();
});

test("each thing on the canvas, and each suggestion, says whether Measure can test it", () => {
  expect(measureState({ kind: "repo-skill" }, M)).toBe("runnable");
  expect(measureState({ kind: "card", card: { kind: "skill", ref: "x" } }, M)).toBe("runnable");
  expect(measureState({ kind: "setup", label: "CLAUDE.md", present: true }, M)).toBe("same");
  expect(measureState({ kind: "setup", label: "CLAUDE.md", present: false }, M)).toBe("absent");
  expect(measureState({ kind: "setup", label: "Hooks", present: true }, M)).toBe("same");
  // A hook, MCP server or CLAUDE.md you add (or edit) is the change: Measure runs it with and without.
  for (const t of ["hook", "mcp", "instructions"]) expect(measureState({ kind: "treatment", treatment: t }, M)).toBe("runnable");
  expect(measureState({ kind: "setup", label: "Test command", present: true }, M)).toBe("check");
  expect(measureState({ kind: "card", card: { kind: "suggestion", ref: "setup/CLAUDE.md" } }, M)).toBe("planned");
  expect(measureState({ kind: "card", card: { kind: "suggestion", ref: "flow/tdd" } }, M)).toBe("not_installed");
  expect(measureState({ kind: "card", card: { kind: "catalog", ref: "a/b" } }, M)).toBe("not_installed");
  expect(measureState({ kind: "card", card: { kind: "part", ref: "a/b:x" } }, M)).toBe("not_installed");
  expect(measureState({ kind: "arch", c: { source: "proposed" } }, M)).toBe("before_after");
  expect(measureState({ kind: "arch", c: { source: "code" } }, M)).toBe("app");
  expect(measureState({ kind: "proposal", p: { measure: "note" } }, M)).toBe("note");
  expect(measureState({ kind: "lane" }, M)).toBeNull();
  expect(measureBadge({ kind: "repo-skill" }, M)).toMatchObject({ id: "runnable", label: "Measurable", tone: "positive" });
  expect(measureBadge({ kind: "repo-skill" }, null)).toBeNull();
});

test("one value in the skill makes a kind measurable everywhere", () => {
  const flipped: MeasureRules = { ...M, treatments: { ...M.treatments, loop: "runnable" } };
  expect(measureState({ kind: "treatment", treatment: "loop" }, M)).toBe("not_yet");
  expect(measureState({ kind: "treatment", treatment: "loop" }, flipped)).toBe("runnable");
  expect(runnableKinds(M)).toBe("skills, hooks, MCP servers and CLAUDE.md files");
  expect(runnableKinds(flipped)).toBe("skills, loops, hooks, MCP servers and CLAUDE.md files");
  // What the repo already has runs in both arms: the row names what you add or change.
  expect(laneLine("setup", M)).toBe("Measure tests what you add or change here");
  // Every state a function can return has a badge.
  for (const s of ["runnable", "same", "not_yet", "before_after", "brief", "note", "enables", "step", "check", "app", "planned", "absent", "not_installed"])
    expect(M.states[s]?.label).toBeTruthy();
});
