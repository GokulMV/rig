import { Maximize2, Minus, Plus, X } from "lucide-react";
import { type ReactNode, type PointerEvent as RPointerEvent, useCallback, useEffect, useRef, useState } from "react";

import { type DragMeta, registerDropTarget } from "../lib/dragSkill";

export interface CanvasNode {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  /** Rendered inside a box positioned at (x, y) in canvas space. */
  render: (state: { dragging: boolean; target: boolean }) => ReactNode;
  /** Optional accessible name for the node's wrapper. */
  label?: string;
  draggable?: boolean;
  /** In/out handles on the left and right edges (default true when linking is on). */
  ports?: boolean;
}

export interface CanvasEdge {
  id?: string;
  from: string;
  to: string;
  /** Marks the edge as live (animated flow), e.g. while a run is in progress. */
  live?: boolean;
  /** A short pill at the middle of the edge. */
  label?: string;
  /** The full text behind a short label, shown on hover. */
  title?: string;
  /** link: a skill applied to a block; planned: not built yet; new: proposed by a suggestion. */
  variant?: "flow" | "link" | "planned" | "new" | "removed";
  /** Faded while a flow is highlighted and this edge isn't on it. */
  dim?: boolean;
  /** Its number in the highlighted flow. */
  step?: number;
  /** When set, the label carries a remove button with this accessible name. */
  onRemove?: () => void;
  removeLabel?: string;
}

interface Props {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  onMove?: (id: string, x: number, y: number) => void;
  onMoveEnd?: (id: string) => void;
  /** A link drawn from a node's [data-port] handle and released on another node. */
  onConnect?: (from: string, to: string) => void;
  /** Can a link from `from` end on `to`? */
  canConnect?: (from: string, to: string) => boolean;
  /** A node to mark as the target (for example the step a dragged card will link to). */
  highlight?: string | null;
  /** Accept skills dragged from the library (lib/dragSkill) anywhere on the grid. */
  onDropAt?: (data: string, x: number, y: number, visible: Rect, meta?: DragMeta) => void;
  /** Size of the card a drop creates, so it lands fully inside the visible area. */
  dropSize?: { w: number; h: number };
  /** Floating panels, positioned by their own classes. */
  overlays?: ReactNode;
  label: string;
  /** Fit again whenever this changes (for example when the layout switches). */
  fitKey?: string;
  /** A map to read, not edit: on open it fits all of it, down to 35%, not just down to 70%. */
  overview?: boolean;
  /** Fit to the width only and let the canvas grow tall (phones). */
  grow?: boolean;
  /** Pan (at the same zoom) to bring this area into view whenever `key` changes: what was just
   * placed. An area larger than the view shows from its top-left corner. */
  reveal?: { key: string; rect: Rect } | null;
}

export interface Rect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

const MIN = 0.4;
const MAX = 1.6;
const PAD = 48;
const TOP = 150;

function bounds(nodes: CanvasNode[]) {
  const xs = nodes.flatMap((n) => [n.x, n.x + n.w]);
  const ys = nodes.flatMap((n) => [n.y, n.y + n.h]);
  return { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) };
}

/** A curve between the facing sides of two nodes: across, back, up or down. Returns the path and
 *  the midpoint between its two ends (in the gap between the boxes, where a label belongs). */
function edgeGeometry(a: CanvasNode, b: CanvasNode): { d: string; mx: number; my: number; gap: number; across: boolean } {
  const acx = a.x + a.w / 2;
  const bcx = b.x + b.w / 2;
  const overlapX = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) > 0;
  let sx: number, sy: number, tx: number, ty: number;
  let c1: [number, number], c2: [number, number];
  let across = false;
  if (overlapX && b.y + b.h < a.y) {
    [sx, sy, tx, ty] = [acx, a.y, bcx, b.y + b.h];
    const dy = (sy - ty) / 2;
    [c1, c2] = [[sx, sy - dy], [tx, ty + dy]];
  } else if (overlapX && b.y > a.y + a.h) {
    [sx, sy, tx, ty] = [acx, a.y + a.h, bcx, b.y];
    const dy = (ty - sy) / 2;
    [c1, c2] = [[sx, sy + dy], [tx, ty - dy]];
  } else {
    across = true;
    const forward = bcx >= acx;
    [sx, sy, tx, ty] = [forward ? a.x + a.w : a.x, a.y + a.h / 2, forward ? b.x : b.x + b.w, b.y + b.h / 2];
    const dx = Math.max(30, Math.abs(tx - sx) / 2) * (forward ? 1 : -1);
    [c1, c2] = [[sx + dx, sy], [tx - dx, ty]];
  }
  const d = `M${sx},${sy} C${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${tx},${ty}`;
  // The curve's own midpoint, B(0.5): where a label sits on the line.
  // The room between the two boxes, along the line: a label wider than it would cover a card.
  const gap = across ? Math.abs(tx - sx) : Math.abs(ty - sy);
  return { d, mx: (sx + 3 * c1[0] + 3 * c2[0] + tx) / 8, my: (sy + 3 * c1[1] + 3 * c2[1] + ty) / 8, gap, across };
}

