#!/usr/bin/env python3
"""
Example WSGI app with TOR exit block middleware.
Run: pip install -e ".[dev]" && python example_app.py
List file: data/tor-exit-nodes.txt (create via tor-exit-fetch first).
"""

import os
from pathlib import Path

from tor_exit_block.middleware import TorExitBlockMiddleware

LIST_PATH = os.environ.get("TOR_LIST_PATH", str(Path.cwd() / "data" / "tor-exit-nodes.txt"))
MONITOR_ONLY = os.environ.get("TOR_BLOCK_MONITOR_ONLY", "").strip() == "1"


def simple_app(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    if path == "/health":
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"healthy"]
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"OK"]


app = TorExitBlockMiddleware(
    simple_app,
    list_path=LIST_PATH,
    refresh_interval_seconds=60,
    monitor_only=MONITOR_ONLY,
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    from wsgiref.simple_server import make_server

    print(f"Example server on http://0.0.0.0:{port} (list: {LIST_PATH})")
    make_server("0.0.0.0", port, app).serve_forever()
