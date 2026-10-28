import { render, screen } from "@testing-library/react";

import { Interval } from "./Interval";

const style = (el: Element | null) => (el as HTMLElement).style;

test("draws the interval to scale on a symmetric axis", () => {
  const { container } = render(<Interval low={0.05} high={0.35} diff={0.2} verdict="helps" mde={0.1} />);
  // The axis half-width is 0.5 (it fits 0.35), so the track spans -50..+50 pts.
  expect(style(container.querySelector(".interval__bar")).left).toBe("55%");
  expect(parseFloat(style(container.querySelector(".interval__bar")).width)).toBeCloseTo(30);
  expect(style(container.querySelector(".interval__zero")).left).toBe("50%");
  expect(style(container.querySelector(".interval__point")).left).toBe("70%");
  expect(parseFloat(style(container.querySelector(".interval__mde")).width)).toBeCloseTo(20);
  expect(
    screen.getByRole("img", { name: "Difference +20.0 pts, 95% interval +5.0 pts to +35.0 pts, axis ±50 pts" }),
  ).toHaveClass("interval--helps");
});

test("values past the axis are clamped to its ends", () => {
  const { container } = render(<Interval low={-2} high={0.1} diff={-0.5} verdict="inconclusive" />);
  expect(style(container.querySelector(".interval__bar")).left).toBe("0%");
});
