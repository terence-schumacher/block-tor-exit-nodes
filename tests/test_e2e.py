"""
End-to-end tests: full flow from fetch to enforcement.
Stub HTTP server → fetcher writes list → app with middleware → blocked IP → 403, allowed IP → 200.
"""

import os

import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tor_exit_block.fetcher import run_fetcher
from tor_exit_block.middleware import TorExitBlockMiddleware

pytestmark = pytest.mark.e2e


def _clear_middleware_cache():
    import tor_exit_block.middleware as m

    m._cached_set = None
    m._cached_path = None
    m._last_load_time = 0.0


class _StubTorListHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = getattr(self.server, "tor_list_body", "")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        pass


@pytest.fixture
def e2e_stub_server():
    """Local HTTP server serving a small TOR exit list for E2E."""
    body = "198.51.100.1\n203.0.113.99\n"
    server = HTTPServer(("127.0.0.1", 0), _StubTorListHandler)
    server.tor_list_body = body
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}/torlist"
    yield base_url, server
    server.shutdown()


class TestE2EFetchThenBlock:
    """Full pipeline: fetch list from stub server → run app with middleware → verify block/allow."""

    def test_e2e_blocked_ip_403_allowed_ip_200(self, e2e_stub_server):
        base_url, _ = e2e_stub_server
        blocked_ip = "198.51.100.1"
        allowed_ip = "10.0.0.1"

        with tempfile.TemporaryDirectory() as tmp:
            # 1. Fetch list from stub server and write to disk
            with patch("tor_exit_block.fetcher.TOR_LIST_URL", base_url):
                with patch("tor_exit_block.fetcher.emit_fetcher_metrics"):
                    run_fetcher(output_dir=tmp)

            list_path = os.path.join(tmp, "tor-exit-nodes.txt")
            assert os.path.isfile(list_path)
            content = Path(list_path).read_text()
            assert blocked_ip in content
            assert allowed_ip not in content

            # 2. Build WSGI app with middleware using that list
            _clear_middleware_cache()

            def app(environ, start_response):
                start_response("200 OK", [("Content-Type", "text/plain")])
                return [b"OK"]

            middleware = TorExitBlockMiddleware(app, list_path=list_path)

            # 3. Request from blocked IP → 403
            with patch("tor_exit_block.middleware.emit_block_event"):
                start_response = MagicMock()
                environ_blocked = {
                    "REMOTE_ADDR": blocked_ip,
                    "PATH_INFO": "/api/foo",
                }
                result_blocked = list(middleware(environ_blocked, start_response))

            start_response.assert_called_once_with(
                "403 Forbidden",
                [("Content-Type", "text/plain; charset=utf-8")],
            )
            assert result_blocked == [b"Access denied."]

            # 4. Request from allowed IP → 200
            _clear_middleware_cache()
            middleware2 = TorExitBlockMiddleware(app, list_path=list_path)
            start_response2 = MagicMock()
            environ_allowed = {
                "REMOTE_ADDR": allowed_ip,
                "PATH_INFO": "/",
            }
            result_allowed = list(middleware2(environ_allowed, start_response2))

            start_response2.assert_called_once_with("200 OK", [("Content-Type", "text/plain")])
            assert result_allowed == [b"OK"]

    def test_e2e_x_forwarded_for_blocked_client_403(self, e2e_stub_server):
        """E2E: fetched list used when client IP comes from X-Forwarded-For."""
        base_url, _ = e2e_stub_server
        blocked_ip = "203.0.113.99"

        with tempfile.TemporaryDirectory() as tmp:
            with patch("tor_exit_block.fetcher.TOR_LIST_URL", base_url):
                with patch("tor_exit_block.fetcher.emit_fetcher_metrics"):
                    run_fetcher(output_dir=tmp)

            list_path = os.path.join(tmp, "tor-exit-nodes.txt")
            _clear_middleware_cache()

            def app(environ, start_response):
                start_response("200 OK", [("Content-Type", "text/plain")])
                return [b"OK"]

            middleware = TorExitBlockMiddleware(app, list_path=list_path, trusted_proxy_count=1)
            start_response = MagicMock()
            environ = {
                "REMOTE_ADDR": "10.0.0.1",
                "HTTP_X_FORWARDED_FOR": f"{blocked_ip}, 10.0.0.1",
                "PATH_INFO": "/",
            }

            with patch("tor_exit_block.middleware.emit_block_event"):
                result = list(middleware(environ, start_response))

            start_response.assert_called_once_with(
                "403 Forbidden",
                [("Content-Type", "text/plain; charset=utf-8")],
            )
            assert result == [b"Access denied."]
