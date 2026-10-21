import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e", workers: 1, timeout: 60000, retries: 0,
  use: { baseURL: "http://127.0.0.1:18761", trace: "retain-on-failure", ...devices["Desktop Chrome"], ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) },
  webServer: [
    { command: `"${process.env.E2E_PYTHON || "python"}" ../scripts/e2e_server.py`, url: "http://127.0.0.1:18760/api/health", reuseExistingServer: false, timeout: 30000 },
    { command: "npm run dev -- --host 127.0.0.1 --port 18761 --strictPort", url: "http://127.0.0.1:18761", reuseExistingServer: false, timeout: 30000 },
  ],
});
