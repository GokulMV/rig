import type { ArchKind, GarageEntry } from "../lib/types";
import { ARCH_STYLE } from "./RepoCanvas";

// A schematic for a card: the flow runs top to bottom, one row per stage, so text stays readable
// at card width (a left-to-right chain of six parts would shrink to unreadable).
const CELL_W = 100;
const CELL_H = 44;
const BOX_W = 88;
const BOX_H = 26;
const PAD = 10;

function short(label: string, max = 14): string {
  return label.length > max ? `${label.slice(0, max - 1)}…` : label;
}

/** Stages: a part sits one row below the latest part that feeds it. Links that go back up (found
 * by a depth-first walk from the parts nothing feeds) are loops and don't push anything down. */
export function stages(entry: GarageEntry): { row: Map<string, number>; back: Set<number> } {
  const ids = entry.components.map((c) => c.id);
  const out = new Map(ids.map((id) => [id, [] as [string, number][]]));
  const fed = new Set<string>();
  entry.connections.forEach(([a, b], i) => {
    if (out.has(a) && out.has(b) && a !== b) {
      out.get(a)!.push([b, i]);
      fed.add(b);
    }
  });
  const back = new Set<number>();
  const state = new Map<string, "open" | "done">();
  const walk = (id: string) => {
    state.set(id, "open");
    for (const [to, i] of out.get(id)!) {
      if (state.get(to) === "open") back.add(i);
      else if (!state.has(to)) walk(to);
    }
    state.set(id, "done");
  };
  for (const id of ids) if (!fed.has(id)) walk(id);
  for (const id of ids) if (!state.has(id)) walk(id); // a cycle with no way in

  const row = new Map(ids.map((id) => [id, 0]));
  for (let pass = 0; pass < ids.length; pass++) {
    entry.connections.forEach(([a, b], i) => {
      if (back.has(i) || !row.has(a) || !row.has(b) || a === b) return;
      row.set(b, Math.max(row.get(b)!, row.get(a)! + 1));
    });
  }
  return { row, back };
}

/** An architecture drawn small: its parts as boxes by stage, its connections as arrows; loops are
 * dashed and curve round the side. */
export function ArchMini({ entry }: { entry: GarageEntry }) {
  const { row, back } = stages(entry);
  const rows = Math.max(...entry.components.map((c) => row.get(c.id) ?? 0)) + 1;
  const perRow: string[][] = Array.from({ length: rows }, () => []);
  for (const c of entry.components) perRow[row.get(c.id) ?? 0].push(c.id);
  const widest = Math.max(...perRow.map((r) => r.length));
  const width = PAD * 2 + (widest - 1) * CELL_W + BOX_W + 16; // room for loops on the right
  const height = PAD * 2 + (rows - 1) * CELL_H + BOX_H;
  const at = new Map<string, { x: number; y: number }>();
  perRow.forEach((ids, r) => {
    const offset = ((widest - ids.length) * CELL_W) / 2; // each row centred
    ids.forEach((id, k) => at.set(id, { x: PAD + offset + k * CELL_W, y: PAD + r * CELL_H }));
  });
  const label = `${entry.name}: ${entry.connections.map(([a, b, what]) => `${a} ${what} ${b}`).join("; ")}`;

  return (
    <svg className="archmini" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      <defs>
        <marker id={`am-${entry.id}`} viewBox="0 0 6 6" refX="5.5" refY="3" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M0,0 L6,3 L0,6 z" fill="var(--edge, #9aa3ad)" />
        </marker>
      </defs>
      {entry.connections.map(([a, b, what], i) => {
        const p = at.get(a);
        const q = at.get(b);
        if (!p || !q || a === b) return null;
        let d: string;
        if (back.has(i)) {
          // Up the right-hand side, back into the earlier part.
          const side = width - PAD / 2;
          d = `M${p.x + BOX_W},${p.y + BOX_H / 2} C${side},${p.y + BOX_H / 2} ${side},${q.y + BOX_H / 2} ${q.x + BOX_W},${q.y + BOX_H / 2}`;
        } else if (q.y === p.y) {
          const [l, r] = q.x > p.x ? [p.x + BOX_W, q.x] : [p.x, q.x + BOX_W];
          d = `M${l},${p.y + BOX_H / 2} L${r},${q.y + BOX_H / 2}`;
        } else {
          const [x1, y1, x2, y2] = [p.x + BOX_W / 2, p.y + BOX_H, q.x + BOX_W / 2, q.y];
          const my = (y1 + y2) / 2;
          d = `M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`;
        }
        return (
          <path
            key={i}
            d={d}
            fill="none"
            stroke="var(--edge, #9aa3ad)"
            strokeWidth="1.2"
            strokeDasharray={back.has(i) ? "3 2" : undefined}
            markerEnd={`url(#am-${entry.id})`}
          >
            <title>{what}</title>
          </path>
        );
      })}
      {entry.components.map((c) => {
        const p = at.get(c.id)!;
        const color = ARCH_STYLE[c.type as ArchKind]?.color ?? ARCH_STYLE.backend.color;
        return (
          <g key={c.id}>
            <title>{`${c.label}: ${c.role}`}</title>
            <rect x={p.x} y={p.y} width={BOX_W} height={BOX_H} rx="5" fill="var(--surface)" stroke={color} strokeWidth="1.2" />
            <rect x={p.x} y={p.y} width="4" height={BOX_H} rx="2" fill={color} />
            <text x={p.x + 9} y={p.y + BOX_H / 2 + 3.5} fontSize="10" fill="var(--text)">
              {short(c.label)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
