import { ChevronLeft, ChevronRight, ExternalLink, FlaskConical, NotebookPen } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import type { CanvasStore } from "../lib/canvasState";
import { plural } from "../lib/format";
import { measureBadge, useRules } from "../lib/rules";
import type { Estimate, Proposed, RepoSkillRef, Scenario, Suggestion, TreatmentItem } from "../lib/types";
import { MeasureLine } from "./MeasureBadge";
import { archStyle, blueprintRole, type MeasuredVerdict, type NodeInfo } from "./RepoCanvas";
import { Term } from "./Term";

/** General guidance per component type: what agents tend to get wrong there. */
const WHY: Record<string, { lead: string; points: string[] }> = {
  frontend: {
    lead: "What users see. Agent changes here are judged by behaviour in the browser, not only by compiling.",
    points: ["Check states: loading, empty, error.", "Keep accessibility (labels, focus, contrast).", "Test in the browser, not only unit tests."],
  },
  backend: {
    lead: "Where the rules of the product live. Most agent tasks land here.",
    points: ["Change behaviour behind tests that fail first.", "Keep API contracts stable for callers.", "Watch error handling and timeouts."],
  },
  database: {
    lead: "State that outlives every run. Mistakes here are the hardest to undo.",
    points: ["Schema changes need migrations, forwards and back.", "Queries need indexes for the real data size.", "Never rely on test data shapes in production paths."],
  },
  messagebus: {
    lead: "Work that happens later, in another process. Failures are quiet.",
    points: ["Handlers must be safe to run twice.", "Think about ordering and retries.", "Make dead letters visible."],
  },
  cloud: {
    lead: "The edge: routing, TLS and proxies in front of the services.",
    points: ["Config changes affect every request.", "Keep timeouts and limits explicit."],
  },
  security: {
    lead: "Identity and secrets. An agent must never weaken these to make a task pass.",
    points: ["No secrets in code or logs.", "Least privilege for every token.", "Changes need review by a person."],
  },
  external: {
    lead: "Something outside this repo that it depends on.",
    points: ["Mock it in tests; do not call it from tasks.", "Plan for it being slow or down."],
  },
};

interface Props {
  info: NodeInfo | null;
  nodeId: string | null;
  order: string[];
  onGo: (id: string) => void;
  store: CanvasStore;
  scenarios: Scenario[];
  suggestions: Suggestion[];
  estimate: Estimate | "loading" | undefined;
  /** Ask the model for a sharper estimate of this card: a paid call, only on a click. */
  onSharpen?: () => void;
  names: Map<string, string>;
  /** The architecture's own connections (from the code or the spec), with what flows on them. */
  flows: { from: string; to: string; label: string | null }[];
  onInstalled: (cardId: string, path: string, name: string) => void;
  onTest: (path: string, name: string) => void;
  /** Lay a GitHub repo card out as its parts (commands, agents, skills, hooks, MCP). */
  onParts?: (cardId: string, repo: string, name: string) => void;
  /** Where a card planned beside a block goes (an open spot next to it), for "Add as a planned part". */
  placeBeside?: (nodeId: string) => { x: number; y: number } | null;
  /** The suggestion each new or taken-away part came from, by component id. */
  origins?: Proposed["origins"];
  /** The selected skill's last run, as Measure shows it. */
  verdict?: MeasuredVerdict;
  /** "Measure it" on a part a suggestion adds or takes away: Measure before and after, for that
   * suggestion (its title). */
  onMeasureCode?: (title: string) => void;
}

/** A missing part of the agent setup: what it is for, what to put in it (with the repo's own
 * test command when there is one), and what the planned card asks for in BUILD.md. */
