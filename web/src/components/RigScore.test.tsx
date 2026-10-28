import { render, screen, within } from "@testing-library/react";

import type { RigScore as Rig } from "../lib/types";
import { RigBadge, RigScore } from "./RigScore";

// The engine's own output for the real Lab bugfix run (engine/tests/test_rig_score.py).
const REAL: Rig = {
  score: 15,
  band: "doesnt",
  tone: "negative",
  label: "Doesn't Work — no lift shown",
  reason: "No lift shown; costs 40× the plain agent; the agent skipped 4 of 5 steps",
  provisional: true,
  pairs: 2,
  parts: [
    { id: "lift", name: "Lift", weight: 0.4, score: 0, detail: "lower bound -79 pts (target +25)" },
    { id: "cost", name: "Cost", weight: 0.2, score: 0, detail: "40.4× the plain agent's cost per solved task" },
    { id: "followed", name: "Followed", weight: 0.15, score: 20, detail: "1 of 5 steps run, 1 on the right model (2 trials read)" },
    { id: "holds_up", name: "Holds Up", weight: 0.15, score: null, detail: "no held-out tasks" },
    { id: "reliable", name: "Reliable", weight: 0.1, score: 100, detail: "4 of 4 trials ran cleanly" },
  ],
  gates: [
    { id: "not_shown", cap: 49, text: "Capped at 49: not shown to help (the interval reaches 0)." },
    { id: "provisional", cap: null, text: "Provisional: 2 pairs, under 10 — more pairs will move it." },
  ],
};

test("the number, the band in words, the reason and five parts", () => {
  render(<RigScore rig={REAL} />);
  const card = screen.getByRole("region", { name: "Rig Score" });
  expect(card).toHaveClass("rig--negative", "rig--provisional");
  expect(within(card).getByText("Rig Score: 15 out of 100.")).toBeInTheDocument();
  expect(within(card).getByText("Doesn't Work — no lift shown")).toBeInTheDocument();
  expect(within(card).getByText(/provisional: 2 pairs/)).toBeInTheDocument();
  expect(within(card).getByText(REAL.reason)).toBeInTheDocument();
  const parts = card.querySelectorAll(".rig__part");
  expect(parts).toHaveLength(5);
  expect(parts[3]).toHaveClass("rig__part--off");
  expect(parts[3]).toHaveTextContent("Holds Up 15%not measuredno held-out tasks");
  expect((parts[2].querySelector(".rig__fill") as HTMLElement).style.width).toBe("20%");
  expect(within(card).getByText(/^Capped at 49/)).toBeInTheDocument();
});

test("nothing measured shows a dash and no parts", () => {
  render(<RigScore rig={{ ...REAL, score: null, band: "none", tone: "neutral", label: "Not Measured Yet", reason: "No complete pairs yet.", provisional: false, gates: [] }} />);
  expect(screen.getByText("—")).toBeInTheDocument();
  expect(screen.getByText("Rig Score: not measured.")).toBeInTheDocument();
  expect(document.querySelectorAll(".rig__part")).toHaveLength(0);
});

test("the badge says Rig N, and provisional in words", () => {
  render(<RigBadge score={72} tone="neutral" provisional label="Works, but cost needs work" />);
  const b = screen.getByTestId("rig-badge");
  expect(b).toHaveTextContent(/^Rig 72/);
  expect(b).toHaveClass("rig-badge--neutral", "rig-badge--provisional");
  expect(b).toHaveTextContent("Rig score 72 out of 100: Works, but cost needs work (provisional: few pairs)");
});

test("a result that isn't evidence: a dash, 'Not Evidence', the validity's reason, no parts", () => {
  render(
    <RigScore
      rig={{
        ...REAL,
        score: null,
        band: "not_evidence",
        tone: "neutral",
        label: "Not Evidence",
        reason: "Invalid: the check is broken. Not a command, so every trial fails both ways: a.",
        provisional: false,
        gates: [],
        formula: null,
      }}
    />,
  );
  const card = screen.getByRole("region", { name: "Rig Score" });
  expect(card).toHaveAttribute("data-band", "not_evidence");
  expect(within(card).getByText("—")).toBeInTheDocument();
  expect(within(card).getByText("Not Evidence")).toBeInTheDocument();
  expect(within(card).getByText(/^Invalid: the check is broken/)).toBeInTheDocument();
  expect(within(card).getByText("Rig Score: no score, not evidence.")).toBeInTheDocument();
  expect(card.querySelectorAll(".rig__part")).toHaveLength(0);
});

