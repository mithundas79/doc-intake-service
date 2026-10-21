# Local document intake and review

An installable single-user FastAPI + React application. Upload an original, wait for bounded background extraction, compare the original with proposed fields, correct and revalidate, then explicitly approve or reject. **Nothing is automatically approved.** Only approved records appear in JSON/CSV exports.

The classifier is a small offline TF-IDF/logistic-regression model. Its suggestions are fallible. Accounting checks are implemented for invoices only. Contracts, statements, receipts, credit notes and other documents use a deliberate manual review workflow.

## Install and run

Tested stack: Python 3.12, Node 20.20, Tesseract 5 with English data. No cloud account, paid API or GPU is needed. Install Python/Node plus native Tesseract: Ubuntu `sudo apt-get install tesseract-ocr`; macOS `brew install tesseract`; Windows use the Tesseract installer and put its directory on PATH. `tesseract --version` must work. Alternatively set `TESSERACT_CMD` to its full executable path before starting the server.

From the repository root:

```sh
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell instead:
# .\.venv\Scripts\Activate.ps1
python -m pip install -r server/requirements-dev.txt
npm --prefix ui ci
```

A model is committed, so training is optional. To reproduce the original synthetic training metrics:

```sh
python training/generate_corpus.py
python training/train.py
```

Start the backend from **server/**, using the environment above:

```sh
cd server
python -m uvicorn doc_intake_service.app:app --host 127.0.0.1 --port 18760
```

Start the UI from **ui/** in another terminal:

```sh
npm run dev -- --host 127.0.0.1 --port 18761 --strictPort
```

Open http://127.0.0.1:18761. Vite proxies `/api` to 18760. Build with `npm --prefix ui run build`; `npm --prefix ui run preview -- --host 127.0.0.1 --port 18761` previews the same built UI and proxy. Use one server process, without `--workers` or development reload. A data-directory process lock prevents a second worker owner. Set `DOC_INTAKE_DATA` to an absolute directory to relocate storage; the default is `server/data` when launched as documented.

## Five-minute walkthrough

1. Upload `samples/valid-invoice.txt`. It becomes `ready`; verify the original beside the proposed fields and explicitly click **Approve document**. Ready is not approved.
2. Upload `samples/incorrect-total.txt`. The total 349.84 fails the arithmetic check. Change **total** to **329.84**, record your review note, click **Save corrections & revalidate**, then approve.
3. Stop and restart the backend with the same data directory. The documents, originals, fields, decisions and history remain. Upload the valid invoice again: **Not a duplicate** fails and approval is blocked. Duplicate recognition includes originals and business identity, including after restart.
4. Upload `samples/two-page-invoice.pdf`. Both pages contribute embedded text and OCR is skipped. It shares identity with the valid invoice, so will require duplicate handling if that sample is already present. To see a fresh ready result, use a separate empty `DOC_INTAKE_DATA` directory.
5. Upload `samples/scanned-invoice.png` or `samples/scanned-invoice.pdf`. Native Tesseract extracts the text. They also share the example invoice identity; that deliberately demonstrates cross-format duplicate detection.
6. Upload `samples/manual-contract.txt`. Select **contract**, check **I checked the document type**, and enter a note such as `Read the terms and verified the parties and effective date`. Save and revalidate, then explicitly approve or reject. Invoice arithmetic is not applied to a contract.
7. **Export approved JSON/CSV** downloads approved records only. Expand **Review history** for corrections, before/after fields, checks and decisions. A rejected record can be reopened with a reason; reopen the original after a mistaken rejection rather than uploading another copy.

All new samples are fictional, authored for this repository. `python scripts/make_samples.py` recreates them using Pillow/ReportLab and an installed font; raster appearance can vary by platform. No personal paperwork is included.

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

## Evaluation and verification

See [evaluation/README.md](evaluation/README.md) for independently prepared fixtures, actual per-class results, predictions and limitations. The generator's 300-document held-out score was 100%; the separately authored 24-document set scored **75% (18/24)**. Both are fictional text sets. Neither measures real-world accuracy, OCR performance, reliable accounting nor legal suitability. Do not use the training score as a generalization claim.

```sh
# From server/ with the Python environment activated:
python -m pytest -q -ra
# From repository root:
python evaluation/evaluate.py
npm --prefix ui run typecheck
npm --prefix ui run build
# From ui/; backend + frontend are started automatically on 18760/18761:
npx playwright install chromium
npm run test:e2e
```

For browser tests, activate the Python environment or set `E2E_PYTHON` to its executable (use quotes for paths with spaces). Optionally set `PLAYWRIGHT_CHANNEL=chrome` to use an installed Chrome. Tests use a fresh temporary database and actual HTTP requests; no mocked backend responses. CI installs Tesseract and Chromium, runs real OCR/PDF tests, typechecks/builds and runs the review/correction/approval/export browser experience. See [docs/implementation-status.md](docs/implementation-status.md) for exact observed results and environment limitations.

## API

`GET /api/health`, `POST /api/documents` (multipart), `GET /api/documents`, `GET /api/documents/{id}`, `GET /api/documents/{id}/original`, `GET /api/documents/{id}/history`.

`POST /api/documents/{id}/review` takes `{version, request_id, record, doc_type, type_confirmed, note}`. It saves corrections and revalidates atomically. `POST .../approve`, `.../reject`, `.../reopen` take `{version, request_id, note}`. `POST /api/exports/json` or `/csv` exports approved records and records the export event. See `/docs` on the backend for request schemas. Statuses: queued  ->  processing  ->  ready/review/failed; ready/review  ->  approved/rejected; rejected  ->  ready/review through explicit reopen.

## License

Repository code and newly authored fixtures: MIT. Dependencies retain their own licenses: pypdf is BSD-3-Clause; pypdfium2's helper code is Apache-2.0/BSD-3-Clause with bundled PDFium third-party notices; Tesseract is Apache-2.0; Pillow, ReportLab, scikit-learn, FastAPI, React and their transitive dependencies have separate licenses. Consult installed distribution notices before redistributing. This project does not use PyMuPDF.