function missingSetup(label: string, tests?: string): { lead: string; put: ReactNode[]; plan: string } | null {
  const run = tests ? <code>{tests}</code> : null;
  if (label === "CLAUDE.md" || label === "AGENTS.md")
    return {
      lead: `This repo has no ${label} yet, so every agent starts without its commands and rules. It's the first file a coding agent reads, with and without the change, in every run.`,
      put: [
        run ? (
          <>How to build, test and run it. Test: {run} (the command Rig found in the repo).</>
        ) : (
          "How to build, test and run it. No test command was found in the build files: write the one your team runs."
        ),
        "Conventions: code style, where things go, naming, what a good change looks like.",
        "What not to touch: generated files, secrets, migrations, vendored code.",
        "When work is done: the checks to run, and to show their output.",
      ],
      plan: `Add ${label} at the repo root: how to build, test and run it${tests ? ` (test: ${tests})` : ""}; its conventions; what not to touch; and to run the checks and show their output before finishing.`,
    };
  if (label === "Hooks")
    return {
      lead: "No hooks in .claude/settings.json. A hook runs a command at a set moment, such as after every edit, so a rule is kept without the agent remembering it.",
      put: [
        run ? <>For example: run {run} after each edit, and show what failed.</> : "For example: run the tests after each edit, and show what failed.",
        "Or block edits to files the agent must not touch.",
      ],
      plan: `Add a hook in .claude/settings.json${tests ? ` that runs ${tests} after each edit` : " that runs the tests after each edit"}.`,
    };
  if (label === "Test command")
    return {
      lead: "No test command found in the repo's build files or CLAUDE.md. Agents and Rig's checks need one way to run the tests.",
      put: ["Write the command your team runs (for example in CLAUDE.md, in backticks), so agents run it before finishing."],
      plan: "Write the repo's test command in CLAUDE.md (in backticks), so agents run it before finishing.",
    };
  if (label === "MCP servers")
    return {
      lead: "No MCP servers in .mcp.json. An MCP server gives the agent tools beyond the repo: a database, an issue tracker, docs.",
      put: ["Only the tools the work needs; each one is in every trial of a run, with and without the change."],
      plan: "Add the MCP servers the work needs to .mcp.json (only those).",
    };
  if (label === "Skills")
    return {
      lead: "No skills in the repo. A skill is instructions an agent opens when a task needs them.",
      put: ["Add one from the library: drag it onto the canvas, and its estimate shows at once."],
      plan: "Add skills under .claude/skills/ for the work the goal names.",
    };
  return null;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="insp__section">
      <div className="insp__label">{title}</div>
      {children}
    </div>
  );
}

function EstimateBox({ e, onSharpen }: { e: Estimate | "loading" | undefined; onSharpen?: () => void }) {
  if (!e) return <p className="small muted">No estimate yet.</p>;
  if (e === "loading") return <p className="small muted">Estimating…</p>;
  if (e.basis === "none") return <p className="small">{e.reason}</p>;
  const sign = (n: number) => `${n > 0 ? "+" : ""}${n}`;
  const label = { measured: "Measured", estimate: "Model estimate", rough: "Rough guess" }[e.basis];
  // The bar spans -30..+30 points: most skills land well inside it.
  const at = (v: number) => 50 + (Math.max(-30, Math.min(30, v)) / 30) * 50;
  return (
    <div className={`estbox estbox--${e.basis}`}>
      <div className="estbox__top">
        <span className="estbox__basis">{label}</span>
        <span className="estbox__value num">
          {sign(e.likely ?? 0)} pts <Term k="pts" />
        </span>
      </div>
      <div className="estbar" aria-hidden="true">
        <span className="estbar__zero" />
        <span
          className="estbar__range"
          style={{ left: `${at(e.low ?? 0)}%`, right: `${100 - at(e.high ?? 0)}%` }}
        />
        <span className="estbar__dot" style={{ left: `${at(e.likely ?? 0)}%` }} />
      </div>
      <div className="small num">
        Range {sign(e.low ?? 0)} to {sign(e.high ?? 0)} pts · confidence {e.confidence}
      </div>
      <p className="small">{e.reason}</p>
      {e.refining ? <p className="small muted">Asking the model (cheapest tier) for a sharper estimate…</p> : null}
      {e.basis === "rough" && onSharpen && !e.refining ? (
        <button type="button" className="btn btn--small" onClick={onSharpen}>
          Sharpen with the Model{e.sharpen_usd != null ? ` (≈$${e.sharpen_usd.toFixed(2)})` : ""}
        </button>
      ) : null}
      {e.note ? <p className="small muted">{e.note}</p> : null}
      {e.basis !== "measured" ? (
        <p className="small muted">
          {e.basis === "rough" ? "Worked out from the skill's text and the repo, no model." : "One quick model call (Haiku)."} Not a
          measurement: a run makes it conclusive.
        </p>
      ) : null}
    </div>
  );
}

