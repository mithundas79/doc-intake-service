import csv
import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from doc_intake_service.app import create_app, MAX_UPLOAD_BYTES, MAX_REQUEST_BYTES
from doc_intake_service.store import Store, Conflict
from conftest import SAMPLES, upload, wait, decision, review


def test_health_and_invoice_never_autoapproves(client):
    assert "synthetic" in client.get("/api/health").json()["model_note"]
    row = upload(client)
    assert row["state"] == "ready", row
    assert row["record"]["total"] == "677.04"
    assert row["ocr_used"] is False
    assert client.post("/api/exports/json").json() == []
    assert "text" not in client.get("/api/documents").json()[0]
    original = client.get(f"/api/documents/{row['id']}/original")
    assert original.content == (SAMPLES / "valid-invoice.txt").read_bytes()
    assert original.headers["x-content-type-options"] == "nosniff"


def test_correction_revalidation_approval_export_and_audit(client):
    row = upload(client, "incorrect-total.txt")
    assert row["state"] == "review"
    assert client.post(f"/api/documents/{row['id']}/approve", json=decision(row)).status_code == 409
    record = dict(row["record"], total="329.84", vendor="=DANGEROUS()")
    response = review(client, row, record=record, note="Checked total against source")
    assert response.status_code == 200, response.text
    fixed = response.json()
    assert fixed["state"] == "ready"
    approved = client.post(f"/api/documents/{row['id']}/approve", json=decision(fixed))
    assert approved.status_code == 200
    assert approved.json()["state"] == "approved"
    assert client.post("/api/exports/json").json()[0]["total"] == "329.84"
    csv_response = client.post("/api/exports/csv")
    exported = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
    assert exported[0]["vendor"] == "'=DANGEROUS()"
    assert csv_response.headers["content-disposition"] == 'attachment; filename="approved-records.csv"'
    history = client.get(f"/api/documents/{row['id']}/history").json()
    event = next(h for h in history if h["action"] == "review")
    assert event["details"]["before"]["record"]["total"] == "349.84"
    assert event["details"]["after"]["record"]["total"] == "329.84"
    assert sum(h["action"] == "approve" for h in history) == 1
    with client.app.state.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM audit WHERE action='export'").fetchone()[0] == 2


def test_restart_persists_original_approval_duplicate_and_history(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        row = upload(client)
        body = decision(row)
        approved = client.post(f"/api/documents/{row['id']}/approve", json=body).json()
    with TestClient(create_app(tmp_path)) as client:
        restored = client.get(f"/api/documents/{row['id']}").json()
        assert restored == approved
        assert client.get(f"/api/documents/{row['id']}/original").content == (SAMPLES / "valid-invoice.txt").read_bytes()
        assert client.post(f"/api/documents/{row['id']}/approve", json=body).json() == approved
        duplicate = upload(client)
        assert duplicate["state"] == "review"
        assert any(not c["ok"] and c["rule"] == "Not a duplicate" for c in duplicate["checks"])
        assert client.post(f"/api/documents/{duplicate['id']}/approve", json=decision(duplicate)).status_code == 409
        assert len(client.post("/api/exports/json").json()) == 1
        assert any(h["action"] == "approve" for h in client.get(f"/api/documents/{row['id']}/history").json())


def test_concurrent_approval_is_idempotent_and_stale_edits_conflict(client):
    row = upload(client)
    body = decision(row)
    path = f"/api/documents/{row['id']}/approve"
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda _: client.post(path, json=body), range(8)))
    assert all(r.status_code == 200 for r in responses)
    assert all(r.json()["state"] == "approved" for r in responses)
    assert len(client.post("/api/exports/json").json()) == 1
    history = client.get(f"/api/documents/{row['id']}/history").json()
    assert sum(h["action"] == "approve" for h in history) == 1
    assert review(client, row).status_code == 409
    assert client.post(path, json=dict(body, note="different contents")).status_code == 409


def test_two_concurrent_reviewers_do_not_lose_corrections(client):
    row = upload(client, "incorrect-total.txt")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda total: review(client, row, record=dict(row["record"], total=total)), ["329.84", "330.00"]))
    assert sorted(r.status_code for r in results) == [200, 409]


def test_distinct_documents_concurrent_duplicate_approval_blocked(client):
    first = upload(client)
    second = upload(client, data=(SAMPLES / "valid-invoice.txt").read_bytes() + b"\nReference copy")
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda r: client.post(f"/api/documents/{r['id']}/approve", json=decision(r)), [first, second]))
    assert sorted(r.status_code for r in responses) == [200, 409]


def test_manual_contract_and_rejection_reopen(client):
    row = upload(client, "manual-contract.txt")
    assert row["state"] == "review"
    assert client.post(f"/api/documents/{row['id']}/approve", json=decision(row)).status_code == 409
    fixed = review(client, row, doc_type="contract", type_confirmed=True, note="Read terms and verified counterparty and date").json()
    assert fixed["state"] == "ready", fixed
    assert not any("Subtotal" in c["rule"] for c in fixed["checks"])
    rejected = client.post(f"/api/documents/{row['id']}/reject", json=decision(fixed, "Wrong intake choice")).json()
    assert rejected["state"] == "rejected"
    duplicate = upload(client, "manual-contract.txt")
    assert any(c["rule"] == "Not a duplicate" and not c["ok"] for c in duplicate["checks"])
    reopened = client.post(f"/api/documents/{row['id']}/reopen", json=decision(rejected, "Rejection was a mistake")).json()
    assert reopened["state"] == "ready"
    assert client.post(f"/api/documents/{row['id']}/approve", json=decision(reopened)).json()["state"] == "approved"


