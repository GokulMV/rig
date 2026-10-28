import { ArrowLeft, ArrowRight, Bot, FolderGit2, GraduationCap, House, Puzzle, Sparkles } from "lucide-react";
import { useEffect } from "react";

import type { TourAt } from "../lib/route";
import { markTutorialDone, TOKENS_TOUR_DONE_KEY, tutorialDone, useTokensTutorial } from "../lib/tutorial";
import type { TokensTourPlace, TokensTourStep, TokensTutorial, TokensTutorialArm, TokensTutorialRun } from "../lib/types";
import { ArmRow } from "./Home";
import { type Step, STEPS } from "./Journey";
import { MetricHeadline } from "./Results";
import { RigBadge, RigScore } from "./RigScore";
import { Card, Code, inline, Markdown, Outcome, TourSteps } from "./Tutorial";

/** Home's second tutorial entry, under the first: Rig your own repo for fewer tokens. Nothing
 * starts without its click. */
export function TokensTourEntry({ data, onStart }: { data: TokensTutorial; onStart: () => void }) {
  const t = data.text.home;
  const done = tutorialDone(TOKENS_TOUR_DONE_KEY);
  return (
    <section className="home__card tourentry tourentry--second" aria-labelledby="tour-tokens-title">
      <div className="tourentry__text">
        <div className="home__wayhead">
          <FolderGit2 size={18} aria-hidden="true" />
          <h2 id="tour-tokens-title">{done ? t.title_done : t.title}</h2>
        </div>
        <p className="small muted">{t.lead}</p>
      </div>
      <button type="button" className="btn btn--quiet tourentry__go" onClick={onStart}>
        {done ? t.replay : t.start} <ArrowRight size={14} aria-hidden="true" />
      </button>
    </section>
  );
}

/** Home's slot for it: reads the track itself, so its arrival re-renders only this entry, never
 * the app (and the Lab mounted behind every page). Nothing until it is read. */
export function TokensTourSlot({ onStart }: { onStart: () => void }) {
  const { data } = useTokensTutorial();
  return data ? <TokensTourEntry data={data} onStart={onStart} /> : null;
}

/** #/tutorial/tokens/…, reading the track itself the same way. */
export function TokensTutorialRoute(props: Omit<Parameters<typeof TokensTutorialPage>[0], "data" | "error">) {
  const { data, error } = useTokensTutorial();
  return <TokensTutorialPage data={data} error={error} {...props} />;
}

const ORDER: TourAt[] = [1, 2, 3, 4, 5, "done"];

/** #/tutorial/tokens/…: the five steps in repo mode on the textkit example, each with what to do
 * on your own repo, then where to go next. It reads only GET /api/tutorial/tokens and keeps only
 * its own "finished" flag. */
export function TokensTutorialPage({
  data,
  error,
  at,
  onAt,
  onOption,
}: {
  data: TokensTutorial | null;
  error?: string | null;
  at: TourAt;
  onAt: (at: TourAt) => void;
  /** A finish option: step 1 in a repo, the first tutorial, or Home. */
  onOption: (to: "repo" | "first" | "home") => void;
}) {
  useEffect(() => {
    if (at === "done") markTutorialDone(TOKENS_TOUR_DONE_KEY);
  }, [at]);
  if (!data) {
    return (
      <main className="steppage tour" id="main">
        {error ? <p className="notice notice--error">Couldn't read the tutorial's example: {error}</p> : <p className="muted">Reading the example…</p>}
      </main>
    );
  }
  if (at === "done") return <Finish data={data} onOption={onOption} onBack={() => onAt(5)} />;
  const s = data.text.steps[at - 1];
  const next = ORDER[ORDER.indexOf(at) + 1];
  return (
    <main className="steppage tour" id="main" data-tour-step={s.id} data-tour-track="tokens">
      <div className="tour__inner">
        <div className="tour__bar">
          <TourSteps label={data.text.stepper} at={at} onAt={onAt} />
          <a className="small tour__leave" href="#/home">
            {data.text.leave}
          </a>
        </div>
        <header className="tour__head">
          <div className="steppage__eyebrow">{data.text.eyebrow.replace("{step}", String(at))}</div>
          <h1 className="tour__title" tabIndex={-1} data-page-title>
            {s.title}
          </h1>
          <p className="tour__lead">{data.run || (s.id !== "measure" && s.id !== "ship") ? s.lead : data.text.not_recorded}</p>
        </header>
        <div className="tour__body">
          <StepBody data={data} step={s} />
        </div>
        <Yours title={data.text.yours_title} items={s.yours} />
        <p className="small muted tour__note">{s.id === "ship" && !data.run ? "" : s.note}</p>
        <nav className="tour__nav" aria-label="Tutorial">
          {at > 1 ? (
            <button type="button" className="btn btn--quiet" onClick={() => onAt((at - 1) as Step)}>
              <ArrowLeft size={14} aria-hidden="true" /> Back
            </button>
          ) : (
            <span />
          )}
          <button type="button" className="btn btn--primary" onClick={() => onAt(next)}>
            {next === "done" ? "Finish" : `Next: ${STEPS[(next as Step) - 1].label}`} <ArrowRight size={14} aria-hidden="true" />
          </button>
        </nav>
      </div>
    </main>
  );
}

