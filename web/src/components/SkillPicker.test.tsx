import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { LabSkill } from "../lib/types";
import { SkillPicker } from "./SkillPicker";

const SKILLS: LabSkill[] = [
  { path: "/u/tdd", name: "tdd", description: "Test first, then code", source: "local" },
  { path: "/u/careful-review", name: "careful-review", description: "Review the diff slowly", source: "local" },
  { path: "gh:obra/superpowers/tdd", name: "test-driven-development", description: "Write the failing test first", source: "github", repo: "obra/superpowers" },
  { path: "gh:x/rag/rag", name: "rag-engineer", description: "Retrieval systems", source: "github", repo: "x/rag" },
];

function setup(chosen: string[] = []) {
  const onPick = vi.fn();
  render(
    <>
      <label htmlFor="pick">Add a skill</label>
      <SkillPicker id="pick" skills={SKILLS} chosen={chosen} onPick={onPick} />
    </>,
  );
  return { onPick, box: screen.getByRole("combobox", { name: "Add a skill" }) };
}

test("lists every skill grouped, yours first, with descriptions", async () => {
  const { box } = setup();
  expect(box).toHaveAttribute("placeholder", "Choose from 4 skills…");
  await userEvent.click(box);
  expect(box).toHaveAttribute("aria-expanded", "true");
  const groups = screen.getAllByRole("group").map((g) => g.getAttribute("aria-labelledby") && document.getElementById(g.getAttribute("aria-labelledby")!)?.textContent);
  expect(groups).toEqual(["Yours", "GitHub · obra/superpowers", "GitHub · x/rag"]);
  expect(screen.getByRole("option", { name: /test-driven-development/ })).toHaveTextContent("Write the failing test first");
});

test("typing filters by name and description; arrows and Enter pick", async () => {
  const { box, onPick } = setup();
  await userEvent.type(box, "failing");
  expect(screen.getAllByRole("option").map((o) => o.querySelector(".skillpick__name")?.textContent)).toEqual(["test-driven-development"]);
  await userEvent.clear(box);
  await userEvent.type(box, "review");
  await userEvent.keyboard("{Enter}");
  expect(onPick).toHaveBeenCalledWith(SKILLS[1]);
  expect(box).toHaveValue("");
});

test("down moves the active option, named by aria-activedescendant", async () => {
  const { box, onPick } = setup();
  await userEvent.click(box);
  await userEvent.keyboard("{ArrowDown}{ArrowDown}");
  const active = document.getElementById(box.getAttribute("aria-activedescendant")!);
  expect(active).toHaveAttribute("aria-selected", "true");
  expect(active).toHaveTextContent("test-driven-development");
  await userEvent.keyboard("{Enter}");
  expect(onPick).toHaveBeenCalledWith(SKILLS[2]);
});

test("a skill already on the step is marked and not picked again; Esc closes", async () => {
  const { box, onPick } = setup(["/u/tdd"]);
  await userEvent.click(box);
  const tdd = screen.getByRole("option", { name: /^tdd/ });
  expect(tdd).toHaveAttribute("aria-disabled", "true");
  expect(tdd).toHaveTextContent("on this step");
  // The active option skips it, both at first and with the arrows.
  expect(document.getElementById(box.getAttribute("aria-activedescendant")!)).toHaveTextContent("careful-review");
  await userEvent.keyboard("{ArrowUp}{ArrowUp}");
  expect(document.getElementById(box.getAttribute("aria-activedescendant")!)).toHaveTextContent("test-driven-development");
  await userEvent.click(tdd);
  expect(onPick).not.toHaveBeenCalled();
  await userEvent.keyboard("{Escape}");
  expect(box).toHaveAttribute("aria-expanded", "false");
});

test("no match says so", async () => {
  const { box } = setup();
  await userEvent.type(box, "kubernetes");
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(screen.getByRole("status")).toHaveTextContent("No skill matches “kubernetes”.");
});

test("a skill on the step says why it was picked, in place of its description", async () => {
  render(
    <>
      <label htmlFor="pick">Add a skill</label>
      <SkillPicker
        id="pick"
        skills={SKILLS}
        chosen={["gh:obra/superpowers/tdd"]}
        why={{ "gh:obra/superpowers/tdd": "picked by Qwen3-Reranker-0.6B (0.99): the step says failing test" }}
        onPick={vi.fn()}
      />
    </>,
  );
  await userEvent.click(screen.getByRole("combobox", { name: "Add a skill" }));
  const on = screen.getByRole("option", { name: /test-driven-development/ });
  expect(on).toHaveTextContent("picked by Qwen3-Reranker-0.6B (0.99): the step says failing test");
  expect(on).not.toHaveTextContent("Write the failing test first");
  expect(screen.getByRole("option", { name: /^tdd/ })).toHaveTextContent("Test first, then code");
});
