"""The one test that runs native Tesseract, against a committed sample.

Skipped cleanly when the binary is absent, so the core suite works on a
machine without Tesseract; CI installs it and exercises this path.
"""

import shutil
from pathlib import Path

import pytest

from doc_intake_service.pipeline import IntakeService

pytestmark = pytest.mark.skipif(shutil.which("tesseract") is None, reason="native tesseract not installed")

SAMPLE = Path(__file__).parent.parent.parent / "samples" / "northwind-invoice.png"


def test_sample_invoice_survives_the_whole_pipeline(tmp_path):
    svc = IntakeService(tmp_path)
    doc = svc.process("northwind-invoice.png", SAMPLE.read_bytes(), "image/png")
    assert doc.ocr_used
    assert doc.record.vendor == "Northwind Supplies"
    assert doc.record.total == 677.04
    assert doc.prediction.label == "invoice"
    assert doc.verdict == "file"