/** What to do on your own repo at this step, in order: the point of this track. */
function Yours({ title, items, label }: { title: string; items: string[]; label?: string }) {
  return (
    <section className="tour__yours" aria-label={label ?? title}>
      <div className="tour__cardhead">
        <FolderGit2 size={16} aria-hidden="true" />
        <h2 className="tour__h">{label ?? title}</h2>
      </div>
      <ol>
        {items.map((x) => (
          <li key={x}>{inline(x)}</li>
        ))}
      </ol>
    </section>
  );
}

function StepBody({ data, step }: { data: TokensTutorial; step: TokensTourStep }) {
  const ex = data.example;
  const run = data.run;
  const s = step as TokensTourStep & Record<string, string>;
  switch (step.id) {
    case "describe": {
      const code = ex.files.find((f) => f.path.endsWith("case.py")) ?? ex.files[0];
      return (
        <div className="tour__grid">
          <Card icon={<FolderGit2 size={16} aria-hidden="true" />} title={s.goal_title}>
            <p className="tour__goal">{s.goal}</p>
            <p className="small">{s.template}</p>
            <p className="small muted">{s.repo}</p>
            <ul className="tour__files small num">
              {ex.files.map((f) => (
                <li key={f.path}>{f.path}</li>
              ))}
              <li>{s.tasks_line}</li>
            </ul>
          </Card>
          <Code path={code.path} text={code.text} />
        </div>
      );
    }
    case "design":
      return (
        <div className="tour__grid">
          <div className="tour__stack">
            <Card icon={<Bot size={16} aria-hidden="true" />} title={s.car}>
              <p className="small">{s.car_text}</p>
            </Card>
            <Card icon={<Puzzle size={16} aria-hidden="true" />} title={s.part}>
              <p className="small">{s.part_text}</p>
              <p className="small muted">{ex.skill.description}</p>
            </Card>
          </div>
          <SkillFile data={data} />
        </div>
      );
    case "build":
      return (
        <div className="tour__grid">
          <Card title={s.places_title}>
            <ul className="tour__places">
              {(step.places as unknown as TokensTourPlace[]).map((p) => (
                <li key={p.what}>
                  <span className="tour__placewhat">
                    <b>{p.what}</b>
                    <span className="small muted">{p.where}</span>
                  </span>
                  <span className={`mbadge mbadge--${p.tone}`}>{p.badge}</span>
                </li>
              ))}
            </ul>
          </Card>
          <SkillFile data={data} />
        </div>
      );
    case "measure": {
      const shown = ex.tasks.find((t) => t.id === "line-count") ?? ex.tasks[0];
      return (
        <div className="tour__stack">
          <h2 className="tour__sub">{s.tasks_heading}</h2>
          <p className="small">{s.tasks_lead}</p>
          <div className="tour__grid">
            <ol className="tour__tasks" aria-label={s.tasks_title}>
              {ex.tasks.map((t) => (
                <li key={t.id}>
                  <b>{t.title}</b>
                  <span className="small muted">{inline(t.instruction)}</span>
                </li>
              ))}
            </ol>
            <Code path={`.proving-ground/scenarios/${shown.id}.yaml`} label={`${s.check_title}: ${shown.title}`} text={shown.check} />
          </div>
          <Yours title={data.text.yours_title} label={`${data.text.yours_title}: ${s.tasks_heading}`} items={step.tasks_yours as string[]} />
          <h2 className="tour__sub">{s.run_heading}</h2>
          {run ? <Measured data={data} run={run} step={s} /> : <p className="notice small">{data.text.not_recorded}</p>}
        </div>
      );
    }
    case "ship":
      if (!run) return <p className="notice small">{data.text.not_recorded}</p>;
      return (
        <div className="tour__grid">
          <Card icon={<Sparkles size={16} aria-hidden="true" />} title={s.brief_title}>
            <ul className="tour__brief">
              {(step.brief as string[]).map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </Card>
          <Card title={s.result_title}>
            {run.metric ? <MetricHeadline m={run.metric} /> : null}
            <ArmRow label={s.without_arm} won={run.without} n={run.n} />
            <ArmRow label={s.with_arm} won={run.with} n={run.n} accent />
            <div className="home__delta">
              {run.rig.score != null ? <RigBadge score={run.rig.score} tone={run.rig.tone} provisional={run.rig.provisional} label={run.rig.label} /> : null}
              <span className="small">{run.rig.label}</span>
            </div>
          </Card>
        </div>
      );
  }
}

function SkillFile({ data }: { data: TokensTutorial }) {
  const sk = data.example.skill;
  return (
    <figure className="tour__code">
      <figcaption className="tour__codepath num">{sk.path}</figcaption>
      <div className="tour__md" tabIndex={0} role="region" aria-label={sk.path}>
        <Markdown text={sk.body} />
      </div>
    </figure>
  );
}

/** The middle of a list of numbers (the median), in thousands: "34.7k". */
function medianK(xs: number[]): string {
  if (!xs.length) return "—";
  const a = [...xs].sort((x, y) => x - y);
  const m = a.length % 2 ? a[(a.length - 1) / 2] : (a[a.length / 2 - 1] + a[a.length / 2]) / 2;
  return m >= 1000 ? `${(m / 1000).toFixed(1)}k` : String(Math.round(m));
}

function Cell({ arm, words }: { arm: TokensTutorialArm; words: Record<string, string> }) {
  return (
    <>
      <Outcome arm={arm} words={words} />
      <span className="small muted num tour__tok">
        {medianK(arm.tokens)} {words.tokens}
      </span>
    </>
  );
}

function Measured({ data, run, step }: { data: TokensTutorial; run: TokensTutorialRun; step: Record<string, string> }) {
  const s = step;
  return (
    <div className="tour__measure">
      <div className="tour__tablewrap">
        <table className="tour__table">
          <caption className="visually-hidden">Each task, without and with the skill: how many passed, and the {s.per_trial}</caption>
          <thead>
            <tr>
              <th scope="col">{s.task}</th>
              <th scope="col">{s.without}</th>
              <th scope="col">{s.with}</th>
            </tr>
          </thead>
          <tbody>
            {run.tasks.map((t) => (
              <tr key={t.id}>
                <th scope="row">{t.title}</th>
                <td>
                  <Cell arm={t.without} words={s} />
                </td>
                <td>
                  <Cell arm={t.with} words={s} />
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">{s.total}</th>
              <td className="num">
                {run.without} of {run.n}
              </td>
              <td className="num">
                {run.with} of {run.n}
              </td>
            </tr>
          </tfoot>
        </table>
        <p className="small muted">{s.tokens_note}</p>
        <p className="small muted tour__recorded">{data.text.recorded_note}</p>
        <details className="tour__settings small">
          <summary>{data.text.settings_title}</summary>
          <ul>
            {data.text.settings.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </details>
        {run.stale ? <p className="notice notice--warning small">{data.text.stale}</p> : null}
      </div>
      <div className="tour__stack">
        {run.metric ? (
          <section className="tour__card" aria-label={s.metric_title}>
            <MetricHeadline m={run.metric} />
          </section>
        ) : null}
        <RigScore rig={run.rig} name={s.score_title} />
      </div>
    </div>
  );
}

const OPTION_ICON = { repo: FolderGit2, first: GraduationCap, home: House } as const;

function Finish({ data, onOption, onBack }: { data: TokensTutorial; onOption: (to: "repo" | "first" | "home") => void; onBack: () => void }) {
  const f = data.text.finish;
  return (
    <main className="steppage tour" id="main" data-tour-step="done" data-tour-track="tokens">
      <div className="tour__inner">
        <header className="tour__head">
          <div className="steppage__eyebrow">{f.eyebrow}</div>
          <h1 className="tour__title" tabIndex={-1} data-page-title>
            {f.title}
          </h1>
          <p className="tour__lead">{f.lead}</p>
        </header>
        <ul className="tour__options" aria-label="Where next">
          {f.options.map((o) => {
            const Icon = OPTION_ICON[o.to];
            return (
              <li key={o.id}>
                <button type="button" className={`tour__option${o.to === "repo" ? " is-primary" : ""}`} onClick={() => onOption(o.to)}>
                  <Icon size={18} aria-hidden="true" />
                  <span className="tour__optionlabel">{o.label}</span>
                  <span className="small muted">{o.text}</span>
                </button>
              </li>
            );
          })}
        </ul>
        <nav className="tour__nav" aria-label="Tutorial">
          <button type="button" className="btn btn--quiet" onClick={onBack}>
            <ArrowLeft size={14} aria-hidden="true" /> Back
          </button>
        </nav>
      </div>
    </main>
  );
}
