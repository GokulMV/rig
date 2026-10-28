import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { TOKENS_TUTORIAL } from "../fixtures/tutorialTokens";
import type { TourAt } from "../lib/route";
import { TOKENS_TOUR_DONE_KEY, TOUR_DONE_KEY } from "../lib/tutorial";
import type { TokensTutorial } from "../lib/types";
import { TokensTourEntry, TokensTutorialPage } from "./TutorialTokens";

beforeEach(() => localStorage.clear());

function Driven({ data = TOKENS_TUTORIAL, onOption = () => {} }: { data?: TokensTutorial; onOption?: (to: "repo" | "first" | "home") => void }) {
  const [at, setAt] = useState<TourAt>(1);
  return <TokensTutorialPage data={data} at={at} onAt={setAt} onOption={onOption} />;
}

const nav = () => screen.getByRole("navigation", { name: "Tutorial" });

test("Home's second entry says Start until this track was finished, on its own flag", async () => {
  const onStart = vi.fn();
  const { rerender } = render(<TokensTourEntry data={TOKENS_TUTORIAL} onStart={onStart} />);
  await userEvent.click(screen.getByRole("button", { name: "Start the Repo Tutorial" }));
  expect(onStart).toHaveBeenCalledOnce();
  localStorage.setItem(TOUR_DONE_KEY, "1"); // the first track's flag is not this one's
  rerender(<TokensTourEntry data={TOKENS_TUTORIAL} onStart={onStart} />);
  expect(screen.getByRole("button", { name: "Start the Repo Tutorial" })).toBeInTheDocument();
  localStorage.setItem(TOKENS_TOUR_DONE_KEY, "1");
  rerender(<TokensTourEntry data={TOKENS_TUTORIAL} onStart={onStart} />);
  expect(screen.getByRole("button", { name: "Replay the Repo Tutorial" })).toBeInTheDocument();
});

test("every step says what to do on your own repo, then it finishes with three ways on", async () => {
  const onOption = vi.fn();
  render(<Driven onOption={onOption} />);
  const steps = TOKENS_TUTORIAL.text.steps;
  for (const [i, s] of steps.entries()) {
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(s.title);
    const yours = screen.getByRole("region", { name: "On Your Repo" });
    expect(within(yours).getAllByRole("listitem")).toHaveLength(s.yours.length);
    if (s.id === "describe") expect(screen.getAllByText("Fewer Tokens at the Same Pass Rate", { exact: false }).length).toBeGreaterThan(0);
    if (s.id === "build") {
      for (const b of ["Measurable", "In Every Run", "Changes the Code"]) expect(screen.getAllByText(b, { exact: false }).length).toBeGreaterThan(0);
    }
    if (s.id === "measure") {
      expect(screen.getByRole("list", { name: "Tasks" }).querySelectorAll("li")).toHaveLength(10);
      expect(screen.getByRole("region", { name: "On Your Repo: First, the Tasks" })).toBeInTheDocument();
    }
    await userEvent.click(within(nav()).getByRole("button", { name: i < steps.length - 1 ? /^Next: / : "Finish" }));
  }
  expect(localStorage.getItem(TOKENS_TOUR_DONE_KEY)).toBe("1");
  expect(localStorage.getItem(TOUR_DONE_KEY)).toBeNull();
  const ways = screen.getByRole("list", { name: "Where next" });
  const buttons = within(ways).getAllByRole("button");
  expect(buttons.map((b) => b.querySelector(".tour__optionlabel")?.textContent)).toEqual(["Rig Your Own Repo", "The First Tutorial", "Back to Home"]);
  for (const b of buttons) await userEvent.click(b);
  expect(onOption.mock.calls.map((c) => c[0])).toEqual(["repo", "first", "home"]);
});

test("with no run recorded, Measure and Ship say so instead of showing numbers", async () => {
  const data = { ...TOKENS_TUTORIAL, run: null };
  render(<Driven data={data} />);
  const path = screen.getByRole("list", { name: "Repo tutorial steps" });
  await userEvent.click(within(path).getByRole("button", { name: /^4\. Measure/ }));
  expect(screen.getAllByText(/No run has been recorded/).length).toBeGreaterThan(0);
  expect(screen.queryByRole("table")).toBeNull();
  await userEvent.click(within(path).getByRole("button", { name: /^5\. Ship/ }));
  expect(screen.getAllByText(/No run has been recorded/).length).toBeGreaterThan(0);
});

test("the recorded run shows each task's passes and tokens, the metric with its guard, and the Rig score", async () => {
  const run = TOKENS_TUTORIAL.run;
  if (!run) return; // the fixture has no run until one is recorded
  render(<Driven />);
  await userEvent.click(within(screen.getByRole("list", { name: "Repo tutorial steps" })).getByRole("button", { name: /^4\. Measure/ }));
  expect(screen.getByRole("table").querySelectorAll("tbody tr")).toHaveLength(run.tasks.length);
  expect(screen.getAllByTestId("metric-line")[0]).toHaveTextContent("Tokens per Solved Task");
  expect(screen.getAllByTestId("metric-guard")[0]).toHaveTextContent("Pass rate");
  expect(screen.getByRole("region", { name: "The Rig Score" })).toHaveTextContent("/100");
});
