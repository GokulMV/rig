import type { LabStep, LabWorkflow } from "./types";

/** The forward connections, also for older workflows that are a plain list. */
export function edgesOf(wf: LabWorkflow): [string, string][] {
  if (wf.edges?.length) return wf.edges;
  const ids = wf.steps.map((s) => s.id);
  return ids.slice(1).map((b, i) => [ids[i], b] as [string, string]);
}

/** Stages, like the engine: a step starts when everything pointing into it is done. */
export function stages(wf: LabWorkflow): string[][] {
  const ids = wf.steps.map((s) => s.id);
  const edges = edgesOf(wf);
  const indeg = new Map(ids.map((i) => [i, 0]));
  const out = new Map(ids.map((i) => [i, [] as string[]]));
  for (const [a, b] of edges) {
    if (out.has(a) && indeg.has(b)) {
      out.get(a)!.push(b);
      indeg.set(b, indeg.get(b)! + 1);
    }
  }
  let stage = ids.filter((i) => indeg.get(i) === 0);
  const res: string[][] = [];
  const seen = new Set<string>();
  while (stage.length) {
    res.push(stage);
    stage.forEach((i) => seen.add(i));
    const next: string[] = [];
    for (const a of stage) for (const b of out.get(a)!) if ((indeg.set(b, indeg.get(b)! - 1), indeg.get(b) === 0)) next.push(b);
    stage = ids.filter((i) => next.includes(i));
  }
  const rest = ids.filter((i) => !seen.has(i));
  if (rest.length) res.push(rest);
  return res;
}

/** "A → B + C → D": parallel steps joined by +. */
export function flowText(wf: LabWorkflow): string {
  return stages(wf)
    .map((st) => st.map((id) => wf.steps.find((s) => s.id === id)?.name ?? id).join(" + "))
    .join(" → ");
}

const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");

/** One step lined up across the workflows: the same step id, else the same name. */
export interface AlignedStep {
  key: string;
  steps: (LabStep | null)[];
}

/** Line the workflows' steps up: by step id first, then by name (a step renamed in a copy keeps
 * its id; two starters that both have "Run the tests" line up by name). In first-seen order. */
export function alignSteps(wfs: LabWorkflow[]): AlignedStep[] {
  const rows: (AlignedStep & { id: string; names: Set<string> })[] = [];
  wfs.forEach((wf, i) => {
    for (const s of wf.steps) {
      let row = rows.find((r) => r.steps[i] === null && r.id === s.id);
      if (!row) row = rows.find((r) => r.steps[i] === null && r.names.has(norm(s.name)));
      if (!row) {
        let key = s.id;
        for (let n = 2; rows.some((r) => r.key === key); n++) key = `${s.id}~${n}`;
        row = { key, id: s.id, names: new Set(), steps: wfs.map(() => null) };
        rows.push(row);
      }
      row.steps[i] = s;
      row.names.add(norm(s.name));
    }
  });
  return rows.map(({ key, steps }) => ({ key, steps }));
}

export type DiffKind = "discipline" | "step" | "renamed" | "kind" | "model" | "skills" | "loop" | "rule" | "order";

/** One line of the Differences: what differs and each workflow's side of it (null: it has none). */
export interface DiffRow {
  kind: DiffKind;
  label: string;
  cells: (string | null)[];
}

export interface DiffNames {
  model?: (id: string) => string;
  rule?: (id: string) => string;
  discipline?: (id: string) => string;
}

const differ = (xs: (string | null)[]) => new Set(xs).size > 1;

/** Only what differs between the workflows, step by step (aligned by id, then name): steps added
 * or removed, renamed, a different kind, model or skills, loops, harness rules and the order. */
