import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { api } from "../lib/api";
import type { GarageEntry, GarageRecommendation } from "../lib/types";
import { GaragePanel } from "./Garage";

// What the engine returns for "support agent workflow" (architecture-catalog: empty_state).
const EMPTY: GarageRecommendation = {
  picks: [],
  note: null,
  explain_usd: 0.01,
  empty: {
    title: "No fits yet",
    matched: "Only 'support' and 'workflow' matched, too little to rank on.",
    near: [
      { id: "plan-and-execute", name: "Plan-and-execute", matched: ["workflow"] },
      { id: "router", name: "Router", matched: ["support"] },
      { id: "swarm-handoffs", name: "Swarm / handoffs", matched: ["support"] },
    ],
    heading: "Close, not a fit yet",
    asks_lead: "To rank one, say:",
    asks: ["whether the work is several steps in order", "what kinds of request come in and who handles each", "when the work is handed to another agent or a person"],
    words: "Words like tickets, customer, feature or implement count too.",
    browse: "Or browse them all below.",
  },
};

const BROWSE = "Say more about the documents, the users or the tools involved, or browse below.";

const ROUTER: GarageEntry = {
  id: "router",
  family: "agent",
  name: "Router",
  summary: "Classify the request once and send it on.",
  when_to_use: "",
  when_not_to_use: "",
  components: [
    { id: "task", label: "Task", type: "frontend", role: "Takes the task in" },
    { id: "m", label: "Model", type: "cloud", role: "Classifies" },
  ],
  connections: [["task", "m", ""]],
  parameters: [],
  tradeoffs: { latency: "low", cost: "low", accuracy: "medium", complexity: "low" },
  signals: [],
  sources: [],
};

beforeEach(() => {
  vi.spyOn(api, "garageCatalog").mockResolvedValue({ families: [], count: 0 });
});
afterEach(() => vi.restoreAllMocks());

const panel = () => (
  <GaragePanel repoId={null} useCase="support agent workflow" blueprint={null} onOpen={() => undefined} onClose={() => undefined} autoRun onEditUseCase={() => undefined} />
);

test("no picks: no Explain offer; the close designs, labelled as not a fit, each with See This Design", async () => {
  const rec = vi.spyOn(api, "garageRecommend").mockResolvedValue(EMPTY);
  const entry = vi.spyOn(api, "garageEntry").mockReturnValue(new Promise(() => undefined));
  render(panel());
  expect(await screen.findByText("Only 'support' and 'workflow' matched, too little to rank on.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Explain the Top Three/ })).toBeNull();
  expect(screen.queryByText(/Nothing matched/)).toBeNull();
  expect(screen.getByText("No fits yet")).toBeInTheDocument();
  expect(screen.queryByText("Best fits")).toBeNull();
  expect(rec).toHaveBeenCalledOnce();
  expect(rec).toHaveBeenCalledWith("support agent workflow", null, false);

  const close = screen.getByRole("region", { name: "Close, not a fit yet" });
  expect(within(close).getAllByRole("button", { name: /^See This Design/ })).toHaveLength(3);
  // Never shown as a pick: no fit label, no numbered list.
  expect(screen.queryByTestId("fit-label")).toBeNull();
  expect(screen.getByText("To rank one, say:")).toBeInTheDocument();
  expect(screen.getByText("when the work is handed to another agent or a person")).toBeInTheDocument();
  expect(screen.getByText("Words like tickets, customer, feature or implement count too.")).toBeInTheDocument();
  expect(screen.getByText("Or browse them all below.")).toBeInTheDocument();

  await userEvent.click(within(close).getByRole("button", { name: "See This Design: Router" }));
  expect(entry).toHaveBeenCalledWith("router");
});

test("no word matched: says so, with the browse hint and nothing else", async () => {
  vi.spyOn(api, "garageRecommend").mockResolvedValue({
    ...EMPTY,
    empty: { title: "No fits yet", matched: "None of its words point at a design.", near: [], heading: null, asks_lead: null, asks: [], words: null, browse: BROWSE },
  });
  render(panel());
  expect(await screen.findByText("None of its words point at a design.")).toBeInTheDocument();
  expect(screen.getByText(BROWSE)).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Close, not a fit yet" })).toBeNull();
  expect(screen.queryByRole("button", { name: /See This Design/ })).toBeNull();
  expect(screen.queryByRole("button", { name: /Explain the Top Three/ })).toBeNull();
});

test("with picks, the Explain offer is there and the empty state is not", async () => {
  vi.spyOn(api, "garageRecommend").mockResolvedValue({
    picks: [{ id: "router", score: 6, fit: "strong", fit_label: "Strong Fit", reasons: ["Because you said 'triage'."], entry: ROUTER, explanation: null }],
    note: null,
    empty: null,
    explain_usd: 0.01,
  });
  render(panel());
  expect(await screen.findByRole("button", { name: "Explain the Top Three with the Model (≈$0.01)" })).toBeInTheDocument();
  expect(screen.getByText("Best fits")).toBeInTheDocument();
  expect(screen.queryByText("No fits yet")).toBeNull();
  expect(screen.queryByRole("region", { name: "Close, not a fit yet" })).toBeNull();
});
