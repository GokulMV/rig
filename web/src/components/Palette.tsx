import {
  BookOpen,
  Bot,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Gauge,
  Layers,
  type LucideIcon,
  Plug,
  Plus,
  Search,
  Star,
  Webhook,
  Workflow,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../lib/api";
import { consumeDragClick, startSkillDrag } from "../lib/dragSkill";
import { searchItems, searchSplit } from "../lib/librarySearch";
import { ProvenRig } from "./RigScore";
import type {
  CatalogCategory,
  CatalogItem,
  CatalogKind,
  CatalogPage,
  CatalogView,
  Recommendation,
  Suggestion,
  TreatmentItem,
  Treatments,
} from "../lib/types";

/** Each kind's icon; its name and one-line explanation come from the catalog (curate-catalog). */
const ICON: Record<CatalogCategory, LucideIcon> = {
  skill: BookOpen,
  agent: Bot,
  mcp: Plug,
  hook: Webhook,
  harness: Layers,
  workflow: Workflow,
  eval: Gauge,
};
const VIEWS: { id: CatalogView; label: string; top: string }[] = [
  { id: "recommended", label: "Recommended", top: "Recommended" },
  { id: "stars", label: "Most Starred", top: "Most starred" },
  { id: "latest", label: "Latest", top: "Most recently updated" },
  {
    id: "relevant",
    label: "Picked for This Repo",
    top: "Picked for this repo",
  },
];
const TOP = 6;

function stars(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n);
}

export function ago(iso: string): string {
  const days = Math.max(
    0,
    Math.round((Date.now() - Date.parse(iso)) / 86_400_000),
  );
  return days === 0
    ? "today"
    : days === 1
      ? "yesterday"
      : days < 60
        ? `${days}d ago`
        : `${Math.round(days / 30)}mo ago`;
}

/** What the details panel shows for a library item. */
export type LibraryItem =
  | { from: "github"; data: string; name: string; item: CatalogItem }
  | {
      from: "local";
      data: string;
      name: string;
      where: string;
      t: TreatmentItem;
    }
  | { from: "suggested"; data: string; name: string; s: Suggestion }
  | {
      from: "create";
      data: string;
      name: string;
      need: string;
      what: string;
      why: string;
    }
  | {
      from: "improve";
      data: string;
      name: string;
      path: string;
      need: string;
      how: string;
      why: string;
    };

interface Props {
  repoId: string;
  treatments: Treatments | null;
  selected: string | null;
  /** Add at an open spot on the canvas (the click path, next to dragging). */
  onAdd: (lib: LibraryItem) => void;
  /** Show the item in the details panel. */
  onInspect: (item: LibraryItem) => void;
}

function Item({
  lib,
  sub,
  meta,
  selected,
  onAdd,
  onInspect,
}: {
  lib: LibraryItem;
  sub?: string;
  meta?: React.ReactNode;
  selected: boolean;
  onAdd: Props["onAdd"];
  onInspect: Props["onInspect"];
}) {
  return (
    <li className={`pal-item${selected ? " is-selected" : ""}`}>
      <button
        type="button"
        className="pal-item__main item--draggable"
        aria-pressed={selected}
        onPointerDown={(e) =>
          startSkillDrag(
            e,
            lib.data,
            lib.name,
            lib.from === "github"
              ? { category: lib.item.category, name: lib.name }
              : undefined,
          )
        }
        onClick={() => {
          if (!consumeDragClick()) onInspect(lib);
        }}
        title="Click for details, drag onto the canvas"
      >
        <span className="pal-item__name">{lib.name}</span>
        {sub ? <span className="pal-item__sub">{sub}</span> : null}
        {meta ? <span className="pal-item__meta">{meta}</span> : null}
      </button>
      <button
        type="button"
        className="pal-item__add"
        aria-label={`Add ${lib.name} to the canvas`}
        onClick={() => onAdd(lib)}
      >
        <Plus size={14} />
      </button>
    </li>
  );
}

function Group({
  title,
  count,
  open,
  children,
}: {
  title: string;
  count: number;
  open?: boolean;
  children: React.ReactNode;
}) {
  return (
    <details className="pal-group" open={open}>
      <summary>
        <span className="pal-group__title">{title}</span>
        <span className="pal-group__count num">{count}</span>
      </summary>
      <ul className="pal-list">{children}</ul>
    </details>
  );
}

