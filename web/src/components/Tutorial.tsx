import { ArrowLeft, ArrowRight, Bot, Check, FolderGit2, GraduationCap, House, Puzzle, Sparkles, X } from "lucide-react";
import { type ReactNode, useEffect } from "react";

import { pts } from "../lib/format";
import type { TourAt } from "../lib/route";
import { markTutorialDone, tutorialDone } from "../lib/tutorial";
import type { Tutorial, TutorialArm, TutorialRun, TutorialStep } from "../lib/types";
import { ArmRow } from "./Home";
import { Interval } from "./Interval";
import { type Step, STEPS } from "./Journey";
import { RigBadge, RigScore } from "./RigScore";

/** Home's tour slot: what the tutorial is, and the one button that starts it ("Replay" once
 * finished). Nothing starts without that click. */
export function TourEntry({ data, onStart }: { data: Tutorial; onStart: () => void }) {
  const t = data.text.home;
  const done = tutorialDone();
  return (
    <section className="home__card tourentry" aria-labelledby="tour-entry-title">
      <div className="tourentry__text">
        <div className="home__wayhead">
          <GraduationCap size={18} aria-hidden="true" />
          <h2 id="tour-entry-title">{done ? t.title_done : t.title}</h2>
        </div>
        <p className="small muted">{t.lead}</p>
      </div>
      <button type="button" className="btn tourentry__go" onClick={onStart}>
        {done ? t.replay : t.start} <ArrowRight size={14} aria-hidden="true" />
      </button>
    </section>
  );
}

/** Home's proof slot: the recorded run, in place of the illustration. Real numbers, said so. */
export function RecordedProof({ data, run }: { data: Tutorial; run: TutorialRun }) {
  const t = data.text.proof;
  const caption = t.caption;
  return (
    <figure className="home__proof" aria-labelledby="home-proof-cap" data-testid="recorded-proof">
      <figcaption id="home-proof-cap" className="home__proofcap small muted">
        <span className="pill pill--positive home__illus">{t.pill}</span> {caption}
      </figcaption>
      <ArmRow label={t.without} won={run.without} n={run.n} />
      <ArmRow label={t.with} won={run.with} n={run.n} accent />
      <div className="home__delta">
        <span className="home__deltanum num">
          {pts(run.diff ?? 0, 0).replace(" pts", "")}
          <span className="home__deltaunit"> pts</span>
        </span>
        {run.ci_low != null && run.ci_high != null ? (
          <span className="small muted num">
            95% interval {pts(run.ci_low, 0).replace(" pts", "")} to {pts(run.ci_high, 0)}
          </span>
        ) : null}
        {run.rig.score != null ? (
          <span className="home__proofrig">
            <RigBadge score={run.rig.score} tone={run.rig.tone} provisional={run.rig.provisional} label={run.rig.label} />
          </span>
        ) : null}
      </div>
      {run.ci_low != null && run.ci_high != null ? <Interval low={run.ci_low} high={run.ci_high} diff={run.diff ?? 0} verdict={run.verdict} /> : null}
    </figure>
  );
}

const ORDER: TourAt[] = [1, 2, 3, 4, 5, "done"];

/** #/tutorial/…: the five steps on the example, then where to go next. It reads only the example
 * (GET /api/tutorial) and keeps only its own "finished" flag. */