function CatalogPicker({ cardId, repo, onInstalled }: { cardId: string; repo: string; onInstalled: Props["onInstalled"] }) {
  const [skills, setSkills] = useState<RepoSkillRef[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setSkills(null);
    api
      .repoSkills(repo)
      .then((s) => live && setSkills(s))
      .catch((e) => live && setError(e instanceof ApiError ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [repo]);
  if (error) return <p className="notice notice--error small">{error}</p>;
  if (!skills) return <p className="small muted">Reading {repo} for skills…</p>;
  if (skills.length === 0) {
    return (
      <p className="small">
        No SKILL.md in this repo, so it stays a planning card: it can't be measured yet. Read it on GitHub to see how
        it's meant to be used.
      </p>
    );
  }
  return (
    <ul className="list">
      {skills.map((s) => (
        <li key={s.path} className="row row--between" style={{ padding: "8px 0", alignItems: "start" }}>
          <span>
            <strong>{s.name}</strong>
            <span className="small muted" style={{ display: "block" }}>
              {s.description || s.path}
            </span>
          </span>
          <button
            type="button"
            className="btn btn--small"
            disabled={busy !== null}
            onClick={async () => {
              setBusy(s.path);
              try {
                const r = await api.install(repo, s.path);
                onInstalled(cardId, r.path, s.name);
              } catch (e) {
                setError(e instanceof ApiError ? e.message : String(e));
              } finally {
                setBusy(null);
              }
            }}
          >
            {busy === s.path ? "Installing…" : "Use This"}
          </button>
        </li>
      ))}
    </ul>
  );
}

export function Inspector(p: Props) {
  const i = p.info;
  const mr = useRules("measurability");
  const idx = p.nodeId ? p.order.indexOf(p.nodeId) : -1;
  const note = p.nodeId ? (p.store.state.notes[p.nodeId] ?? "") : "";
  const [draft, setDraft] = useState(note);
  useEffect(() => setDraft(note), [note, p.nodeId]);

  if (!i || !p.nodeId) {
    return (
      <div className="insp">
        <div className="insp__band" style={{ ["--node" as string]: "#1b6c80" }}>
          Select anything on the canvas
        </div>
        <div className="insp__body">
          <p>Each block explains itself here: what it is, why it matters for an agent, and what's measured.</p>
          <ul className="insp__points">
            <li>Drag skills, harness techniques or workflows from the library onto the canvas.</li>
            <li>Connect any block to any other from its left or right handle.</li>
            <li>Every skill shows an estimate at once; a run makes it conclusive.</li>
          </ul>
        </div>
      </div>
    );
  }

  const links = p.store.state.links;
  const ins = links.filter((l) => l.to === p.nodeId);
  const outs = links.filter((l) => l.from === p.nodeId);
  let color = "#1b6c80";
  let band = "";
  let title = "";
  let subtitle = "";
  let body: ReactNode = null;

  if (i.kind === "arch" && i.blueprint) {
    // A catalog design's part: a role in the design, not infrastructure in your repo.
    const st = archStyle(i.c);
    color = st.color;
    band = i.c.role || blueprintRole(i.c) || st.label;
    title = i.c.label;
    subtitle = "In the catalog design, not your repo";
    body = (
      <>
        {i.c.sublabel ? <p className="insp__lead">{i.c.sublabel}.</p> : null}
        <p className="small muted">
          Choose this design to build from it: in a repo, it is a direction to move toward; with nothing yet, it is the plan. Undo and
          Reset don't apply to a blueprint.
        </p>
      </>
    );
  } else if (i.kind === "arch") {
    const st = archStyle(i.c);
    const why = WHY[i.c.type] ?? WHY.backend;
    color = st.color;
    band = st.label;
    title = i.c.label;
    const from = i.c.source === "proposed" || i.c.source === "removed" ? p.origins?.[i.c.id] : undefined;
    subtitle = [
      i.c.sublabel,
      i.c.source === "proposed" ? "added by a suggestion" : i.c.source === "removed" ? "taken away by a suggestion" : i.c.source,
    ]
      .filter(Boolean)
      .join(" · ");
    body = (
      <>
        <p className="insp__lead">{why.lead}</p>
        <Section title="Key points">
          <ul className="insp__points">
            {why.points.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </Section>
        {i.c.check ? (
          <Section title="Checked against the code">
            <p className={`small check check--${i.c.check}`}>
              <strong>{{ found: "Found", weak: "Weak evidence", missing: "Not found" }[i.c.check]}.</strong> {i.c.why}
            </p>
            {i.c.evidence?.length ? (
              <p className="small muted">The agent cited: {i.c.evidence.join(", ")}</p>
            ) : null}
          </Section>
        ) : i.c.source === "proposed" || i.c.source === "removed" ? (
          <Section title="From the suggestion">
            <p className="small" data-testid="part-origin">
              {from ? (
                <>
                  <b>{from.title}</b> · {from.state === "accepted" ? "accepted" : "previewed, not accepted yet"}.{" "}
                  {i.c.source === "proposed" ? "It adds this part" : "It takes this part away"}; nothing changes in the code until a
                  coding agent follows the brief.
                </>
              ) : (
                "A suggestion on the right proposes it; nothing changes in the code until a coding agent follows the brief."
              )}
            </p>
          </Section>
        ) : i.c.source ? (
          <Section title="Read from">
            <p className="small mono">{i.c.source}</p>
          </Section>
        ) : null}
        {(() => {
          const mine = p.flows.filter((f) => f.from === i.c.id || f.to === i.c.id);
          if (!mine.length) return null;
          const name = (id: string) => p.names.get(`arch:${id}`) ?? id;
          return (
            <Section title="Talks to">
              <ul className="insp__points">
                {mine.map((f) => (
                  <li key={`${f.from}-${f.to}`}>
                    {f.from === i.c.id ? `→ ${name(f.to)}` : `← ${name(f.from)}`}
                    {f.label ? <span className="muted"> · {f.label}</span> : null}
                  </li>
                ))}
              </ul>
            </Section>
          );
        })()}
      </>
    );
  } else if (i.kind === "step") {
    const own = p.scenarios.filter((s) => s.step === i.name);
    color = "#1b6c80";
    band = `Workflow step ${i.index + 1}`;
    title = i.name;
    subtitle = i.type;
    body = (
      <>
        {i.why ? <p className="insp__lead">{i.why}</p> : null}
        <Section title={`Tasks (${own.length})`}>
          {own.length ? (
            <ul className="insp__points">
              {own.map((s) => (
                <li key={s.id}>
                  {s.title || s.id} <span className="muted small">· {s.kind} · {s.runnable ? "approved" : "needs review"}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="small muted">None yet. Add one in step 4, Measure.</p>
          )}
        </Section>
      </>
    );
  } else if (i.kind === "setup" && i.present === false) {
    const m = missingSetup(i.label, i.tests);
    const ref = `setup/${i.label}`;
    const planned = p.store.state.cards.find((c) => c.ref === ref);
    color = "#334155";
    band = "Agent setup · missing";
    title = i.label;
    subtitle = "Missing: not in the repo yet";
    body = (
      <>
        <p className="insp__lead">{m?.lead ?? i.detail}</p>
        {m ? (
          <Section title="What to put in it">
            <ul className="insp__points" data-testid="setup-missing-points">
              {m.put.map((x, n) => (
                <li key={n}>{x}</li>
              ))}
            </ul>
          </Section>
        ) : null}
        {planned ? (
          <p className="small" role="status">
            Planned: on the canvas in the agent setup lane, and listed in BUILD.md under "Planned, not written yet".
          </p>
        ) : (
          <button
            type="button"
            className="btn btn--primary btn--block"
            onClick={() => {
              const nodeId = p.nodeId!;
              const at = p.placeBeside?.(nodeId) ?? { x: 0, y: 0 };
              p.store.addCard(
                {
                  kind: "suggestion",
                  ref,
                  name: i.label,
                  x: Math.round(at.x),
                  y: Math.round(at.y),
                  why: `Planned for the agent setup: ${i.label} is missing.`,
                  plan: m?.plan ?? `Add ${i.label}.`,
                },
                [nodeId],
              );
            }}
          >
            Add as a Planned Part
          </button>
        )}
        <p className="small muted">A planned part is not written for you: BUILD.md lists it with what to put in it.</p>
      </>
    );
  } else if (i.kind === "setup") {
    color = "#334155";
    band = "Agent setup";
    title = i.label;
    subtitle = "Already in the repo";
    body = (
      <p className="insp__lead">
        {/mcp/i.test(i.label)
          ? "Tools the agent can call, from .mcp.json. Every trial runs with them, with and without the change, unless a server is itself the change you measure: then only the \"with\" arm gets it."
          : /hook/i.test(i.label)
            ? "Commands that run at set moments, such as after every edit, from .claude/settings.json. A hook can be the change you measure on Measure: then only the \"with\" arm gets it."
            : /test/i.test(i.label)
              ? "How the repo's tests run: what a task's check can call."
              : <>Instructions every agent reads first. When something else is the change, they stay the same in both arms<Term k="arms" /> of a run, so a result measures only the change. To measure the instructions themselves, pick CLAUDE.md (or an edited copy) as the change on Measure: the &ldquo;with&rdquo; arm gets it, the &ldquo;without&rdquo; arm keeps the committed one.</>}
      </p>
    );
  } else if (i.kind === "repo-skill" || (i.kind === "card" && i.card.kind === "skill")) {
    const t: TreatmentItem | null = i.kind === "repo-skill" ? i.t : null;
    const name = t?.name ?? (i.kind === "card" ? i.card.name : "");
    const path = t?.path ?? (i.kind === "card" ? i.card.ref : "");
    color = "#7c3aed";
    band = i.kind === "repo-skill" ? "Skill · already in the repo" : "Skill";
    title = name;
    subtitle = path.split("/").slice(-3).join("/");
    body = (
      <>
        {t?.description ? <p className="insp__lead">{t.description}</p> : null}
        <Section title="Effect on this repo">
          {p.verdict ? (
            <p className="small" data-testid="skill-verdict">
              <b>
                Last run (#{p.verdict.run}): Rig {p.verdict.score ?? "–"} · {p.verdict.word}.
              </b>{" "}
              The same result Measure shows; a bigger run settles it.
            </p>
          ) : (
            <EstimateBox e={p.estimate} onSharpen={p.onSharpen} />
          )}
        </Section>
        <div>
          <button type="button" className="btn btn--primary btn--block" onClick={() => p.onTest(path, name)}>
            Confirm with a Run
          </button>
        </div>
      </>
    );
  } else if (i.kind === "card" && i.card.kind === "catalog") {
    color = "#24292f";
    band = "From GitHub";
    title = i.card.name;
    subtitle = i.card.ref;
    body = (
      <>
        {i.card.parts ? (
          <p className="insp__lead">
            Laid out as its {i.card.parts} parts, read from its file tree: instructions, commands, agents, skills, hooks and MCP
            config, left to right. A line means one part's text names the other. Remove any part you don't want.
          </p>
        ) : (
          <>
            <p className="insp__lead">Pick which skill in this repo to try. Only that folder is downloaded.</p>
            <CatalogPicker cardId={i.card.id} repo={i.card.ref} onInstalled={p.onInstalled} />
          </>
        )}
        {p.onParts && !i.card.parts ? (
          <button type="button" className="btn btn--block" onClick={() => p.onParts?.((i.card as { id: string }).id, i.card.ref, i.card.name)}>
            Show Its Parts on the Canvas
          </button>
        ) : null}
        <a className="btn btn--quiet btn--small" href={`https://github.com/${i.card.ref}`} target="_blank" rel="noreferrer">
          Open on GitHub <ExternalLink size={12} />
        </a>
      </>
    );
  } else if (i.kind === "card" && i.card.kind === "part") {
    const [repo, path] = [i.card.ref.split(":")[0], i.card.ref.split(":").slice(1).join(":")];
    color = "#24292f";
    band = `${i.card.part?.label ?? "Part"} · from GitHub`;
    title = i.card.name;
    subtitle = `${repo} · ${path}`;
    body = (
      <>
        {i.card.part?.description ? <p className="insp__lead">{i.card.part.description}</p> : null}
        <p className="small muted">
          One part of {repo}, laid out with the others from its file tree. A line between parts means this part's text names
          the other one. Remove what you don't want; Undo brings it back.
        </p>
        {i.card.part?.url ? (
          <a className="btn btn--quiet btn--small" href={i.card.part.url} target="_blank" rel="noreferrer">
            Read it on GitHub <ExternalLink size={12} />
          </a>
        ) : null}
      </>
    );
  } else if (i.kind === "card" && i.card.kind === "suggestion" && i.card.ref.startsWith("setup/")) {
    color = "#334155";
    band = "Planned · agent setup";
    title = i.card.name;
    subtitle = "Not written yet";
    body = (
      <>
        <p className="insp__lead">{i.card.plan ?? `Add ${i.card.name}.`}</p>
        <p className="small muted">BUILD.md lists it under "Planned, not written yet". Remove the card to leave it out; Undo brings it back.</p>
      </>
    );
  } else if (i.kind === "card" && i.card.kind === "suggestion") {
    const s = p.suggestions.find((x) => `${x.workflow}/${x.name}` === i.card.ref);
    color = "#6b7280";
    band = "Suggested · not installed";
    title = i.card.name;
    subtitle = s ? `for ${s.workflow}${s.step ? `, step ${s.step}` : ""}` : "";
    body = (
      <>
        <p className="insp__lead">{s?.why ?? "Suggested when tasks were generated."}</p>
        <p className="small muted">
          Find a skill like this in the library (search “{i.card.name}”), or write one under .claude/skills/. A plan card
          can't be measured until a real skill replaces it.
        </p>
      </>
    );
  }

  return (
    <div className="insp">
      <div className="insp__band" style={{ ["--node" as string]: color }}>
        {band}
      </div>
      <div className="insp__body">
        <h3 className="insp__title">{title}</h3>
        {subtitle ? <div className="insp__subtitle">{subtitle}</div> : null}
        {body}
        {i.kind === "arch" && i.blueprint ? null : (
          <Section title="Can Measure test it?">
            <MeasureLine b={measureBadge(i, mr)} />
            {i.kind === "arch" && mr && p.onMeasureCode && measureBadge(i, mr)?.id === "before_after" ? (
              <button
                type="button"
                className="btn btn--small"
                data-testid="insp-measure-it"
                onClick={() => p.onMeasureCode?.(p.origins?.[i.c.id]?.title ?? i.c.label)}
              >
                <FlaskConical size={13} aria-hidden="true" /> {mr.before_after.measure_it}
              </button>
            ) : null}
          </Section>
        )}
        {i.kind === "card" && i.card.why ? (
          <Section title="Why it's here">
            <p className="small">{i.card.why}</p>
            {i.card.fit ? <p className="small fit-note">{i.card.fit}</p> : null}
            <p className="small muted">Drag it anywhere else, or re-link it from its handles.</p>
          </Section>
        ) : null}
        <Section title="Connections">
          {ins.length + outs.length === 0 ? (
            <p className="small muted">None of yours yet. Drag from a handle on the block's left or right edge.</p>
          ) : (
            <ul className="list">
              {[...ins.map((l) => ({ l, dir: "from", other: l.from })), ...outs.map((l) => ({ l, dir: "to", other: l.to }))].map(
                ({ l, dir, other }) => (
                  <li key={l.id} className="row row--between" style={{ padding: "6px 0" }}>
                    <span className="small">
                      {dir === "from" ? "From" : "To"} {p.names.get(other) ?? other}
                    </span>
                    <button
                      type="button"
                      className="btn btn--small btn--quiet"
                      aria-label={`Remove the link ${dir} ${p.names.get(other) ?? other}`}
                      onClick={() => p.store.disconnect(l.id)}
                    >
                      Remove
                    </button>
                  </li>
                ),
              )}
            </ul>
          )}
        </Section>
        <Section title="Your notes">
          <label className="visually-hidden" htmlFor="insp-note">
            Notes for {title}
          </label>
          <textarea
            id="insp-note"
            className="textarea insp__note"
            placeholder="Design notes, trade-offs, assumptions…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => p.store.setNote(p.nodeId!, draft)}
          />
          <span className="small muted row" style={{ gap: 4 }}>
            <NotebookPen size={12} aria-hidden="true" /> Kept in this browser.
          </span>
        </Section>
        <p className="small muted">{plural(p.order.length, "block")} on the canvas</p>
      </div>
      <div className="stage__nav">
        <button type="button" className="btn" disabled={idx <= 0} onClick={() => p.onGo(p.order[idx - 1])}>
          <ChevronLeft size={16} aria-hidden="true" /> Previous
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={idx < 0 || idx >= p.order.length - 1}
          onClick={() => p.onGo(p.order[idx + 1])}
        >
          Next <ChevronRight size={16} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
