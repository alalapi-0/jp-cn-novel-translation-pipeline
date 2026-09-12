import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";

const port = Number(process.env.PLAYWRIGHT_PORT || "5174");
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error("Invalid test port");
const python = existsSync(".venv/bin/python") ? ".venv/bin/python" : "python3";

export default defineConfig({
  testDir: "tests/ui",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  outputDir: "artifacts/playwright",
  webServer: {
    command: `${python} scripts/serve_ui_fixture.py --port ${port}`,
    port,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
