import { ExternalLink, Plus, Star } from "lucide-react";
import { useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import { ago, type LibraryItem } from "./Palette";

const KIND: Record<string, { label: string; what: string; color: string }> = {
  skill: {
    label: "Skill",
    what: "Instructions the agent loads when a task matches: a SKILL.md and any files it points to.",
    color: "#6d28d9",
  },
  agent: {
    label: "Agent / subagent",
    what: "An agent definition or a pack of subagents the main agent can hand work to.",
    color: "#0f766e",
  },
  mcp: {
    label: "MCP server",
    what: "A tool server the agent connects to over the Model Context Protocol (a database, a browser, an API).",
    color: "#1d4ed8",
  },
  hook: {
    label: "Hooks & commands",
    what: "Hooks that run on agent events (before a tool call, at the end) and slash commands.",
    color: "#b45309",
  },
  harness: {
    label: "Harness technique",
    what: "A change to how the agent is run: loops, context handling, memory, plugins.",
    color: "#7c2d12",
  },
  workflow: {
    label: "Agentic workflow",
    what: "A way of splitting work across steps or agents, such as spec first then build, or plan, act, review.",
    color: "#9d174d",
  },
  eval: {
    label: "Eval suite",
    what: "Benchmarks and graders to compare against: useful as extra tasks for this repo.",
    color: "#374151",
  },
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="insp__section">
      <div className="insp__label">{title}</div>
      {children}
    </div>
  );
}

/** The details panel for something in the library, before it is on the canvas. */
export function LibraryDetail({
  lib,
  onAdd,
  onSaved,
}: {
  lib: LibraryItem;
  onAdd: (lib: LibraryItem) => void;
  onSaved?: (path: string, name: string) => void;
}) {
  if (lib.from === "create" || lib.from === "improve") return <DraftDetail lib={lib} onSaved={onSaved} />;
  return <ItemDetail lib={lib} onAdd={onAdd} />;
}

