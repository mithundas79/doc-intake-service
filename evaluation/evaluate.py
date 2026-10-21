"""Evaluate only; this file and its fixtures are never imported by training."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from sklearn.metrics import classification_report, confusion_matrix
from doc_intake_service.classify import classify, MODEL_PATH
from doc_intake_service.extract import extract
from doc_intake_service.rules import normalize_record, validate

source = Path(__file__).with_name("independent.jsonl")
rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
labels = sorted(set(r["label"] for r in rows))
results = []
for row in rows:
    pred = classify(row["text"])
    record = normalize_record(extract(row["text"]).as_dict())
    checks = validate(record, pred.label, pred.confidence)
    results.append(dict(id=row["id"], expected=row["label"], predicted=pred.label,
                        confidence=round(pred.confidence, 4), ready_before_review=all(c["ok"] for c in checks)))
y = [r["expected"] for r in results]
pred = [r["predicted"] for r in results]
output = dict(fixture_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
              model_sha256=hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
              documents=len(rows), labels=labels,
              classification_report=classification_report(y, pred, output_dict=True, zero_division=0),
              confusion_matrix=confusion_matrix(y, pred, labels=labels).tolist(),
              results=results,
              limitations="24 hand-authored fictional text documents, six per class. Separately prepared from the training generator but still synthetic; not a blind real-world benchmark, not OCR or extraction accuracy. No training/tuning performed on this evaluation. Ready means deterministic checks passed, never auto-approved.")
Path(__file__).with_name("results.json").write_text(json.dumps(output, indent=2)+"\n", encoding="utf-8")
print(classification_report(y, pred, zero_division=0))
print("Ready before human review:", sum(r["ready_before_review"] for r in results))
