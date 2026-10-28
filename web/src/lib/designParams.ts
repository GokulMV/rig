import { useSyncExternalStore } from "react";

/** The parameter values edited on a Garage design, by design id: step 2 writes them, the brief
 * in step 5 reads them. Kept in this browser; values are text, as the form has them. */
type Values = Record<string, string>;
const KEY = "pg.design-params";
let all: Record<string, Values> = load();
const listeners = new Set<() => void>();

function load(): Record<string, Values> {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    return v && typeof v === "object" ? v : {};
  } catch {
    return {};
  }
}

export function designParams(id: string): Values {
  return all[id] ?? EMPTY;
}
const EMPTY: Values = {};

export function setDesignParam(id: string, name: string, value: string) {
  all = { ...all, [id]: { ...(all[id] ?? {}), [name]: value } };
  try {
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    // Storage blocked: the values still last for this visit.
  }
  listeners.forEach((f) => f());
}

function subscribe(f: () => void) {
  listeners.add(f);
  return () => listeners.delete(f);
}

/** The values edited on one design, kept up to date. */
export function useDesignParams(id: string | null | undefined): Values {
  return useSyncExternalStore(subscribe, () => (id ? designParams(id) : EMPTY));
}
