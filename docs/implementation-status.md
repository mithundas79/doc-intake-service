# Implementation checkpoint

Branch: feature/persistent-document-review. Issue: #1.

## Acceptance mapping

- Durable originals, fields, jobs, decisions, duplicate identity, history: `store.py`; SQLite WAL/FULL transactions, originals stored as BLOBs in the same DB.
- Bounded processing/restart: two worker threads, queue cap 32, isolated decoder children, hard 240-second timeout; restart requeues interrupted attempts fewer than 3, otherwise fails visibly.
- Real text/image/multipage PDF: `pipeline.py`, pypdf + pypdfium2; embedded text skips OCR, scans invoke native Tesseract with 20-second per-page timeout; 8 MB, 10 pages, 16 MP/page and 500000 text-character bounds.
- React list/preview/correction/revalidation/explicit decisions/history: `ui/src/App.tsx`.
- Transactional review/idempotency/exports: expected version and request IDs; unique approval hash and business identity. Failed checks cannot approve. JSON/CSV contain approved records only; CSV formula cells escaped.
- Type policy: invoices checked with exact decimal arithmetic. Contracts, statements, receipts, credit notes and other are manual only; confirmation and explanatory note required.
- Security: loopback hosting, trusted Host/Origin gate including simple multipart requests, ASGI/request/file reading bounds, server IDs, no caller-provided filesystem paths. Single-user local boundary, no multi-tenant claims.
- Independent evaluation: 24 hand-authored fictional texts separate from generator in `evaluation/independent.jsonl`; actual `results.json` reports 18/24 correct (75%), never a real-world accuracy claim.
- Samples: valid/bad total TXT, manual contract, 2-page text PDF, PNG scan, scanned PDF; rights-safe authored sources plus generation script.
- CI/startup/docs and final verification: in progress.

## Observed verification at this checkpoint

- Initial Python suite before isolated-decoder addition: 38 passed, 1 failed in 12.02s. Failure was streamed oversized upload returning parser 400; changed raised exception to HTTPException 413. Rerun in progress, not yet claimed passed.
- `npm --prefix ui run build`: passed twice (TypeScript plus Vite build).
- `.venv/Scripts/python evaluation/evaluate.py`: completed; contract P/R/F1 1.00/.83/.91; invoice .67/.67/.67; receipt .60/1.00/.75; statement 1.00/.50/.67. 1/24 ready before review; zero automatically approved by application policy.
- First real Playwright run: correction/approval/refresh/export test passed; second upload/scan/manual test hit a UI timing assumption (waited on old document's shared status). Added explicit selected-document name waits before checks. Rerun pending. Windows webserver teardown hung and required stopping the known test-owned backend PID; not claimed as a passing browser run.

## Remaining work

Finish API and live-browser reruns; add CI and startup/walkthrough/security/evaluation docs; inspect output, push milestone and open draft PR. Windows has per-input/page/pixel/time limits but does not apply the POSIX child address-space ceiling. Classifier/extractor are English-first demo heuristics, not financial or legal judgment. Existing audit.jsonl from the old demo is not automatically migrated.

Checkpoint SHA: 71ab8c6 (first implementation milestone; pushed).

Additional updates: isolated-decoder hard-timeout and real HTTP subprocess restart tests, late-poll UI regression, CI and full walkthrough added. UI responses are guarded by effect cleanup and selected document identity; switching is disabled during mutations/uploads.

Local verification blocker: automatic approval review rejected polling the second Python suite, citing an unapproved telemetry request to dc.services.visualstudio.com with unknown payload. The second suite result is unknown, not passed. No rerun through another local launcher was attempted. First browser test passed locally, second timing failure fixed but local browser rerun remains unverified. Required GitHub CI will run against committed fictional data with real backend/frontend/OCR and publish artifacts. No host files or credentials are test fixtures.
