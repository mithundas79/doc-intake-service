"""Real parser and native OCR coverage. CI requires Tesseract; no OCR mocks."""
import io
import shutil
from unittest.mock import patch

import pytest
from pypdf import PdfWriter
from PIL import Image
from doc_intake_service.pipeline import read_document
from conftest import SAMPLES, upload


def test_multipage_embedded_pdf_never_calls_ocr(client):
    with patch("doc_intake_service.pipeline.image_text", side_effect=AssertionError("OCR must not run for embedded text")):
        text, used, pages = read_document((SAMPLES / "two-page-invoice.pdf").read_bytes(), "application/pdf")
        assert not used and pages == 2 and "Supporting delivery note" in text
    row = upload(client, "two-page-invoice.pdf")
    assert row["state"] == "ready", row
    assert row["pages"] == 2
    assert "Supporting delivery note" in row["text"]
    assert row["ocr_used"] is False
    assert row["record"]["total"] == "677.04"

@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Install native Tesseract 5; CI installs and requires it")
@pytest.mark.parametrize("name", ["scanned-invoice.png", "scanned-invoice.pdf"])
def test_native_tesseract_on_committed_scan(client, name):
    row = upload(client, name)
    assert row["state"] == "ready", row
    assert row["ocr_used"] is True
    assert row["record"]["vendor"] == "Northwind Supplies"
    assert row["record"]["total"] == "677.04"
    assert row["prediction"]["label"] == "invoice"


def test_pdf_page_and_encryption_limits():
    pdf = PdfWriter()
    for _ in range(11):
        pdf.add_blank_page(100, 100)
    buffer = io.BytesIO(); pdf.write(buffer)
    with pytest.raises(ValueError, match="1 to 10 pages"):
        read_document(buffer.getvalue(), "application/pdf")
    pdf = PdfWriter(); pdf.add_blank_page(100, 100); pdf.encrypt("password")
    buffer = io.BytesIO(); pdf.write(buffer)
    with pytest.raises(ValueError, match="Encrypted"):
        read_document(buffer.getvalue(), "application/pdf")


def test_image_and_text_resource_bounds():
    buffer = io.BytesIO()
    Image.new("1", (5000, 4000)).save(buffer, format="PNG")
    with pytest.raises(ValueError, match="(megapixel|DecompressionBomb|pixels)"):
        read_document(buffer.getvalue(), "image")
    with pytest.raises(ValueError, match="500000"):
        read_document(b"x"*500001, "text/plain")


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Native Tesseract required")
def test_concurrent_scanned_pdfs_are_isolated(client):
    from concurrent.futures import ThreadPoolExecutor
    import doc_intake_service.store as store_module
    assert store_module.JOB_SECONDS == 240, "Prior timeout test must restore the decoder deadline"
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda _: upload(client, "scanned-invoice.pdf"), range(2)))
    assert sorted(r["state"] for r in rows) == ["ready", "review"], rows
    assert all(r["record"]["total"] == "677.04" and r["ocr_used"] for r in rows)
