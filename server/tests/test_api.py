import io

import pytest
from fastapi.testclient import TestClient

from doc_intake_service.app import app
from doc_intake_service.classify import MODEL_PATH

pytestmark = pytest.mark.skipif(
    not MODEL_PATH.exists(), reason="train the model first (training/train.py)"
)

client = TestClient(app)

INVOICE = b"""Northwind Supplies
INVOICE
Invoice No: NW-2026-0481
Invoice Date: 12 Aug 2026
Filter cartridges 10 in 24 408.00
Sealing rings box of 50 6 171.00
Delivery 1 45.00
Subtotal 624.00
Tax 8.5% 53.04
Total Due 677.04"""

RECEIPT = b"""HARBOR COFFEE ROASTERS
RECEIPT
02 Sep 2026 09:41
2x Flat White 9.00
1x Almond croissant 4.50
Total 13.50
VISA **** 4412 - APPROVED
Thank you for your visit"""


def test_health_reports_model_and_honest_note():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["model_present"] is True
    assert "synthetic" in body["model_note"]


def test_txt_invoice_files_itself():
    r = client.post(
        "/api/documents",
        files={"file": ("invoice.txt", io.BytesIO(INVOICE), "text/plain")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ocr_used"] is False
    assert body["prediction"]["label"] == "invoice"
    assert body["verdict"] == "file"
    assert "text" in body  # full text returned for a direct upload


def test_receipt_is_classified_as_receipt():
    r = client.post(
        "/api/documents",
        files={"file": ("coffee.txt", io.BytesIO(RECEIPT), "text/plain")},
    )
    assert r.status_code == 200
    assert r.json()["prediction"]["label"] == "receipt"


def test_empty_upload_is_rejected():
    r = client.post("/api/documents", files={"file": ("x.txt", io.BytesIO(b""), "text/plain")})
    assert r.status_code == 400


def test_listing_omits_document_bodies():
    r = client.get("/api/documents")
    assert r.status_code == 200
    assert all("text" not in row for row in r.json())
