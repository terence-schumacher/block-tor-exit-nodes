"""Tests for TorExitBlockMiddleware."""

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from tor_exit_block.middleware import TorExitBlockMiddleware, wrap_flask_app

# Reset module-level cache before tests that rely on file content
_cached_set = None
_cached_path = None
_last_load_time = 0.0


def _clear_middleware_cache():
    import tor_exit_block.middleware as m

    m._cached_set = None
    m._cached_path = None
    m._last_load_time = 0.0


@pytest.fixture
def wsgi_app():
    def app(environ, start_response):
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"OK"]

    return app


@pytest.fixture
def list_file():
    """Create a temp file with known TOR exit IPs."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("192.168.1.100\n10.0.0.99\n")
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


class TestTorExitBlockMiddleware:
    def test_blocked_ip_returns_403(self, wsgi_app, list_file):
        _clear_middleware_cache()
        middleware = TorExitBlockMiddleware(wsgi_app, list_path=list_file)
        start_response = MagicMock()
        environ = {"REMOTE_ADDR": "192.168.1.100", "PATH_INFO": "/api/foo"}

        with patch("tor_exit_block.middleware.emit_block_event"):
            result = list(middleware(environ, start_response))

        start_response.assert_called_once_with(
            "403 Forbidden",
            [("Content-Type", "text/plain; charset=utf-8")],
        )
        assert result == [b"Access denied."]

    def test_allowed_ip_passes_to_app(self, wsgi_app, list_file):
        _clear_middleware_cache()
        middleware = TorExitBlockMiddleware(wsgi_app, list_path=list_file)
        start_response = MagicMock()
        environ = {"REMOTE_ADDR": "192.168.1.1", "PATH_INFO": "/"}

        result = list(middleware(environ, start_response))

        start_response.assert_called_once_with("200 OK", [("Content-Type", "text/plain")])
        assert result == [b"OK"]

    def test_monitor_only_blocks_but_passes_through(self, wsgi_app, list_file):
        _clear_middleware_cache()
        middleware = TorExitBlockMiddleware(wsgi_app, list_path=list_file, monitor_only=True)
        start_response = MagicMock()
        environ = {"REMOTE_ADDR": "10.0.0.99", "PATH_INFO": "/"}

        with patch("tor_exit_block.middleware.emit_block_event") as mock_emit:
            result = list(middleware(environ, start_response))

        mock_emit.assert_called_once_with(client_ip="10.0.0.99", path="/")
        start_response.assert_called_once_with("200 OK", [("Content-Type", "text/plain")])
        assert result == [b"OK"]

    def test_empty_client_ip_passes_to_app(self, wsgi_app, list_file):
        _clear_middleware_cache()
        middleware = TorExitBlockMiddleware(wsgi_app, list_path=list_file)
        start_response = MagicMock()
        environ = {"PATH_INFO": "/"}

        result = list(middleware(environ, start_response))

        start_response.assert_called_once_with("200 OK", [("Content-Type", "text/plain")])
        assert result == [b"OK"]

    def test_custom_blocked_body(self, wsgi_app, list_file):
        _clear_middleware_cache()
        middleware = TorExitBlockMiddleware(wsgi_app, list_path=list_file, blocked_body="Blocked.")
        start_response = MagicMock()
        environ = {"REMOTE_ADDR": "192.168.1.100", "PATH_INFO": "/"}

        with patch("tor_exit_block.middleware.emit_block_event"):
            result = list(middleware(environ, start_response))

        assert result == [b"Blocked."]

    def test_uses_x_forwarded_for_for_client_ip(self, wsgi_app, list_file):
        _clear_middleware_cache()
        middleware = TorExitBlockMiddleware(wsgi_app, list_path=list_file, trusted_proxy_count=1)
        start_response = MagicMock()
        environ = {
            "REMOTE_ADDR": "172.16.0.1",
            "HTTP_X_FORWARDED_FOR": "192.168.1.100, 172.16.0.1",
            "PATH_INFO": "/",
        }

        with patch("tor_exit_block.middleware.emit_block_event"):
            result = list(middleware(environ, start_response))

        start_response.assert_called_once_with(
            "403 Forbidden",
            [("Content-Type", "text/plain; charset=utf-8")],
        )
        assert result == [b"Access denied."]

    def test_missing_list_file_treats_as_empty_set(self, wsgi_app):
        _clear_middleware_cache()
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "missing.txt")
            middleware = TorExitBlockMiddleware(wsgi_app, list_path=missing)
            start_response = MagicMock()
            environ = {"REMOTE_ADDR": "192.168.1.1", "PATH_INFO": "/"}

            result = list(middleware(environ, start_response))

        start_response.assert_called_once_with("200 OK", [("Content-Type", "text/plain")])
        assert result == [b"OK"]

    def test_emit_block_event_called_when_blocking(self, wsgi_app, list_file):
        _clear_middleware_cache()
        middleware = TorExitBlockMiddleware(wsgi_app, list_path=list_file)
        environ = {"REMOTE_ADDR": "10.0.0.99", "PATH_INFO": "/api/bar"}

        with patch("tor_exit_block.middleware.emit_block_event") as mock_emit:
            list(middleware(environ, MagicMock()))

        mock_emit.assert_called_once_with(client_ip="10.0.0.99", path="/api/bar")

    def test_wrap_flask_app_returns_middleware(self, wsgi_app, list_file):
        """wrap_flask_app(wsgi_app, ...) returns a TorExitBlockMiddleware wrapping the app."""
        _clear_middleware_cache()
        wrapped = wrap_flask_app(wsgi_app, list_path=list_file)
        assert isinstance(wrapped, TorExitBlockMiddleware)
        start_response = MagicMock()
        environ = {"REMOTE_ADDR": "192.168.1.100", "PATH_INFO": "/"}
        with patch("tor_exit_block.middleware.emit_block_event"):
            result = list(wrapped(environ, start_response))
        start_response.assert_called_once_with(
            "403 Forbidden",
            [("Content-Type", "text/plain; charset=utf-8")],
        )
        assert result == [b"Access denied."]
