"""Private bounded child-process decoder. Never accepts filenames or shell commands."""
import json
import os
import sys

if __name__ == "__main__":
    # POSIX gets an address-space ceiling as well as cross-platform byte/page/pixel/time limits.
    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024, 1536 * 1024 * 1024))
    try:
        from .pipeline import process_document
        data = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("Upload exceeds decoder byte limit")
        payload = process_document(data, sys.argv[1])
        sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    except Exception as exc:
        sys.stderr.buffer.write(f"{type(exc).__name__}: {str(exc)[:500]}".encode("utf-8", errors="replace"))
        sys.exit(1)
