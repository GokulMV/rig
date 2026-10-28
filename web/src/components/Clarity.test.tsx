import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import RULES from "../fixtures/rules.json";
import { measureBadge, setRules } from "../lib/rules";
import type { GoalRules, MeasureRules } from "../lib/types";
import { Describe, Guide } from "./Journey";
import { MeasureEmpty } from "./MeasureBadge";
import { shipDifference, ShipToggle } from "./ShipToggle";

const M = RULES.measurability as MeasureRules;
const G = RULES["repo-goals"] as GoalRules;
const diff = (tasks: string[], notes: string[]) => ({
  added: [],
  removed: [],
  connected: 0,
  disconnected: 0,
  suggestions: tasks.length + notes.length,
  task_items: tasks.map((title, i) => ({ id: `t${i}`, title })),
  note_items: notes.map((title, i) => ({ id: `n${i}`, title })),
});

test("Ship says when the two briefs are the same, and why", () => {
  expect(shipDifference(0, null)).toMatchObject({ same: true });
  const notes = shipDifference(4, diff([], ["a", "b", "c", "d"]));
  expect(notes.same).toBe(true);
  expect(notes.text).toMatch(/^Your 4 accepted suggestions are diagram notes/);
  const tasks = shipDifference(2, diff(["Split refund rules"], ["Show where web gets its input"]));
  expect(tasks).toMatchObject({ same: false, tasks: ["Split refund rules"], notes: ["Show where web gets its input"] });
  expect(tasks.text).toContain("adds 1 change to make and 1 diagram note");
});

test("Ship lists exactly what “with” adds, and can't pick it with nothing accepted", async () => {
  const onSource = vi.fn();
  const { rerender } = render(<ShipToggle source="repo" onSource={onSource} accepted={0} diff={null} />);
  expect(screen.getByRole("radio", { name: "With the Accepted Suggestions" })).toBeDisabled();
  rerender(<ShipToggle source="repo" onSource={onSource} accepted={1} diff={diff(["Split refund rules"], [])} />);
  expect(screen.getByRole("listitem")).toHaveTextContent("Split refund rules");
  await userEvent.click(screen.getByRole("radio", { name: "With the Accepted Suggestions" }));
  expect(onSource).toHaveBeenCalledWith("suggested");
});

test("Ship marks a split or merge as Build does: “Changes the code”, in the skill's words", () => {
  setRules("measurability", M);
  const d = {
    ...diff([], []),
    task_items: [
      { id: "split", title: "Split refund rules", measure: "before_after" },
      { id: "doc", title: "Document the refund flow", measure: "brief" },
      { id: "task", title: "Add a check for refunds", measure: "enables" },
    ],
    note_items: [{ id: "n", title: "Show where web gets its input", measure: "note" }],
  };
  render(<ShipToggle source="suggested" onSource={() => {}} accepted={4} diff={d} />);
  const items = screen.getAllByRole("listitem");
  const badge = (i: number) => items[i].querySelector(".mbadge");
  expect(badge(0)).toHaveTextContent(M.states.before_after.label);
  expect(badge(0)).toHaveAttribute("title", M.states.before_after.says);
  expect(badge(1)).toBeNull(); // "Brief only": the whole list is the brief
  expect(badge(2)).toHaveTextContent(M.states.enables.label);
  expect(badge(3)).toHaveTextContent(M.states.note.label);
  setRules("measurability", null);
});

test("Measure with nothing to run says what it runs, what it can't and why, and links to Build", async () => {
  const onBuild = vi.fn();
  render(
    <MeasureEmpty
      rules={M}
      notRunnable={[
        { name: "CLAUDE.md", b: measureBadge({ kind: "setup", label: "CLAUDE.md", present: true }, M) },
        { name: "2 accepted suggestions", b: measureBadge({ kind: "arch", c: { source: "proposed" } }, M) },
      ]}
      onBuild={onBuild}
    />,
  );
  expect(screen.getByText("Nothing Here Measure Can Run Yet")).toBeInTheDocument();
  expect(screen.getByText(/^Measure runs skills, hooks, MCP servers and CLAUDE\.md files, with and without/)).toBeInTheDocument();
  expect(screen.getByText("In Every Run")).toBeInTheDocument();
  expect(screen.getByText("Changes the Code")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Add a Skill on Build" }));
  expect(onBuild).toHaveBeenCalled();
});

test("Describe offers one-click goals for a repo; picking one fills the box", async () => {
  const onTemplate = vi.fn();
  render(
    <Guide.Provider value={{ workspace: false }}>
      <Describe
        space="repo"
        onSpace={() => {}}
        repos={[{ id: "r1", name: "proj", root: "/Users/me/proj" } as never]}
        repoId="r1"
        onRepo={() => {}}
        onDetach={async () => {}}
        labText=""
        onLabText={() => {}}
        repoText=""
        onRepoText={() => {}}
        repoReady
        repoDirty={false}
        repoHasGoal={false}
        repoSaved={false}
        onSave={async () => {}}
        attach={null}
        onStep={() => {}}
        templates={G.templates}
        template="runs-tests"
        onTemplate={onTemplate}
      />
    </Guide.Provider>,
  );
  const group = screen.getByRole("group", { name: "Start from a common goal" });
  expect(group.querySelectorAll("button")).toHaveLength(G.templates.length);
  expect(screen.getByRole("button", { name: "Always Runs the Tests" })).toHaveAttribute("aria-pressed", "true");
  await userEvent.click(screen.getByRole("button", { name: "Fewer Tokens at the Same Pass Rate" }));
  expect(onTemplate).toHaveBeenCalledWith(expect.objectContaining({ id: "fewer-tokens", metric: "tokens" }));
});