/** Matches that only a topic, a theme or scattered words found: folded away, after the strong ones. */
function Weaker({ count, children }: { count: number; children: React.ReactNode }) {
  if (!count) return null;
  return (
    <details className="pal-group pal-weaker">
      <summary>
        <span className="pal-group__title">Weaker matches ({count})</span>
      </summary>
      <ul className="pal-list">{children}</ul>
    </details>
  );
}

function githubLib(it: CatalogItem): LibraryItem {
  return { from: "github", data: `catalog:${it.id}`, name: it.name, item: it };
}

function Meta({ it }: { it: CatalogItem }) {
  return (
    <>
      <span className="num">
        <Star size={11} aria-hidden="true" /> {stars(it.stars)}
      </span>
      <span>{it.owner}</span>
      <span>{ago(it.pushed_at)}</span>
      {it.pinned && (
        <span title="A canonical repository, picked by hand">well known</span>
      )}
      {it.fit_note ? <FitNote note={it.fit_note} /> : null}
    </>
  );
}

/** What a run on a bench measured for a skill, on its library row. */
function ProvenMeta({ proven }: { proven: NonNullable<TreatmentItem["proven"]> }) {
  return (
    <span
      className="num"
      data-testid="proven-badge"
      title={`Measured on ${proven.bench}: ${proven.pairs} pairs`}
    >
      <ProvenRig proven={proven} />
      {proven.rig != null ? " " : ""}
      {proven.verdict === "helps"
        ? `measured ${proven.diff_pts > 0 ? "+" : ""}${Math.round(proven.diff_pts)}`
        : proven.verdict === "hurts"
          ? `measured ${Math.round(proven.diff_pts)}, hurts`
          : "measured, no effect"}
    </span>
  );
}

/** Written for a language the repo has none of: said on the row, never hidden. */
function FitNote({ note }: { note: string }) {
  return (
    <span className="fit-note" data-testid="fit-note">
      {note}
    </span>
  );
}

