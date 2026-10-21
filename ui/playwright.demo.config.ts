import { defineConfig, devices } from "@playwright/test";

const publishedURL = process.env.PUBLISHED_DEMO_URL;
const allowedPublishedURL = "https://mithundas79.github.io/doc-intake-service/";
if (publishedURL !== undefined && publishedURL !== allowedPublishedURL) {
  throw new Error(`PUBLISHED_DEMO_URL must be exactly ${allowedPublishedURL}`);
}

// Local mode serves dist at the project path. Published mode uses only the
// public fictional preview and never starts a local server or Python backend.
export default defineConfig({
  testDir: "./e2e-demo",
  outputDir: publishedURL ? "./test-results-demo-live" : "./test-results-demo",
  reporter: publishedURL
    ? [["line"], ["junit", { outputFile: "test-results-demo-live/results.xml" }]]
    : undefined,
  workers: 1,
  retries: 0,
  timeout: 30000,
  use: {
    baseURL: publishedURL ?? "http://127.0.0.1:18762/doc-intake-service/",
    trace: "retain-on-failure",
    ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}),
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1100 } } },
    { name: "mobile", use: { ...devices["iPhone 13"], browserName: "chromium" } },
  ],
  webServer: publishedURL ? undefined : {
    command: "npm run preview:demo -- --host 127.0.0.1 --port 18762 --strictPort",
    url: "http://127.0.0.1:18762/doc-intake-service/",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
