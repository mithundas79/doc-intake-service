"""SQLite is the authority for originals, jobs, review versions and audit events."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .pipeline import JOB_SECONDS
from .rules import TYPES, duplicate_key, normalize_record, validate

METADATA_COLUMNS = "seq,id,name,kind,sha256,state,version,created,updated,payload,identity,error,attempts"

class Conflict(ValueError):
    pass

class Store:
    def __init__(self, data_dir, workers=2, max_pending=32):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "intake.sqlite3"
        self.workers = workers
        self.max_pending = max_pending
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.threads = []
        self.lockfile = None
        with self.connection() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS documents (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
              name TEXT NOT NULL, kind TEXT NOT NULL, original BLOB NOT NULL, sha256 TEXT NOT NULL,
              state TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0,
              created REAL NOT NULL, updated REAL NOT NULL, payload TEXT NOT NULL DEFAULT '{}',
              identity TEXT, error TEXT, attempts INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS documents_hash ON documents(sha256);
            CREATE INDEX IF NOT EXISTS documents_identity ON documents(identity);
            CREATE TABLE IF NOT EXISTS approvals (
              document_id TEXT PRIMARY KEY REFERENCES documents(id), sha256 TEXT UNIQUE NOT NULL,
              identity TEXT UNIQUE, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT, action TEXT NOT NULL,
              created REAL NOT NULL, details TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS requests (
              request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, response TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def event(self, db, doc_id, action, details):
        db.execute("INSERT INTO audit(document_id,action,created,details) VALUES(?,?,?,?)",
                   (doc_id, action, time.time(), json.dumps(details, ensure_ascii=False)))

    def start(self):
        # Only one service process owns job recovery; requests still use independent DB connections.
        self.lockfile = (self.data_dir / "worker.lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.lockfile.seek(0)
                self.lockfile.write(b"0")
                self.lockfile.flush()
                self.lockfile.seek(0)
                msvcrt.locking(self.lockfile.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lockfile.close()
            self.lockfile = None
            raise RuntimeError("Data directory already has a running service; use one server process")
        with self.connection(True) as db:
            for row in db.execute("SELECT id,attempts FROM documents WHERE state='processing'").fetchall():
                state = "queued" if row["attempts"] < 3 else "failed"
                db.execute("UPDATE documents SET state=?,error=?,updated=? WHERE id=?",
                           (state, "Interrupted processing recovered" if state == "queued" else "Interrupted three times; upload a new copy", time.time(), row["id"]))
                self.event(db, row["id"], "recovered", {"state": state})
        self.stop.clear()
        self.threads = [threading.Thread(target=self.worker, name=f"intake-{i}", daemon=True) for i in range(self.workers)]
        for thread in self.threads:
            thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        for thread in self.threads:
            thread.join()  # bounded OCR per page; finish before releasing process lock
        if self.lockfile:
            self.lockfile.close()
            self.lockfile = None

    def row(self, db, doc_id):
        row = db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if row is None:
            raise KeyError(doc_id)
        return row

    def serialize(self, row, include_text=True):
        payload = json.loads(row["payload"])
        if not include_text:
            payload.pop("text", None)
        return dict(id=row["id"], name=row["name"], kind=row["kind"], state=row["state"],
                    version=row["version"], sha256=row["sha256"], created=row["created"],
                    updated=row["updated"], error=row["error"], attempts=row["attempts"], **payload)

    def get(self, doc_id):
        with self.connection() as db:
            return self.serialize(self.row(db, doc_id))

    def list(self):
        with self.connection() as db:
            return [self.serialize(r, False) for r in db.execute(f"SELECT {METADATA_COLUMNS} FROM documents ORDER BY seq DESC")]

    def create(self, name, kind, data):
        doc_id = uuid.uuid4().hex
        now = time.time()
        with self.connection(True) as db:
            if db.execute("SELECT COUNT(*) FROM documents WHERE state IN ('queued','processing')").fetchone()[0] >= self.max_pending:
                raise Conflict("Processing queue is full; retry after existing jobs finish")
            db.execute("INSERT INTO documents(id,name,kind,original,sha256,state,created,updated) VALUES(?,?,?,?,?,'queued',?,?)",
                       (doc_id, name, kind, data, hashlib.sha256(data).hexdigest(), now, now))
            self.event(db, doc_id, "uploaded", {"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            result = self.serialize(self.row(db, doc_id))
        self.wake.set()
        return result

    def checks(self, db, row, payload):
        identity = duplicate_key(payload["record"])
        duplicate = db.execute("""SELECT 1 FROM documents WHERE id != ? AND
            ((seq < ? AND state != 'failed' AND (sha256=? OR (? IS NOT NULL AND identity=?))) OR
             (state='approved' AND (sha256=? OR (? IS NOT NULL AND identity=?)))) LIMIT 1""",
            (row["id"], row["seq"], row["sha256"], identity, identity, row["sha256"], identity, identity)).fetchone() is not None
        return validate(payload["record"], payload["doc_type"], payload["prediction"]["confidence"],
                        type_confirmed=payload.get("type_confirmed", False), manual_note=payload.get("manual_note", ""), duplicate=duplicate), identity

    def worker(self):
        while not self.stop.is_set():
            with self.connection(True) as db:
                row = db.execute("SELECT * FROM documents WHERE state='queued' ORDER BY seq LIMIT 1").fetchone()
                if row:
                    db.execute("UPDATE documents SET state='processing',attempts=attempts+1,error=NULL,updated=? WHERE id=?", (time.time(), row["id"]))
                    self.event(db, row["id"], "processing", {"attempt": row["attempts"] + 1})
            if row is None:
                self.wake.wait(.25)
                self.wake.clear()
                continue
            try:
                # One isolated child per active worker: PDFium never shares threads,
                # native crashes do not kill the API, and the parent enforces a hard deadline.
                environment = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
                environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(Path(__file__).resolve().parents[1]), environment.get("PYTHONPATH")]))
                completed = subprocess.run([sys.executable, "-m", "doc_intake_service.processor", row["kind"]],
                    input=row["original"], capture_output=True, timeout=JOB_SECONDS, env=environment)
                if completed.returncode != 0:
                    raise ValueError(completed.stderr.decode("utf-8", errors="replace")[-600:] or "Document decoder exited unexpectedly")
                payload = json.loads(completed.stdout)
                payload.update(doc_type=payload["prediction"]["label"], type_confirmed=False, manual_note="")
                with self.connection(True) as db:
                    checks, identity = self.checks(db, row, payload)
                    payload["checks"] = checks
                    state = "ready" if all(c["ok"] for c in checks) else "review"
                    db.execute("UPDATE documents SET state=?,payload=?,identity=?,version=version+1,updated=? WHERE id=?",
                               (state, json.dumps(payload), identity, time.time(), row["id"]))
                    self.event(db, row["id"], "processed", {"state": state, "checks": checks, "prediction": payload["prediction"]})
            except Exception as exc:
                with self.connection(True) as db:
                    error = f"{type(exc).__name__}: {str(exc)[:600]}"
                    db.execute("UPDATE documents SET state='failed',error=?,version=version+1,updated=? WHERE id=?", (error, time.time(), row["id"]))
                    self.event(db, row["id"], "failed", {"error": error})

    def mutate(self, doc_id, action, body):
        fingerprint = hashlib.sha256(json.dumps([doc_id, action, body], sort_keys=True).encode()).hexdigest()
        with self.connection(True) as db:
            prior = db.execute("SELECT * FROM requests WHERE request_id=?", (body["request_id"],)).fetchone()
            if prior:
                if prior["fingerprint"] != fingerprint:
                    raise Conflict("Request ID was already used with different contents")
                return json.loads(prior["response"])
            row = self.row(db, doc_id)
            if row["version"] != body["version"]:
                raise Conflict("Document changed; reload before submitting")
            if action == "reopen":
                if row["state"] != "rejected" or len(body["note"].strip()) < 3:
                    raise Conflict("Only rejected documents can be reopened, with a reason")
            elif row["state"] not in ("review", "ready"):
                raise Conflict("Only ready/review documents can be changed; final decisions are immutable")
            payload = json.loads(row["payload"])
            before = {k: payload.get(k) for k in ("record", "doc_type", "type_confirmed", "manual_note")}
            if action == "review":
                payload["record"] = normalize_record(body["record"])
                if body["doc_type"] not in TYPES:
                    raise ValueError("Unsupported document type")
                payload.update(doc_type=body["doc_type"], type_confirmed=body["type_confirmed"], manual_note=body["note"])
            checks, identity = self.checks(db, row, payload)
            payload["checks"] = checks
            state = "ready" if all(c["ok"] for c in checks) else "review"
            if action == "approve":
                if state != "ready":
                    raise Conflict("Approval blocked: correct failed checks and revalidate")
                try:
                    db.execute("INSERT INTO approvals VALUES(?,?,?,?)", (doc_id, row["sha256"], identity, time.time()))
                except sqlite3.IntegrityError as exc:
                    raise Conflict("Approval blocked: an approved record has the same identity or original") from exc
                state = "approved"
            elif action == "reject":
                if len(body["note"].strip()) < 3:
                    raise ValueError("Provide a rejection reason of at least 3 characters")
                state = "rejected"
            db.execute("UPDATE documents SET state=?,payload=?,identity=?,version=version+1,updated=? WHERE id=?",
                       (state, json.dumps(payload), identity, time.time(), doc_id))
            after = {k: payload.get(k) for k in before}
            self.event(db, doc_id, action, {"from_version": row["version"], "to_version": row["version"]+1,
                                         "before": before, "after": after, "note": body["note"], "state": state, "checks": checks})
            result = self.serialize(self.row(db, doc_id))
            db.execute("INSERT INTO requests VALUES(?,?,?)", (body["request_id"], fingerprint, json.dumps(result)))
            return result

    def history(self, doc_id):
        with self.connection() as db:
            self.row(db, doc_id)
            return [dict(seq=r["seq"], action=r["action"], created=r["created"], details=json.loads(r["details"]))
                    for r in db.execute("SELECT * FROM audit WHERE document_id=? ORDER BY seq", (doc_id,))]

    def original(self, doc_id):
        with self.connection() as db:
            row = self.row(db, doc_id)
            return row["original"], row["kind"]

    def export(self, format):
        with self.connection(True) as db:
            rows = [self.serialize(r) for r in db.execute(f"SELECT {METADATA_COLUMNS} FROM documents WHERE state='approved' ORDER BY seq")]
            records = [dict(id=r["id"], name=r["name"], doc_type=r["doc_type"], **r["record"]) for r in rows]
            self.event(db, None, "export", {"format": format, "documents": [r["id"] for r in rows], "versions": [r["version"] for r in rows]})
            if format == "json":
                return json.dumps(records, ensure_ascii=False, indent=2).encode()
            output = io.StringIO(newline="")
            columns = ["id", "name", "doc_type", "vendor", "number", "date", "currency", "subtotal", "tax", "total", "line_total"]
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for record in records:
                safe = {}
                for k in columns:
                    value = "" if record.get(k) is None else str(record[k])
                    # Spreadsheet formulas may start after whitespace/control characters.
                    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
                        value = "'" + value
                    safe[k] = value
                writer.writerow(safe)
            return output.getvalue().encode("utf-8-sig")