/** "Sort: Recommended ▾": a small menu, not a full-width select. */
function SortMenu({
  view,
  onChange,
}: {
  view: CatalogView;
  onChange: (v: CatalogView) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const current = VIEWS.find((x) => x.id === view)!;
  useEffect(() => {
    if (!open) return;
    wrap.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus();
    const away = (e: PointerEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);
  const pick = (v: CatalogView) => {
    setOpen(false);
    onChange(v);
    button.current?.focus();
  };
  return (
    <div className="sortmenu" ref={wrap}>
      <button
        ref={button}
        type="button"
        className="sortmenu__button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Sort: ${current.label}`}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="muted">Sort:</span> {current.label}{" "}
        <ChevronDown size={13} aria-hidden="true" />
      </button>
      {open ? (
        <ul
          className="sortmenu__list"
          role="menu"
          aria-label="Sort"
          onKeyDown={(e) => {
            const items = [
              ...(wrap.current?.querySelectorAll<HTMLElement>(
                '[role="menuitemradio"]',
              ) ?? []),
            ];
            const at = items.indexOf(document.activeElement as HTMLElement);
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              items[
                (at + (e.key === "ArrowDown" ? 1 : items.length - 1)) %
                  items.length
              ]?.focus();
            } else if (e.key === "Home" || e.key === "End") {
              e.preventDefault();
              items[e.key === "Home" ? 0 : items.length - 1]?.focus();
            } else if (e.key === "Escape" || e.key === "Tab") {
              // Closes the menu only; the Library doesn't also go back.
              if (e.key === "Escape") {
                e.preventDefault();
                e.stopPropagation();
                button.current?.focus();
              }
              setOpen(false);
            }
          }}
        >
          {VIEWS.map((x) => (
            <li key={x.id} role="none">
              <button
                type="button"
                role="menuitemradio"
                aria-checked={x.id === view}
                tabIndex={-1}
                onClick={() => pick(x.id)}
              >
                <Check
                  size={13}
                  aria-hidden="true"
                  className="sortmenu__check"
                />
                {x.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** One kind on the Library's home: what it is, why you'd add one, and how many there are. */
function KindTile({
  kind,
  count,
  onOpen,
}: {
  kind: CatalogKind;
  count: number | null;
  onOpen: () => void;
}) {
  const Icon = ICON[kind.id];
  return (
    <li>
      <button
        type="button"
        className="kind-tile"
        data-kind={kind.id}
        aria-label={count === null ? kind.label : `${kind.label}, ${count}`}
        aria-describedby={`kind-blurb-${kind.id}`}
        onClick={onOpen}
      >
        <span
          className={`kind-tile__icon kind-tile__icon--${kind.id}`}
          aria-hidden="true"
        >
          <Icon size={17} />
        </span>
        <span className="kind-tile__text">
          <span className="kind-tile__label">{kind.label}</span>
          <span className="kind-tile__blurb" id={`kind-blurb-${kind.id}`}>
            {kind.blurb}
          </span>
        </span>
        <span className="kind-tile__count num" aria-hidden="true">
          {count ?? ""}
        </span>
        <ChevronRight size={15} aria-hidden="true" className="kind-tile__go" />
      </button>
    </li>
  );
}

export function Palette({
  repoId,
  treatments,
  selected,
  onAdd,
  onInspect,
}: Props) {
  /** null: the home, the kinds; else the kind drilled into. */
  const [kind, setKind] = useState<CatalogCategory | null>(null);
  const [view, setView] = useState<CatalogView>("recommended");
  const [q, setQ] = useState("");
  const [page, setPage] = useState<{
    scope: string;
    view: CatalogView;
    p: CatalogPage;
  } | null>(null);
  const [kinds, setKinds] = useState<CatalogKind[]>([]);
  const [error, setError] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const backTo = useRef<CatalogCategory | null>(null);
  const drilled = useRef(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const scope = kind ?? "all";
  const pageView = kind ? view : "recommended";

  useEffect(() => {
    let live = true;
    let timer: number | undefined;
    const load = async () => {
      try {
        const p = await api.catalog(scope, pageView, q);
        if (!live) return;
        setPage({ scope, view: pageView, p });
        if (p.kinds?.length) setKinds(p.kinds);
        setError(null);
        // The first build runs in the background: check again until it is ready.
        if (p.loading) timer = window.setTimeout(load, 3000);
      } catch (e) {
        if (live) setError(String((e as Error).message ?? e));
      }
    };
    const t = window.setTimeout(load, q ? 250 : 0);
    return () => {
      live = false;
      window.clearTimeout(t);
      if (timer) window.clearTimeout(timer);
    };
  }, [scope, pageView, q, repoId]);

  // "/" (or "+", to add something) puts the cursor in the search, unless you are typing somewhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (
        (e.key !== "/" && e.key !== "+") ||
        e.metaKey ||
        e.ctrlKey ||
        e.altKey ||
        e.defaultPrevented
      )
        return;
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))
      )
        return;
      const input = searchRef.current;
      if (!input || !input.offsetParent) return; // the Library is hidden
      e.preventDefault();
      input.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Into a kind, the focus goes to its title (the tile clicked is gone); back on the home, to
  // the kind you came from.
  useEffect(() => {
    if (kind !== null) {
      if (drilled.current) headingRef.current?.focus();
      drilled.current = false;
      return;
    }
    if (backTo.current === null) return;
    const id = backTo.current;
    backTo.current = null;
    bodyRef.current?.querySelector<HTMLElement>(`[data-kind="${id}"]`)?.focus();
  }, [kind]);

  const openKind = (k: CatalogCategory) => {
    drilled.current = true;
    setKind(k);
    setView("recommended");
    bodyRef.current?.scrollTo?.({ top: 0 });
  };
  const goHome = () => {
    backTo.current = q ? null : kind;
    setKind(null);
    if (q) searchRef.current?.focus();
  };

  const localLists = useMemo(() => {
    if (!treatments) return null;
    const find = <T extends { name: string; description?: string }>(
      list: T[],
      extra?: (x: T) => string,
    ) =>
      searchItems(
        list.map((x) => ({ ...x, extra: extra?.(x) })),
        q,
      ) as T[];
    return {
      repo: find(treatments.repo, (t) => t.source ?? ""),
      user: find(treatments.user, (t) => t.source ?? ""),
      installed: find(treatments.installed ?? [], (t) => t.source ?? ""),
      created: find(treatments.created ?? [], (t) => t.source ?? ""),
      suggested: find(
        treatments.suggested.map((s) => ({ ...s, description: s.why })),
        () => "",
      ),
    };
  }, [treatments, q]);
  const localCount = treatments
    ? treatments.repo.length +
      treatments.user.length +
      (treatments.installed ?? []).length +
      (treatments.created ?? []).length
    : 0;

  const fresh =
    page && page.scope === scope && page.view === pageView ? page.p : null;
  const items = fresh?.items ?? [];
  // A search's weak matches (only a topic, a theme or scattered words) fold away at the end.
  const strongItems = useMemo(() => items.filter((i) => !i.weak), [items]);
  const weakItems = useMemo(() => items.filter((i) => i.weak), [items]);
  const top = strongItems.slice(0, TOP);
  // Themes in the order of their best item, so the sort decides what comes first.
  const byTheme = useMemo(() => {
    const m = new Map<string, CatalogItem[]>();
    for (const i of strongItems.slice(TOP))
      m.set(i.theme, [...(m.get(i.theme) ?? []), i]);
    return [...m.entries()];
  }, [strongItems]);
  const v = VIEWS.find((x) => x.id === view)!;
  const has = (list: { length: number } | undefined) => Boolean(list?.length);
  const label = (k: CatalogCategory) =>
    kinds.find((x) => x.id === k)?.label ?? k;
  const counts = fresh?.counts ?? page?.p.counts ?? {};

  const row = (lib: LibraryItem, sub?: string, meta?: React.ReactNode) => (
    <Item
      key={lib.data}
      lib={lib}
      sub={sub}
      meta={meta}
      selected={selected === `lib:${lib.data}`}
      onAdd={onAdd}
      onInspect={onInspect}
    />
  );

  const localRow = (t: TreatmentItem, where: string) =>
    row(
      { from: "local", data: `skill:${t.path}`, name: t.name, where, t },
      t.source ?? t.description,
      t.fit_note || t.proven ? (
        <>
          {t.fit_note ? <FitNote note={t.fit_note} /> : null}
          {t.proven ? <ProvenMeta proven={t.proven} /> : null}
        </>
      ) : undefined,
    );
  const localGroups = localLists
    ? ([
        ["In this repo", localLists.repo, "in this repo"],
        ["Your skills", localLists.user, "in your skills folder"],
        [
          "Installed from GitHub",
          localLists.installed,
          "installed from GitHub",
        ],
        ["Created here", localLists.created, "created here"],
      ] as const)
    : [];
  const anyLocal =
    localLists &&
    (has(localLists.repo) ||
      has(localLists.user) ||
      has(localLists.installed) ||
      has(localLists.created) ||
      has(localLists.suggested));

  const loadingNote =
    !fresh || (fresh.loading && items.length === 0) ? (
      <p className="small muted" aria-live="polite">
        Fetching the catalog from GitHub. The first time takes a minute or two.
      </p>
    ) : null;

  const home = (
    <>
      {error ? <p className="notice notice--error small">{error}</p> : null}
      {kinds.length === 0 && !error ? (
        <p className="small muted" aria-live="polite">
          Opening the library…
        </p>
      ) : null}
      <ul className="kind-tiles" aria-label="Kinds">
        {kinds.map((k) => (
          <KindTile
            key={k.id}
            kind={k}
            count={
              counts[k.id] === undefined
                ? null
                : (counts[k.id] ?? 0) + (k.id === "skill" ? localCount : 0)
            }
            onOpen={() => openKind(k.id)}
          />
        ))}
      </ul>
    </>
  );

  // Searching from the home: your own skills first, best match first, each saying where it is;
  // weak matches fold away under them.
  const localSplit = searchSplit(
    localGroups.flatMap(([, list, where]) =>
      list.map((t) => ({
        name: t.name,
        description: t.description,
        extra: t.source ?? "",
        t,
        where,
      })),
    ),
    q,
  );
  const allLocal = localSplit.strong;
  const firstAt = (k: CatalogCategory) => {
    const i = items.findIndex((x) => x.category === k);
    return i < 0 ? Infinity : i;
  };
  const results = (
    <>
      {error ? <p className="notice notice--error small">{error}</p> : null}
      {allLocal.length || localSplit.weak.length ? (
        <section className="pal-section" aria-label="Matches on this machine">
          <div className="pal-kindhead">
            <span className="pal-kindhead__label">
              <BookOpen size={14} aria-hidden="true" /> Your skills, on this
              machine
            </span>
            <span className="pal-group__count num">{allLocal.length}</span>
          </div>
          {allLocal.length ? (
            <ul className="pal-list">
              {allLocal.slice(0, 5).map(({ t, where }) => localRow(t, where))}
            </ul>
          ) : null}
          <Weaker count={localSplit.weak.length}>
            {localSplit.weak.map(({ t, where }) => localRow(t, where))}
          </Weaker>
          {allLocal.length > 5 ? (
            <button
              type="button"
              className="linkish pal-more"
              onClick={() => openKind("skill")}
            >
              All {allLocal.length} in Skills{" "}
              <ChevronRight size={13} aria-hidden="true" />
            </button>
          ) : null}
        </section>
      ) : null}
      {loadingNote}
      {/* The kind with the best match first (the server sends the matches best first). */}
      {[...kinds]
        .sort((a, b) => firstAt(a.id) - firstAt(b.id))
        .map((k) => {
          const n = fresh?.matches?.[k.id] ?? 0;
          const list = strongItems.filter((i) => i.category === k.id);
          const weak = weakItems.filter((i) => i.category === k.id);
          if (!n || !(list.length + weak.length)) return null;
          const Icon = ICON[k.id];
          return (
            <section
              key={k.id}
              className="pal-section"
              aria-label={`Matches in ${k.label}`}
            >
              <div className="pal-kindhead">
                <span className="pal-kindhead__label">
                  <Icon size={14} aria-hidden="true" /> {k.label}
                </span>
                <span className="pal-group__count num">{n}</span>
              </div>
              {list.length ? (
                <ul className="pal-list">
                  {list.map((it) =>
                    row(githubLib(it), it.description, <Meta it={it} />),
                  )}
                </ul>
              ) : null}
              <Weaker count={weak.length}>
                {weak.map((it) => row(githubLib(it), it.description, <Meta it={it} />))}
              </Weaker>
              {n > list.length + weak.length ? (
                <button
                  type="button"
                  className="linkish pal-more"
                  onClick={() => openKind(k.id)}
                >
                  All {n} in {k.label}{" "}
                  <ChevronRight size={13} aria-hidden="true" />
                </button>
              ) : null}
            </section>
          );
        })}
      {fresh &&
      !fresh.loading &&
      !allLocal.length &&
      !localSplit.weak.length &&
      !Object.values(fresh.matches ?? {}).some(Boolean) ? (
        <p className="small muted">Nothing matches “{q.trim()}” in any kind.</p>
      ) : null}
    </>
  );

  const kindView = kind ? (
    <>
      {kind === "skill" && localLists && anyLocal ? (
        <div className="pal-section">
          <div className="pal-section__title">On This Machine</div>
          {localGroups.map(([title, list, where]) =>
            list.length ? (
              <Group
                key={title}
                title={title}
                count={list.length}
                open={list.length <= 6 || Boolean(q)}
              >
                {list.map((t) => localRow(t, where))}
              </Group>
            ) : null,
          )}
          {localLists.suggested.length ? (
            <Group
              title="Suggested for this repo"
              count={localLists.suggested.length}
              open
            >
              {localLists.suggested.map((s) =>
                row(
                  {
                    from: "suggested",
                    data: `suggestion:${s.workflow}/${s.name}`,
                    name: s.name,
                    s,
                  },
                  s.why,
                ),
              )}
            </Group>
          ) : null}
        </div>
      ) : null}

      {view === "relevant" ? (
        <Picked
          tab={kind}
          kindLabel={label(kind)}
          repoId={repoId}
          local={treatments}
          row={row}
          onShowRecommended={() => setView("recommended")}
        />
      ) : (
        <div className="pal-section">
          <div className="pal-section__title">From GitHub</div>
          {error ? <p className="notice notice--error small">{error}</p> : null}
          {loadingNote}
          {fresh?.partial ? (
            <p className="small muted">
              Some searches failed; showing what came back. Retrying soon.
            </p>
          ) : null}
          {fresh && !fresh.loading && items.length === 0 ? (
            <p className="small muted">
              {q
                ? `Nothing in ${label(kind)} matches “${q.trim()}”.`
                : "Nothing here yet."}
            </p>
          ) : null}
          {top.length ? (
            <div className="pal-top">
              <div className="pal-top__title">{q ? "Best matches" : v.top}</div>
              <ul className="pal-list">
                {top.map((it) =>
                  row(githubLib(it), it.description, <Meta it={it} />),
                )}
              </ul>
            </div>
          ) : null}
          {byTheme.map(([theme, list]) => (
            <Group
              key={theme}
              title={theme}
              count={list.length}
              open={Boolean(q)}
            >
              {list.map((it) =>
                row(githubLib(it), it.description, <Meta it={it} />),
              )}
            </Group>
          ))}
          <Weaker count={weakItems.length}>
            {weakItems.map((it) => row(githubLib(it), it.description, <Meta it={it} />))}
          </Weaker>
          {fresh && (fresh.matches?.[kind] ?? 0) > items.length ? (
            <p className="small muted pal-cap">
              Showing the first {items.length} of {fresh.matches?.[kind]}.
              Search to find the rest.
            </p>
          ) : null}
        </div>
      )}
    </>
  ) : null;

  const KindIcon = kind ? ICON[kind] : null;
  return (
    <section
      className="pane palette"
      aria-label="Library"
      onKeyDown={(e) => {
        if (e.key !== "Escape" || e.defaultPrevented) return;
        // Esc goes up one level: from a kind to the home; on the home, it clears the search.
        if (kind) {
          e.preventDefault();
          goHome();
        } else if (q) {
          e.preventDefault();
          setQ("");
        }
      }}
    >
      <div className="palette__top">
        <div className="palette__head">
          {kind && KindIcon ? (
            <div className="palette__crumbs">
              <button
                type="button"
                className="palette__back"
                aria-label="Library: all kinds"
                onClick={goHome}
              >
                <ChevronLeft size={15} aria-hidden="true" />
                Library
              </button>
              <span className="palette__sep" aria-hidden="true">
                /
              </span>
              <h2 ref={headingRef} tabIndex={-1}>
                <KindIcon size={15} aria-hidden="true" /> {label(kind)}
              </h2>
            </div>
          ) : (
            <h2>Library</h2>
          )}
        </div>
        <div className="palette__controls">
          <label className="search">
            <Search size={15} aria-hidden="true" />
            <span className="visually-hidden">
              {kind ? `Search ${label(kind)}` : "Search the library"}
            </span>
            <input
              ref={searchRef}
              type="search"
              placeholder={
                kind
                  ? `Search ${label(kind).toLowerCase()}`
                  : "Search every kind"
              }
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-keyshortcuts="/ +"
            />
            <kbd className="search__key" aria-hidden="true">
              /
            </kbd>
          </label>
          {kind ? (
            <div className="palette__sortrow">
              <span className="small muted num">
                {fresh?.matches?.[kind] !== undefined
                  ? `${fresh.matches[kind]}${q ? " matching" : ""} from GitHub`
                  : ""}
              </span>
              <SortMenu view={view} onChange={setView} />
            </div>
          ) : null}
        </div>
      </div>
      <div className="palette__body" ref={bodyRef}>
        {kind ? kindView : q.trim() ? results : home}
      </div>
    </section>
  );
}

/** "Picked for this repo": what the repo needs, what serves each need, and what to create or rewrite. */
function Picked({
  tab,
  kindLabel,
  repoId,
  local,
  row,
  onShowRecommended,
}: {
  tab: CatalogCategory;
  kindLabel: string;
  repoId: string;
  local: Treatments | null;
  row: (
    lib: LibraryItem,
    sub?: string,
    meta?: React.ReactNode,
  ) => React.ReactNode;
  onShowRecommended: () => void;
}) {
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The rough picker by default (no model); the model only on "Ask the model to pick".
  const load = (refresh = false, model = false) => {
    setBusy(true);
    setError(null);
    api
      .recommend(tab, refresh, model)
      .then(setRec, (e) => setError(String((e as Error).message ?? e)))
      .finally(() => setBusy(false));
  };
  useEffect(() => {
    setRec(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, repoId]);

  const localByPath = new Map(
    [
      ...(local?.repo ?? []),
      ...(local?.user ?? []),
      ...(local?.installed ?? []),
      ...(local?.created ?? []),
    ].map((t) => [t.path, t]),
  );
  const kind = kindLabel.toLowerCase();

  if (error) return <p className="notice notice--error small">{error}</p>;
  if (!rec)
    return (
      <p className="small muted" aria-live="polite">
        {busy ? "Reading what this repo needs…" : ""}
      </p>
    );
  const nothing =
    !rec.picks.length && !rec.create.length && !rec.improve.length;

  return (
    <div className="pal-section picked">
      <details className="needs">
        <summary>
          What This Repo Needs{" "}
          <span className="pal-group__count num">{rec.needs.length}</span>
        </summary>
        <ul>
          {rec.needs.map((n) => (
            <li key={n.text}>
              <span className="needs__src">{n.source}</span> {n.text}
            </li>
          ))}
        </ul>
      </details>

      <div className="picked__basis small muted">
        {rec.basis === "model" ? "Picked by the cheapest model from the repo's needs." : "Rough picks from the repo's needs, no model."}{" "}
        <button type="button" className="linkish" disabled={busy} onClick={() => load(true, true)}>
          {busy
            ? "Picking…"
            : `${rec.basis === "model" ? "Ask the model again" : "Ask the model to pick"}${rec.model_pick_usd != null ? ` (≈$${rec.model_pick_usd.toFixed(2)})` : ""}`}
        </button>
        {rec.note ? <span className="block">{rec.note}</span> : null}
      </div>

      {rec.picks.length ? (
        <div className="pal-top">
          <div className="pal-top__title">Picked for this repo</div>
          <ul className="pal-list">
            {rec.picks.map((p) =>
              p.item
                ? row(
                    {
                      from: "github",
                      data: `catalog:${p.item.id}`,
                      name: p.item.name,
                      item: p.item,
                    },
                    p.why,
                    <span className="need-tag" title={p.need}>
                      for: {p.need}
                    </span>,
                  )
                : null,
            )}
          </ul>
        </div>
      ) : null}

      {rec.create.length ? (
        <div className="pal-top">
          <div className="pal-top__title">Nothing fits: create</div>
          <ul className="pal-list">
            {rec.create.map((c) =>
              row(
                {
                  from: "create",
                  data: `create:${c.name}`,
                  name: c.name,
                  need: c.need,
                  what: c.what,
                  why: c.why,
                },
                c.why,
                <span className="need-tag need-tag--new">
                  new skill · for: {c.need}
                </span>,
              ),
            )}
          </ul>
        </div>
      ) : null}

      {rec.improve.length ? (
        <div className="pal-top">
          <div className="pal-top__title">Improve what you have</div>
          <ul className="pal-list">
            {rec.improve.map((c) => {
              const t = localByPath.get(c.path);
              const name = t?.name ?? c.path.split("/").pop() ?? c.path;
              return row(
                {
                  from: "improve",
                  data: `improve:${c.path}`,
                  name,
                  path: c.path,
                  need: c.need,
                  how: c.how,
                  why: c.why,
                },
                c.how,
                <span className="need-tag need-tag--new">
                  rewrite · for: {c.need}
                </span>,
              );
            })}
          </ul>
        </div>
      ) : null}

      {nothing ? (
        <div className="picked__empty">
          <p className="small">
            None of the {kind} in the library serve what this repo needs
            {rec.creatable ? ", and nothing to create came up" : ""}.
          </p>
          <button
            type="button"
            className="btn btn--small"
            onClick={onShowRecommended}
          >
            Show Recommended Instead
          </button>
        </div>
      ) : null}
    </div>
  );
}
