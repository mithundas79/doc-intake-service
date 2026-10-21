"""Local-only HTTP API. Run one uvicorn process; OCR never runs on the event loop."""
from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from .classify import MODEL_PATH
from .pipeline import IMAGE_EXTENSIONS
from .store import Conflict, Store

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 65536

class RequestTooLarge(HTTPException):
    def __init__(self):
        super().__init__(413, "Request exceeds 8 MB upload limit")

class LocalBoundary:
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        host = headers.get(b"host", b"").decode("latin1").split(":")[0].lower()
        origin = headers.get(b"origin", b"").decode("latin1")
        # No arbitrary Host or cross-site browser access, including simple multipart POSTs.
        allowed_hosts = {"localhost", "127.0.0.1", "testserver"}
        trusted_origins = {"http://localhost:18761", "http://127.0.0.1:18761", "http://localhost:5173", "http://127.0.0.1:5173"}
        origin_ok = not origin or origin in trusted_origins or origin == "http://" + headers.get(b"host", b"").decode("latin1")
        if host not in allowed_hosts or not origin_ok or headers.get(b"sec-fetch-site") == b"cross-site":
            return await JSONResponse({"detail": "Local host/origin required"}, status_code=403)(scope, receive, send)
        consumed = 0
        try:
            if int(headers.get(b"content-length", b"0")) > MAX_REQUEST_BYTES:
                raise RequestTooLarge()
        except ValueError:
            return await JSONResponse({"detail": "Invalid content length"}, status_code=400)(scope, receive, send)
        except RequestTooLarge:
            return await JSONResponse({"detail": "Request exceeds 8 MB upload limit"}, status_code=413)(scope, receive, send)
        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > MAX_REQUEST_BYTES:
                raise RequestTooLarge()
            return message
        try:
            await self.app(scope, bounded_receive, send)
        except RequestTooLarge:
            await JSONResponse({"detail": "Request exceeds 8 MB upload limit"}, status_code=413)(scope, receive, send)

class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: StrictInt = Field(ge=0)
    request_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    note: str = Field(default="", max_length=3000)

class Review(Decision):
    record: dict
    doc_type: Literal["invoice", "receipt", "contract", "statement", "credit_note", "other"]
    type_confirmed: StrictBool = False


def create_app(data_dir=None, workers=2, max_pending=32):
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(data_dir or os.environ.get("DOC_INTAKE_DATA", "data"), workers, max_pending)
        app.state.store.start()
        try:
            yield
        finally:
            app.state.store.close()
    app = FastAPI(title="Local document review", version="0.2.0", lifespan=lifespan)
    app.add_middleware(LocalBoundary)

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)
    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": "Document not found"}, status_code=404)
    @app.exception_handler(ValueError)
    async def bad_input(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/api/health")
    def health():
        path = MODEL_PATH.parent / "metrics.json"
        metrics = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return {"status": "ok", "model_present": MODEL_PATH.exists(), "model_note": metrics.get("honest_note", "Train the model first"), "workers": workers, "max_pending": max_pending}

    @app.post("/api/documents", status_code=202)
    async def upload(file: UploadFile = File(...)):
        # Limit both total ASGI bytes (before multipart spooling) and actual file reads.
        try:
            name = re.split(r"[/\\]", file.filename or "upload")[-1]
            name = re.sub(r"[\x00-\x1f\x7f]", "", name)[:200] or "upload"
            extension = Path(name).suffix.lower()
            kind = "text/plain" if extension == ".txt" else "application/pdf" if extension == ".pdf" else "image" if extension in IMAGE_EXTENSIONS else None
            if kind is None:
                raise HTTPException(415, "Supported uploads: UTF-8 TXT, PDF, PNG/JPEG/WebP/BMP/TIFF")
            data = bytearray()
            while chunk := await file.read(65536):
                data.extend(chunk)
                if len(data) > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "File exceeds 8 MB upload limit")
            if not data:
                raise HTTPException(400, "Empty upload")
            # Short DB write in a worker thread; route stays responsive during OCR.
            from starlette.concurrency import run_in_threadpool
            return await run_in_threadpool(app.state.store.create, name, kind, bytes(data))
        finally:
            await file.close()

    @app.get("/api/documents")
    def listing():
        return app.state.store.list()

    @app.get("/api/documents/{doc_id}")
    def document(doc_id: str):
        return app.state.store.get(doc_id)

    @app.get("/api/documents/{doc_id}/original")
    def original(doc_id: str):
        data, kind = app.state.store.original(doc_id)
        if kind == "image":
            from PIL import Image
            import io
            with Image.open(io.BytesIO(data)) as image:
                kind = Image.MIME.get(image.format, "application/octet-stream")
        suffix = {"text/plain": "txt", "application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}.get(kind, "bin")
        return Response(data, media_type=kind, headers={"Content-Disposition": f'inline; filename="document-{doc_id}.{suffix}"', "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox", "Cache-Control": "no-store"})

    @app.get("/api/documents/{doc_id}/history")
    def history(doc_id: str):
        return app.state.store.history(doc_id)

    @app.post("/api/documents/{doc_id}/review")
    def review(doc_id: str, body: Review):
        return app.state.store.mutate(doc_id, "review", body.model_dump())

    @app.post("/api/documents/{doc_id}/approve")
    def approve(doc_id: str, body: Decision):
        return app.state.store.mutate(doc_id, "approve", body.model_dump())

    @app.post("/api/documents/{doc_id}/reject")
    def reject(doc_id: str, body: Decision):
        return app.state.store.mutate(doc_id, "reject", body.model_dump())

    @app.post("/api/documents/{doc_id}/reopen")
    def reopen(doc_id: str, body: Decision):
        return app.state.store.mutate(doc_id, "reopen", body.model_dump())

    @app.post("/api/exports/{format}")
    def export(format: Literal["json", "csv"]):
        data = app.state.store.export(format)
        return Response(data, media_type="application/json" if format == "json" else "text/csv", headers={"Content-Disposition": f'attachment; filename="approved-records.{format}"', "Cache-Control": "no-store"})
    return app

app = create_app()