export function diffWorkflows(wfs: LabWorkflow[], names: DiffNames = {}): DiffRow[] {
  if (wfs.length < 2) return [];
  const model = names.model ?? ((x: string) => x);
  const rule = names.rule ?? ((x: string) => x);
  const disc = names.discipline ?? ((x: string) => x);
  const out: DiffRow[] = [];
  const disciplines = wfs.map((w) => disc(w.discipline));
  if (differ(disciplines)) out.push({ kind: "discipline", label: "Discipline", cells: disciplines });

  const aligned = alignSteps(wfs);
  const keyOf = wfs.map((_, i) => new Map(aligned.flatMap((a) => (a.steps[i] ? [[a.steps[i]!.id, a.key] as const] : []))));
  const nameOfKey = new Map(aligned.map((a) => [a.key, a.steps.find(Boolean)!.name]));
  for (const a of aligned) {
    const here = a.steps.map((s) => s?.name ?? null);
    const title = nameOfKey.get(a.key)!;
    if (here.some((x) => x === null)) {
      out.push({ kind: "step", label: `Step: ${title}`, cells: here });
    } else if (differ(here.map((x) => norm(x!)))) {
      out.push({ kind: "renamed", label: `Step renamed: ${title}`, cells: here });
    }
    const present = a.steps.filter(Boolean) as LabStep[];
    if (present.length < 2) continue;
    const kinds = a.steps.map((s) => s?.kind ?? null);
    if (differ(kinds.filter(Boolean) as string[])) out.push({ kind: "kind", label: `Kind: ${title}`, cells: kinds });
    const models = a.steps.map((s) => (s ? model(s.model) : null));
    if (differ(models.filter(Boolean) as string[])) out.push({ kind: "model", label: `Model: ${title}`, cells: models });
    const skills = a.steps.map((s) => (s ? s.skills.map((k) => k.name).sort().join(", ") || "none" : null));
    if (differ(skills.filter(Boolean) as string[])) out.push({ kind: "skills", label: `Skills: ${title}`, cells: skills });
  }

  // Loops, by the aligned steps they join: missing in some, or a different number of tries.
  const loops = new Map<string, { label: string; cells: (string | null)[] }>();
  wfs.forEach((wf, i) => {
    for (const [from, to, n] of wf.loops ?? []) {
      const k = `${keyOf[i].get(from) ?? from}>${keyOf[i].get(to) ?? to}`;
      const label = `Loop: ${nameOfKey.get(keyOf[i].get(from) ?? "") ?? from} back to ${nameOfKey.get(keyOf[i].get(to) ?? "") ?? to}`;
      const row = loops.get(k) ?? { label, cells: wfs.map(() => null) };
      row.cells[i] = `at most ${n}×`;
      loops.set(k, row);
    }
  });
  for (const row of loops.values()) if (differ(row.cells)) out.push({ kind: "loop", ...row });

  const rules = [...new Set(wfs.flatMap((w) => w.harness))];
  for (const r of rules) {
    const cells = wfs.map((w) => (w.harness.includes(r) ? "on" : null));
    if (differ(cells)) out.push({ kind: "rule", label: `Rule: ${rule(r)}`, cells });
  }

  // The order: the steps every workflow has, run in a different order or side by side instead of
  // one after another. A step added or removed (said above) doesn't count on its own.
  const shared = aligned.filter((a) => a.steps.every(Boolean));
  const shape = wfs.map((wf, i) => {
    const at = new Map(stages(wf).flatMap((st, n) => st.map((id) => [id, n] as const)));
    const raw = shared.map((a) => at.get(a.steps[i]!.id) ?? 0);
    const dense = [...new Set(raw)].sort((x, y) => x - y);
    return raw.map((x) => dense.indexOf(x)).join(",");
  });
  if (shared.length > 1 && differ(shape)) out.push({ kind: "order", label: "Order of steps", cells: wfs.map(flowText) });
  return out;
}

/** Which aligned steps are not in every workflow: drawn marked in the mini diagrams. */
export function notShared(wfs: LabWorkflow[]): Set<string>[] {
  const aligned = alignSteps(wfs);
  return wfs.map((_, i) => new Set(aligned.filter((a) => a.steps[i] && a.steps.some((s) => s === null)).map((a) => a.steps[i]!.id)));
}
