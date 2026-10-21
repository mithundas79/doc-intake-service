import { defineConfig, devices } from "@playwright/test";

// The deployed project path is part of the test. Serve dist, never the dev source.
export default defineConfig({
  testDir: "./e2e-demo",
  outputDir: "./test-results-demo",
  workers: 1,
  retries: 0,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:18762/doc-intake-service/",
    trace: "retain-on-failure",
    ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}),
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1100 } } },
    { name: "mobile", use: { ...devices["iPhone 13"], browserName: "chromium" } },
  ],
  webServer: {
    command: "npm run preview:demo -- --host 127.0.0.1 --port 18762 --strictPort",
    url: "http://127.0.0.1:18762/doc-intake-service/",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
