import { useState } from "react";

const LIMITS = { left: [220, 520], right: [280, 640] } as const;
const DEFAULTS = { left: 300, right: 360 };

function read<T>(key: string, fallback: T, parse: (v: string) => T): T {
  try {
    const v = window.localStorage.getItem(key);
    return v === null ? fallback : parse(v);
  } catch {
    return fallback;
  }
}

function write(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Not remembered in a private window.
  }
}

/** Which side panes are hidden and how wide they are, remembered in this browser. */
export function usePanes(key: string) {
  const [left, setLeft] = useState(() => read(`pg.panes.${key}.left`, false, (v) => v === "hidden"));
  const [right, setRight] = useState(() => read(`pg.panes.${key}.right`, false, (v) => v === "hidden"));
  const [widths, setWidths] = useState(() => ({
    left: read(`pg.panes.${key}.left.w`, DEFAULTS.left, Number) || DEFAULTS.left,
    right: read(`pg.panes.${key}.right.w`, DEFAULTS.right, Number) || DEFAULTS.right,
  }));
  const resize = (side: "left" | "right", w: number) => {
    const [lo, hi] = LIMITS[side];
    const next = Math.round(Math.max(lo, Math.min(hi, w)));
    setWidths((x) => ({ ...x, [side]: next }));
    write(`pg.panes.${key}.${side}.w`, String(next));
  };
  return {
    left,
    right,
    widths,
    limits: LIMITS,
    resize,
    reset: (side: "left" | "right") => resize(side, DEFAULTS[side]),
    toggleLeft: () => {
      setLeft(!left);
      write(`pg.panes.${key}.left`, !left ? "hidden" : "shown");
    },
    toggleRight: () => {
      setRight(!right);
      write(`pg.panes.${key}.right`, !right ? "hidden" : "shown");
    },
    className: `${left ? " panes--no-left" : ""}${right ? " panes--no-right" : ""}`,
    style: { ["--left-w" as string]: `${widths.left}px`, ["--right-w" as string]: `${widths.right}px` },
  };
}
