import { adherenceText, humanName, modelText, ofWorkflow, outcomeWord, spentText, statusText, verdictWord } from "./evidence";
import type { RigScore } from "./types";

const rig = (band: RigScore["band"]) => ({ band }) as RigScore;

test("the verdict word follows the score's band", () => {
  expect(verdictWord(rig("not_proven"), "inconclusive")).toEqual({ word: "Not Proven", tone: "inconclusive" });
  expect(verdictWord(rig("not_evidence"), "helps").word).toBe("Not Evidence");
  expect(verdictWord(rig("doesnt"), "hurts")).toEqual({ word: "Hurts", tone: "hurts" });
  expect(verdictWord(rig("doesnt"), "inconclusive")).toEqual({ word: "Doesn't Help", tone: "hurts" });
  expect(verdictWord(rig("helps_but"), "helps").word).toBe("Helps");
  expect(verdictWord(null, "inconclusive").word).toBe("Inconclusive");
});

test("the engine's plain verdict wins over the band when the result has one", () => {
  const v = (id: "helps" | "doesnt" | "cant", word: string) => ({ band: "not_proven", verdict: { id, word, tone: "neutral", reason: "", next: "", facts: [] } }) as unknown as RigScore;
  expect(verdictWord(v("doesnt", "Doesn't Help"), "hurts")).toEqual({ word: "Doesn't Help", tone: "hurts" });
  expect(verdictWord(v("cant", "Can't Tell Yet"), "inconclusive")).toEqual({ word: "Can't Tell Yet", tone: "inconclusive" });
  expect(verdictWord(v("helps", "Helps"), "inconclusive")).toEqual({ word: "Helps", tone: "helps" });
});

test("a timed-out fail reads 'timed out'; every other outcome reads as itself", () => {
  expect(outcomeWord({ outcome: "fail", timed_out: true })).toBe("timed out");
  expect(outcomeWord({ outcome: "fail" })).toBe("fail");
  expect(outcomeWord({ outcome: "errored", timed_out: false })).toBe("errored");
});

test("treatment ids read as names", () => {
  expect(humanName("DietrichGebert__ponytail__ponytail-audit")).toBe("ponytail-audit (DietrichGebert/ponytail)");
  expect(humanName("refund-policy")).toBe("refund-policy");
  expect(humanName("a__b")).toBe("a__b");
});

test("a Lab result belongs to its workflow, any agent's form, and no other", () => {
  expect(ofWorkflow({ workflow_id: "rag", treatment: "workflow-rag" }, "rag")).toBe(true);
  expect(ofWorkflow({ workflow_id: "rag-v2", treatment: "workflow-rag-v2" }, "rag")).toBe(false);
  expect(ofWorkflow({ treatment: "workflow-rag-codex" }, "rag")).toBe(true);
  expect(ofWorkflow({ treatment: "workflow-rag-v2" }, "rag")).toBe(false);
});

test("spent, the budget and why it went over", () => {
  expect(spentText(2.9, 2, { note: "went over before the budget cap existed" })).toBe("$2.90 of $2.00 · went over before the budget cap existed");
  expect(spentText(1, 2)).toBe("$1.00 of $2.00");
});

test("statuses are words, never the raw value", () => {
  expect(statusText("stopped_budget")).toBe("Stopped at the budget");
  expect(statusText("done")).toBe("Done");
  expect(statusText("failed_preflight")).toMatch(/^Couldn't start: /);
  expect(statusText("something_new")).toBe("Something new");
  expect(statusText("stopped_budget", "The engine's words")).toBe("The engine's words");
});

test("adherence reads the same on a result and on its run page", () => {
  const a = { trials: 3, read: 3, followed: 0, steps_run: 0, models_ok: null, loop_broken: 0, not_opened: 3, missing: [], skipped: [], wrong_model: [] };
  expect(adherenceText(a)).toBe('Followed the whole workflow in 0 of the 3 "with" trials whose logs could be read · never opened the workflow in 3');
  expect(adherenceText({ ...a, read: 0, not_opened: 0 })).toBe("No session logs to check it followed the workflow");
});

test("a run on a local model names it by its label; any other by its model", () => {
  expect(modelText({ model: "local:ollama-11434-qwen3-8b", local_model: { id: "local:ollama-11434-qwen3-8b", label: "qwen3:8b · ollama" } })).toBe(
    "qwen3:8b · ollama (local)",
  );
  expect(modelText({ model: "claude-sonnet-5-5", local_model: null })).toBe("claude-sonnet-5-5");
  expect(modelText({ model: "claude-sonnet-5-5" })).toBe("claude-sonnet-5-5");
});
