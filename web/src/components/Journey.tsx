import {
  ArrowLeft,
  ArrowRight,
  Check,
  FolderGit2,
  Gauge,
  Hammer,
  History,
  House,
  LayoutTemplate,
  type LucideIcon,
  MoreHorizontal,
  PenLine,
  Rocket,
  Sparkles,
} from "lucide-react";
import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react";

import { goalHeading } from "../lib/format";
import type { GoalRules, RepoRef } from "../lib/types";
import { ProviderIcon } from "./RemoteRepo";

export type Step = 1 | 2 | 3 | 4 | 5;
/** One name per step, the same on the guided path and as workspace tabs. */
export const STEPS: { n: Step; label: string; hint: string; icon: LucideIcon }[] = [
  { n: 1, label: "Describe", hint: "What you're building, and where it lives", icon: PenLine },
  { n: 2, label: "Design", hint: "Keep your design, or start from an architecture ranked for your goal", icon: LayoutTemplate },
  { n: 3, label: "Build", hint: "Add, remove and connect skills, agents, tools", icon: Hammer },
  { n: 4, label: "Measure", hint: "Run it on tasks, with and without each change", icon: Gauge },
  { n: 5, label: "Ship", hint: "A build brief any coding agent can follow", icon: Rocket },
];

/** "Step 2 of 5 · Design": where you are on the guided path. */
export function stepName(n: Step): string {
  return `Step ${n} of 5 · ${STEPS[n - 1].label}`;
}

/** The guided path (numbered steps, Back and Next) or, after a first full pass, a workspace of tabs. */
export const Guide = createContext<{ workspace: boolean; onSkip?: () => void }>({ workspace: false });

/** Each step's own link: #/describe, #/design, #/build, #/measure, #/ship. */
export const STEP_SLUG: Record<Step, string> = { 1: "describe", 2: "design", 3: "build", 4: "measure", 5: "ship" };

/** Pages off the step path that the bar can mark as current. */
export type OffPath = "home" | "runs" | "compare" | "score" | "tutorial";

/** Home in the bar: a link, so it is never counted among the steps. */
function HomeLink({ current }: { current: boolean }) {
  return (
    <li className="stepbar__home">
      <a href="#/home" className={`stepbar__homelink${current ? " is-current" : ""}`} aria-current={current ? "page" : undefined} title="What Rig is, where you left off, recent runs">
        <House size={15} aria-hidden="true" />
        <span className="stepbar__homelabel">Home</span>
      </a>
    </li>
  );
}

