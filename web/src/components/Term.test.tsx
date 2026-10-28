import { act, fireEvent, render, screen } from "@testing-library/react";

import { setGlossary } from "../lib/glossary";
import { Term, TERM_OPEN_MS } from "./Term";

beforeEach(() => {
  vi.useFakeTimers();
  setGlossary({ pts: { term: "pts (pass-rate points)", short: "Percentage points of tasks passed." } });
});
afterEach(() => {
  vi.useRealTimers();
  setGlossary(null);
});

const button = () => screen.getByRole("button", { name: "What is pts (pass-rate points)?" });

test("opens on hover after a short delay, stays while over it, and closes on leaving", () => {
  render(<Term k="pts" />);
  const wrap = button().parentElement!;
  fireEvent.pointerEnter(wrap, { pointerType: "mouse" });
  expect(screen.queryByRole("tooltip")).toBeNull(); // not at once: passing over it is not asking
  act(() => vi.advanceTimersByTime(TERM_OPEN_MS));
  expect(screen.getByRole("tooltip")).toHaveTextContent("pts (pass-rate points): Percentage points of tasks passed.");
  expect(button()).toHaveAttribute("aria-describedby", screen.getByRole("tooltip").id);
  fireEvent.pointerLeave(wrap, { pointerType: "mouse" });
  act(() => vi.advanceTimersByTime(300));
  expect(screen.queryByRole("tooltip")).toBeNull();
});

test("opens on keyboard focus, closes on Esc and on blur", () => {
  render(<Term k="pts" />);
  act(() => button().focus());
  act(() => vi.advanceTimersByTime(TERM_OPEN_MS));
  expect(screen.getByRole("tooltip")).toBeInTheDocument();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("tooltip")).toBeNull();
  fireEvent.click(button());
  expect(screen.getByRole("tooltip")).toBeInTheDocument();
  act(() => button().blur());
  expect(screen.queryByRole("tooltip")).toBeNull();
});
