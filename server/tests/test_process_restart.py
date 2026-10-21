"""Real HTTP process restart, using the identical DB and stored original bytes."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx
from conftest import SAMPLES, decision

@contextmanager
def server(directory):
    with socket.socket() as address:
        address.bind(("127.0.0.1", 0))
        port = address.getsockname()[1]
    environment = dict(os.environ, DOC_INTAKE_DATA=str(directory))
    with (directory / "server.log").open("ab") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "doc_intake_service.app:app", "--host", "127.0.0.1", "--port", str(port)],
                                   env=environment, stdout=log, stderr=log)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    try:
                        if client.get("/api/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(.05)
                else:
                    raise AssertionError((directory / "server.log").read_text(errors="replace"))
                yield client
        finally:
            process.terminate()
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()

def finished(client, doc_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        row = client.get(f"/api/documents/{doc_id}").json()
        if row["state"] not in ("queued", "processing"):
            return row
        time.sleep(.05)
    raise AssertionError("Timed out waiting for job")

def test_restart_with_same_database_and_original(tmp_path):
    original = (SAMPLES / "valid-invoice.txt").read_bytes()
    with server(tmp_path) as client:
        response = client.post("/api/documents", files={"file": ("invoice.txt", original)})
        assert response.status_code == 202
        row = finished(client, response.json()["id"])
        assert row["state"] == "ready", row
        approved = client.post(f"/api/documents/{row['id']}/approve", json=decision(row)).json()
        assert approved["state"] == "approved"
    with server(tmp_path) as client:
        assert client.get(f"/api/documents/{row['id']}").json() == approved
        assert client.get(f"/api/documents/{row['id']}/original").content == original
        duplicate_id = client.post("/api/documents", files={"file": ("invoice-copy.txt", original)}).json()["id"]
        duplicate = finished(client, duplicate_id)
        assert duplicate["state"] == "review"
        assert client.post(f"/api/documents/{duplicate_id}/approve", json=decision(duplicate)).status_code == 409
        assert len(client.post("/api/exports/json").json()) == 1
