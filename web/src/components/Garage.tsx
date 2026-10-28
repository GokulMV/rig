import { ArrowLeft, Sparkles, Workflow } from "lucide-react";
import { useEffect, useState, useRef } from "react";

import { ArchMini } from "./ArchMini";
import { api, ApiError } from "../lib/api";
import { setDesignParam, useDesignParams } from "../lib/designParams";
import type { GarageBlueprint, GarageCatalog, GarageEmpty, GarageEntry, GarageRecommendation, Level } from "../lib/types";

const FAMILY: Record<string, string> = { rag: "RAG", agent: "Agent" };
const AXES = ["latency", "cost", "accuracy", "complexity"] as const;
// For latency, cost and complexity, low is the good end; for accuracy, high is.
const GOOD: Record<(typeof AXES)[number], Level> = { latency: "low", cost: "low", accuracy: "high", complexity: "low" };

function Tradeoffs({ t }: { t: GarageEntry["tradeoffs"] }) {
  return (
    <div className="chips" role="list" aria-label="Trade-offs">
      {AXES.map((a) => (
        <span key={a} role="listitem" className={`pill ${t[a] === GOOD[a] ? "pill--positive" : "pill--outline"}`}>
          {a} {t[a]}
        </span>
      ))}
    </div>
  );
}

/** A parameter's name in words: the catalog's `what` text ("Which actions pause for a person"),
 * the raw key shown beside it in small mono. */
export function humanLabel(what: string | undefined, key: string): string {
  const t = (what ?? "").trim().replace(/\.$/, "");
  return t || key.replace(/_/g, " ");
}

const FIT_CLASS: Record<string, string> = { strong: "pill--positive", good: "pill--outline", possible: "pill--outline" };
const FIT_LABEL: Record<string, string> = { strong: "Strong Fit", good: "Good Fit", possible: "Possible" };

