import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "../lib/api";
import type { RemoteProvider, RemoteRepoRow, RepoRef } from "../lib/types";

const GITHUB_PATH =
  "M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z";
const GITLAB_PATH = "M8 14.8 1.2 9.9l1.4-4.4L4.2 9h7.6l1.6-3.5 1.4 4.4z";

/** The mark for where a repo came from. */
export function ProviderIcon({ provider, size = 14 }: { provider: "github" | "gitlab"; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d={provider === "github" ? GITHUB_PATH : GITLAB_PATH} />
    </svg>
  );
}

const msg = (e: unknown) => (e instanceof ApiError ? e.message : String(e));

function SignIn({ p, onChange }: { p: RemoteProvider; onChange: () => void }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const id = `remote-token-${p.id}`;
  if (p.via === "cli")
    return (
      <p className="small">
        <ProviderIcon provider={p.id} /> {p.label}: Using your {p.cli} login ({p.cli_account})
      </p>
    );
  if (p.via === "token")
    return (
      <p className="small">
        <ProviderIcon provider={p.id} /> {p.label}: signed in with a token kept in memory{" "}
        <button
          type="button"
          className="btn btn--small btn--quiet"
          onClick={async () => {
            await api.clearRemoteToken(p.id);
            onChange();
          }}
        >
          Sign Out of {p.label}
        </button>
      </p>
    );
  return (
    <div className="remote__signin">
      <label htmlFor={id} className="small">
        <ProviderIcon provider={p.id} /> {p.label} token (only needed for private repos)
      </label>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input
          id={id}
          className="input mono"
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
        <button
          type="button"
          className="btn"
          disabled={busy || !token.trim()}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await api.setRemoteToken(p.id, token);
              setToken("");
              onChange();
            } catch (e) {
              setError(msg(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          Sign In to {p.label}
        </button>
      </div>
      <p className="small muted">
        {p.hint}
        {p.installed ? ` Or run \`${p.cli} auth login\` in a terminal.` : ""}
      </p>
      {error ? (
        <p className="small" role="alert" style={{ color: "var(--negative)" }}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

function Picker({ p, onPick }: { p: RemoteProvider; onPick: (r: RemoteRepoRow) => void }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<RemoteRepoRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      api
        .remoteRepos(p.id, q)
        .then((r) => live && (setRows(r), setError(null)))
        .catch((e) => live && (setRows([]), setError(msg(e))));
    }, 250);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [p.id, q]);
  const id = `remote-search-${p.id}`;
  return (
    <div className="remote__picker">
      <label htmlFor={id} className="small">
        Search your {p.label} repos
      </label>
      <input id={id} className="input" value={q} onChange={(e) => setQ(e.target.value)} />
      {error ? (
        <p className="small" role="alert" style={{ color: "var(--negative)" }}>
          {error}
        </p>
      ) : null}
      <ul className="remote__list" aria-label={`Your ${p.label} repos`}>
        {rows === null ? <li className="small muted">Loading…</li> : null}
        {rows?.length === 0 && !error ? <li className="small muted">No matching repos.</li> : null}
        {rows?.map((r) => (
          <li key={r.url}>
            <button type="button" onClick={() => onPick(r)}>
              <strong>{r.full_name}</strong>
              {r.private ? <span className="remote__tag"> private</span> : null}
              {r.description ? <span className="small muted"> {r.description}</span> : null}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Add a repo that isn't on this machine: paste its address or pick one of yours; Rig clones it. */
export function RemoteRepoForm({ onAttached }: { onAttached: (r: RepoRef, warning?: string) => void }) {
  const [providers, setProviders] = useState<RemoteProvider[]>([]);
  const [url, setUrl] = useState("");
  const [stage, setStage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const timer = useRef<number | null>(null);
  const loadStatus = useCallback(() => {
    api
      .remotesStatus()
      .then(setProviders)
      .catch(() => setProviders([]));
  }, []);
  useEffect(loadStatus, [loadStatus]);
  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );
  const working = stage !== null;
  useEffect(() => {
    if (!working) return;
    setSeconds(0);
    const t = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, [working]);

  const poll = (job: string) => {
    timer.current = window.setTimeout(async () => {
      try {
        const j = await api.cloneJob(job);
        if (j.state === "running") {
          setStage(j.stage);
          poll(job);
        } else if (j.state === "done" && j.repo) {
          setStage(null);
          setUrl("");
          onAttached(j.repo, j.warning);
        } else {
          setStage(null);
          setError(j.error ?? "The clone failed.");
        }
      } catch (e) {
        setStage(null);
        setError(msg(e));
      }
    }, 700);
  };

  const signed = providers.filter((p) => p.signed_in);
  return (
    <form
      className="attach remote"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!url.trim() || working) return;
        setError(null);
        setStage("Starting…");
        try {
          poll((await api.cloneRepo(url.trim())).job);
        } catch (err) {
          setStage(null);
          setError(msg(err));
        }
      }}
    >
      <label htmlFor="remote-url" className="attach__label">
        Repo address or owner/name
      </label>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input
          id="remote-url"
          className="input mono"
          placeholder="https://github.com/owner/name"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={working}
        />
        <button type="submit" className="btn btn--primary" disabled={working || !url.trim()}>
          {working ? "Cloning…" : "Clone"}
        </button>
      </div>
      <p className="small muted">
        GitHub, GitLab, or your own GitLab by its full address. Public repos need no sign-in. Cloned shallow, under
        ~/.proving-ground/repos.
      </p>
      {working ? (
        <p className="small" role="status">
          {stage} ({seconds}s)
        </p>
      ) : null}
      {error ? (
        <p className="small" role="alert" style={{ color: "var(--negative)" }}>
          {error}
        </p>
      ) : null}
      {providers.map((p) => (
        <SignIn key={p.id} p={p} onChange={loadStatus} />
      ))}
      {signed.map((p) => (
        <Picker key={`${p.id}-${p.via}`} p={p} onPick={(r) => setUrl(r.url)} />
      ))}
    </form>
  );
}
