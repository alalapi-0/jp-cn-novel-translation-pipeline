import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/ui",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  outputDir: "artifacts/playwright",
  webServer: {
    command: "python3 scripts/serve_frontend.py --port 5174",
    port: 5174,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