/** The path through the app: numbered steps while guided, plain tabs once it's a workspace. */
export function StepBar({
  step,
  onStep,
  reached,
  page,
  onRuns,
}: {
  /** null while a page off the path (Home, Runs, the Rig score) is open. */
  step: Step | null;
  onStep: (s: Step) => void;
  /** The furthest step reached: the ones before it are ticked, whatever the current one is. */
  reached: number;
  page?: OffPath | null;
  onRuns?: () => void;
}) {
  const { workspace } = useContext(Guide);
  if (workspace) {
    return (
      <nav className="stepbar stepbar--tabs" aria-label="Workspace">
        <ol>
          <HomeLink current={page === "home"} />
          {STEPS.map((s) => (
            <li key={s.n}>
              <button
                type="button"
                className={`stepbar__tab${s.n === step && !page ? " is-current" : ""}`}
                aria-current={s.n === step && !page ? "page" : undefined}
                title={s.hint}
                onClick={() => onStep(s.n)}
              >
                <s.icon size={15} aria-hidden="true" />
                {s.label}
              </button>
            </li>
          ))}
          {onRuns ? (
            <li className="stepbar__aside">
              <button
                type="button"
                className={`stepbar__tab${page === "runs" ? " is-current" : ""}`}
                aria-current={page === "runs" ? "page" : undefined}
                title="Every run, past and present"
                onClick={onRuns}
              >
                <History size={15} aria-hidden="true" />
                Runs
              </button>
            </li>
          ) : null}
        </ol>
      </nav>
    );
  }
  // The line into each step fills once the path has reached it: how far along you are, at a glance.
  const at = step && !page ? step : 0;
  return (
    <nav className="stepbar" aria-label="Steps">
      <ol>
        <HomeLink current={page === "home"} />
        {STEPS.map((s) => {
          const current = s.n === at;
          const done = !current && s.n < reached;
          return (
            <li key={s.n} className={s.n <= Math.max(reached, at) ? "is-reached" : undefined}>
              {s.n > 1 ? (
                <span className="stepbar__link" aria-hidden="true">
                  <span className="stepbar__fill" />
                </span>
              ) : null}
              <button
                type="button"
                className={`stepbar__step${current ? " is-current" : done ? " is-done" : ""}`}
                aria-current={current ? "step" : undefined}
                title={s.hint}
                aria-label={`${s.n}. ${s.label}${done ? " (done)" : ""}`}
                onClick={() => onStep(s.n)}
              >
                <span className="stepbar__n num" aria-hidden="true">
                  {done ? <Check size={12} /> : s.n}
                </span>
                <span className="stepbar__label">{s.label}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** The head of a step that fills the screen with panes (Build, Measure): its own heading, what it
 * is for, Back, and its one forward action. Guided, Back and Next; in the workspace Back names the
 * step it goes to and the forward action is named for what it does. */
export function StageHead({
  step,
  title,
  lead,
  action,
  extra,
  onStep,
}: {
  step: 3 | 4;
  title: string;
  lead: ReactNode;
  /** The workspace's forward action (guided, it is Next). */
  action: { label: string; to: Step };
  /** Quiet links beside the lead. */
  extra?: ReactNode;
  onStep: (s: Step) => void;
}) {
  const { workspace } = useContext(Guide);
  const after = STEPS[step];
  return (
    <div className="stagehead" data-stage={step === 3 ? "build" : "measure"}>
      <div className="stagehead__text">
        {workspace ? null : <div className="steppage__eyebrow stagehead__eyebrow">{stepName(step)}</div>}
        <h1 className="stagehead__title" tabIndex={-1} data-page-title>
          {title}
        </h1>
        <p className="stagehead__lead small muted">
          {lead}
          {extra ? <> {extra}</> : null}
        </p>
      </div>
      <div className="stagehead__actions">
        {workspace ? (
          <>
            {/* The tabs go anywhere, but the page's own way back stays, as on every other step. */}
            <button type="button" className="btn btn--quiet" onClick={() => onStep((step - 1) as Step)}>
              <ArrowLeft size={14} aria-hidden="true" /> Back to {STEPS[step - 2].label}
            </button>
            <button type="button" className="btn btn--primary" onClick={() => onStep(action.to)}>
              {action.label} <ArrowRight size={14} aria-hidden="true" />
            </button>
          </>
        ) : (
          <>
            <button type="button" className="btn btn--quiet" onClick={() => onStep((step - 1) as Step)}>
              <ArrowLeft size={14} aria-hidden="true" /> Back
            </button>
            <button type="button" className="btn btn--primary" onClick={() => onStep(after.n)}>
              Next: {after.label} <ArrowRight size={14} aria-hidden="true" />
            </button>
          </>
        )}
      </div>
    </div>
  );
}

/** Back and Next at the foot of a step page; Next names where it goes. In the workspace too, so no page is a dead end. */
export function StepNav({
  step,
  onStep,
  next,
  disabled,
}: {
  step: Step;
  onStep: (s: Step) => void;
  next?: () => void | Promise<void>;
  disabled?: boolean;
}) {
  const { workspace, onSkip } = useContext(Guide);
  const after = STEPS.find((s) => s.n === step + 1);
  return (
    <div className="stepnav">
      {step > 1 ? (
        <button type="button" className="btn btn--quiet" onClick={() => onStep((step - 1) as Step)}>
          <ArrowLeft size={14} aria-hidden="true" /> Back
        </button>
      ) : onSkip && !workspace ? (
        <button type="button" className="btn btn--quiet" onClick={onSkip} title="Use the steps as tabs, and go to Build">
          Skip the Guide
        </button>
      ) : (
        <span />
      )}
      {after ? (
        <button
          type="button"
          className="btn btn--primary"
          disabled={disabled}
          onClick={async () => {
            try {
              await next?.();
            } catch {
              return; // the step shows what went wrong, and stays
            }
            onStep(after.n);
          }}
        >
          Next: {after.label} <ArrowRight size={14} aria-hidden="true" />
        </button>
      ) : (
        <span />
      )}
    </div>
  );
}

/** A full-width step page with a heading that says what this step is for. */
export function StepPage({
  step,
  title,
  lead,
  children,
  footer,
}: {
  step: Step;
  title: string;
  lead: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const { workspace } = useContext(Guide);
  return (
    <main className="steppage" id="main">
      <div className="steppage__inner">
        {workspace ? null : (
          <div className="steppage__where">
            <div className="steppage__eyebrow">{stepName(step)}</div>
            <p className="steppage__hint small muted">{STEPS[step - 1].hint}</p>
          </div>
        )}
        <h1 className="steppage__title" tabIndex={-1} data-page-title>
          {title}
        </h1>
        <p className="steppage__lead muted">{lead}</p>
        {children}
        {footer}
      </div>
    </main>
  );
}

const LAB_GOAL = "pg.goal.lab";
const OLD_USE_CASE = "pg.usecase"; // one box for both "Start from" choices, before each had its own

/** The "Nothing yet" goal: what you're building, kept in this browser as it's typed. A repo's goal
 * is the repo's own, on the server, and never comes from here. */
export function storedLabGoal(): string {
  try {
    const got = window.localStorage.getItem(LAB_GOAL);
    if (got !== null) return got;
    // The old shared box counts only if it was last written in "Nothing yet".
    return window.localStorage.getItem("pg.space") === "lab" ? (window.localStorage.getItem(OLD_USE_CASE) ?? "") : "";
  } catch {
    return "";
  }
}

export function storeLabGoal(text: string): void {
  try {
    window.localStorage.setItem(LAB_GOAL, text);
  } catch {
    // Not remembered in a private window.
  }
}

/** "/Users/me/code/app" as "~/code/app": enough to tell two repos of the same name apart. */
export function shortPath(root: string): string {
  return root.replace(/^\/(?:Users|home)\/[^/]+(?=\/|$)/, "~");
}

/** The ⋯ on a repo chip: Detach, which asks once more before it does it. */
function RepoMenu({ repo, onDetach }: { repo: RepoRef; onDetach: (id: string) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLSpanElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) close();
    };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [open]);
  const close = () => {
    setOpen(false);
    setConfirm(false);
    setError(null);
  };
  return (
    <span
      className="repo-chip__menu"
      ref={box}
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) {
          close();
          button.current?.focus();
        }
      }}
    >
      <button
        ref={button}
        type="button"
        className="repo-chip__x"
        aria-label={`More for ${repo.name}`}
        aria-expanded={open}
        onClick={() => (open ? close() : setOpen(true))}
      >
        <MoreHorizontal size={14} aria-hidden="true" />
      </button>
      {open ? (
        <div className="repo-pop" role="group" aria-label={`${repo.name}: more`}>
          {confirm ? (
            <>
              <p className="small">
                Detach <b>{repo.name}</b>? Rig stops showing it; nothing in <span className="mono">{shortPath(repo.root)}</span> is deleted.
              </p>
              {error ? (
                <p className="small" role="alert" style={{ color: "var(--negative)" }}>
                  {error}
                </p>
              ) : null}
              <div className="row" style={{ gap: 6 }}>
                <button
                  type="button"
                  className="btn btn--small btn--primary"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await onDetach(repo.id);
                    } catch (e) {
                      setError(String((e as Error).message ?? e));
                      setBusy(false);
                    }
                  }}
                >
                  Detach
                </button>
                <button type="button" className="btn btn--small btn--quiet" onClick={close}>
                  Cancel
                </button>
              </div>
            </>
          ) : (
            <button type="button" className="btn btn--small btn--quiet repo-pop__item" onClick={() => setConfirm(true)}>
              Detach…
            </button>
          )}
        </div>
      ) : null}
    </span>
  );
}

