import { parseRoute, routeHash, routeOrder } from "./route";

test("every page has a hash, and the hash brings the same page back", () => {
  expect(parseRoute("")).toEqual({ page: "home" });
  expect(parseRoute("#/home")).toEqual({ page: "home" });
  expect(parseRoute("#/nowhere")).toEqual({ page: "home" });
  expect(parseRoute("#/build")).toEqual({ page: null, step: 3 });
  expect(parseRoute("#/measure")).toEqual({ page: null, step: 4 });
  expect(parseRoute("#/runs/bench/bugfix/1")).toEqual({ page: "runs" });
  expect(parseRoute("#/rig-score")).toEqual({ page: "score" });
  for (const h of ["#/home", "#/describe", "#/design", "#/build", "#/measure", "#/ship", "#/runs", "#/compare", "#/rig-score"])
    expect(routeHash(parseRoute(h))).toBe(h);
});

test("Home comes first, then the steps in order: the transition's direction", () => {
  expect(routeOrder("home", 4)).toBeLessThan(routeOrder(null, 1));
  expect(routeOrder(null, 3)).toBeLessThan(routeOrder(null, 4));
  expect(routeOrder(null, 5)).toBeLessThan(routeOrder("score", 1));
});

test("the tutorial has its own hashes, one per step on the example and one for its finish", () => {
  expect(parseRoute("#/tutorial")).toEqual({ page: "tutorial", at: 1 });
  expect(parseRoute("#/tutorial/measure")).toEqual({ page: "tutorial", at: 4 });
  expect(parseRoute("#/tutorial/done")).toEqual({ page: "tutorial", at: "done" });
  expect(parseRoute("#/tutorial/nowhere")).toEqual({ page: "tutorial", at: 1 });
  for (const h of ["#/tutorial/describe", "#/tutorial/design", "#/tutorial/build", "#/tutorial/measure", "#/tutorial/ship", "#/tutorial/done"])
    expect(routeHash(parseRoute(h))).toBe(h);
  // Its steps go forward in their own order, after every other page.
  expect(routeOrder("tutorial", 1, 2)).toBeLessThan(routeOrder("tutorial", 1, 3));
  expect(routeOrder("tutorial", 1, 5)).toBeLessThan(routeOrder("tutorial", 1, "done"));
  expect(routeOrder("score", 1)).toBeLessThan(routeOrder("tutorial", 1, 1));
});

test("the repo tutorial (fewer tokens) has hashes of its own, beside the first track's", () => {
  expect(parseRoute("#/tutorial/tokens")).toEqual({ page: "tutorial", at: 1, track: "tokens" });
  expect(parseRoute("#/tutorial/tokens/measure")).toEqual({ page: "tutorial", at: 4, track: "tokens" });
  expect(parseRoute("#/tutorial/tokens/done")).toEqual({ page: "tutorial", at: "done", track: "tokens" });
  for (const h of ["#/tutorial/tokens/describe", "#/tutorial/tokens/build", "#/tutorial/tokens/ship", "#/tutorial/tokens/done"]) expect(routeHash(parseRoute(h))).toBe(h);
  expect(routeHash({ page: "tutorial", at: 2 })).toBe("#/tutorial/design");
});
