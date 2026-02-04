#!/usr/bin/env python3
"""
Example FastAPI app with TOR exit block middleware.
Run: pip install -e ".[dev]" && python example_app.py
List file: data/tor-exit-nodes.txt (create via tor-exit-fetch first).
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from tor_exit_block import add_tor_exit_block_middleware

LIST_PATH = os.environ.get("TOR_LIST_PATH", str(Path.cwd() / "data" / "tor-exit-nodes.txt"))
MONITOR_ONLY = os.environ.get("TOR_BLOCK_MONITOR_ONLY", "").strip() == "1"

app = FastAPI(title="Example TOR exit block app")

add_tor_exit_block_middleware(
    app,
    list_path=LIST_PATH,
    refresh_interval_seconds=60,
    monitor_only=MONITOR_ONLY,
)


@app.get("/", response_class=PlainTextResponse)
def root() -> str:
    return "OK"


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "healthy"


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "3000"))
    print(f"Example server on http://0.0.0.0:{port} (list: {LIST_PATH})")
    uvicorn.run(app, host="0.0.0.0", port=port)