test("no credit before a lift is shown, the formula and the trial ledger are on the card", () => {
  const parts = REAL.parts.map((p) =>
    p.id === "cost" || p.id === "reliable" ? { ...p, counted: false, note: "counts once a lift is shown" } : { ...p, counted: p.score != null },
  );
  const formula = { text: "40% × 0 + 20% × 0 (Cost: no credit yet) + 15% × 20 + 10% × 0 (Reliable: no credit yet) = 3.0; ÷ 85% (weights rescaled to the measured parts; holds up not measured) = 3.5; rounded: 4", measured_weight: 0.85, raw: 3.53, not_measured: ["holds up"] };
  render(
    <RigScore
      rig={{
        ...REAL,
        score: 4,
        band: "not_proven",
        tone: "warning",
        label: "Not Proven — no lift seen in 2 pairs yet; more pairs would settle it",
        parts,
        formula,
        gates: [{ id: "not_shown", cap: 49, text: "Capped at 49: not shown to help (the interval reaches 0).", binding: false }],
        ledger_text: "4 trials (2 with, 2 without) · 2 complete pairs · 4 ran cleanly",
      }}
    />,
  );
  const card = screen.getByRole("region", { name: "Rig Score" });
  const rel = card.querySelectorAll(".rig__part")[4];
  expect(rel).toHaveClass("rig__part--nocredit");
  expect(rel).toHaveTextContent("no credit");
  expect(rel).toHaveTextContent("counts once a lift is shown");
  expect(rel.querySelector(".rig__fill")).toBeNull();
  expect(within(card).getByTestId("rig-formula")).toHaveTextContent("weights rescaled to the measured parts");
  expect(within(card).getByTestId("rig-ledger")).toHaveTextContent("Trials: 4 trials (2 with, 2 without)");
  // A cap the number is under changes nothing: not listed.
  expect(within(card).queryByText(/^Capped at 49/)).toBeNull();
});

// The engine's verdict for the real finance run (engine/tests/test_verdict.py).
const FINANCE: Rig = {
  ...REAL,
  score: 12,
  label: "Doesn't Work — the agent alone already passes every task",
  reason: "Does worse than the plain agent (-60 pts); costs 54× the plain agent",
  provisional: true,
  pairs: 5,
  verdict: {
    id: "doesnt",
    word: "Doesn't Help",
    tone: "negative",
    reason: "The agent alone already passes every task; with the workflow it costs 21× more per trial, takes 12× as long and timed out on 3 of 5.",
    next: "Next: a harder bench, or drop the workflow.",
    facts: [
      "Quality: 2 of 5 passed with, 5 of 5 passed without (-60 pts, 95% interval -88 to -3)",
      "Cost: $0.87 vs $0.041 per trial (21×); $2.18 vs $0.041 per task solved (54×)",
      "Time: 7.6 min vs 39 s per trial (12×)",
      "Reliability: with, 3 of 5 timed out; without, all 5 ran cleanly",
    ],
  },
};

test("the verdict is the headline, with its reason, next step and facts; the number sits beside it", () => {
  render(<RigScore rig={FINANCE} />);
  const card = screen.getByRole("region", { name: "Rig Score" });
  expect(card).toHaveAttribute("data-verdict", "doesnt");
  const head = within(card).getByTestId("rig-verdict");
  expect(head).toHaveTextContent("Doesn't Help");
  expect(head).toHaveClass("rig__verdict--negative");
  expect(within(card).getByTestId("rig-why")).toHaveTextContent(
    "The agent alone already passes every task; with the workflow it costs 21× more per trial, takes 12× as long and timed out on 3 of 5. Next: a harder bench, or drop the workflow.",
  );
  expect(within(card).getByText("Rig Score: 12 out of 100.")).toBeInTheDocument();
  expect(within(card).getByText(FINANCE.label)).toBeInTheDocument();
  const facts = within(card).getByTestId("rig-facts").querySelectorAll("li");
  expect([...facts].map((f) => f.textContent)).toEqual(FINANCE.verdict!.facts);
  // The score's own drags stay, one line, under the verdict.
  expect(within(card).getByText(`Score: ${FINANCE.reason}`)).toBeInTheDocument();
  expect(card.querySelectorAll(".rig__part")).toHaveLength(5);
});

test("can't tell yet with no score: the dash, the verdict, and no facts list in the compact form", () => {
  const broken: Rig = {
    ...REAL,
    score: null,
    band: "not_evidence",
    tone: "neutral",
    label: "Not Evidence",
    reason: "Invalid: the check is broken.",
    provisional: false,
    gates: [],
    formula: null,
    verdict: {
      id: "cant",
      word: "Can't Tell Yet",
      tone: "neutral",
      reason: "The task's check isn't a command, so every trial fails both ways.",
      next: "Next: give the task a real check.",
      facts: ["Cost: $0.10 vs $0.10 per trial (1.0×)"],
    },
  };
  render(<RigScore rig={broken} compact />);
  const card = screen.getByRole("region", { name: "Rig Score" });
  expect(within(card).getByTestId("rig-verdict")).toHaveTextContent("Can't Tell Yet");
  expect(within(card).getByText("—")).toBeInTheDocument();
  expect(within(card).getByTestId("rig-why")).toHaveTextContent("Next: give the task a real check.");
  expect(within(card).queryByTestId("rig-facts")).toBeNull();
  expect(card.querySelectorAll(".rig__part")).toHaveLength(0);
});
