import { ArrowRight, FolderGit2, Sparkles } from "lucide-react";
import { Fragment, type ReactNode, useEffect, useState } from "react";

import { api } from "../lib/api";
import { humanName, verdictWord } from "../lib/evidence";
import { pts } from "../lib/format";
import { exampleVerdict, useRigExplain, weightPct } from "../lib/rigExplain";
import type { RepoRef, RigExplain, RigScore, Verdict } from "../lib/types";
import { Interval } from "./Interval";
import { WeightBar } from "./RigExplain";
import { RigBadge } from "./RigScore";
import { runHref } from "./Runs";

/** Where a returning visit left off: "Step 3 · Build", and in which repo or workflow. */
export interface Resume {
  label: string;
  where: string;
}

type Recent = { key: string; href: string; what: string; where: string; date: string; id: number; rig: RigScore | null; verdict: string | null; status: string };

const RECENT_MAX = 5;

/** The newest runs across every repo and the Lab: the same lists the Runs page reads. */
function useRecentRuns(repos: RepoRef[]): Recent[] | null {
  const [rows, setRows] = useState<Recent[] | null>(null);
  const ids = repos.map((r) => r.id).join(",");
  useEffect(() => {
    let live = true;
    void Promise.allSettled([api.labResults(), ...repos.map((r) => api.experimentsOf(r.id).then((list) => ({ r, list })))]).then((got) => {
      if (!live) return;
      const out: Recent[] = [];
      const [lab, ...byRepo] = got;
      if (lab.status === "fulfilled")
        for (const x of lab.value as Awaited<ReturnType<typeof api.labResults>>)
          out.push({ key: `bench:${x.bench}:${x.id}`, href: runHref("bench", x.bench, x.id), what: x.workflow, where: `bench ${x.bench_name}`, date: x.date ?? "", id: x.id, rig: x.rig ?? null, verdict: x.verdict, status: x.status });
      for (const g of byRepo) {
        if (g.status !== "fulfilled") continue;
        const { r, list } = g.value as { r: RepoRef; list: Awaited<ReturnType<typeof api.experimentsOf>> };
        for (const e of list)
          out.push({ key: `repo:${r.id}:${e.id}`, href: runHref("repo", r.id, e.id), what: e.treatment_name, where: `repo ${r.name}`, date: e.created_at.slice(0, 10), id: e.id, rig: e.rig ?? null, verdict: e.verdict ?? null, status: e.status });
      }
      out.sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id || a.key.localeCompare(b.key));
      setRows(out.slice(0, RECENT_MAX));
    });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids]);
  return rows;
}

