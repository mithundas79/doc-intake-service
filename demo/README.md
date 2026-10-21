# Guided sample preview

A separate static workflow illustration for GitHub Pages, built at `/doc-intake-service/`. It is not the production React UI with a fake backend. This preview performs no API calls, uploads, OCR, live classification or SQLite storage.

Original text is imported directly from the three fictional application samples in `samples/`. `src/fixtures.ts` declares prepared field snapshots. `src/main.ts` contains small, explicitly labeled client-side sample checks; the Python backend remains authoritative for the complete local application.

From the repository root:

```sh
npm --prefix ui ci
npm --prefix ui run build:demo
npm --prefix ui run preview:demo -- --host 127.0.0.1 --port 18762 --strictPort
```

Open http://127.0.0.1:18762/doc-intake-service/. No Python setup is required. The public preview address is https://mithundas79.github.io/doc-intake-service/. Check the [Pages release workflow](https://github.com/mithundas79/doc-intake-service/actions/workflows/pages.yml) for deployment status.

Follow the in-page walkthrough: correct total 349.84 to 329.84, save/revalidate, explicitly approve, and download approved-only JSON/CSV. The manual contract requires type confirmation and a review note. Rejection requires a reason and discards unsaved field/type changes. Reset or reload restores all prepared samples and clears in-memory decisions and activity; it does not delete previously downloaded files.

To test built output, install Chromium once from `ui/` with `npx playwright install chromium`, then run:

```sh
npm --prefix ui run build:demo
npm --prefix ui run test:demo
```

The separate Playwright configuration serves `demo/dist` under the real project base path at desktop/mobile sizes. It tests corrections, approval, downloads, manual review, rejection, CSV cell safety, reset and keyboard focus, captures screenshots and asserts that no Python API requests occur.

The Pages workflow builds on main/manual dispatch and deploys only from main, subject to the `github-pages` environment protections. Live-page verification follows a successful deployment; the source build alone does not establish that a deployment is available.

All fixtures are fictional and provided under the repository MIT license. The separate classifier evaluation scores 75% on 24 authored fictional texts; this static preview does not run that evaluation or claim real-world accuracy. See the [root README](../README.md) for local installation, test commands and operating limits.
