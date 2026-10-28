import { defineConfig } from "@playwright/test";

// Several checkouts can test at once: each sets its own port and cache folder.
declare const process: { env: Record<string, string | undefined> };
const PORT = Number(process.env.PG_E2E_PORT ?? 7361);
const TAG = process.env.PG_E2E_TAG ?? "pg-e2e";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    // The installed Chrome: no browser download.
    channel: "chrome",
    viewport: { width: 1440, height: 900 },
  },
  webServer: {
    // A fresh seeded project with Docker and the Claude API replaced by fakes (e2e/fake_server.py).
    command: `rm -rf "$HOME/.cache/${TAG}" "$HOME/.cache/${TAG}-user-skills" "$HOME/.cache/${TAG}-home" "$HOME/.cache/${TAG}-blog" && cd ../engine && uv run python ../web/e2e/fake_server.py --root "$HOME/.cache/${TAG}" --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/project`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