export function TutorialPage({
  data,
  error,
  at,
  onAt,
  onOption,
}: {
  data: Tutorial | null;
  /** Why the example couldn't be read, if it couldn't. */
  error?: string | null;
  at: TourAt;
  onAt: (at: TourAt) => void;
  /** A finish option: step 1 in a repo or the Lab, or Home. */
  onOption: (to: "repo" | "lab" | "home") => void;
}) {
  useEffect(() => {
    if (at === "done") markTutorialDone();
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
  const i = ORDER.indexOf(at);
  const next = ORDER[i + 1];
  return (
    <main className="steppage tour" id="main" data-tour-step={s.id}>
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
          <p className="tour__lead">{s.lead}</p>
        </header>
        <div className="tour__body">
          <StepBody data={data} step={s} />
        </div>
        <p className="small muted tour__note">{s.note}</p>
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

/** The tutorial's own steps: a small path of its own, never the top bar's. */
export function TourSteps({ label, at, onAt }: { label: string; at: Step; onAt: (at: TourAt) => void }) {
  return (
    <ol className="tour__steps" aria-label={label}>
      {STEPS.map((s) => {
        const current = s.n === at;
        const done = s.n < at;
        return (
          <li key={s.n}>
            <button
              type="button"
              className={`tour__step${current ? " is-current" : done ? " is-done" : ""}`}
              aria-current={current ? "step" : undefined}
              aria-label={`${s.n}. ${s.label}${done ? " (seen)" : ""}`}
              onClick={() => onAt(s.n)}
            >
              <span className="tour__stepn num" aria-hidden="true">
                {done ? <Check size={11} /> : s.n}
              </span>
              <span className="tour__steplabel">{s.label}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

export function Code({ path, text, label }: { path: string; text: string; label?: string }) {
  return (
    <figure className="tour__code">
      <figcaption className="tour__codepath num">{label ?? path}</figcaption>
      <pre tabIndex={0} aria-label={label ?? path}>
        <code>{text}</code>
      </pre>
    </figure>
  );
}

export function Card({ icon, title, children }: { icon?: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="tour__card" aria-label={title}>
      <div className="tour__cardhead">
        {icon}
        <h2 className="tour__h">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function StepBody({ data, step }: { data: Tutorial; step: TutorialStep }) {
  const ex = data.example;
  const run = data.run;
  switch (step.id) {
    case "describe": {
      const code = ex.files.find((f) => f.path.endsWith("tags.py")) ?? ex.files[0];
      return (
        <div className="tour__grid">
          <Card icon={<FolderGit2 size={16} aria-hidden="true" />} title={step.goal_title as string}>
            <p className="tour__goal">{step.goal as string}</p>
            <p className="small muted">{step.repo as string}</p>
            <ul className="tour__files small num">
              {ex.files.map((f) => (
                <li key={f.path}>{f.path}</li>
              ))}
              <li>{step.tasks_line as string}</li>
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
            <Card icon={<Bot size={16} aria-hidden="true" />} title={step.car as string}>
              <p className="small">{step.car_text as string}</p>
            </Card>
            <Card icon={<Puzzle size={16} aria-hidden="true" />} title={step.part as string}>
              <p className="small">{step.part_text as string}</p>
              <p className="small muted">{ex.skill.description}</p>
            </Card>
          </div>
          <figure className="tour__code">
            <figcaption className="tour__codepath num">{ex.skill.path}</figcaption>
            <div className="tour__md" tabIndex={0} role="region" aria-label={ex.skill.path}>
              <Markdown text={ex.skill.body} />
            </div>
          </figure>
        </div>
      );
    case "build": {
      const shown = ex.tasks.find((t) => t.id === "refund") ?? ex.tasks[0];
      return (
        <div className="tour__grid">
          <ol className="tour__tasks" aria-label={step.tasks_title as string}>
            {ex.tasks.map((t) => (
              <li key={t.id}>
                <b>{t.title}</b>
                <span className="small muted">{inline(t.instruction)}</span>
              </li>
            ))}
          </ol>
          <Code path={`.proving-ground/scenarios/${shown.id}.yaml`} label={`${step.check_title as string}: ${shown.title}`} text={shown.check} />
        </div>
      );
    }
    case "measure":
      return run ? <Measured data={data} run={run} step={step} /> : <p className="muted">No run recorded yet.</p>;
    case "ship":
      return (
        <div className="tour__grid">
          <Card icon={<Sparkles size={16} aria-hidden="true" />} title={step.brief_title as string}>
            <ul className="tour__brief">
              {(step.brief as string[]).map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </Card>
          {run ? (
            <Card title={step.result_title as string}>
              <ArmRow label={data.text.proof.without} won={run.without} n={run.n} />
              <ArmRow label={data.text.proof.with} won={run.with} n={run.n} accent />
              <div className="home__delta">
                {run.rig.score != null ? <RigBadge score={run.rig.score} tone={run.rig.tone} provisional={run.rig.provisional} label={run.rig.label} /> : null}
                <span className="small">{run.rig.label}</span>
              </div>
            </Card>
          ) : null}
        </div>
      );
  }
}

export function Outcome({ arm, words }: { arm: TutorialArm; words: Record<string, string> }) {
  const ok = arm.trials > 0 && arm.passed === arm.trials;
  // One trial: what happened to it (passed, failed, timed out, errored). Several: how many passed.
  const why = (i: number) =>
    arm.outcomes[i] === "pass"
      ? words.passed
      : arm.details[i]?.startsWith("timed out")
        ? words.timed_out
        : arm.outcomes[i] === "errored" || arm.outcomes[i] === "broken"
          ? words.errored
          : words.failed;
  const word = arm.trials === 1 ? why(0) : `${arm.passed} of ${arm.trials} ${words.passed}`;
  return (
    <span className={`tour__outcome${ok ? " is-pass" : " is-fail"}`}>
      {ok ? <Check size={14} aria-hidden="true" /> : <X size={14} aria-hidden="true" />}
      {word}
    </span>
  );
}

function Measured({ data, run, step }: { data: Tutorial; run: TutorialRun; step: TutorialStep }) {
  const s = step as TutorialStep & Record<string, string>;
  return (
    <div className="tour__measure">
      <div className="tour__tablewrap">
        <table className="tour__table">
          <caption className="visually-hidden">Each task, without and with the skill</caption>
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
                  <Outcome arm={t.without} words={s} />
                </td>
                <td>
                  <Outcome arm={t.with} words={s} />
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
        <p className="small tour__rows">{s.rows}</p>
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
        <Card title={s.interval_title}>
          <div className="home__delta tour__delta">
            <span className="home__deltanum num">
              {pts(run.diff ?? 0, 0).replace(" pts", "")}
              <span className="home__deltaunit"> pts</span>
            </span>
            {run.ci_low != null && run.ci_high != null ? (
              <span className="small muted num">
                95% interval {pts(run.ci_low, 0).replace(" pts", "")} to {pts(run.ci_high, 0)}
              </span>
            ) : null}
          </div>
          {run.ci_low != null && run.ci_high != null ? <Interval low={run.ci_low} high={run.ci_high} diff={run.diff ?? 0} verdict={run.verdict} /> : null}
        </Card>
        <RigScore rig={run.rig} name={s.score_title} />
      </div>
    </div>
  );
}

const OPTION_ICON = { repo: FolderGit2, lab: Sparkles, home: House } as const;

function Finish({ data, onOption, onBack }: { data: Tutorial; onOption: (to: "repo" | "lab" | "home") => void; onBack: () => void }) {
  const f = data.text.finish;
  return (
    <main className="steppage tour" id="main" data-tour-step="done">
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

/** Just enough Markdown for a SKILL.md: headings, paragraphs and lists (wrapped lines joined),
 * `code` and **bold**. No HTML is ever read from the text. */
export function Markdown({ text }: { text: string }) {
  const blocks: { kind: "h1" | "h2" | "p" | "ul"; lines: string[] }[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const last = blocks[blocks.length - 1];
    if (!line.trim()) {
      blocks.push({ kind: "p", lines: [] });
    } else if (line.startsWith("## ")) {
      blocks.push({ kind: "h2", lines: [line.slice(3)] });
    } else if (line.startsWith("# ")) {
      blocks.push({ kind: "h1", lines: [line.slice(2)] });
    } else if (line.startsWith("- ")) {
      if (last?.kind === "ul") last.lines.push(line.slice(2));
      else blocks.push({ kind: "ul", lines: [line.slice(2)] });
    } else if (last?.kind === "ul" && raw.startsWith("  ")) {
      last.lines[last.lines.length - 1] += ` ${line.trim()}`;
    } else if (last?.kind === "p") {
      last.lines.push(line.trim());
    } else {
      blocks.push({ kind: "p", lines: [line.trim()] });
    }
  }
  return (
    <>
      {blocks
        .filter((b) => b.lines.length)
        .map((b, i) =>
          b.kind === "ul" ? (
            <ul key={i}>
              {b.lines.map((l) => (
                <li key={l}>{inline(l)}</li>
              ))}
            </ul>
          ) : b.kind === "h1" ? (
            <h3 key={i}>{inline(b.lines[0])}</h3>
          ) : b.kind === "h2" ? (
            <h4 key={i}>{inline(b.lines[0])}</h4>
          ) : (
            <p key={i}>{inline(b.lines.join(" "))}</p>
          ),
        )}
    </>
  );
}

export function inline(text: string): ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/).map((part, i) =>
    part.startsWith("`") && part.endsWith("`") && part.length > 1 ? (
      <code key={i}>{part.slice(1, -1)}</code>
    ) : part.startsWith("**") && part.endsWith("**") && part.length > 3 ? (
      <b key={i}>{part.slice(2, -2)}</b>
    ) : (
      part
    ),
  );
}
