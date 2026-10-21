import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from doc_intake_service.app import create_app

SAMPLES = Path(__file__).resolve().parents[2] / "samples"

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        yield client

def wait(client, doc_id):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        row = client.get(f"/api/documents/{doc_id}").json()
        if row["state"] not in ("queued", "processing"):
            return row
        time.sleep(.03)
    raise AssertionError("Background job did not finish")

def upload(client, name="valid-invoice.txt", data=None):
    data = data if data is not None else (SAMPLES / name).read_bytes()
    response = client.post("/api/documents", files={"file": (name, data)})
    assert response.status_code == 202, response.text
    return wait(client, response.json()["id"])

def decision(row, note=""):
    return dict(version=row["version"], request_id=uuid.uuid4().hex, note=note)

def review(client, row, **changes):
    body = dict(**decision(row), record=row["record"], doc_type=row["doc_type"], type_confirmed=row["type_confirmed"])
    body.update(changes)
    return client.post(f"/api/documents/{row['id']}/review", json=body)
