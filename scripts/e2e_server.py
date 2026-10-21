"""Launch an isolated real backend for Playwright, with a fresh temporary database."""
import os
from pathlib import Path
import sys
import tempfile
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from doc_intake_service.app import create_app

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="doc-intake-e2e-") as directory:
        uvicorn.run(create_app(directory), host="127.0.0.1", port=18760)