function ParamField({
  p,
  value,
  onChange,
}: {
  p: GarageEntry["parameters"][number];
  value: string;
  onChange: (v: string) => void;
}) {
  const id = `garage-param-${p.name}`;
  const hint = p.options ? p.options.join(" · ") : p.range ? `${p.range[0]} to ${p.range[1]}` : "";
  return (
    <div className="field">
      <label htmlFor={id}>
        {humanLabel(p.what, p.name)} <code className="param__key small muted">{p.name}</code>{" "}
        <span className="muted small">default {String(p.default)}</span>
      </label>
      {p.options ? (
        <select id={id} className="select" value={value} onChange={(e) => onChange(e.target.value)}>
          {p.options.map((o) => (
            <option key={String(o)} value={String(o)}>
              {String(o)}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          className="input"
          type="number"
          min={p.range?.[0]}
          max={p.range?.[1]}
          step="any"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {hint ? <span className="small muted">{hint}</span> : null}
    </div>
  );
}

function Detail({
  e,
  open,
  onBack,
  onOpen,
  onClose,
  openLabel,
}: {
  e: GarageBlueprint;
  open: boolean;
  onBack: () => void;
  onOpen: (b: GarageBlueprint) => void;
  onClose: () => void;
  openLabel: string;
}) {
  // Kept by design id across reloads, so the brief in Ship has the values you set here.
  const values = useDesignParams(e.id);
  const label = new Map(e.components.map((c) => [c.id, c.label]));
  return (
    <div className="stack" style={{ display: "grid", gap: 12 }}>
      <button type="button" className="btn btn--small btn--quiet" onClick={onBack} style={{ justifySelf: "start" }}>
        <ArrowLeft size={13} aria-hidden="true" /> All Architectures
      </button>
      <div>
        <div className="insp__label">{FAMILY[e.family]}</div>
        <h3 style={{ margin: "2px 0 4px" }}>{e.name}</h3>
        <p>{e.summary}</p>
      </div>
      <ArchMini entry={e} />
      {open ? (
        <button type="button" className="btn btn--block" onClick={onClose}>
          Stop Using This Design
        </button>
      ) : (
        <button type="button" className="btn btn--primary btn--block" onClick={() => onOpen(e)}>
          <Workflow size={14} aria-hidden="true" /> {openLabel}
        </button>
      )}
      <Tradeoffs t={e.tradeoffs} />
      <div>
        <div className="insp__label">Use it when</div>
        <p className="small">{e.when_to_use}</p>
      </div>
      <div>
        <div className="insp__label">Skip it when</div>
        <p className="small">{e.when_not_to_use}</p>
      </div>
      <div>
        <div className="insp__label">Parts and links</div>
        <ul className="small" style={{ margin: "4px 0 0", paddingLeft: 18 }}>
          {e.connections.map(([a, b, l], i) => (
            <li key={i}>
              {label.get(a) ?? a} → {label.get(b) ?? b}
              <span className="muted"> · {l}</span>
            </li>
          ))}
        </ul>
      </div>
      <form
        style={{ display: "grid", gap: 10 }}
        onSubmit={(ev) => ev.preventDefault()}
        aria-label={`Parameters of ${e.name}`}
      >
        <div className="insp__label">Parameters</div>
        <p className="small muted">Start from the defaults. Your edits are kept and go into the brief in Ship.</p>
        {e.parameters.map((p) => (
          <ParamField
            key={p.name}
            p={p}
            value={values[p.name] ?? String(p.default)}
            onChange={(v) => setDesignParam(e.id, p.name, v)}
          />
        ))}
      </form>
      <div>
        <div className="insp__label">Sources</div>
        <ul className="small garage-sources">
          {e.sources.map((s) => (
            <li key={s.url}>
              <a href={s.url} target="_blank" rel="noreferrer">
                {s.title}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** " (≈$0.01)": what asking the model costs, when the engine says. */
function cost(r: GarageRecommendation): string {
  return r.explain_usd ? ` (≈$${r.explain_usd.toFixed(2)})` : "";
}

/** The model has explained at least one pick. */
function explained(r: GarageRecommendation): boolean {
  return r.picks.some((p) => p.explanation);
}

/** No picks: what matched, the close designs (labelled as not a fit), and what to add. */
function Empty({ empty, onView }: { empty: GarageEmpty; onView: (id: string) => void }) {
  return (
    <div style={{ display: "grid", gap: 8 }}>
      <p className="small">{empty.matched}</p>
      {empty.near.length ? (
        <section aria-label={empty.heading ?? undefined} style={{ display: "grid", gap: 6 }}>
          <div className="small muted">{empty.heading}</div>
          <ul className="garage-near">
            {empty.near.map((n) => (
              <li key={n.id}>
                <span className="small">
                  <strong>{n.name}</strong> <span className="muted">· {n.matched.map((w) => `'${w}'`).join(", ")}</span>
                </span>
                <button type="button" className="btn btn--small" onClick={() => onView(n.id)} aria-label={`See This Design: ${n.name}`}>
                  See This Design
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {empty.asks.length ? (
        <div className="small">
          {empty.asks_lead}
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {empty.asks.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {empty.words ? <p className="small">{empty.words}</p> : null}
      <p className="small muted">{empty.browse}</p>
    </div>
  );
}

export function GaragePanel({
  repoId,
  useCase,
  blueprint,
  onOpen,
  onClose,
  autoRun = false,
  openLabel = "Open on the Canvas",
  onEditUseCase,
  onViewing,
}: {
  repoId: string | null;
  useCase: string | null;
  blueprint: GarageBlueprint | null;
  onOpen: (b: GarageBlueprint) => void;
  onClose: () => void;
  /** Rank at once for the use case given (the Design step). */
  autoRun?: boolean;
  openLabel?: string;
  /** With autoRun: the use case is edited in Describe, so only a link back is shown here. */
  onEditUseCase?: () => void;
  /** Parameter values changed from the defaults, by design id. */
  /** The design open in the detail view, or null on the list: Design's Next asks about it. */
  onViewing?: (b: GarageBlueprint | null) => void;
}) {
  const [catalog, setCatalog] = useState<GarageCatalog | null>(null);
  const [text, setText] = useState(useCase ?? "");
  const [explain, setExplain] = useState(false);
  const [result, setResult] = useState<GarageRecommendation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // "Explain the top three with the model": one paid call, on that click only; said while it runs.
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [family, setFamily] = useState<"all" | "rag" | "agent">("all");
  const [viewing, setViewing] = useState<GarageBlueprint | null>(blueprint);
  // A design restored after the page loaded (or chosen elsewhere) opens here too.
  useEffect(() => {
    if (blueprint) setViewing(blueprint);
  }, [blueprint?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const viewingRef = useRef(onViewing);
  viewingRef.current = onViewing;
  useEffect(() => viewingRef.current?.(viewing), [viewing]);

  useEffect(() => {
    api.garageCatalog().then(setCatalog, (e) => setError(e instanceof ApiError ? e.message : "Couldn't load the catalog."));
  }, []);
  // A different repo starts fresh; the first load of this one (null to an id) keeps what you typed.
  const lastRepo = useRef(repoId);
  useEffect(() => {
    if (lastRepo.current && repoId && lastRepo.current !== repoId) {
      setText(useCase ?? "");
      setResult(null);
    }
    lastRepo.current = repoId;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId]);
  const typed = useRef(false);
  useEffect(() => {
    if (useCase && !typed.current) setText(useCase); // the repo's use case, until you type your own
  }, [useCase]);

  const view = async (id: string) => {
    setError(null);
    try {
      setViewing(await api.garageEntry(id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't open that architecture.");
    }
  };
  const recommend = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.garageRecommend(text.trim(), repoId, explain));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't rank the architectures.");
    } finally {
      setBusy(false);
    }
  };

  const ran = useRef(false);
  useEffect(() => {
    if (autoRun && !ran.current && text.trim()) {
      ran.current = true;
      void recommend();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun, text]);

  if (viewing) {
    return (
      <Detail
        e={viewing}
        open={blueprint?.id === viewing.id}
        onBack={() => setViewing(null)}
        onOpen={onOpen}
        onClose={onClose}
        openLabel={openLabel}
      />
    );
  }

  const families = catalog?.families.filter((f) => family === "all" || f.id === family) ?? [];
  return (
    <div style={{ display: "grid", gap: 14 }}>
      {autoRun && onEditUseCase ? (
        text.trim() ? (
          <div className="garage-for small">
            <span className="muted">For</span>
            <q>{text.trim()}</q>
            <button type="button" className="linkish" onClick={onEditUseCase}>
              Change
            </button>
            {result && asking ? (
              <span className="garage-ask small" role="status">
                Asking the model{cost(result)}…
              </span>
            ) : result?.picks.length && !explained(result) ? (
              <button
                type="button"
                className="linkish"
                disabled={busy}
                onClick={async () => {
                  setAsking(true);
                  setAskError(null);
                  try {
                    const got = await api.garageRecommend(text.trim(), repoId, true);
                    setResult(got);
                    // Asked but not explained (no sign-in, the model didn't answer): its note says why.
                    if (!explained(got) && !got.note) setAskError("The model sent no explanations; the ranking is the same.");
                  } catch (e) {
                    setAskError(`Couldn't ask the model: ${e instanceof ApiError ? e.message : String(e)} The ranking is the same.`);
                  } finally {
                    setAsking(false);
                  }
                }}
              >
                Explain the Top Three with the Model{cost(result)}
              </button>
            ) : null}
          </div>
        ) : null
      ) : (
        <form
          style={{ display: "grid", gap: 8 }}
          onSubmit={(ev) => {
            ev.preventDefault();
            if (text.trim()) void recommend();
          }}
        >
          <div className="field">
            <label htmlFor="garage-use-case">What do you want to build?</label>
            <textarea
              id="garage-use-case"
              className="textarea"
              rows={3}
              value={text}
              placeholder="For example: answer questions over 500 PDFs with tables and citations"
              onChange={(e) => {
                typed.current = true;
                setText(e.target.value);
              }}
            />
          </div>
          <label className="small" style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input type="checkbox" checked={explain} onChange={(e) => setExplain(e.target.checked)} />
            Explain the top three with the model
          </label>
          <button type="submit" className="btn btn--primary" disabled={busy || !text.trim()}>
            <Sparkles size={14} aria-hidden="true" /> {busy ? "Ranking…" : "Recommend"}
          </button>
        </form>
      )}
      {error ? <p className="notice notice--error small">{error}</p> : null}
      {askError ? (
        <p className="notice notice--error small" role="alert">
          {askError}
        </p>
      ) : null}
      {result ? (
        <section aria-label="Recommended architectures" style={{ display: "grid", gap: 8 }}>
          <div className="insp__label">{!result.picks.length && result.empty ? result.empty.title : "Best fits"}</div>
          {result.note ? <p className="notice small">{result.note}</p> : null}
          {result.picks.length ? (
            <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
              {result.picks.map((r, n) => (
                <li key={r.id} className="prop">
                  <button type="button" className="prop__title" onClick={() => void view(r.id)}>
                    {n + 1}. {r.entry.name}
                  </button>
                  <span className="small muted row" style={{ gap: 6 }}>
                    <span className={`pill ${FIT_CLASS[r.fit ?? "possible"]}`} data-testid="fit-label">
                      {r.fit_label ?? FIT_LABEL[r.fit ?? (r.weak ? "possible" : "good")]}
                    </span>
                    {FAMILY[r.entry.family]}
                  </span>
                  <p className="small">{r.entry.summary}</p>
                  <ArchMini entry={r.entry} />
                  <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                    {r.reasons.map((why, i) => (
                      <li key={i}>{why}</li>
                    ))}
                  </ul>
                  {r.explanation ? <p className="small">{r.explanation}</p> : null}
                  <button type="button" className="btn btn--small" style={{ justifySelf: "start" }} onClick={() => void view(r.id)}>
                    See This Design
                  </button>
                </li>
              ))}
            </ol>
          ) : result.empty ? (
            <Empty empty={result.empty} onView={(id) => void view(id)} />
          ) : null}
        </section>
      ) : null}
      <section aria-label="Catalog" style={{ display: "grid", gap: 8 }}>
        <div className="insp__label">All architectures{catalog ? ` · ${catalog.count}` : ""}</div>
        <div className="chips" role="radiogroup" aria-label="Family">
          {(["all", "rag", "agent"] as const).map((f) => (
            <button key={f} type="button" role="radio" aria-checked={family === f} className="chip" onClick={() => setFamily(f)}>
              {f === "all" ? "All" : FAMILY[f]}
            </button>
          ))}
        </div>
        {catalog === null && !error ? <p className="muted small">Loading…</p> : null}
        {families.map((f) => (
          <div key={f.id} style={{ display: "grid", gap: 6 }}>
            <div className="small muted">{FAMILY[f.id] ?? f.id}</div>
            <ul className="archcards">
              {f.entries.map((e) => (
                <li key={e.id}>
                  <button type="button" className="archcard" onClick={() => void view(e.id)}>
                    <span className="archcard__name">{e.name}</span>
                    <ArchMini entry={e} />
                    <span className="archcard__summary small muted">{e.summary}</span>
                    <span className="archcard__trade small">
                      {AXES.map((a) => (
                        <span key={a} className={e.tradeoffs[a] === GOOD[a] ? "is-good" : undefined}>
                          {a} {e.tradeoffs[a]}
                        </span>
                      ))}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>
    </div>
  );
}
