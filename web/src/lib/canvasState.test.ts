import { describe, expect, it } from "vitest";

import { type CanvasState, canvasAdded } from "./canvasState";

const state: CanvasState = {
  positions: {},
  removed: [],
  cards: [
    { id: "s", kind: "skill", ref: "/lib/installed/acme__review", name: "careful-review", x: 0, y: 0 },
    { id: "r", kind: "catalog", ref: "loops/ralph", name: "ralph", x: 0, y: 0, parts: 2, category: "harness" },
    {
      id: "p1",
      kind: "part",
      ref: "loops/ralph:.claude/commands/ship.md",
      name: "ship",
      x: 0,
      y: 0,
      part: { kind: "command", label: "Command", description: "Ship one change", url: "https://github.com/loops/ralph/blob/main/.claude/commands/ship.md" },
    },
    {
      id: "p2",
      kind: "part",
      ref: "other/repo:agents/planner.md",
      name: "planner",
      x: 0,
      y: 0,
      part: { kind: "agent", label: "Agent", description: "", url: "" },
    },
    { id: "g", kind: "suggestion", ref: "default/write-tests", name: "write-tests", x: 0, y: 0 },
  ],
  links: [
    { id: "1", from: "card:r", to: "card:p1" }, // the repo holding its part: said by listing it
    { id: "2", from: "card:p1", to: "card:p2" },
    { id: "3", from: "card:s", to: "step:fix" },
    { id: "4", from: "arch:api", to: "arch:db" },
    { id: "5", from: "card:s", to: "step:gone" }, // not drawn: left out
  ],
  notes: { "card:p1": "  run it first  ", "arch:db": "   ", "step:gone": "lost" },
};

const names: Record<string, string> = {
  "card:s": "careful-review",
  "card:r": "ralph",
  "card:p1": "ship",
  "card:p2": "planner",
  "card:g": "write-tests",
  "step:fix": "fix",
  "arch:api": "api",
  "arch:db": "db",
};

describe("canvasAdded", () => {
  const out = canvasAdded(
    state,
    (id) => names[id] ?? null,
    (path) => (path.endsWith("acme__review") ? { repo: "acme/review", folder: "skills/careful-review" } : null),
  );

  it("says where each skill comes from", () => {
    expect(out.skills).toEqual([
      { name: "careful-review", path: "/lib/installed/acme__review", repo: "acme/review", folder: "skills/careful-review" },
    ]);
  });

  it("groups parts under their repo, even one whose repo card was removed", () => {
    expect(out.repos.map((r) => [r.repo, r.category, r.parts.map((p) => p.name)])).toEqual([
      ["loops/ralph", "harness", ["ship"]],
      ["other/repo", "", ["planner"]],
    ]);
  });

  it("keeps suggestions as planned", () => {
    expect(out.planned).toEqual([{ name: "write-tests", ref: "default/write-tests" }]);
  });

  it("names each link's relation and leaves out links to blocks not drawn", () => {
    expect(out.links).toEqual([
      { from: "ship", to: "planner", relation: "uses" },
      { from: "careful-review", to: "fix", relation: "applies to" },
      { from: "api", to: "db", relation: "connects to" },
    ]);
  });

  it("keeps only real notes on drawn blocks", () => {
    expect(out.notes).toEqual([{ on: "ship", text: "run it first" }]);
  });
});
