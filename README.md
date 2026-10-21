# doc-intake-service

A local document review workspace for one person handling invoices and business documents. Upload TXT, an image or a multipage PDF; background workers propose text, fields and a document type; compare them with the original, correct mistakes, revalidate, and explicitly approve or reject. SQLite keeps originals, decisions, duplicate identity and review history across restarts. JSON/CSV exports contain **approved records only**. Nothing is automatically approved.

**[Try the guided browser preview](https://mithundas79.github.io/doc-intake-service/)** | [Preview source](demo/) | [Install the complete app](#install-the-complete-local-application) | [Run the tests](#test-the-application-and-preview)

The browser preview uses three fictional samples and prepared field snapshots: **no Python API, native OCR, live classifier or SQLite runs on GitHub Pages**. You can also build it locally with the commands below. Check the [Pages release workflow](https://github.com/mithundas79/doc-intake-service/actions/workflows/pages.yml) for deployment status.

## What this does, and where it runs

| Capability | Guided browser preview | Complete local application |
| --- | --- | --- |
| Input | Three bundled fictional TXT samples | Your UTF-8 TXT, common images and multipage PDFs |
| Text and type proposals | Prepared snapshots, explicitly labeled | Native Tesseract OCR, embedded PDF text and a trained classifier |
| Human review | Edit, save/revalidate, approve/reject sample fields | Backend-validated corrections and explicit decisions |
| Original comparison | Fictional original text beside prepared fields | Stored original preview beside extracted fields |
| Export | Client-side approved-only JSON/CSV downloads | Transactional approved-only exports with audit events |
| History and duplicates | Memory in this tab; resets on reload; no duplicate detection | Durable SQLite history and byte/business-identity duplicate checks |

Only invoices have automated accounting checks. Contracts, statements, receipts, credit notes and other types require explicit manual review. The English-first extractor and classifier are fallible; this is a focused single-user local application, not an authenticated multi-user production service or professional accounting/legal judgment.

## Try the guided preview

The default **Incorrect total** sample deliberately states 349.84. Its subtotal 304.00 plus tax 25.84 equals 329.84.

1. Compare the original with the fields. Approval starts disabled.
2. Change **Total** to **329.84** and click **Save & revalidate**. The status becomes **ready**, while the approved count remains 0.
3. Click **Approve sample**. The status becomes **approved** and downloads include exactly that sample.
4. Download approved JSON/CSV and inspect the corrected total. Try **Manual review**: confirm the type, enter a note such as `Read the terms and verified the parties and date`, save/revalidate, then explicitly decide. Invoice arithmetic is not applied to the agreement.
5. Try **Valid invoice**: it starts ready but is not exported until approved. Rejection requires a reason and excludes the sample from exports.
6. **Reset all samples** or reload to restore the original samples and clear in-memory edits, approvals and activity. Already downloaded files remain on your computer.

The preview is an illustrative client-side workflow, not a replacement for the Python rule engine. It performs no uploads or duplicate checks. Its small validation functions and activity display are clearly distinguished from backend validation and durable audit.

To build and run only this static preview, install Node 20.20+ and run from the repository root (after cloning as below):

```sh
npm --prefix ui ci
npm --prefix ui run build:demo
npm --prefix ui run preview:demo -- --host 127.0.0.1 --port 18762 --strictPort
```

Open **http://127.0.0.1:18762/doc-intake-service/**. This serves the built Pages bundle at its real project base path. It needs no Python or Tesseract. Browser automation for it is separate from the full application's tests.

## Install the complete local application

Clone `main` using the platform-specific commands below. The complete application and guided preview share this repository.

| Requirement | Version / check |
| --- | --- |
| Git | Needed to clone the repository |
| Python | 3.12 tested; `python3 --version` on Linux/macOS or `py -3.12 --version` on Windows |
| Node and npm | Node 20.20 tested; `node --version` and `npm --version` |
| Native Tesseract + English language data |5.x; `tesseract --version` and `tesseract --list-langs` (must include `eng`) |

Ubuntu: `sudo apt-get install tesseract-ocr`. macOS: `brew install tesseract`. On Windows, install Tesseract and add its executable directory to PATH, or set `TESSERACT_CMD` to the full executable path before running the server. No paid cloud account, GPU or external model API is required. Initial package installation downloads dependencies; OCR/classification then run locally.

**Linux / macOS, fresh checkout:**

```sh
git clone --branch main --single-branch https://github.com/mithundas79/doc-intake-service.git
cd doc-intake-service
python3 -m venv .venv
.venv/bin/python -m pip install -r server/requirements-dev.txt
npm --prefix ui ci
tesseract --version
```

**Windows PowerShell, fresh checkout:**

```powershell
git clone --branch main --single-branch https://github.com/mithundas79/doc-intake-service.git
cd doc-intake-service
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r server\requirements-dev.txt
npm --prefix ui ci
tesseract --version
# If Tesseract is not on PATH, set this in the backend terminal:
# $env:TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

A trained model is committed. Training is optional, not a hidden startup requirement. To reproduce the synthetic training pipeline:

```sh
# Linux/macOS; on Windows use .\.venv\Scripts\python.exe instead:
.venv/bin/python training/generate_corpus.py
.venv/bin/python training/train.py
```

## Run the complete application

Use two terminals, both starting in the repository root. The commands choose a stable database directory and bind only to loopback.

**Terminal 1 - backend, Linux / macOS:**

```sh
DOC_INTAKE_DATA="$PWD/server/data" .venv/bin/python -m uvicorn --app-dir server doc_intake_service.app:app --host 127.0.0.1 --port 18760
```

**Terminal 1 - backend, Windows PowerShell:**

```powershell
$env:DOC_INTAKE_DATA = Join-Path (Get-Location) 'server\data'
.\.venv\Scripts\python.exe -m uvicorn --app-dir server doc_intake_service.app:app --host 127.0.0.1 --port 18760
```

**Terminal 2 - React UI, either platform:**

```sh
npm --prefix ui run dev -- --host 127.0.0.1 --port 18761 --strictPort
```

Open **http://127.0.0.1:18761**. The UI proxies `/api` to 18760; backend API docs are at http://127.0.0.1:18760/docs. Use one backend process, without `--workers` or reload. A directory lock prevents a second worker owner. Stop the server with Ctrl+C and restart using the same data directory to preserve the review result.

`npm --prefix ui run build` builds the production UI. With the backend running, `npm --prefix ui run preview -- --host 127.0.0.1 --port 18761 --strictPort` previews that build with the same proxy. This is distinct from `preview:demo`.

## Walk through real intake

| Sample / action | Expected result in the local app |
| --- | --- |
| Upload `samples/valid-invoice.txt` | `ready`; explicit approval still required before export |
| Upload `samples/incorrect-total.txt` | `review`; correct total 349.84 to 329.84, save/revalidate, then explicitly approve |
| Restart and upload the valid invoice again | Original approval/history persist; the duplicate check fails and blocks approval |
| Upload `samples/two-page-invoice.pdf` | Both embedded-text pages are read without OCR |
| Upload `samples/scanned-invoice.png` or `.pdf` | Actual native Tesseract is used; review its extracted text/fields |
| Upload `samples/manual-contract.txt` | Manual-only review; confirm contract type and add a 10-character review note, then save/revalidate and decide |
| Export approved JSON/CSV | Only explicitly approved records are included; mutations and exports appear in history |

The valid TXT, text PDF and scanned invoice share the same invoice identity. After the first is present, the others deliberately demonstrate cross-format duplicate detection; use a fresh `DOC_INTAKE_DATA` directory to observe each one's independent ready result. A rejected original can be reopened with a reason after a mistaken rejection. All new samples are fictional and rights-safe. `scripts/make_samples.py` recreates them using Pillow/ReportLab and an installed font; raster appearance can vary.

## Test the application and preview

Run from the repository root. Full application tests use a fresh temporary database and actual backend HTTP requests; the three browser workflows run the React UI plus backend, not mock responses. The separate static demo suite serves **built** output at `/doc-intake-service/` and exercises actual sample interactions/downloads at desktop/mobile sizes.

**Linux / macOS:**

```sh
(cd server && ../.venv/bin/python -m pytest -q -ra)
.venv/bin/python evaluation/evaluate.py
npm --prefix ui run typecheck
npm --prefix ui run build
(cd ui && npx playwright install chromium)
E2E_PYTHON="$PWD/.venv/bin/python" npm --prefix ui run test:e2e
npm --prefix ui run build:demo
npm --prefix ui run test:demo
```

**Windows PowerShell:**

```powershell
Push-Location server
..\.venv\Scripts\python.exe -m pytest -q -ra
Pop-Location
.\.venv\Scripts\python.exe evaluation\evaluate.py
npm --prefix ui run typecheck
npm --prefix ui run build
Push-Location ui
npx playwright install chromium
Pop-Location
$env:E2E_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
npm --prefix ui run test:e2e
npm --prefix ui run build:demo
npm --prefix ui run test:demo
```

On Linux, if Chromium reports missing system libraries, run `npx playwright install --with-deps chromium` from `ui/`. Optionally set `PLAYWRIGHT_CHANNEL=chrome` to use an installed Chrome. Test servers reserve 18760/18761 for the complete app and 18762 for the built preview; stop manually running copies before browser tests. Native OCR tests require Tesseract and are skipped when it is absent locally; CI installs Tesseract and runs them. CI preserves the original 43 Python + 3 application-browser checks and adds the static preview interactions/screenshots.

The demo build commands reuse the existing UI tool dependencies; there is no second install or Python dependency for `demo/`. The Pages workflow builds on main/manual dispatch and deploys only from main, subject to the `github-pages` environment protections. Publishing configuration and live URL verification are separate from building/testing the PR.

## Evaluation: useful evidence, limited claims

[Separate evaluation details](evaluation/README.md) and [actual predictions/results](evaluation/results.json) are committed. The generator's 300 related held-out documents score 100%; the separately authored fictional 24-text set scores **75% (18/24)** with macro F1 .748. Both are synthetic and English-only. Neither measures real-world accuracy, OCR quality, reliable accounting or legal suitability. The preview does not run either evaluation or the classifier.

See [implementation and verification evidence](docs/implementation-status.md) for exact observed runs, earlier failure history and scope limits.

## Persistence and processing policy

SQLite `intake.sqlite3` stores original bytes, SHA-256 hashes, extracted text, decimal field strings, predictions, checks, duplicate identity, versions, decisions and audit events transactionally. WAL mode and `synchronous=FULL` are enabled. No original filename is used as a storage path. Back up the data directory only while the service is stopped (or use SQLite's backup API); copying a live database without its WAL is unsafe. Old demo `audit.jsonl` entries are not migrated automatically.

The API persists the upload then returns HTTP 202. Two workers claim queued jobs in transactions and each launches a separate decoder process, preventing simultaneous PDFium calls in threads. At most 32 queued/processing jobs are admitted. A child has a hard 240-second deadline; each Tesseract page has 20 seconds. POSIX children additionally have a 1.5 GiB address-space ceiling. Windows applies input/page/pixel/time bounds but has no OS address-space ceiling. A native decoder crash or error becomes a visible failed job. Interrupted processing jobs are requeued at startup if fewer than three attempts have started; after three interruptions they fail with an explanation. Completed ready/review/approved/rejected/failed states are not reprocessed automatically. A failed input can be uploaded again after its cause is fixed.

Input limits: 8 MiB/file, bounded request body before multipart spooling, UTF-8 TXT, PNG/JPEG/WebP/BMP/TIFF, PDF, at most 10 PDF pages or image frames, at most 16 million rendered/image pixels per page, and 500000 extracted text characters. Embedded-text PDF pages avoid OCR; pages with fewer than 20 non-whitespace characters are rendered and OCRed. Encrypted PDFs are rejected. Mixed text/image pages with substantial embedded text do not currently OCR additional image regions. Garbled existing text layers, rotation, photos and unusual layouts can need manual correction. Corrupt and unsupported inputs produce explicit upload or failed-job errors.

Review operations require the current document version and a unique request ID. SQLite serializes them. Repeating the same request returns its original response; reusing an ID with different contents or applying a stale version returns HTTP 409. Approval rechecks all rules inside the transaction. Separate uniqueness constraints on approved byte hashes and business identities prevent concurrent duplicate approvals. Approved decisions are immutable. Rejection can be reversed only through an audited reopen operation with a reason.

Duplicate identity is **SHA-256 of exact original bytes OR normalized vendor + document number + currency + total**. The earliest non-failed document reserves the identity, including while awaiting review or after rejection. Failed jobs do not reserve it. If the first copy was rejected accidentally, reopen it. Identity is recalculated after corrections. Manual documents lacking number/total use byte identity only, so semantic duplicates of those documents still require the reviewer to notice them. The rule is deliberately conservative, not fuzzy matching.

## Validation, money and exports

Invoices require a vendor, number, unambiguous valid ISO date, explicit supported currency, complete nonnegative subtotal/tax/total, exact subtotal + tax = total, and line-amount sum = subtotal. Missing tax requires an explicit reviewed zero rather than inference. Amounts are stored/exported as two-decimal strings and checked using Decimal, with a maximum magnitude of 9999999999.99; NaN, infinity and extra decimal precision are rejected. Extraction is conservative English-first, uses dot decimals, accepts comma grouping, and does not infer European decimal commas. USD/EUR/GBP/INR are supported without exchange conversion; missing/multiple currency indicators become UNKNOWN and require correction. Ambiguous numeric dates are not guessed. Extracted amounts/line sums are proposals; the reviewer must verify them against the original.

Classifier confidence below 0.70 requires a checked type confirmation. All non-invoice types additionally require that confirmation and a review note of at least 10 characters. They still require vendor/counterparty, date, currency and no duplicate. This is metadata review, not automated legal analysis, bank reconciliation or receipt accounting. A reviewer can correct the suggested type, including choosing `other`.

Exports are auditable POST operations. JSON/CSV contain the approved snapshot with IDs and useful fields. Filenames are fixed server-side. CSV quotes/commas/newlines are handled by the standard CSV writer; cells beginning with spreadsheet formula markers, including after leading whitespace, are prefixed with an apostrophe. Treat any exported source data with appropriate care in downstream software. Audit export events record included document IDs and versions. The local audit is durable, not tamper-proof against someone with filesystem access.

## Local security boundary

**Run only on loopback for one trusted user.** There are no accounts, authentication, authorization, encryption at rest, malware scanner, tenant isolation or production operations guarantees. Originals and audit corrections may contain sensitive data; protect and back up the data directory yourself. Do not use network shares or expose this server through public tunnels/reverse proxies. Uploaded PDFs/images invoke native parsers; use documents you trust and keep native dependencies updated.

The HTTP gate rejects untrusted Host, external/null Origin and cross-site browser requests, including simple multipart POSTs. Only the local UI origins on ports 18761/5173 or the request's same origin are trusted; scripts without Origin are permitted. This reduces drive-by browser access but is not authentication against another program or user on the machine. IDs resolve database rows, never caller-supplied paths. Original responses use safe generated filenames, nosniff and a sandbox CSP. No source text is sent to an external model/service.

## API

`GET /api/health`, `POST /api/documents` (multipart), `GET /api/documents`, `GET /api/documents/{id}`, `GET /api/documents/{id}/original`, `GET /api/documents/{id}/history`.

`POST /api/documents/{id}/review` takes `{version, request_id, record, doc_type, type_confirmed, note}`. It saves corrections and revalidates atomically. `POST .../approve`, `.../reject`, `.../reopen` take `{version, request_id, note}`. `POST /api/exports/json` or `/csv` exports approved records and records the export event. See `/docs` on the backend for request schemas. Statuses: queued  ->  processing  ->  ready/review/failed; ready/review  ->  approved/rejected; rejected  ->  ready/review through explicit reopen.

## License

Repository code and newly authored fixtures: MIT. Dependencies retain their own licenses: pypdf is BSD-3-Clause; pypdfium2's helper code is Apache-2.0/BSD-3-Clause with bundled PDFium third-party notices; Tesseract is Apache-2.0; Pillow, ReportLab, scikit-learn, FastAPI, React and their transitive dependencies have separate licenses. Consult installed distribution notices before redistributing. This project does not use PyMuPDF.