@pytest.mark.parametrize("name,data", [("corrupt.png", b"not an image"), ("corrupt.pdf", b"%PDF broken"), ("binary.txt", b"\x00garbage"), ("invalid.txt", b"\xff")])
def test_corrupt_inputs_fail_observably(client, name, data):
    row = upload(client, name, data)
    assert row["state"] == "failed"
    assert row["error"]
    assert client.post(f"/api/documents/{row['id']}/approve", json=decision(row)).status_code == 409


def test_upload_bounds_and_paths_and_origin(client):
    assert client.post("/api/documents", files={"file": ("x.exe", b"abc")}).status_code == 415
    assert client.post("/api/documents", files={"file": ("x.txt", b"")}).status_code == 400
    assert client.post("/api/documents", files={"file": ("x.txt", b"a"*(MAX_UPLOAD_BYTES+1))}).status_code == 413
    row = upload(client, "../../escape.txt", (SAMPLES / "valid-invoice.txt").read_bytes())
    assert row["name"] == "escape.txt"
    assert client.get("/api/documents/missing/original").status_code == 404
    assert client.post("/api/documents", files={"file": ("x.txt", b"abc")}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/documents", headers={"Host": "evil.example"}).status_code == 403
    assert client.post("/api/exports/json", headers={"Origin": "null"}).status_code == 403


def test_chunked_request_is_bounded_before_multipart_buffering(client):
    boundary = "sample-boundary"
    consumed = []
    def content():
        prefix = f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="x.txt"\r\nContent-Type: text/plain\r\n\r\n'.encode()
        yield prefix
        for i in range(1000):
            consumed.append(i)
            yield b"x"*65536
        yield f"\r\n--{boundary}--\r\n".encode()
    response = client.post("/api/documents", content=content(), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    assert response.status_code == 413, response.text
    # TestClient aggregates generators into one receive event; real ASGI receive test below
    # verifies that the limiter itself stops requesting chunks.


def test_queue_bound_and_recovery_without_changing_db(tmp_path):
    store = Store(tmp_path, workers=0, max_pending=1)
    row = store.create("valid.txt", "text/plain", (SAMPLES / "valid-invoice.txt").read_bytes())
    with pytest.raises(Conflict, match="queue is full"):
        store.create("another.txt", "text/plain", b"more")
    with store.connection(True) as db:
        db.execute("UPDATE documents SET state='processing',attempts=1 WHERE id=?", (row["id"],))
    with TestClient(create_app(tmp_path)) as client:
        recovered = wait(client, row["id"])
        assert recovered["state"] == "ready"
        assert recovered["attempts"] == 2
        assert any(h["action"] == "recovered" for h in client.get(f"/api/documents/{row['id']}/history").json())
    with Store(tmp_path).connection(True) as db:
        db.execute("UPDATE documents SET state='processing',attempts=3 WHERE id=?", (row["id"],))
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(f"/api/documents/{row['id']}").json()["state"] == "failed"


def test_failed_jobs_do_not_poison_retry_identity(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        row = upload(client)
        with client.app.state.store.connection(True) as db:
            db.execute("UPDATE documents SET state='failed' WHERE id=?", (row["id"],))
        assert upload(client)["state"] == "ready"


def test_multiple_service_processes_cannot_recover_active_jobs(tmp_path):
    first = Store(tmp_path, workers=0)
    first.start()
    try:
        with pytest.raises(RuntimeError, match="already has a running service"):
            Store(tmp_path, workers=0).start()
    finally:
        first.close()


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1.001", True, "10000000000.00"])
def test_malformed_money_rejected_without_state_change(client, value):
    row = upload(client)
    response = review(client, row, record=dict(row["record"], total=value))
    assert response.status_code == 422, response.text
    assert client.get(f"/api/documents/{row['id']}").json()["version"] == row["version"]


def test_decoder_hard_timeout_is_terminal_and_api_remains_responsive(tmp_path, monkeypatch):
    import doc_intake_service.store as module
    monkeypatch.setattr(module, "JOB_SECONDS", .001)
    with TestClient(create_app(tmp_path)) as client:
        row = upload(client)
        assert row["state"] == "failed"
        assert "TimeoutExpired" in row["error"]
        assert client.get("/api/health").status_code == 200
        assert any(h["action"] == "failed" for h in client.get(f"/api/documents/{row['id']}/history").json())


def test_asgi_stream_limiter_stops_receiving_after_bound():
    import asyncio
    from doc_intake_service.app import LocalBoundary
    received, sent = [], []
    async def inner(scope, receive, send):
        while True:
            await receive()
    async def receive():
        received.append(1)
        return {"type": "http.request", "body": b"x"*65536, "more_body": True}
    async def send(message):
        sent.append(message)
    scope = {"type": "http", "headers": [(b"host", b"localhost")], "method": "POST", "path": "/api/documents"}
    asyncio.run(LocalBoundary(inner)(scope, receive, send))
    assert sent[0]["status"] == 413
    assert len(received) <= MAX_REQUEST_BYTES // 65536 + 1
