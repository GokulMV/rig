import { Cpu, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import type { LocalModel, LocalModels as LocalData, LocalTemplateFix, LocalTest } from "../lib/types";

function message(e: unknown) {
  return e instanceof ApiError ? e.message : String(e);
}

/** Models people run themselves: find them, add them, check them, pick one for helper calls. */
export function LocalModels({ onChanged }: { onChanged?: (d: LocalData) => void }) {
  const [data, setData] = useState<LocalData | null>(null);
  const [found, setFound] = useState<LocalModel[] | null>(null);
  const [base, setBase] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [tests, setTests] = useState<Record<string, LocalTest>>({});
  const [fixes, setFixes] = useState<Record<string, LocalTemplateFix>>({});
  const [error, setError] = useState<string | null>(null);

  const set = useCallback(
    (d: LocalData) => {
      setData(d);
      onChanged?.(d);
    },
    [onChanged],
  );
  useEffect(() => {
    api.localModels().then(set, (e) => setError(message(e)));
  }, [set]);

  const act = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(null);
    }
  };
  const have = new Set(data?.models.map((m) => m.id));
  const shown = (found ?? []).filter((m) => !have.has(m.id));

  return (
    <div className="localm">
      <p className="small muted" style={{ margin: 0 }}>
        Models you run yourself: Ollama, LM Studio, llama.cpp, vLLM or Jan, on this machine or your network. Only local
        addresses are accepted, so nothing you test leaves.
      </p>
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn btn--small"
          disabled={busy !== null}
          onClick={() =>
            act("scan", async () => {
              const d = await api.localModels(true);
              set(d);
              setFound(d.found ?? []);
            })
          }
        >
          <Search size={13} aria-hidden="true" /> {busy === "scan" ? "Looking…" : "Look on This Machine"}
        </button>
      </div>
      <form
        className="row"
        style={{ gap: 8, flexWrap: "nowrap" }}
        onSubmit={(e) => {
          e.preventDefault();
          if (!base.trim()) return;
          void act("url", async () => setFound(await api.scanLocal(base.trim())));
        }}
      >
        <label htmlFor="local-base" className="visually-hidden">
          Server address
        </label>
        <input
          id="local-base"
          className="input input--small"
          placeholder="http://127.0.0.1:8089"
          value={base}
          onChange={(e) => setBase(e.target.value)}
        />
        <button type="submit" className="btn btn--small" disabled={!base.trim() || busy !== null}>
          {busy === "url" ? "Asking…" : "Find Models"}
        </button>
      </form>
      {error ? <p className="notice notice--error small">{error}</p> : null}

      {found !== null ? (
        shown.length ? (
          <ul className="localm__list" aria-label="Found local models">
            {shown.map((m) => (
              <li key={m.id} className="localm__item">
                <div>
                  <b>{m.model.split("/").pop()}</b>
                  <div className="small muted">
                    {m.kind} · {m.base}
                    {m.anthropic ? " · can run Claude Code" : ""}
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn--small btn--primary"
                  disabled={busy !== null}
                  onClick={() => act(`add-${m.id}`, async () => set(await api.addLocal({ base: m.base, model: m.model, kind: m.kind })))}
                >
                  Add
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="small muted">
            No new models found. Start one (for example <code>ollama serve</code> or <code>llama-server -m model.gguf</code>), or
            type its address above.
          </p>
        )
      ) : null}

      {data?.models.length ? (
        <ul className="localm__list" aria-label="Your local models">
          {data.models.map((m) => {
            const t = tests[m.id];
            return (
              <li key={m.id} className="localm__item localm__item--mine">
                <div style={{ minWidth: 0 }}>
                  <b>
                    <Cpu size={13} aria-hidden="true" /> {m.label}
                  </b>
                  <div className="small muted">
                    {m.base} ·{" "}
                    {m.anthropic ? "runs Claude Code, estimates and judging" : "estimates and judging (its server doesn't speak the Anthropic API Claude Code needs)"}
                  </div>
                  {t ? (
                    <div role="status" className="small">
                      <div className={t.helper_ok ? "ok" : "adh"}>
                        {t.helper_ok ? "Helper ready" : `Helper not ready: ${t.stages[0]?.why ?? t.why}`}
                      </div>
                      {t.claude_code_ok === null ? (
                        <div className="muted">Claude Code: not checked (its server doesn't speak the Anthropic API).</div>
                      ) : (
                        <div className={t.claude_code_ok ? "ok" : "adh"}>
                          {t.claude_code_ok
                            ? "Claude Code ready"
                            : `Not ready for Claude Code: ${t.stages.find((x) => x.name !== "helper" && !x.ok)?.why ?? "see below"}`}
                        </div>
                      )}
                      <ul className="localm__notes" aria-label={`Checks for ${m.label}`}>
                        {t.stages.map((x) => (
                          <li key={x.name} className={x.ok ? "muted" : "adh"}>
                            {x.name}: {x.ok ? "passed" : "failed"}, {x.why}
                          </li>
                        ))}
                      </ul>
                      {t.warnings.map((w) => (
                        <div key={w} className="adh">
                          {w}
                        </div>
                      ))}
                      <div className="muted">{t.seconds}s</div>
                      {t.fix_command ? (
                        <div>
                          <button
                            type="button"
                            className="btn btn--small"
                            disabled={busy !== null}
                            onClick={() =>
                              act(`fix-${m.id}`, async () => {
                                const f = await api.localTemplateFix(m.id);
                                setFixes((x) => ({ ...x, [m.id]: f }));
                              })
                            }
                          >
                            {busy === `fix-${m.id}` ? "Saving…" : "Save a Fixed Template"}
                          </button>
                          {fixes[m.id] ? (
                            <p style={{ margin: "6px 0 0" }}>
                              Saved to <code>{fixes[m.id].path}</code>. Restart the server with:
                              <br />
                              <code style={{ overflowWrap: "anywhere" }}>{fixes[m.id].command}</code>
                            </p>
                          ) : (
                            <span className="muted"> {t.fix_command}</span>
                          )}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  <label className="check-row small">
                    <input
                      type="radio"
                      name="local-helper"
                      checked={data.helper === m.id}
                      onChange={() => {
                        setData({ ...data, helper: m.id }); // shown at once, confirmed by the reply
                        void act(`helper-${m.id}`, async () => set(await api.localHelper(m.id)));
                      }}
                    />
                    <span>Use for estimates, picks and judging</span>
                  </label>
                </div>
                <div className="localm__actions">
                  <button
                    type="button"
                    className="btn btn--small"
                    disabled={busy !== null}
                    onClick={() =>
                      act(`test-${m.id}`, async () => {
                        const r = await api.testLocal(m.id);
                        setTests((x) => ({ ...x, [m.id]: r }));
                      })
                    }
                  >
                    {busy === `test-${m.id}` ? "Testing…" : "Test"}
                  </button>
                  <button
                    type="button"
                    className="btn btn--small btn--quiet"
                    disabled={busy !== null}
                    onClick={() => act(`rm-${m.id}`, async () => set(await api.removeLocal(m.id)))}
                  >
                    Remove
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
      {data?.helper ? (
        <button
          type="button"
          className="linkish small"
          onClick={() => act("helper-none", async () => set(await api.localHelper(null)))}
        >
          Use Claude for Estimates and Judging Again
        </button>
      ) : null}
      <details className="small">
        <summary>Known Issues Running Claude Code on a Local Model</summary>
        <ul className="localm__notes">
          <li>
            Start the server with room for Claude Code's prompt (10–15k tokens before any work), e.g. <code>-c 65536</code>.
          </li>
          <li>
            If trials fail with "System message must be at the beginning", the model's chat template refuses Claude Code's
            messages (seen with Qwen 3.5 on llama.cpp). A template that allows a later system message fixes it; chatml loses
            tool calls.
          </li>
          <li>Small models often skip the workflow: check "Followed the workflow" on the result before trusting it.</li>
        </ul>
      </details>
      <p className="small muted" style={{ margin: 0 }}>
        Test runs a few tiny asks on your machine (free): the helper JSON, a Claude Code-style tool call, and the context size. Before trusting a local judge, use "Check the Judge First" on a judged
        bench: small models often can't tell good work from bad.
      </p>
    </div>
  );
}
