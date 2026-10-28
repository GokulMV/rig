import { type OffPath, type Step, STEP_SLUG } from "../components/Journey";

/** Where the tutorial is: one of its five steps on the example, or its finish screen. */
export type TourAt = Step | "done";
/** The tutorial's second track, "Rig your own repo: fewer tokens" (#/tutorial/tokens/…); the
 * first track has no name in the hash. */
export type TourTrack = "tokens";

/** Where the hash says you are: a step (#/build), a page off the path (#/home, #/runs…,
 * #/compare, #/rig-score), or the tutorial (#/tutorial/describe … #/tutorial/done, and its second
 * track's #/tutorial/tokens/describe …). No hash, or one Rig doesn't know, is Home. */
export type Route = { page: Exclude<OffPath, "tutorial"> } | { page: "tutorial"; at: TourAt; track?: TourTrack } | { page: null; step: Step };
const SLUG_STEP = new Map((Object.entries(STEP_SLUG) as [string, string][]).map(([n, slug]) => [slug, Number(n) as Step]));

export function parseRoute(hash: string): Route {
  if (hash.startsWith("#/runs")) return { page: "runs" };
  if (hash.startsWith("#/compare")) return { page: "compare" };
  if (hash.startsWith("#/rig-score")) return { page: "score" };
  const tour = /^#\/tutorial(\/tokens)?(?:\/([a-z]+))?$/.exec(hash);
  if (tour) {
    const at: TourAt = tour[2] === "done" ? "done" : (SLUG_STEP.get(tour[2] ?? "") ?? 1);
    return tour[1] ? { page: "tutorial", at, track: "tokens" } : { page: "tutorial", at };
  }
  const step = SLUG_STEP.get(/^#\/([a-z]+)$/.exec(hash)?.[1] ?? "");
  return step ? { page: null, step } : { page: "home" };
}

export function routeHash(r: Route): string {
  if (r.page === null) return `#/${STEP_SLUG[r.step]}`;
  if (r.page === "tutorial") return `#/tutorial/${r.track ? `${r.track}/` : ""}${r.at === "done" ? "done" : STEP_SLUG[r.at]}`;
  return r.page === "score" ? "#/rig-score" : `#/${r.page}`;
}

/** Home first, then the steps in order, then the pages beside them, then the tutorial's steps in
 * their own order: which way a move goes. */
export function routeOrder(page: OffPath | null, step: Step, at?: TourAt): number {
  if (page === "tutorial") return 10 + (at === "done" ? 6 : (at ?? 1));
  return page === "home" ? 0 : page === null ? step : 6;
}
