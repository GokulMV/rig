# Contributing

Thanks for helping. Bug reports, fixes and new benches are all welcome.

## Set up

Follow Install in `README.md`. You need Python 3.12+, uv, Node.js (22.22.2+, 24.15+ or 26+) and
Docker.

## Run the tests

Engine:

```bash
cd engine
uv run python -m pytest -q         # the default suite: no Docker, no model calls
uv run ruff check .                # lint, as CI runs it
uv run python -m pytest -m docker -q   # real containers; needs Docker running; free
```

The default suite leaves out three markers (see `addopts` in `engine/pyproject.toml`):

- `docker`: needs a running Docker daemon. Free: no model calls.
- `integration`: needs Docker and `ANTHROPIC_API_KEY`, and makes paid model calls. Run it only
  on purpose.
- `models`: loads the skill matcher's real models, a one-time download of about 1.1 GB.

Web:

```bash
cd web
npm ci
npm run typecheck
npm test
npm run build
npx playwright test                # browser tests against a fake engine (web/e2e/fake_server.py)
```

The Playwright tests use the Chrome installed on your machine, not a downloaded browser. They
start a fake engine on port 7361; set `PG_E2E_PORT` to use another.

CI (`.github/workflows/ci.yml`) runs the engine suite with ruff, and the web typecheck, unit
tests and build, on every push and pull request.

## Rules for changes

- Tests use fakes. No test in the default suite may call a paid model.
- Keys stay in memory. Nothing that handles a key may write it to a file, the database, a log or
  an API response. See `SECURITY.md`.
- Dependencies are pinned to exact versions at least two weeks old. The engine's resolver
  window is `exclude-newer` in `engine/pyproject.toml`; the web's is `before` in `web/.npmrc`.
- Keep the voice of the docs and the UI: short plain sentences.

## Pull requests

One change per pull request, with tests. Say what you ran to check it.
