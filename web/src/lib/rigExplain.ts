import { useEffect, useState } from "react";

import { api } from "./api";
import type { RigExplain, Verdict } from "./types";

// Read once per page load: the definition doesn't change while the app is open.
let cached: Promise<RigExplain> | null = null;

/** The Rig score's definition from the engine (GET /api/rig-score); null until read, or on error. */
export function useRigExplain(): { data: RigExplain | null; error: string | null } {
  const [data, setData] = useState<RigExplain | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    cached ??= api.rigExplain();
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

/** The share of 100 a weight is, as the page says it: 0.4 → "40%". */
export function weightPct(w: number): string {
  return `${Math.round(w * 100)}%`;
}

/** The worked example's verdict as the interval draws it. */
export function exampleVerdict(d: RigExplain): Verdict {
  const id = d.example.result.verdict?.id;
  return id === "helps" ? "helps" : id === "doesnt" ? "hurts" : "inconclusive";
}
