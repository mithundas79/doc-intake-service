"""One document end to end: OCR (when needed) -> extract -> classify -> rules -> verdict.

The service variant of the pipeline: OCR through native Tesseract via
pytesseract, document type from the trained classifier, and the same
authority split as everywhere else in this family - models and parsers
propose, rules decide.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
from dataclasses import dataclass
from pathlib import Path

import pytesseract
from PIL import Image

from .classify import TypePrediction, classify
from .extract import DocumentRecord, extract
from .rules import RuleResult, SessionDuplicateStore, check

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/bmp", "image/tiff"}


@dataclass
class ProcessedDocument:
    name: str
    sha256: str
    ocr_used: bool
    ocr_confidence: float | None
    text: str
    record: DocumentRecord
    prediction: TypePrediction
    checks: list[RuleResult]
    verdict: str  # "file" | "review"
    processed_at: float

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "ocr_used": self.ocr_used,
            "ocr_confidence": self.ocr_confidence,
            "text": self.text,
            "record": self.record.as_dict(),
            "prediction": self.prediction.as_dict(),
            "checks": [c.as_dict() for c in self.checks],
            "verdict": self.verdict,
            "processed_at": self.processed_at,
        }


def ocr_image(data: bytes) -> tuple[str, float | None]:
    image = Image.open(io.BytesIO(data))
    text = pytesseract.image_to_string(image, lang="eng")
    try:
        d = pytesseract.image_to_data(image, lang="eng", output_type=pytesseract.Output.DICT)
        confs = [int(c) for c in d.get("conf", []) if str(c).lstrip("-").isdigit() and int(c) >= 0]
        confidence = round(sum(confs) / len(confs), 1) if confs else None
    except Exception:  # confidence is a nicety, never a blocker
        confidence = None
    return text, confidence


class IntakeService:
    """Holds per-run state (duplicate memory, audit log) for the API."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.dupes = SessionDuplicateStore()
        self.processed: list[ProcessedDocument] = []

    def process(self, name: str, data: bytes, content_type: str | None) -> ProcessedDocument:
        is_image = (content_type in IMAGE_TYPES) or name.lower().endswith(
            (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
        )
        if is_image:
            text, ocr_confidence = ocr_image(data)
            ocr_used = True
        else:
            text = data.decode("utf-8", errors="replace")
            ocr_confidence = None
            ocr_used = False

        record = extract(text)
        prediction = classify(text)
        checks = check(record, prediction.label, prediction.confidence, self.dupes)
        verdict = "file" if all(c.ok for c in checks) else "review"

        doc = ProcessedDocument(
            name=name,
            sha256=hashlib.sha256(data).hexdigest(),
            ocr_used=ocr_used,
            ocr_confidence=ocr_confidence,
            text=text,
            record=record,
            prediction=prediction,
            checks=checks,
            verdict=verdict,
            processed_at=time.time(),
        )
        self.processed.append(doc)
        with (self.data_dir / "audit.jsonl").open("a", encoding="utf-8") as f:
            entry = doc.as_dict()
            entry.pop("text")  # the audit log records decisions, not full document bodies
            f.write(json.dumps(entry) + "\n")
        return doc
