"""The HTTP surface. Three endpoints; everything interesting lives in the pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .classify import MODEL_PATH
from .pipeline import IntakeService

app = FastAPI(title="doc-intake-service", version="0.1.0")

# The dev UI runs on another port; this is a local demo service, not a
# hardened deployment - stated plainly in the README.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

service = IntakeService(data_dir=Path("data"))

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


@app.get("/api/health")
def health() -> dict:
    metrics_path = MODEL_PATH.parent / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None
    return {
        "status": "ok",
        "model_present": MODEL_PATH.exists(),
        "model_note": metrics["honest_note"] if metrics else "model not trained yet - see README",
    }


@app.post("/api/documents")
async def upload(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file larger than 8 MB")
    try:
        doc = service.process(file.filename or "upload", data, file.content_type)
    except FileNotFoundError as e:  # model missing
        raise HTTPException(status_code=503, detail=str(e)) from e
    return doc.as_dict()


@app.get("/api/documents")
def list_documents() -> list[dict]:
    out = []
    for d in service.processed:
        row = d.as_dict()
        row.pop("text")
        out.append(row)
    return out
