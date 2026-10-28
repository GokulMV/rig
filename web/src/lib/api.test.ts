import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./api";

describe("request", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("turns a non-JSON server error into a plain message, not a SyntaxError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("Internal Server Error", { status: 500 })));
    const e = await api.lab().catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect(e.message).toMatch(/The engine hit an error \(HTTP 500\)/);
    expect(e.status).toBe(500);
  });

  it("says the request didn't go through, and why, only when it never got an answer", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const e = await api.lab().catch((x) => x);
    expect(e.message).toBe("The request didn't go through (network).");
    expect(e.status).toBe(0);
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new DOMException("aborted", "AbortError"))));
    const a = await api.lab().catch((x) => x);
    expect(a.message).toBe("The request didn't go through (cancelled).");
  });

  it("shows the server's own message for an HTTP error, never 'can't reach'", async () => {
    const json = (body: unknown, status: number) =>
      new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "Task 'cost' can't be approved: `token cost` isn't a command" }, 422)));
    let e = await api.lab().catch((x) => x);
    expect(e.message).toBe("Task 'cost' can't be approved: `token cost` isn't a command");
    expect(e.status).toBe(422);
    // FastAPI's own validation errors: a list of {loc, msg}.
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: [{ loc: ["body", "check"], msg: "Field required" }] }, 422)));
    e = await api.lab().catch((x) => x);
    expect(e.message).toBe("check: Field required");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("Not Found", { status: 404 })));
    e = await api.lab().catch((x) => x);
    expect(e.message).toBe("Request failed (HTTP 404): Not Found");
    expect(e.message).not.toMatch(/reach/);
  });
});

describe("generate", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends the unsaved goal with the estimate and the real call, and nothing when there is none", async () => {
    const bodies: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => {
        bodies.push(JSON.parse(String(init.body)));
        return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
      }),
    );
    await api.dryRun("typical=1", "m", "Ship invoices.");
    await api.generate("typical=1", "m", "Ship invoices.");
    await api.generate("typical=1", "m");
    expect(bodies).toEqual([
      { mix: "typical=1", model: "m", dry_run: true, use_case: "Ship invoices." },
      { mix: "typical=1", model: "m", use_case: "Ship invoices." },
      { mix: "typical=1", model: "m" },
    ]);
  });
});
