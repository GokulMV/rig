import { searchItems, searchSplit, wordMatch } from "./librarySearch";

// Real local skills: "rag" must not rank apple-design and pick-ui-library (they say "drag") first.
const LOCAL = [
  { name: "apple-design", description: "Gesture-driven UI, spring animations, drag/swipe/sheet interactions" },
  { name: "pick-ui-library", description: "Choose a UI library; covers drag and drop kits" },
  { name: "rag-engineer", description: "Expert in building Retrieval-Augmented Generation systems" },
  { name: "prompt-caching", description: "Caching strategies for LLM prompts including CAG" },
  { name: "code-review", description: "Review the current diff for correctness bugs" },
  { name: "simplify", description: "Review the changed code for reuse and simplification" },
  { name: "test-driven-development", description: "Write the failing test first" },
  { name: "webapp-testing", description: "Toolkit for testing local web applications using Playwright" },
];
const names = (q: string) => searchItems(LOCAL, q).map((x) => x.name);

test("a name word beats a description word, and 'rag' is not 'drag'", () => {
  expect(names("rag")).toEqual(["rag-engineer"]);
});

test("'code review' finds the review skills, the one named so first", () => {
  expect(names("code review")).toEqual(["code-review", "simplify"]);
});

test("'testing' finds testing by name and by word start", () => {
  expect(names("testing")[0]).toBe("webapp-testing");
  expect(names("test")).toEqual(["test-driven-development", "webapp-testing"]);
});

test("one typo in a longer word still matches", () => {
  expect(wordMatch("reveiw", "review")).toBeGreaterThan(0);
  expect(names("simplfy")).toEqual(["simplify"]);
  expect(wordMatch("test", "best")).toBe(0);
});

test("an empty query keeps every item in order", () => {
  expect(names("")).toEqual(LOCAL.map((x) => x.name));
});

// Real descriptions: "bug" must find test-driven-development ("any feature or bugfix"), and
// "code review" must not put review-animations and web-design-guidelines first.
const REAL = [
  { name: "review-animations", description: "Reviews animation and motion code against a high craft bar." },
  { name: "web-design-guidelines", description: 'Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI".' },
  { name: "test-driven-development", description: "Use when implementing any feature or bugfix, before writing implementation code" },
  { name: "requesting-code-review", description: "Use when completing tasks to verify work meets requirements" },
  { name: "systematic-debugging", description: "Use when encountering any bug, test failure, or unexpected behavior" },
];
const real = (q: string) => searchItems(REAL, q).map((x) => x.name);

test("'bug' finds a skill that says 'bugfix', and 'bugs' finds 'bug'", () => {
  expect(real("bug")).toContain("test-driven-development");
  expect(real("bugs")).toContain("systematic-debugging");
  expect(wordMatch("bug", "bugfix")).toBeGreaterThan(0);
  expect(wordMatch("bug", "bugle")).toBe(0);
});

test("'code review' puts the skill named for it before ones that only say both words", () => {
  expect(real("code review")[0]).toBe("requesting-code-review");
});

// Words scattered through a description, as in review-animations and web-design-guidelines,
// fold under "Weaker matches".
test("'code review': only what says it as a phrase or in its name is strong; scattered words are weak", () => {
  const { strong, weak } = searchSplit(REAL, "code review");
  expect(strong.map((x) => x.name)).toEqual(["requesting-code-review"]);
  expect(weak.map((x) => x.name)).toEqual(expect.arrayContaining(["review-animations", "web-design-guidelines"]));
  // searchItems keeps the strong ones first.
  expect(real("code review").slice(0, 1)).toEqual(["requesting-code-review"]);
});

test("one word: in the name, or in the description as the word or a form of it; a topic only is weak", () => {
  const items = [
    { name: "pg-aiguide", description: "MCP server and Claude plugin for Postgres skills and documentation." },
    { name: "Pseudolife-MCP", description: "Persistent long-term memory for Agents", topics: ["postgres", "memory"] },
    { name: "Douyin_TikTok_Download_API", description: "Video downloader with a PostgreSQL archive." },
  ];
  const { strong, weak } = searchSplit(items, "postgres");
  expect(strong.map((x) => x.name)).toEqual(["pg-aiguide"]);
  expect(weak.map((x) => x.name)).toEqual(expect.arrayContaining(["Pseudolife-MCP", "Douyin_TikTok_Download_API"]));
  expect(searchSplit(REAL, "bug").strong.map((x) => x.name)).toEqual(expect.arrayContaining(["test-driven-development", "systematic-debugging"]));
});
