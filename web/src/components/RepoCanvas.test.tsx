import { archStyle, blueprintRole } from "./RepoCanvas";
import { humanLabel } from "./Garage";
import { notesOnly } from "../lib/format";

test("a model gateway is a Model, a proxy an Edge / proxy, other cloud a Cloud service", () => {
  expect(archStyle({ type: "cloud", label: "LLM gateway", sublabel: "Anthropic API" }).label).toBe("Model");
  expect(archStyle({ type: "external", label: "Claude", sublabel: null }).label).toBe("Model");
  expect(archStyle({ type: "cloud", label: "Nginx", sublabel: "reverse proxy" }).label).toBe("Edge / proxy");
  expect(archStyle({ type: "cloud", label: "S3 bucket", sublabel: null }).label).toBe("Cloud service");
});

test("a parameter reads by what it does, not its key", () => {
  expect(humanLabel("Which actions pause for a person.", "approval_required_for")).toBe("Which actions pause for a person");
  expect(humanLabel("", "timeout_hours")).toBe("timeout hours");
});

test("suggestions that change no parts say so", () => {
  expect(notesOnly(4)).toBe("4 accepted suggestions, all diagram notes: no parts or links change");
  expect(notesOnly(1)).toBe("1 accepted suggestion, all diagram notes: no parts or links change");
  expect(notesOnly(0, true)).toMatch(/^Previewing one open suggestion/);
});

test("a catalog blueprint's blocks are named by their role, never Cloud service", () => {
  const role = (label: string, type: "cloud" | "external" = "cloud", sublabel: string | null = null) => blueprintRole({ type, label, sublabel });
  expect(role("Planner")).toBe("Planner");
  expect(role("Relevance grader")).toBe("Checker");
  expect(role("Classifier")).toBe("Router");
  expect(role("Orchestrator")).toBe("Coordinator");
  expect(role("Reranker")).toBe("Retrieval step");
  expect(role("Worker 1", "cloud", "Does one subtask")).toBe("Agent");
  expect(role("Answer", "external")).toBe("Output");
  expect(role("Tools", "external")).toBe("Tools");
  expect(role("Model", "cloud", "Writes the answer from what it is given")).toBeNull(); // archStyle says Model
  expect(blueprintRole({ type: "database", label: "Vector store" })).toBeNull();
});