function ItemDetail({ lib, onAdd }: { lib: Exclude<LibraryItem, { from: "create" | "improve" }>; onAdd: (lib: LibraryItem) => void }) {
  const [text, setText] = useState<string | null>(null);
  const [files, setFiles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setText(null);
    setFiles([]);
    setError(null);
    const load =
      lib.from === "github"
        ? api.readme(lib.item.id).then((r) => r.text)
        : lib.from === "local"
          ? api.skillText(lib.t.path).then((r) => {
              if (live) setFiles(r.files);
              return r.text;
            })
          : Promise.resolve("");
    load
      .then((t) => live && setText(t))
      .catch((e) => live && setError(e instanceof ApiError ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [lib]);

  const kind = lib.from === "github" ? KIND[lib.item.category] ?? KIND.skill : KIND.skill;
  const band = lib.from === "github" ? `From GitHub · ${kind.label}` : lib.from === "local" ? `Skill · ${lib.where}` : "Suggested skill";

  return (
    <div className="insp">
      <div className="insp__band" style={{ ["--node" as string]: kind.color }}>
        {band}
      </div>
      <div className="insp__body">
        <h3 className="insp__title">{lib.name}</h3>
        {lib.from === "github" ? <div className="insp__subtitle">{lib.item.id}</div> : null}
        {lib.from === "local" ? <div className="insp__subtitle">{lib.t.path}</div> : null}

        <p className="insp__lead">
          {lib.from === "github"
            ? lib.item.description || "No description on GitHub."
            : lib.from === "local"
              ? lib.t.description || "No description in its SKILL.md."
              : lib.s.why}
        </p>

        {lib.from === "github" ? (
          <div className="libmeta">
            <span className="num">
              <Star size={13} aria-hidden="true" /> {lib.item.stars.toLocaleString()} stars
            </span>
            <span>by {lib.item.owner}</span>
            <span>updated {ago(lib.item.pushed_at)}</span>
            {lib.item.theme ? <span>{lib.item.theme}</span> : null}
          </div>
        ) : null}

        <Section title={`What ${/^[aeiou]/i.test(kind.label) ? "an" : "a"} ${kind.label.toLowerCase()} is`}>
          <p className="small">{kind.what}</p>
        </Section>

        {lib.from === "github" && lib.item.topics.length ? (
          <Section title="Topics">
            <div className="tags">
              {lib.item.topics.slice(0, 12).map((t) => (
                <span key={t} className="tag">
                  {t}
                </span>
              ))}
            </div>
          </Section>
        ) : null}

        {lib.from !== "suggested" ? (
          <Section title={lib.from === "github" ? "From its README" : "Its SKILL.md"}>
            {error ? <p className="notice notice--error small">{error}</p> : null}
            {text === null && !error ? <p className="small muted">Reading…</p> : null}
            {text === "" ? <p className="small muted">Nothing to show.</p> : null}
            {text ? (
              <div className="readme" tabIndex={0} aria-label={lib.from === "github" ? "README" : "SKILL.md"}>
                {text}
              </div>
            ) : null}
            {files.length > 1 ? <p className="small muted">{files.length} files: {files.slice(0, 6).join(", ")}{files.length > 6 ? "…" : ""}</p> : null}
          </Section>
        ) : (
          <Section title="Not installed yet">
            <p className="small">Rig suggested it from the repo. Put it on the canvas to plan with it; a run needs the skill itself.</p>
          </Section>
        )}

        <div className="row" style={{ gap: 8 }}>
          <button type="button" className="btn btn--primary" onClick={() => onAdd(lib)}>
            <Plus size={14} aria-hidden="true" /> Add to the Canvas
          </button>
          {lib.from === "github" ? (
            <a className="btn btn--quiet" href={lib.item.url} target="_blank" rel="noreferrer">
              Open on GitHub <ExternalLink size={12} aria-hidden="true" />
            </a>
          ) : null}
        </div>
        <p className="small muted">
          {lib.from === "github"
            ? "On the canvas you pick which of its skills to use; only that folder is downloaded."
            : "On the canvas it gets an estimate at once; a run makes it conclusive."}
        </p>
      </div>
    </div>
  );
}

/** A new skill to write for this repo, or a rewrite of one you have: read the draft, then save it. */
function DraftDetail({
  lib,
  onSaved,
}: {
  lib: Extract<LibraryItem, { from: "create" | "improve" }>;
  onSaved?: (path: string, name: string) => void;
}) {
  const [text, setText] = useState<string | null>(null);
  const [busy, setBusy] = useState<"draft" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const improving = lib.from === "improve";
  const name = improving ? `${lib.name}-improved` : lib.name;
  useEffect(() => {
    setText(null);
    setSaved(null);
    setError(null);
  }, [lib]);

  return (
    <div className="insp">
      <div className="insp__band" style={{ ["--node" as string]: "#6d28d9" }}>
        {improving ? "Improve a skill you have" : "A new skill for this repo"}
      </div>
      <div className="insp__body">
        <h3 className="insp__title">{name}</h3>
        <div className="insp__subtitle">for: {lib.need}</div>
        <p className="insp__lead">{improving ? lib.how : lib.what}</p>
        <Section title="Why">
          <p className="small">{lib.why}</p>
        </Section>
        <Section title="What happens next">
          <ol className="insp__points">
            <li>A draft is written from this repo's facts: its commands, files, steps and checks.</li>
            <li>You read and edit it here. Nothing is saved until you say so.</li>
            <li>
              It's saved to your library{improving ? " as a new version next to the old one" : ""}, then put on the canvas and
              measured like any other skill{improving ? ": old against new" : ""}.
            </li>
          </ol>
        </Section>
        {error ? <p className="notice notice--error small">{error}</p> : null}
        {text === null ? (
          <button
            type="button"
            className="btn btn--primary"
            disabled={busy !== null}
            onClick={async () => {
              setBusy("draft");
              setError(null);
              try {
                const d = await api.draft({ name, need: lib.need, what: improving ? lib.how : lib.what, improves: improving ? lib.path : null });
                setText(d.text);
              } catch (e) {
                setError(e instanceof ApiError ? e.message : String(e));
              } finally {
                setBusy(null);
              }
            }}
          >
            {busy === "draft" ? "Writing the draft…" : "Write a Draft"}
          </button>
        ) : (
          <Section title="Draft SKILL.md">
            <label className="visually-hidden" htmlFor="draft-text">
              Draft SKILL.md
            </label>
            <textarea id="draft-text" className="input mono draft" value={text} onChange={(e) => setText(e.target.value)} />
            {saved ? (
              <p className="notice small">Saved to your library as {saved}. It's under "Created here".</p>
            ) : (
              <div className="row" style={{ gap: 8 }}>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={busy !== null || !text.trim()}
                  onClick={async () => {
                    setBusy("save");
                    try {
                      const r = await api.saveDraft({ name, text, improves: improving ? lib.path : null });
                      setSaved(r.name);
                      onSaved?.(r.path, r.name);
                    } catch (e) {
                      setError(e instanceof ApiError ? e.message : String(e));
                    } finally {
                      setBusy(null);
                    }
                  }}
                >
                  {busy === "save" ? "Saving…" : "Save to My Library"}
                </button>
                <button type="button" className="btn btn--quiet" onClick={() => setText(null)}>
                  Discard
                </button>
              </div>
            )}
          </Section>
        )}
        <p className="small muted">Drafts use a stronger model than estimates (one call), through your sign-in.</p>
      </div>
    </div>
  );
}
