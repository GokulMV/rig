# Security

## Reporting a problem

Please report a vulnerability privately, through GitHub's "Report a vulnerability" button on
this repo's Security tab. Don't open a public issue for it. Say what you found, how to reproduce
it, and what it lets someone do.

## What Rig promises about keys

- A key or token you type into the app (an agent's API key, a Claude subscription token, a
  GitHub or GitLab token) is held in the engine's memory only. Rig never writes it to a file,
  the database or a log, and the API never returns it. It is gone when you quit.
- A key in your shell's environment (`ANTHROPIC_API_KEY` and the like) is read from there.
- A login already on this machine (Codex's `~/.codex/auth.json`, Gemini's
  `~/.gemini/oauth_creds.json`, OpenCode's) stays the file its own CLI wrote. Rig checks that it
  exists and tells Harbor to use it; Harbor copies it into that trial's sandbox.
- A GitHub or GitLab token reaches git only in the environment of one command, read by an askpass
  script that holds no secret. It is never in a clone's remote URL or on a command line.
- In a trial, the agent gets its key as an environment variable, because it needs it to reach
  its model. The sandbox can reach only that model's hosts. The check runs with no network.

## Known limits

Trials run through [Harbor](https://pypi.org/project/harbor/) 0.24.0, which handles the key
inside a trial like this:

- Each trial's `config.json` under `<repo>/.proving-ground/runs/` records the agent's environment
  with secret values replaced: a key from your shell is written as `${NAME}`; a key typed in the
  app is written as its first 4 and last 3 characters with `****` between.
- Trial logs are scrubbed of the key's value when the trial ends. If the engine is killed during
  a trial, a log the agent wrote could keep a key it printed. Binary files are not scrubbed.
- While a trial runs, the key is an argument to `docker compose exec`, so other processes of
  your user can see it (for example with `ps`).

## Other safeguards

- The engine listens on 127.0.0.1 only.
- No paid model call runs without your go-ahead. Tests use fakes.
- Dependencies are pinned to exact versions at least two weeks old.
