import { useCallback, useState } from "react";

import type { AgentInfo, LocalModels as LocalData, LocalRepoWords, MetricId } from "../lib/types";
import { LocalModels } from "./LocalModels";

/** "{name}" in the engine's words, filled in. */
export function fill(text: string, values: Record<string, string | number>): string {
  return text.replace(/\{(\w+)\}/g, (all, k: string) => (k in values ? String(values[k]) : all));
}

/** Where a repo's run on Measure runs, as the Lab's "Run on": the signed-in agent, or Claude Code
 * on a local model (free, no sign-in). The words are the engine's (local-models skill: repo).
 * `select` goes beside the run's other choices; `manage` (find and add local models) holds a
 * form of its own, so it goes outside the run's form. */
export function useRunOn(agent: AgentInfo | null) {
  const [data, setData] = useState<LocalData | null>(null);
  const [runOn, setRunOn] = useState(""); // "" = the signed-in agent; else a local model's id
  const onLocals = useCallback((d: LocalData) => {
    setData(d);
    setRunOn((cur) => (cur && !d.models.some((m) => m.id === cur) ? "" : cur));
  }, []);
  const locals = data?.models ?? [];
  const local = locals.find((m) => m.id === runOn) ?? null;
  const words = data?.repo ?? null;
  const agentLabel = agent?.label ?? "Claude Code";
  const select = (
    <div className="field">
      <label htmlFor="repo-run-on">Run on</label>
      <select id="repo-run-on" className="select" value={runOn} disabled={!data} onChange={(e) => setRunOn(e.target.value)}>
        <option value="">{words ? fill(words.sign_in, { agent: agentLabel }) : agentLabel}</option>
        {locals.length && words ? (
          <optgroup label={words.group}>
            {locals.map((m) => (
              <option key={m.id} value={m.id} disabled={!m.anthropic}>
                {m.label}
                {m.anthropic ? "" : words.cant_run}
              </option>
            ))}
          </optgroup>
        ) : null}
      </select>
      {local && words ? (
        <p className="notice small" data-testid="run-on-local">
          {fill(words.notice, { label: local.label, factor: data?.timeout_factor ?? 1 })}
        </p>
      ) : data && !locals.length && words ? (
        <p className="small muted" data-testid="run-on-none">
          {words.none}
        </p>
      ) : null}
    </div>
  );
  const manage = (
    <details className="keybox">
      <summary>Local Models{locals.length ? ` · ${locals.length}` : ""}</summary>
      <LocalModels onChanged={onLocals} />
    </details>
  );
  return { local, words, select, manage, factor: data?.timeout_factor ?? 1 };
}

/** Cost as the metric on a local model: nothing to compare (it costs nothing), so the start is
 * held back and the engine refuses it too. A repo's Measure and the Lab alike. */
export function costOnLocal(local: unknown, metric: MetricId | null | undefined): boolean {
  return !!local && metric === "cost";
}

/** Said beside the metric when costOnLocal: the engine's words (local-models: repo.cost_metric). */
export function CostOnLocal({ show, words }: { show: boolean; words: LocalRepoWords | null | undefined }) {
  return show && words ? (
    <p className="notice notice--warning small" data-testid="cost-on-local">
      {words.cost_metric}
    </p>
  ) : null;
}
