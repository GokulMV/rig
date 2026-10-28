import { ArrowLeft, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import { humanName, modelText, spentText, statusText, verdictWord } from "../lib/evidence";
import { isEvidence } from "../lib/provenance";
import type { ExperimentDetail, ExperimentRow, LabResult, LocalRun, OverBudget, RepoRef, RigScore, Validity } from "../lib/types";
import { Result, Trials } from "./Results";
import { RigBadge } from "./RigScore";

const POLL_MS = 5000;

type Row = {
  key: string;
  kind: "repo" | "bench";
  id: number;
  /** The id the run measured: a workflow's name, or a skill folder like "owner__repo__skill". */
  what: string;
  where: string;
  /** repo id or bench id: the run's link. */
  place: string;
  model: string;
  /** The local model it ran on, or null on the signed-in agent. */
  local_model: LocalRun | null;
  agent: string;
  date: string;
  pairs: number;
  status: string;
  /** The engine's words for it (trial-budget: status_words). */
  statusText?: string;
  verdict: string | null;
  rig: RigScore | null;
  validity: Validity | null;
  spent: number;
  budget: number | null;
  over: OverBudget | null;
  repo?: RepoRef;
  lab?: LabResult;
};

const AGENT: Record<string, string> = {
  "claude-code": "Claude Code",
  codex: "Codex",
  "gemini-cli": "Gemini CLI",
  opencode: "OpenCode",
};

/** What a run found, in words that agree with its Rig score: the verdict once done, else where it stopped. */
function outcome(r: Row): string {
  // A baseline check has no "with" arm: what it found is how the agent alone did.
  if (r.lab?.probe && r.status !== "running") return r.lab.probe_result?.text ?? statusText(r.status, r.statusText);
  const v = verdictWord(r.rig, r.verdict).word;
  if (r.status === "done") return v;
  const status = statusText(r.status, r.statusText);
  const say = r.status !== "running" && r.status !== "failed_preflight" && (r.rig?.verdict != null || (r.verdict && r.rig?.band !== "not_evidence"));
  return say ? `${status} · ${v.toLowerCase()} so far` : status;
}

/** The run's own link: #/runs/repo/<repo id>/<id> or #/runs/bench/<bench id>/<id>. */
export function runHref(kind: "repo" | "bench", place: string, id: number): string {
  return `#/runs/${kind}/${encodeURIComponent(place)}/${id}`;
}

/** The run a hash names, if any. */
export function parseRunHash(hash: string): { kind: "repo" | "bench"; place: string; id: number } | null {
  const m = /^#\/runs\/(repo|bench)\/([^/]+)\/(\d+)$/.exec(hash);
  return m ? { kind: m[1] as "repo" | "bench", place: decodeURIComponent(m[2]), id: Number(m[3]) } : null;
}

function useHash(): string {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

/** Every run, past and present: each repo's experiments and every Lab result, in one table;
 * each run opens read-only at its own link, without changing what you have open. */
export function RunsPage({
  repos,
  currentRepoId,
  onOpenRepo,
  onOpenLab,
}: {
  repos: RepoRef[];
  /** The repo open now (null in the Lab): opening a run elsewhere asks first. */
  currentRepoId?: string | null;
  onOpenRepo: (repoId: string) => void;
  onOpenLab: (r: LabResult) => void;
}) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [forget, setForget] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const hash = useHash();
  const route = parseRunHash(hash);

  // The page has its own link, so a reload or a shared link comes back here.
  useEffect(() => {
    if (!window.location.hash.startsWith("#/runs")) window.history.replaceState(null, "", "#/runs");
  }, []);

  const load = useCallback(async () => {
    const got = await Promise.allSettled([
      api.labResults(),
      ...repos.map((r) => api.experimentsOf(r.id).then((list) => ({ r, list }))),
    ]);
    const out: Row[] = [];
    const bad: string[] = [];
    const [lab, ...byRepo] = got;
    if (lab.status === "fulfilled") {
      for (const x of lab.value as LabResult[])
        out.push({
          key: `bench:${x.bench}:${x.id}`,
          kind: "bench",
          id: x.id,
          what: x.workflow,
          where: x.bench_name,
          place: x.bench,
          model: x.model,
          local_model: x.local_model ?? null,
          agent: x.agent ?? "claude-code",
          date: x.date ?? "",
          pairs: x.n_pairs,
          status: x.status,
          statusText: x.status_text,
          verdict: x.verdict,
          rig: x.rig ?? null,
          validity: x.validity ?? null,
          spent: x.spent_usd,
          budget: x.budget_usd ?? null,
          over: x.over_budget ?? null,
          lab: x,
        });
    } else bad.push(`Couldn't read the Lab's results. ${lab.reason instanceof ApiError ? lab.reason.message : String(lab.reason)}`);
    byRepo.forEach((g, i) => {
      const r = repos[i];
      if (g.status === "rejected") {
        bad.push(`Couldn't read ${r.name}'s runs. ${g.reason instanceof ApiError ? g.reason.message : String(g.reason)}`);
        return;
      }
      for (const e of (g.value as { list: ExperimentRow[] }).list)
        out.push({
          key: `repo:${r.id}:${e.id}`,
          kind: "repo",
          id: e.id,
          what: e.treatment_name,
          where: r.name,
          place: r.id,
          model: e.model,
          local_model: e.local_model ?? null,
          agent: e.agent ?? "claude-code",
          date: e.created_at.slice(0, 10),
          pairs: e.n_pairs ?? 0,
          status: e.status,
          statusText: e.status_text,
          verdict: e.verdict ?? null,
          rig: e.rig ?? null,
          validity: e.validity ?? null,
          spent: e.spent_usd,
          budget: e.budget_usd,
          over: e.over_budget ?? null,
          repo: r,
        });
    });
    // Newest first; a day's runs by id, newest first too.
    out.sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id || a.key.localeCompare(b.key));
    setRows(out);
    setProblems(bad);
  }, [repos]);
  useEffect(() => {
    void load();
  }, [load]);
  const going = rows?.some((r) => r.status === "running") ?? false;
  useEffect(() => {
    if (!going) return;
    const t = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(t);
  }, [going, load]);

  const sameName = (r: Row) => r.repo && repos.filter((x) => x.name === r.repo!.name).length > 1;

  if (route) {
    const row = rows?.find((r) => r.kind === route.kind && r.place === route.place && r.id === route.id) ?? null;
    return (
      <main className="steppage" id="main">
        <div className="steppage__inner">
          <RunDetail route={route} row={row} repos={repos} currentRepoId={currentRepoId} onOpenRepo={onOpenRepo} onOpenLab={onOpenLab} />
        </div>
      </main>
    );
  }

  return (
    <main className="steppage" id="main">
      <div className="steppage__inner">
        <h1 className="steppage__title">Runs</h1>
        <p className="steppage__lead muted">
          Every run, past and present: what each measured, where, on which model and agent, and what it found. Each run has its own
          link; viewing one changes nothing you have open.
        </p>
        {problems.map((p) => (
          <p key={p} className="notice notice--warning small">
            {p}
          </p>
        ))}
        {error ? (
          <p className="notice notice--error small" role="alert">
            {error}
          </p>
        ) : null}
        {rows === null ? (
          <p className="muted">Reading the runs…</p>
        ) : rows.length === 0 ? (
          <p className="muted">No runs yet. Measure a change on the Measure step and it's listed here.</p>
        ) : (
          <div className="table-wrap runs" tabIndex={0} role="region" aria-label="Every run">
            <table className="runs__table">
              <colgroup>
                <col className="runs__c-what" />
                <col className="runs__c-model" />
                <col className="runs__c-pairs" />
                <col className="runs__c-result" />
                <col className="runs__c-rig" />
                <col className="runs__c-valid" />
                <col className="runs__c-spent" />
                <col className="runs__c-act" />
              </colgroup>
              <thead>
                <tr>
                  <th scope="col">Measured</th>
                  <th scope="col">Model</th>
                  <th scope="col" className="num">
                    Pairs
                  </th>
                  <th scope="col">Result</th>
                  <th scope="col">Rig score</th>
                  <th scope="col">Validity</th>
                  <th scope="col" className="num">
                    Spent
                  </th>
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const name = humanName(r.what);
                  const v = verdictWord(r.rig, r.verdict);
                  return (
                    <tr key={r.key} className={r.status === "running" ? "is-running" : undefined}>
                      <td className="runs__what">
                        <a className="runs__name" href={runHref(r.kind, r.place, r.id)} title={r.what}>
                          {name}
                        </a>
                        <span className="runs__where small muted">
                          {r.kind === "repo" ? "repo" : "bench"} {r.where}
                          {sameName(r) ? <span className="mono"> · {r.repo!.root}</span> : null} · <span className="num">{r.date}</span>
                        </span>
                      </td>
                      <td className="runs__model">
                        <span className="mono small">{modelText(r)}</span>
                        <span className="small muted">{AGENT[r.agent] ?? r.agent}</span>
                      </td>
                      <td className="num">{r.pairs}</td>
                      <td>
                        <span
                          className={`pill${r.status === "done" && v.tone === "helps" ? " pill--positive" : r.status === "done" && v.tone === "hurts" ? " pill--negative" : r.status === "running" ? " pill--warning" : ""}`}
                        >
                          {outcome(r)}
                        </span>
                        {r.status !== "running" && r.status !== "failed_preflight" && r.rig?.verdict ? (
                          <span className="verdict-why small muted" title={`${r.rig.verdict.reason} ${r.rig.verdict.next}`} data-testid="runs-why">
                            {r.rig.verdict.reason}
                          </span>
                        ) : null}
                      </td>
                      <td data-testid="runs-rig">
                        {r.status === "running" || !r.rig ? (
                          <span className="small muted">—</span>
                        ) : r.rig.score == null ? (
                          r.rig.band === "not_evidence" ? (
                            <RigBadge score={null} tone="neutral" band="not_evidence" />
                          ) : (
                            <span className="small muted">—</span>
                          )
                        ) : (
                          <RigBadge score={r.rig.score} tone={r.rig.tone} provisional={r.rig.provisional} label={r.rig.label} />
                        )}
                      </td>
                      <td className="small" data-testid="runs-validity">
                        {r.status === "running" || !r.validity ? (
                          <span className="muted">—</span>
                        ) : isEvidence(r.validity) ? (
                          "Valid"
                        ) : (
                          <span className="runs__invalid" title={r.validity.reason ?? undefined}>
                            {r.validity.badge}
                          </span>
                        )}
                      </td>
                      <td className="num small runs__spent">
                        {r.local_model ? "Free (local)" : spentText(r.spent, r.budget)}
                        {r.over ? <span className="runs__over muted">{r.over.note}</span> : null}
                      </td>
                      <td className="runs__act">
                        <a className="btn btn--small" href={runHref(r.kind, r.place, r.id)} aria-label={`View ${name} on ${r.where}`}>
                          View
                        </a>
                        {r.status === "running" ? null : forget === r.key ? (
                          <span className="small">
                            Forget?{" "}
                            <button
                              type="button"
                              className="linkish"
                              onClick={async () => {
                                setForget(null);
                                setError(null);
                                try {
                                  if (r.lab) await api.labForget(r.lab.bench, r.lab.id);
                                  else if (r.repo) await api.forgetExperiment(r.id, r.repo.id);
                                  await load();
                                } catch (e) {
                                  setError(e instanceof ApiError ? e.message : String(e));
                                }
                              }}
                            >
                              Yes
                            </button>{" "}
                            <button type="button" className="linkish" onClick={() => setForget(null)}>
                              No
                            </button>
                          </span>
                        ) : (
                          <button
                            type="button"
                            className="iconbtn"
                            aria-label={`Forget the run ${name} on ${r.where}`}
                            title="Forget this result: its trials are deleted"
                            onClick={() => setForget(r.key)}
                          >
                            <X size={14} aria-hidden="true" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}

/** One run, read-only: its result card and trials. "Open in context" asks before it switches anything. */
function RunDetail({
  route,
  row,
  repos,
  currentRepoId,
  onOpenRepo,
  onOpenLab,
}: {
  route: { kind: "repo" | "bench"; place: string; id: number };
  row: Row | null;
  repos: RepoRef[];
  currentRepoId?: string | null;
  onOpenRepo: (repoId: string) => void;
  onOpenLab: (r: LabResult) => void;
}) {
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [lab, setLab] = useState<LabResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const repo = route.kind === "repo" ? (repos.find((r) => r.id === route.place) ?? null) : null;
  useEffect(() => {
    let live = true;
    setDetail(null);
    setError(null);
    setAsking(false);
    const got =
      route.kind === "repo"
        ? api.experimentOf(route.place, route.id).then((d) => ({ d, l: null as LabResult | null }))
        : api.labResult(route.place, route.id).then((d) => ({ d: d as ExperimentDetail, l: d as unknown as LabResult }));
    got.then(
      ({ d, l }) => {
        if (!live) return;
        setDetail(d);
        setLab(l);
      },
      (e) => live && setError(e instanceof ApiError ? e.message : String(e)),
    );
    return () => {
      live = false;
    };
  }, [route.kind, route.place, route.id]);

  const name = humanName(lab?.workflow ?? detail?.treatment_name ?? row?.what ?? `run ${route.id}`);
  const where = route.kind === "repo" ? (repo?.name ?? route.place) : (lab?.bench_name ?? row?.where ?? route.place);
  // Opening a run of the repo already open switches nothing: no question to ask.
  const switches = route.kind === "bench" || currentRepoId !== route.place;
  const open = () => {
    if (route.kind === "repo") onOpenRepo(route.place);
    else if (lab) onOpenLab(lab);
  };
  return (
    <section aria-label={`Run ${name} on ${where}`} data-testid="run-detail">
      <a className="linkish small" href="#/runs">
        <ArrowLeft size={14} aria-hidden="true" /> All runs
      </a>
      <h1 className="steppage__title">{name}</h1>
      <p className="steppage__lead muted">
        {route.kind === "repo" ? "Repo" : "Bench"} {where} · run #{route.id}. Read-only: nothing you have open changes.
      </p>
      {error ? (
        <p className="notice notice--error small" role="alert">
          {error}
        </p>
      ) : null}
      {route.kind === "repo" && !repo ? <p className="notice notice--warning small">That repo isn't in your workspace any more.</p> : null}
      <div className="row" style={{ gap: 8, margin: "8px 0" }}>
        {asking ? (
          <div className="card" role="alertdialog" aria-label="Open in Context">
            <strong>{route.kind === "repo" ? `Switch to ${where}?` : `Open ${name} in the Lab?`}</strong>
            <p className="small">
              {route.kind === "repo"
                ? "Your canvas stays saved: each repo keeps its own."
                : "It replaces the workflow on the Lab canvas; save that one to your library first if you want to keep it."}
            </p>
            <div className="row" style={{ gap: 8 }}>
              <button type="button" className="btn btn--primary btn--small" onClick={open}>
                {route.kind === "repo" ? `Switch to ${where}` : "Open in the Lab"}
              </button>
              <button type="button" className="btn btn--quiet btn--small" onClick={() => setAsking(false)}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="btn btn--small"
            disabled={(route.kind === "repo" && !repo) || (route.kind === "bench" && (!lab || !!lab.probe))}
            title={lab?.probe ? "A baseline check ran no workflow: there is nothing to open" : undefined}
            onClick={() => (switches ? setAsking(true) : open())}
          >
            Open in Context
          </button>
        )}
      </div>
      {detail ? (
        <>
          <Result detail={detail} />
          <Trials detail={detail} />
        </>
      ) : error ? null : (
        <p className="muted">Reading the run…</p>
      )}
    </section>
  );
}
