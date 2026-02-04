"""
Integration tests: multiple components together with real I/O.
- Fetcher: real HTTP to local stub server → real parse → real file write.
- Middleware: real list file on disk → real WSGI app → real block/allow.
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

pytestmark = pytest.mark.integration


def _clear_middleware_cache():
    import tor_exit_block.middleware as m

    m._cached_set = None
    m._cached_path = None
    m._last_load_time = 0.0


class _StubTorListHandler(BaseHTTPRequestHandler):
    """Serves a configurable TOR exit list body."""

    def do_GET(self):
        body = getattr(self.server, "tor_list_body", "")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        pass


@pytest.fixture
def stub_tor_list_server():
    """Start a local HTTP server serving a small TOR exit list; yield (base_url, server)."""
    body = "192.168.100.1\n10.0.0.50\n2001:db8::1\n"
    server = HTTPServer(("127.0.0.1", 0), _StubTorListHandler)
    server.tor_list_body = body
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}/torlist"
    yield base_url, server
    server.shutdown()


class TestFetcherIntegration:
    """Fetcher with real HTTP (to local stub), real parser, real list_store."""

    def test_fetcher_downloads_and_writes_list(self, stub_tor_list_server):
        base_url, _ = stub_tor_list_server
        with tempfile.TemporaryDirectory() as tmp:
            with patch("tor_exit_block.fetcher.TOR_LIST_URL", base_url):
                with patch("tor_exit_block.fetcher.emit_fetcher_metrics"):
                    run_fetcher(output_dir=tmp)

            output_file = Path(tmp) / "tor-exit-nodes.txt"
            assert output_file.exists()
            content = output_file.read_text()
            lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
            assert set(lines) == {"192.168.100.1", "10.0.0.50", "2001:db8::1"}

            last_fetch = Path(tmp) / ".last-fetch-time"
            assert last_fetch.exists()
            assert int(last_fetch.read_text().strip()) > 0

    def test_fetcher_creates_output_dir_if_missing(self, stub_tor_list_server):
        base_url, _ = stub_tor_list_server
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "nested", "data")
            with patch("tor_exit_block.fetcher.TOR_LIST_URL", base_url):
                with patch("tor_exit_block.fetcher.emit_fetcher_metrics"):
                    run_fetcher(output_dir=out_dir)

            assert os.path.isdir(out_dir)
            output_file = Path(out_dir) / "tor-exit-nodes.txt"
            assert output_file.exists()
            assert "192.168.100.1" in output_file.read_text()


class TestMiddlewareIntegration:
    """Middleware with real list file on disk and real WSGI app (no mocks for list load)."""

    @pytest.fixture
    def list_file_on_disk(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("203.0.113.10\n198.51.100.20\n")
            path = f.name
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    def test_blocked_ip_returns_403_from_real_file(self, list_file_on_disk):
        _clear_middleware_cache()

        def app(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"OK"]

        middleware = TorExitBlockMiddleware(app, list_path=list_file_on_disk)
        start_response = MagicMock()
        environ = {"REMOTE_ADDR": "203.0.113.10", "PATH_INFO": "/api/foo"}

        with patch("tor_exit_block.middleware.emit_block_event"):
            result = list(middleware(environ, start_response))

        start_response.assert_called_once_with(
            "403 Forbidden",
            [("Content-Type", "text/plain; charset=utf-8")],
        )
        assert result == [b"Access denied."]

    def test_allowed_ip_passes_through_from_real_file(self, list_file_on_disk):
        _clear_middleware_cache()

        def app(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"OK"]

        middleware = TorExitBlockMiddleware(app, list_path=list_file_on_disk)
        start_response = MagicMock()
        environ = {"REMOTE_ADDR": "192.168.1.1", "PATH_INFO": "/"}

        result = list(middleware(environ, start_response))

        start_response.assert_called_once_with("200 OK", [("Content-Type", "text/plain")])
        assert result == [b"OK"]

    def test_x_forwarded_for_client_ip_blocked_from_real_file(self, list_file_on_disk):
        _clear_middleware_cache()

        def app(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"OK"]

        middleware = TorExitBlockMiddleware(app, list_path=list_file_on_disk, trusted_proxy_count=1)
        start_response = MagicMock()
        environ = {
            "REMOTE_ADDR": "10.0.0.1",
            "HTTP_X_FORWARDED_FOR": "198.51.100.20, 10.0.0.1",
            "PATH_INFO": "/",
        }

        with patch("tor_exit_block.middleware.emit_block_event"):
            result = list(middleware(environ, start_response))

        start_response.assert_called_once_with(
            "403 Forbidden",
            [("Content-Type", "text/plain; charset=utf-8")],
        )
        assert result == [b"Access denied."]
