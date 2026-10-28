import { useEffect, useState } from "react";

import { api } from "./api";
import type { TokensTutorial, Tutorial } from "./types";

/** The tutorial keeps one flag in this browser, under its own name: whether it was finished. It
 * never reads or writes the app's own state (pg.step, pg.space, pg.repo, the goal…). */
export const TOUR_DONE_KEY = "rig-tutorial.done";
/** The repo tutorial's (fewer tokens) own flag, the same way. */
export const TOKENS_TOUR_DONE_KEY = "rig-tutorial-tokens.done";

export function tutorialDone(key: string = TOUR_DONE_KEY): boolean {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

export function markTutorialDone(key: string = TOUR_DONE_KEY): void {
  try {
    window.localStorage.setItem(key, "1");
  } catch {
    // Not remembered in a private window: the button keeps saying "Start".
  }
}

// Read once per page load: the example and its recorded run don't change while the app is open.
let cached: Promise<Tutorial> | null = null;

/** The tutorial's example space from the engine (GET /api/tutorial); null until read, or on error. */
export function useTutorial(): { data: Tutorial | null; error: string | null } {
  const [data, setData] = useState<Tutorial | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    cached ??= api.tutorial();
    cached.then(
      (d) => live && setData(d),
      (e) => {
        cached = null; // a later visit asks again
        if (live) setError(String((e as Error).message ?? e));
      },
    );
    return () => {
      live = false;
    };
  }, []);
  return { data, error };
}

let cachedTokens: Promise<TokensTutorial> | null = null;

/** The repo tutorial's example space (GET /api/tutorial/tokens), read once per page load the same way. */
export function useTokensTutorial(): { data: TokensTutorial | null; error: string | null } {
  const [data, setData] = useState<TokensTutorial | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    cachedTokens ??= api.tutorialTokens();
    cachedTokens.then(
      (d) => live && setData(d),
      (e) => {
        cachedTokens = null;
        if (live) setError(String((e as Error).message ?? e));
      },
    );
    return () => {
      live = false;
    };
  }, []);
  return { data, error };
}

/** For tests: forget the cached reads. */
export function resetTutorialCache(): void {
  cached = null;
  cachedTokens = null;
}