/** #/home: what Rig is, the two ways in, where you left off, recent runs, and the Rig score. */
export function Home({
  repos,
  resume,
  onStart,
  onResume,
  onOpenRepo,
  tour,
  proof,
}: {
  repos: RepoRef[];
  /** A returning visit's last step; null on a first visit. */
  resume: Resume | null;
  /** Rig a Repo ("repo") or Rig a Workflow ("lab"): step 1 in that mode. */
  onStart: (space: "repo" | "lab") => void;
  onResume: () => void;
  /** An attached repo, opened on step 1. */
  onOpenRepo: (id: string) => void;
  /** A slot for the tutorial's entry (its Start button); nothing is shown without it. */
  tour?: ReactNode;
  /** In place of the illustration beside the headline: a real recorded run, when one ships. */
  proof?: ReactNode;
}) {
  const recent = useRecentRuns(repos);
  const { data: rig } = useRigExplain();
  return (
    <main className="steppage home" id="main">
      <div className="home__inner">
        <section className="home__hero" aria-labelledby="home-title">
          <div className="home__thesis">
            <div className="steppage__eyebrow">A garage for AI agent architectures</div>
            <h1 id="home-title" className="home__title" tabIndex={-1} data-page-title>
              Swap One Part. Rerun With and Without. See What It Changed.
            </h1>
            <p className="home__lead muted">
              Your architecture is the car. A skill, a step, a model, a loop, a hook, an MCP server or a CLAUDE.md rule is a part. Rig
              runs the same tasks with and without the change, each in its own sandbox, and shows what it really changed, with a
              confidence interval.
            </p>
          </div>
          {proof ?? (rig ? <ProofIllustration example={rig.example} verdict={exampleVerdict(rig)} /> : null)}
        </section>

        {resume ? (
          <div className="home__resume" role="group" aria-label="Where you left off">
            <span className="small">
              <b>Where you left off:</b> {resume.label} <span className="muted">· {resume.where}</span>
            </span>
            <button type="button" className="btn btn--primary" onClick={onResume}>
              Continue: {resume.label} <ArrowRight size={14} aria-hidden="true" />
            </button>
          </div>
        ) : null}

        <section className="home__ways" aria-label="Start">
          <div className="home__way">
            <div className="home__wayhead">
              <FolderGit2 size={18} aria-hidden="true" />
              <h2>Rig a Repo</h2>
            </div>
            <p className="small muted">On your own code. Rig maps the architecture, suggests what would help, writes test tasks, and measures each change.</p>
            {repos.length ? (
              <ul className="home__repos" aria-label="Attached repos">
                {repos.slice(0, 4).map((r) => (
                  <li key={r.id}>
                    <button type="button" className="home__repo" onClick={() => onOpenRepo(r.id)} title={r.root} aria-label={`Open ${r.name}`}>
                      <FolderGit2 size={13} aria-hidden="true" />
                      <span>{r.name}</span>
                    </button>
                  </li>
                ))}
                {repos.length > 4 ? <li className="small muted">+{repos.length - 4} more</li> : null}
              </ul>
            ) : null}
            <button type="button" className={`btn${resume ? "" : " btn--primary"} home__go`} onClick={() => onStart("repo")}>
              {repos.length ? "Rig a Repo" : "Add a Repo"} <ArrowRight size={14} aria-hidden="true" />
            </button>
          </div>
          <div className="home__way">
            <div className="home__wayhead">
              <Sparkles size={18} aria-hidden="true" />
              <h2>Rig a Workflow</h2>
            </div>
            <p className="small muted">
              No repo needed. Build or pick a workflow (starters, business processes, agentic patterns, or your own) and measure it on
              built-in benches, imported eval suites, or a bench made for it.
            </p>
            <button type="button" className={`btn${resume ? "" : " btn--primary"} home__go`} onClick={() => onStart("lab")}>
              Rig a Workflow <ArrowRight size={14} aria-hidden="true" />
            </button>
          </div>
        </section>

        {tour ? (
          <div className="home__tour" data-slot="tour">
            {tour}
          </div>
        ) : null}

        <div className="home__more">
          <section className="home__card" aria-labelledby="home-runs">
            <div className="row row--between">
              <h2 id="home-runs" className="home__h">
                Recent Runs
              </h2>
              <a className="small home__link" href="#/runs">
                All Runs
              </a>
            </div>
            {recent === null ? (
              <p className="small muted">Reading runs…</p>
            ) : recent.length ? (
              <ul className="home__runs">
                {recent.map((r) => {
                  const v = verdictWord(r.rig, r.verdict);
                  return (
                    <li key={r.key}>
                      <a href={r.href} className="home__run">
                        <span className="home__runname" title={r.what}>
                          {humanName(r.what)}
                        </span>
                        <span className="small muted home__runwhere">
                          {r.where} · <span className="num">{r.date}</span>
                        </span>
                      </a>
                      <span className="home__runout">
                        {r.status === "running" ? (
                          <span className="pill pill--warning">Running</span>
                        ) : r.rig?.score != null ? (
                          <RigBadge score={r.rig.score} tone={r.rig.tone} provisional={r.rig.provisional} label={r.rig.label} />
                        ) : (
                          <span className="small muted">{v.word}</span>
                        )}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="small muted">No runs yet. Measure a change in step 4 and it shows here.</p>
            )}
          </section>

          <section className="home__card" aria-labelledby="home-rig">
            <h2 id="home-rig" className="home__h">
              The Rig Score
            </h2>
            <p className="small muted">
              One number from 0 to 100 for whether a change works, made from five measured parts and capped when the evidence is thin.
            </p>
            {rig ? <WeightBar parts={rig.parts} labelled={false} /> : null}
            {rig ? (
              <p className="small muted num home__weights">
                {rig.parts.map((p, i) => (
                  <Fragment key={p.id}>
                    {i ? " · " : ""}
                    <span className="home__weight">
                      {p.name} {weightPct(p.weight)}
                    </span>
                  </Fragment>
                ))}
              </p>
            ) : null}
            <a className="btn home__go" href="#/rig-score">
              How the Rig Score Works <ArrowRight size={14} aria-hidden="true" />
            </a>
          </section>
        </div>
      </div>
    </main>
  );
}

/** The idea, drawn: the same tasks without and with one change, and what it changed with its 95%
 * interval. Made-up numbers (the Rig score explainer's worked example), labelled as such. */
export function ProofIllustration({ example, verdict }: { example: RigExplain["example"]; verdict: Verdict }) {
  const ex = example.evidence;
  return (
    <figure className="home__proof" aria-labelledby="home-proof-cap">
      <figcaption id="home-proof-cap" className="home__proofcap small muted">
        <span className="pill home__illus">Illustration, Not a Real Run</span> {example.title}
      </figcaption>
      <ArmRow label="Without" won={Math.round(ex.pass_without * ex.n_pairs)} n={ex.n_pairs} />
      <ArmRow label="With the change" won={Math.round(ex.pass_with * ex.n_pairs)} n={ex.n_pairs} accent />
      <div className="home__delta">
        <span className="home__deltanum num">
          {pts(ex.diff, 0).replace(" pts", "")}
          <span className="home__deltaunit"> pts</span>
        </span>
        <span className="small muted num">
          95% interval {pts(ex.ci_low, 0).replace(" pts", "")} to {pts(ex.ci_high, 0)}
        </span>
      </div>
      <Interval low={ex.ci_low} high={ex.ci_high} diff={ex.diff} verdict={verdict} />
    </figure>
  );
}

/** One arm of a run as a bar: "8 of 16 passed". */
export function ArmRow({ label, won, n, accent }: { label: string; won: number; n: number; accent?: boolean }) {
  return (
    <div className="home__arm">
      <span className="small">{label}</span>
      <span className="home__armtrack" aria-hidden="true">
        <span className={`home__armfill${accent ? " is-with" : ""}`} style={{ transform: `scaleX(${n ? won / n : 0})` }} />
      </span>
      <span className="small num">
        {won} of {n} passed
      </span>
    </div>
  );
}