/** A pannable, zoomable dotted grid with nodes, curved edges and floating overlays. */
// The least zoom a reveal (showing a just-dropped layout) goes to: below it labels can't be read.
const REVEAL_MIN = 0.45;

export function Canvas({
  nodes,
  edges,
  onMove,
  onMoveEnd,
  onConnect,
  canConnect,
  highlight,
  onDropAt,
  dropSize,
  overlays,
  label,
  fitKey,
  overview,
  grow,
  reveal,
}: Props) {
  const host = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [height, setHeight] = useState<number | undefined>(undefined);
  const [dropOver, setDropOver] = useState(false);
  // A node press becomes a drag only after it moves 4px; otherwise it stays a click.
  type Drag = { id: string; dx: number; dy: number; sx: number; sy: number; moved: boolean };
  // `reverse`: drawn from an in-handle, so the new edge ends at `from`.
  type Link = { from: string; x: number; y: number; over: string | null; reverse: boolean };
  const [drag, setDragState] = useState<Drag | null>(null);
  const [link, setLinkState] = useState<Link | null>(null);
  // Pointer-up can arrive before React re-renders after the last move, so the handlers read refs.
  const dragRef = useRef<Drag | null>(null);
  const linkRef = useRef<Link | null>(null);
  const setDrag = (d: Drag | null) => {
    dragRef.current = d;
    setDragState(d);
  };
  const setLink = (l: Link | null) => {
    linkRef.current = l;
    setLinkState(l);
  };
  const swallowClick = useRef(false);
  const pan = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  const fitted = useRef<string | undefined | null>(null);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const [motion] = useState(
    () => typeof window !== "undefined" && !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  );

  // On open, never below 70% (readable). Asked for with the button: everything, however small.
  const fit = useCallback((all = false) => {
    const el = host.current;
    if (!el || nodes.length === 0) return;
    const b = bounds(nodes);
    const w = el.clientWidth;
    const h = el.clientHeight;
    if (grow) {
      // Below the overlays, as wide as the screen allows, as tall as the flow needs.
      const k = Math.min(1, (w - PAD) / (b.x1 - b.x0));
      const top = 196;
      setView({ k, x: (w - (b.x1 - b.x0) * k) / 2 - b.x0 * k, y: top - b.y0 * k });
      setHeight(top + (b.y1 - b.y0) * k + 72);
      return;
    }
    setHeight(undefined);
    // Fit on open (width and height), but never below 70%: smaller than that, labels stop being readable.
    // When it still doesn't fit, start from the left edge so the flow reads from its beginning.
    const k = Math.max(all ? 0.2 : overview ? 0.35 : 0.7, Math.min(1, (w - PAD) / (b.x1 - b.x0), (h - TOP - PAD) / (b.y1 - b.y0)));
    const wide = (b.x1 - b.x0) * k;
    const x = wide <= w - PAD ? (w - wide) / 2 - b.x0 * k : PAD / 2 - b.x0 * k;
    // Start below the floating cards at the top (title, evidence layer).
    setView({ k, x, y: Math.max(TOP, (h - (b.y1 - b.y0) * k) / 2 + 20) - b.y0 * k });
  }, [nodes, grow, overview]);

  useEffect(() => {
    if (fitted.current !== fitKey && nodes.length) {
      fitted.current = fitKey;
      fit();
    }
  }, [fit, nodes.length, fitKey]);

  const revealRef = useRef(reveal);
  revealRef.current = reveal;
  useEffect(() => {
    const el = host.current;
    const r = revealRef.current?.rect;
    if (!el || !r || grow) return;
    setView((v) => {
      // Inside the margins, below the floating toolbar and clear of the zoom buttons. Too wide or
      // tall at this zoom: zoom out until all of it fits (never below REVEAL_MIN, where text is lost).
      const [L, T, R, B] = [PAD / 2, 96, el.clientWidth - 64, el.clientHeight - 56];
      const k = Math.max(REVEAL_MIN, Math.min(v.k, (R - L) / (r.x1 - r.x0), (B - T) / (r.y1 - r.y0)));
      if (k < v.k) {
        const wide = (r.x1 - r.x0) * k;
        return { k, x: L + Math.max(0, (R - L - wide) / 2) - r.x0 * k, y: T - r.y0 * k };
      }
      const [x0, y0, x1, y1] = [r.x0 * v.k + v.x, r.y0 * v.k + v.y, r.x1 * v.k + v.x, r.y1 * v.k + v.y];
      const shift = (a: number, b: number, lo: number, hi: number) =>
        b - a > hi - lo || a < lo ? lo - a : b > hi ? hi - b : 0;
      const [dx, dy] = [shift(x0, x1, L, R), shift(y0, y1, T, B)];
      return dx || dy ? { ...v, x: v.x + dx, y: v.y + dy } : v;
    });
  }, [reveal?.key, grow]);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (grow && !(e.ctrlKey || e.metaKey)) return; // let the page scroll
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        const r = el.getBoundingClientRect();
        const px = e.clientX - r.left;
        const py = e.clientY - r.top;
        setView((v) => {
          const k = Math.max(MIN, Math.min(MAX, v.k * Math.exp(-e.deltaY * 0.01)));
          return { k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k };
        });
      } else {
        setView((v) => ({ ...v, x: v.x - e.deltaX, y: v.y - e.deltaY }));
      }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [grow]);

  const zoom = (f: number) =>
    setView((v) => {
      const el = host.current!;
      const cx = el.clientWidth / 2;
      const cy = el.clientHeight / 2;
      const k = Math.max(MIN, Math.min(MAX, v.k * f));
      return { k, x: cx - ((cx - v.x) * k) / v.k, y: cy - ((cy - v.y) * k) / v.k };
    });

  function onBackgroundDown(e: RPointerEvent<HTMLDivElement>) {
    if (grow) return;
    if (e.target !== e.currentTarget && !(e.target as HTMLElement).classList.contains("canvas__edges")) return;
    pan.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function nodeAt(x: number, y: number, except: string): string | null {
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      if (n.id !== except && x >= n.x && x <= n.x + n.w && y >= n.y && y <= n.y + n.h) return n.id;
    }
    return null;
  }

  function onMovePointer(e: RPointerEvent<HTMLDivElement>) {
    const link = linkRef.current;
    const drag = dragRef.current;
    if (link) {
      const w = toWorld(e.clientX, e.clientY);
      const over = nodeAt(w.x, w.y, link.from);
      const [a, b] = link.reverse ? [over, link.from] : [link.from, over];
      const ok = over && a && b && (!canConnect || canConnect(a, b));
      setLink({ ...link, x: w.x, y: w.y, over: ok ? over : null });
    } else if (drag && onMove) {
      if (!drag.moved && Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy) < 4) return;
      if (!drag.moved) {
        // A real drag: keep the pointer even if it leaves the block.
        e.currentTarget.setPointerCapture(e.pointerId);
        setDrag({ ...drag, moved: true });
      }
      const w = toWorld(e.clientX, e.clientY);
      onMove(drag.id, w.x - drag.dx, w.y - drag.dy);
    } else if (pan.current) {
      const p = pan.current;
      setView((v) => ({ ...v, x: p.vx + e.clientX - p.x, y: p.vy + e.clientY - p.y }));
    }
  }

  function swallowNextClick() {
    // Only the click produced by this release; cleared before any later click.
    swallowClick.current = true;
    setTimeout(() => {
      swallowClick.current = false;
    }, 0);
  }

  function onUp() {
    pan.current = null;
    const link = linkRef.current;
    const drag = dragRef.current;
    if (link) {
      if (link.over) {
        if (link.reverse) onConnect?.(link.over, link.from);
        else onConnect?.(link.from, link.over);
      }
      swallowNextClick();
      setLink(null);
    }
    if (drag?.moved) {
      onMoveEnd?.(drag.id);
      swallowNextClick();
    }
    setDrag(null);
  }

  // Register as a drop target for skills dragged from the library; refs keep the latest view.
  const viewRef = useRef(view);
  viewRef.current = view;
  const dropRef = useRef(onDropAt);
  dropRef.current = onDropAt;
  const dropSizeRef = useRef(dropSize);
  dropSizeRef.current = dropSize;
  useEffect(() => {
    if (!onDropAt) return;
    return registerDropTarget({
      el: () => host.current,
      setOver: setDropOver,
      drop: (path, cx, cy, meta) => {
        const r = host.current!.getBoundingClientRect();
        const v = viewRef.current;
        let x = (cx - r.left - v.x) / v.k;
        let y = (cy - r.top - v.y) / v.k;
        // The visible part of the canvas, inside the margins and clear of the zoom buttons.
        const visible = {
          x0: -v.x / v.k + 16 / v.k,
          y0: -v.y / v.k + 16 / v.k,
          x1: (r.width - v.x) / v.k - 64 / v.k,
          y1: (r.height - v.y) / v.k - 56 / v.k, // clear of the legend
        };
        const size = dropSizeRef.current;
        if (size) {
          const hx = size.w / 2;
          const hy = size.h / 2;
          x = Math.min(Math.max(x, visible.x0 + hx), Math.max(visible.x0 + hx, visible.x1 - hx));
          y = Math.min(Math.max(y, visible.y0 + hy), Math.max(visible.y0 + hy, visible.y1 - hy));
        }
        dropRef.current?.(path, x, y, visible, meta);
      },
    });
  }, [Boolean(onDropAt)]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Client coordinates to canvas coordinates. */
  function toWorld(clientX: number, clientY: number) {
    const r = host.current!.getBoundingClientRect();
    return { x: (clientX - r.left - view.x) / view.k, y: (clientY - r.top - view.y) / view.k };
  }

  return (
    <div className="canvas" role="group" aria-label={label} style={height ? { height, minHeight: height } : undefined}>
      <div
        ref={host}
        className={`canvas__surface${pan.current ? " is-panning" : ""}${grow ? " is-static" : ""}${dropOver ? " is-drop" : ""}${link ? " is-linking" : ""}`}
        // The dot grid moves and scales with the world.
        style={{ backgroundSize: `${24 * view.k}px ${24 * view.k}px`, backgroundPosition: `${view.x}px ${view.y}px` }}
        onPointerDown={onBackgroundDown}
        onPointerMove={onMovePointer}
        onPointerUp={onUp}
        onPointerCancel={onUp}
      >
        <div
          className="canvas__world"
          style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`, ["--zoom" as string]: view.k }}
        >
          <svg className="canvas__edges" width="1" height="1" aria-hidden="true">
            <defs>
              <marker id="pg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,1 L9,5 L0,9 z" fill="var(--edge)" />
              </marker>
              <marker id="pg-arrow-link" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,1 L9,5 L0,9 z" fill="var(--skill)" />
              </marker>
            </defs>
            {edges.map((e, i) => {
              const a = byId.get(e.from);
              const b = byId.get(e.to);
              if (!a || !b) return null;
              const { d } = edgeGeometry(a, b);
              return (
                <g key={e.id ?? `${e.from}-${e.to}`}>
                  <path
                    className={`canvas__edge${e.live ? " is-live" : ""}${e.variant && e.variant !== "flow" ? ` canvas__edge--${e.variant}` : ""}${e.dim ? " is-dim" : ""}`}
                    d={d}
                    markerEnd={e.variant === "link" ? "url(#pg-arrow-link)" : "url(#pg-arrow)"}
                  />
                  {motion && e.variant !== "planned" && e.variant !== "removed" && !e.dim ? (
                    // A dot travelling along the line, as on syde: the direction of flow at a glance.
                    <circle className={`canvas__dot${e.variant === "link" ? " canvas__dot--link" : ""}`} r={3.5}>
                      <animateMotion
                        dur={e.live ? "1.2s" : "2.8s"}
                        repeatCount="indefinite"
                        path={d}
                        begin={`-${(i % 7) * 0.4}s`}
                      />
                    </circle>
                  ) : null}
                </g>
              );
            })}
            {link
              ? (() => {
                  const a = byId.get(link.from)!;
                  const sx = link.reverse ? a.x : a.x + a.w;
                  const sy = a.y + Math.min(a.h / 2, 60);
                  const dx = Math.max(40, Math.abs(link.x - sx) / 2) * (link.reverse ? -1 : 1);
                  return (
                    <path
                      className="canvas__edge canvas__edge--link canvas__edge--drawing"
                      d={`M${sx},${sy} C${sx + dx},${sy} ${link.x - dx},${link.y} ${link.x},${link.y}`}
                      markerEnd="url(#pg-arrow-link)"
                    />
                  );
                })()
              : null}
          </svg>
          {nodes.map((n) => (
            <div
              key={n.id}
              className={`canvas__node${drag?.moved && drag.id === n.id ? " is-dragging" : ""}`}
              style={{ left: n.x, top: n.y, width: n.w }}
              aria-label={n.label}
              onPointerDown={(e) => {
                const target = e.target as HTMLElement;
                if (target.closest("[data-no-drag]")) return;
                const surface = e.currentTarget.parentElement?.parentElement as HTMLElement;
                const w = toWorld(e.clientX, e.clientY);
                const port = target.closest("[data-port]");
                if (port && onConnect) {
                  e.stopPropagation();
                  surface.setPointerCapture(e.pointerId);
                  const reverse = port.getAttribute("data-port") === "in";
                  setLink({ from: n.id, x: w.x, y: w.y, over: null, reverse });
                  return;
                }
                if (!n.draggable || !onMove) return;
                e.stopPropagation();
                // No pointer capture yet: capturing now would send the click to the surface, not the block.
                setDrag({ id: n.id, dx: w.x - n.x, dy: w.y - n.y, sx: e.clientX, sy: e.clientY, moved: false });
              }}
              onClickCapture={(e) => {
                // The click that ends a drag or a link is not a click on the node.
                if (swallowClick.current) {
                  swallowClick.current = false;
                  e.stopPropagation();
                  e.preventDefault();
                }
              }}
            >
              {n.render({
                dragging: Boolean(drag?.moved && drag.id === n.id),
                target: link?.over === n.id || highlight === n.id,
              })}
              {onConnect && n.ports !== false ? (
                <>
                  <span className="handle handle--in" data-port="in" title="Connect from left" aria-hidden="true" />
                  <span className="handle handle--out" data-port="out" title="Connect from right" aria-hidden="true" />
                </>
              ) : null}
            </div>
          ))}
        </div>
        {/* Labels in screen space: their buttons stay full size at any zoom. */}
        <div className="canvas__labels">
          {edges.map((e) => {
            const a = byId.get(e.from);
            const b = byId.get(e.to);
            if (!a || !b || !e.step) return null;
            const { mx, my } = edgeGeometry(a, b);
            return (
              <span key={`step-${e.id ?? `${e.from}-${e.to}`}`} className="canvas__step num" style={{ left: view.x + mx * view.k, top: view.y + my * view.k }}>
                {e.step}
              </span>
            );
          })}
          {(() => {
            // Labels in screen space, each moved down just enough not to sit on one placed before
            // it: two links whose midpoints meet would otherwise stack their × buttons.
            const placed: { x0: number; x1: number; y0: number; y1: number }[] = [];
            return edges.map((e) => {
              const a = byId.get(e.from);
              const b = byId.get(e.to);
              if (!a || !b || !e.label) return null;
              const { mx, my, gap, across } = edgeGeometry(a, b);
              // Too little room between the boxes for the words: only the dot (and its ×) stays on
              // the line, the words in its title, so it never covers a card's title.
              const room = gap * view.k;
              const tight = across ? room < e.label.length * 6.5 + (e.onRemove ? 40 : 24) : room < 26;
              const w = tight ? (e.onRemove ? 34 : 12) : e.label.length * 6.5 + (e.onRemove ? 44 : 24);
              const x = view.x + mx * view.k;
              let y = view.y + my * view.k;
              const hits = (yy: number) => placed.some((r) => x - w / 2 < r.x1 + 4 && x + w / 2 > r.x0 - 4 && yy - 15 < r.y1 && yy + 15 > r.y0);
              for (let n = 0; n < 6 && hits(y); n++) y += 32;
              placed.push({ x0: x - w / 2, x1: x + w / 2, y0: y - 15, y1: y + 15 });
              return (
                <span
                  key={`label-${e.id ?? `${e.from}-${e.to}`}`}
                  className={`canvas__label${e.variant === "planned" ? " canvas__label--planned" : ""}${tight ? " canvas__label--tight" : ""}`}
                  title={tight ? [e.label, e.title].filter(Boolean).join(": ") : e.title}
                  style={{ left: x, top: y }}
                >
                  <span className={tight ? "visually-hidden" : undefined}>{e.label}</span>
                  {e.onRemove ? (
                    <button type="button" aria-label={e.removeLabel} onClick={e.onRemove}>
                      <X size={11} />
                    </button>
                  ) : null}
                </span>
              );
            });
          })()}
        </div>
      </div>
      <div className="canvas__zoom" role="toolbar" aria-label="Zoom">
        <button type="button" className="canvas__btn" onClick={() => zoom(1.2)} aria-label="Zoom in">
          <Plus size={16} />
        </button>
        <span className="canvas__pct num" aria-live="polite">
          {Math.round(view.k * 100)}%
        </span>
        <button type="button" className="canvas__btn" onClick={() => zoom(1 / 1.2)} aria-label="Zoom out">
          <Minus size={16} />
        </button>
        <button type="button" className="canvas__btn" onClick={() => fit(true)} aria-label="Fit everything" title="Fit everything">
          <Maximize2 size={14} />
        </button>
      </div>
      {overlays}
    </div>
  );
}