/** Step 1: where it lives (a repo, or nothing yet), and the goal for that place. Two goals, never
 * mixed: "Nothing yet" has what you're building (kept in this browser); each repo has its own saved
 * goal (on the server). An edit of it is a draft, kept in this browser and used by every step; only
 * Save goal writes it to the repo. A first visit chooses nothing until you pick a card. */
export function Describe({
  space,
  onSpace,
  repos,
  repoId,
  onRepo,
  onDetach,
  labText,
  onLabText,
  repoText,
  onRepoText,
  repoReady,
  repoDirty,
  repoHasGoal,
  repoSaved,
  onSave,
  attach,
  onStep,
  templates,
  template,
  onTemplate,
}: {
  /** One-click goals for a repo (repo-goals: templates); null until they load. */
  templates?: GoalRules["templates"] | null;
  /** The template the repo's goal box still comes from, if any. */
  template?: string | null;
  /** A template picked: its text fills the box, as a draft. */
  onTemplate?: (t: GoalRules["templates"][number]) => void;
  /** null on a first visit, until a "Start from" card is picked. */
  space: "repo" | "lab" | null;
  onSpace: (s: "repo" | "lab") => void;
  repos: RepoRef[];
  repoId: string | null;
  onRepo: (id: string) => void;
  onDetach: (id: string) => Promise<void>;
  /** The "Nothing yet" goal. */
  labText: string;
  onLabText: (t: string) => void;
  /** The chosen repo's goal box: its saved goal, or your edit of it. */
  repoText: string;
  onRepoText: (t: string) => void;
  /** The chosen repo's saved goal has been read (until then the box waits). */
  repoReady: boolean;
  /** The box differs from the repo's saved goal. */
  repoDirty: boolean;
  /** The chosen repo has a saved goal (the box's heading says saved, or draft of it). */
  repoHasGoal: boolean;
  /** Saved just now (Save goal or Next): the button says so. */
  repoSaved: boolean;
  /** Saves the box as the chosen repo's goal (Save goal; Next never does). */
  onSave: () => Promise<void>;
  attach: ReactNode;
  onStep: (s: Step) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const needsRepo = space === "repo" && !repoId;
  const unchosen = space === null;
  const repo = space === "repo" ? (repos.find((r) => r.id === repoId) ?? null) : null;
  useEffect(() => setError(null), [repoId, space]);

  const save = async () => {
    setError(null);
    setSaving(true);
    try {
      await onSave();
    } catch (e) {
      setError(`Couldn't save ${repo?.name ?? "the repo"}'s goal. ${String((e as Error).message ?? e)}`);
      throw e;
    } finally {
      setSaving(false);
    }
  };

  return (
    <StepPage
      step={1}
      title={unchosen ? "What Are You Working On?" : space === "repo" ? "What Should Your Agent Get Better At?" : "What Are You Building?"}
      lead={
        unchosen
          ? "Start from a repo you have, or from nothing yet. Then say in plain words what you want; every later step uses it."
          : space === "repo"
            ? "Say it in plain words: the work it does in the repo, where it slips, what it must never get wrong. Every later step uses this."
            : "Say it in plain words: who it's for, what it does, what it must never get wrong. Every later step uses this."
      }
      // Next never saves: a repo's draft goal is used as it is, and only Save goal writes it.
      footer={<StepNav step={1} onStep={onStep} disabled={unchosen || needsRepo || saving} />}
    >
      <fieldset className="describe__from">
        <legend>Start From</legend>
        <div className="describe__ways" role="radiogroup" aria-label="Start From">
          <button type="button" role="radio" aria-checked={space === "repo"} className="describe__way" onClick={() => onSpace("repo")}>
            <FolderGit2 size={18} aria-hidden="true" />
            <span>
              <b>My Repo — {repos.length ? `${repos.length} attached` : "none attached yet"}</b>
              <span className="small muted">Read its code and agent setup, then improve it.</span>
            </span>
          </button>
          <button type="button" role="radio" aria-checked={space === "lab"} className="describe__way" onClick={() => onSpace("lab")}>
            <Sparkles size={18} aria-hidden="true" />
            <span>
              <b>Nothing Yet</b>
              <span className="small muted">Start from a design and a workflow; no code needed.</span>
            </span>
          </button>
        </div>
        {space === "repo" ? (
          <div className="describe__repos">
            {repos.length ? (
              <div className="describe__chips" role="radiogroup" aria-label="Repo">
                {repos.map((r) => (
                  <span key={r.id} className={`repo-chip repo-chip--tall${r.id === repoId ? " is-active" : ""}`}>
                    <button
                      type="button"
                      role="radio"
                      aria-checked={r.id === repoId}
                      aria-label={r.name}
                      aria-describedby={`repo-path-${r.id}`}
                      title={r.root}
                      onClick={() => onRepo(r.id)}
                    >
                      {r.provider ? <ProviderIcon provider={r.provider} /> : <FolderGit2 size={13} aria-hidden="true" />}
                      <span className="repo-chip__text">
                        <span className="repo-chip__name">{r.name}</span>
                        <span id={`repo-path-${r.id}`} className="repo-chip__path mono">
                          {shortPath(r.root)}
                        </span>
                      </span>
                    </button>
                    <RepoMenu repo={r} onDetach={onDetach} />
                  </span>
                ))}
              </div>
            ) : null}
            <details className="describe__add" open={repos.length === 0}>
              <summary className="small">{repos.length ? "Add Another Repo" : "Add Your Repo"}</summary>
              {attach}
            </details>
          </div>
        ) : null}
      </fieldset>

      {space === "lab" ? (
        <div className="describe__goal">
          <label className="describe__label" htmlFor="describe-lab-goal">
            What you're building
          </label>
          <textarea
            id="describe-lab-goal"
            className="textarea describe__text"
            rows={4}
            value={labText}
            autoFocus
            placeholder="For example: a support agent that answers tickets from our policy docs and hands refunds over $500 to a person."
            onChange={(e) => onLabText(e.target.value)}
          />
          <p className="small muted describe__hint">Kept in this browser as you type.</p>
        </div>
      ) : repo ? (
        <div className="describe__goal" key={repo.id}>
          <label className="describe__label" htmlFor="describe-repo-goal">
            {goalHeading(repo.name, repoHasGoal, repoDirty)}
          </label>
          {templates?.length && onTemplate ? (
            <div className="goal-templates" role="group" aria-label="Start from a common goal">
              <span className="small muted">Start from one:</span>
              {templates.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={`goal-template${template === t.id ? " is-on" : ""}`}
                  aria-pressed={template === t.id}
                  title={t.text}
                  disabled={!repoReady}
                  onClick={() => onTemplate(t)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          ) : null}
          <textarea
            id="describe-repo-goal"
            className="textarea describe__text"
            rows={4}
            value={repoText}
            readOnly={!repoReady}
            aria-describedby="describe-repo-goal-state"
            placeholder={
              repoReady
                ? `What should your agent get better at in ${repo.name}? For example: fix refund bugs without breaking the plan limits, and always run the tests before finishing.`
                : `Reading ${repo.name}'s saved goal…`
            }
            onChange={(e) => onRepoText(e.target.value)}
          />
          <div className="describe__save">
            <button
              type="button"
              className={`btn${repoDirty ? " btn--primary" : ""}`}
              disabled={!repoDirty || !repoText.trim() || saving}
              onClick={() => void save().catch(() => undefined)}
            >
              {saving ? (
                "Saving…"
              ) : !repoDirty && repoSaved ? (
                <>
                  <Check size={14} aria-hidden="true" /> Saved
                </>
              ) : (
                "Save Goal"
              )}
            </button>
            <span id="describe-repo-goal-state" className="small muted" role="status">
              {!repoReady
                ? ""
                : repoDirty
                  ? `Unsaved draft, only in this browser: every step uses it. Save Goal makes it ${repo.name}'s goal.`
                  : repoText.trim()
                    ? `${repo.name}'s goal, as saved in the repo.`
                    : `${repo.name} has no goal saved yet.`}
            </span>
          </div>
        </div>
      ) : null}
      {error ? (
        <p className="notice notice--error small" role="alert">
          {error}
        </p>
      ) : null}
    </StepPage>
  );
}
