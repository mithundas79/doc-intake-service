# Separate evaluation

`independent.jsonl` contains 24 fictional documents, six per class, authored directly for evaluation. It does not import the corpus generator or its vendor/item/template lists, and training never reads this directory. Wording includes engagement letters, confidentiality undertakings, cash/payment confirmations, account movements and unfamiliar bills. The texts and labels are provided under the repository MIT license; no external documents, personal data or copyrighted scans were copied.

This is **separately prepared synthetic evaluation**, not blind independent third-party validation. The fixtures were written as part of this implementation with knowledge of the system's supported labels. They were not used to fit or tune the classifier or thresholds. After inspection they should be treated as a development benchmark, not a forever-unseen test set.

Run from the root with the documented Python dependencies:

```sh
python evaluation/evaluate.py
```

The command loads the committed model, records model/fixture SHA-256, evaluates every fixture, and writes `results.json` including each prediction/confidence, confusion matrix, exact per-class scores and pre-review readiness. Observed result for the committed model:

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| contract | 1.000 | .833 | .909 | 6 |
| invoice | .667 | .667 | .667 | 6 |
| receipt | .600 | 1.000 | .750 | 6 |
| statement | 1.000 | .500 | .667 | 6 |

Accuracy: **18/24 = 75%**. Macro F1: **.748**. One document passed pre-review validation; the application still requires explicit approval. Classification confusions include statements predicted as invoices/receipts and an engagement contract predicted as a receipt. Those weaknesses are visible rather than filtered from the report.

For comparison, `server/doc_intake_service/model/metrics.json` records 100% accuracy on 300 held-out documents sharing the training generator (1200 total). That validates a narrow synthetic pipeline and is substantially easier than these unfamiliar texts. Neither number estimates real-world accuracy. This 24-text set is small, English-only, still fictional, and not representative of photographed/rotated/non-English documents. It does not quantify OCR/extraction accuracy or correctness of human decisions. Committed image/PDF samples and native integration tests demonstrate specific paths, not broad OCR quality. Additional independent labelled documents and prospective evaluation are required before making any accuracy claim.
