import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "dot" : "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node tests/e2e/pairing-broker.mjs",
      url: "http://127.0.0.1:3775/healthz",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1",
      env: {
        GLIO_AUTH_DATABASE_PATH: path.join(process.cwd(), "test-results", "auth.sqlite3"),
        T3_CODE_URL: "http://127.0.0.1:3775",
        T3_PAIRING_BROKER_URL: "http://127.0.0.1:3775/pairing",
      },
      url: "http://127.0.0.1:3000/healthz",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
