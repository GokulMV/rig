import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { TUTORIAL } from "../fixtures/tutorial";
import { api } from "../lib/api";
import type { TourAt } from "../lib/route";
import { TOUR_DONE_KEY } from "../lib/tutorial";
import { Markdown, RecordedProof, TourEntry, TutorialPage } from "./Tutorial";

const run = TUTORIAL.run!;

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

/** The page as App drives it: its own position, and the three ways out. */
function Driven({ onOption }: { onOption: (to: "repo" | "lab" | "home") => void }) {
  const [at, setAt] = useState<TourAt>(1);
  return <TutorialPage data={TUTORIAL} at={at} onAt={setAt} onOption={onOption} />;
}

test("Home's entry says Start until the tutorial was finished once, then Replay; only its click starts it", async () => {
  const onStart = vi.fn();
  const { rerender } = render(<TourEntry data={TUTORIAL} onStart={onStart} />);
  expect(onStart).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Start the Tutorial" }));
  expect(onStart).toHaveBeenCalledOnce();
  localStorage.setItem(TOUR_DONE_KEY, "1");
  rerender(<TourEntry data={TUTORIAL} onStart={onStart} />);
  expect(screen.getByRole("button", { name: "Replay the Tutorial" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Start the Tutorial" })).toBeNull();
});

test("it walks the five steps on the example with Next and Back, then finishes with three ways on", async () => {
  const onOption = vi.fn();
  render(<Driven onOption={onOption} />);
  const nav = () => screen.getByRole("navigation", { name: "Tutorial" });
  const titles = TUTORIAL.text.steps.map((s) => s.title);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(titles[0]);
  expect(within(nav()).queryByRole("button", { name: /Back/ })).toBeNull();
  // Describe shows the example's own code.
  expect(screen.getByText(/def price\(cents: int\) -> str:/)).toBeInTheDocument();
  for (const [i, next] of ["Design", "Build", "Measure", "Ship"].entries()) {
    await userEvent.click(within(nav()).getByRole("button", { name: `Next: ${next}` }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(titles[i + 1]);
  }
  await userEvent.click(within(nav()).getByRole("button", { name: /Back/ }));
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(titles[3]);
  // Its own small path jumps straight to a step; the current one is marked.
  const path = screen.getByRole("list", { name: "Tutorial steps" });
  await userEvent.click(within(path).getByRole("button", { name: /^2\. Design/ }));
  expect(within(path).getByRole("button", { name: /^2\. Design/ })).toHaveAttribute("aria-current", "step");
  await userEvent.click(within(path).getByRole("button", { name: /^5\. Ship/ }));
  expect(localStorage.getItem(TOUR_DONE_KEY)).toBeNull();
  await userEvent.click(within(nav()).getByRole("button", { name: "Finish" }));

  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(TUTORIAL.text.finish.title);
  expect(localStorage.getItem(TOUR_DONE_KEY)).toBe("1");
  const ways = screen.getByRole("list", { name: "Where next" });
  expect(within(ways).getAllByRole("button").map((b) => b.querySelector(".tour__optionlabel")?.textContent)).toEqual([
    "Rig Your Own Repo",
    "Rig a Workflow",
    "Back to Home",
  ]);
  await userEvent.click(within(ways).getByRole("button", { name: /Rig Your Own Repo/ }));
  await userEvent.click(within(ways).getByRole("button", { name: /Rig a Workflow/ }));
  await userEvent.click(within(ways).getByRole("button", { name: /Back to Home/ }));
  expect(onOption.mock.calls).toEqual([["repo"], ["lab"], ["home"]]);
});

test("Measure shows each task with and without the skill, the totals, the interval and the Rig score with its parts", () => {
  render(<TutorialPage data={TUTORIAL} at={4} onAt={() => undefined} onOption={() => undefined} />);
  const table = screen.getByRole("table");
  const rows = within(table).getAllByRole("row");
  // A head row, one per task, and the totals.
  expect(rows).toHaveLength(run.tasks.length + 2);
  for (const t of run.tasks) {
    const row = within(table).getByRole("row", { name: new RegExp(`^${t.title}`) });
    // What happened to each arm's trial: passed, failed, or timed out (the agent ran out of time).
    const said = (a: typeof t.with) => (a.outcomes[0] === "pass" ? "passed" : a.details[0].startsWith("timed out") ? "timed out" : "failed");
    expect(row.querySelectorAll("td")[0]).toHaveTextContent(said(t.without));
    expect(row.querySelectorAll("td")[1]).toHaveTextContent(said(t.with));
  }
  const total = rows[rows.length - 1];
  expect(total).toHaveTextContent(`${run.without} of ${run.n}`);
  expect(total).toHaveTextContent(`${run.with} of ${run.n}`);
  const score = screen.getByRole("region", { name: "The Rig Score" });
  for (const p of run.rig.parts) expect(score).toHaveTextContent(p.name);
  if (run.rig.score != null) expect(score).toHaveTextContent(`${run.rig.score}/100`);
  expect(screen.getByText(TUTORIAL.text.recorded_note)).toBeInTheDocument();
  // The rows, not only the total: the recorded run has a task the skill made worse.
  expect(screen.getByText(TUTORIAL.text.steps[3].rows as string)).toBeInTheDocument();
  expect(within(table).getByRole("row", { name: /^Read a label back/ })).toHaveTextContent(/passed.*timed out/);
});

test("the tutorial reads nothing of yours: no API call, and no key in this browser but its own flag", async () => {
  const calls: string[] = [];
  const methods = api as unknown as Record<string, (...a: unknown[]) => unknown>;
  for (const k of Object.keys(methods))
    vi.spyOn(methods, k).mockImplementation((...a: unknown[]) => {
      calls.push(`${k}(${a.length})`);
      return Promise.reject(new Error("no API in this test"));
    });
  localStorage.setItem("pg.step", "3");
  localStorage.setItem("pg.space", "lab");
  localStorage.setItem("pg.repo", "r1");
  const before = { ...localStorage };
  const set = vi.spyOn(Storage.prototype, "setItem");
  const get = vi.spyOn(Storage.prototype, "getItem");
  render(<Driven onOption={() => undefined} />);
  for (let i = 0; i < 5; i++) await userEvent.click(within(screen.getByRole("navigation", { name: "Tutorial" })).getByRole("button", { name: /^(Next|Finish)/ }));
  render(<TourEntry data={TUTORIAL} onStart={() => undefined} />);
  // The glossary (the (?) beside a term in the Rig score) is the app's own words, the same for
  // everyone: the one read allowed. Nothing per repo, run or person.
  expect(calls.filter((c) => !c.startsWith("glossary("))).toEqual([]);
  expect(new Set(set.mock.calls.map((c) => c[0]))).toEqual(new Set([TOUR_DONE_KEY]));
  expect(get.mock.calls.every((c) => c[0] === TOUR_DONE_KEY)).toBe(true);
  expect({ ...localStorage }).toEqual({ ...before, [TOUR_DONE_KEY]: "1" });
});

test("Home's proof is the recorded run's own numbers, labelled as a real run", () => {
  render(<RecordedProof data={TUTORIAL} run={run} />);
  const fig = screen.getByTestId("recorded-proof");
  expect(fig).toHaveTextContent(TUTORIAL.text.proof.pill);
  expect(fig).toHaveTextContent(`${run.without} of ${run.n} passed`);
  expect(fig).toHaveTextContent(`${run.with} of ${run.n} passed`);
  expect(fig).not.toHaveTextContent("Illustration");
});

test("a SKILL.md reads as text: headings, joined lines, lists, code and bold, and never as HTML", () => {
  const { container } = render(<Markdown text={"# Title\n\nOne line\nwrapped.\n\n## Rules\n\n- **Bold:** `code` and\n  more\n- <img src=x onerror=alert(1)>"} />);
  expect(container.querySelector("h3")).toHaveTextContent("Title");
  expect(container.querySelector("p")).toHaveTextContent("One line wrapped.");
  const items = container.querySelectorAll("li");
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveTextContent("Bold: code and more");
  expect(items[0].querySelector("b")).toHaveTextContent("Bold:");
  expect(items[0].querySelector("code")).toHaveTextContent("code");
  expect(container.querySelector("img")).toBeNull();
});
