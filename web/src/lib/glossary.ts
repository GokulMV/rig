import { useSyncExternalStore } from "react";

import { api } from "./api";

/** The plain meaning of each measurement word (the glossary skill, via /api/glossary), fetched
 * once per page load and shared by every (?) on the page. */
export type Glossary = Record<string, { term: string; short: string }>;

let terms: Glossary | null = null;
let asked = false;
const listeners = new Set<() => void>();

function ask() {
  if (asked) return;
  asked = true;
  api.glossary().then(
    (g) => {
      terms = g.terms;
      listeners.forEach((f) => f());
    },
    () => {
      asked = false; // try again next time a (?) mounts
    },
  );
}

function subscribe(f: () => void) {
  listeners.add(f);
  ask();
  return () => listeners.delete(f);
}

/** The glossary, or null until it has loaded. */
export function useGlossary(): Glossary | null {
  return useSyncExternalStore(subscribe, () => terms);
}

/** For tests: set the terms without a request. */
export function setGlossary(g: Glossary | null) {
  terms = g;
  asked = g !== null;
  listeners.forEach((f) => f());
}
