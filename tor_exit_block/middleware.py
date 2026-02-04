"""
WSGI middleware: block requests whose client IP is in the TOR exit list.
Returns 403 with generic body; emits block event to Datadog.
"""

import os
import time
from pathlib import Path
from typing import Any, Callable

from .list_store import read_list_from_file
from .client_ip import get_client_ip, ClientIpOptions
from .datadog import emit_block_event

DEFAULT_403_BODY = "Access denied."
DEFAULT_LIST_PATH = str(Path.cwd() / "data" / "tor-exit-nodes.txt")

# Module-level cache
_cached_set: set[str] | None = None
_cached_path: str | None = None
_last_load_time: float = 0.0


def _load_set(list_path: str) -> set[str]:
    global _cached_set, _cached_path, _last_load_time
    mtime = os.path.getmtime(list_path) if os.path.isfile(list_path) else 0.0
    if _cached_set is not None and _cached_path == list_path and mtime and mtime <= _last_load_time:
        return _cached_set
    if not os.path.isfile(list_path):
        _cached_set = set()
        _cached_path = list_path
        _last_load_time = time.time()
        return _cached_set
    _cached_set = read_list_from_file(list_path)
    _cached_path = list_path
    _last_load_time = mtime
    return _cached_set


class TorExitBlockMiddleware:
    """
    WSGI middleware that blocks requests whose client IP is in the TOR exit list.
    Use with any WSGI server (Gunicorn, uWSGI, etc.).
    """

    def __init__(
        self,
        app: Callable[..., Any],
        *,
        list_path: str | None = None,
        refresh_interval_seconds: int = 3600,
        trusted_proxy_count: int = 1,
        monitor_only: bool = False,
        blocked_body: str | None = None,
        forwarded_for_header: str = "x-forwarded-for",
        real_ip_header: str = "x-real-ip",
    ):
        self.app = app
        self.list_path = list_path or DEFAULT_LIST_PATH
        self.refresh_interval_seconds = refresh_interval_seconds
        self.monitor_only = monitor_only
        self.blocked_body = (blocked_body or DEFAULT_403_BODY).encode("utf-8")
        self.options = ClientIpOptions(
            trusted_proxy_count=trusted_proxy_count,
            forwarded_for_header=forwarded_for_header,
            real_ip_header=real_ip_header,
        )
        self._last_refresh: float = 0.0

    def _maybe_refresh(self) -> set[str]:
        global _cached_path, _last_load_time
        now = time.time()
        if now - self._last_refresh >= self.refresh_interval_seconds:
            self._last_refresh = now
            _cached_path = None  # force re-read on next _load_set
        return _load_set(self.list_path)

    def __call__(
        self,
        environ: dict[str, Any],
        start_response: Callable[..., Any],
    ) -> Any:
        ips = self._maybe_refresh()
        client_ip = get_client_ip(environ, options=self.options)
        if not client_ip:
            return self.app(environ, start_response)

        if client_ip in ips:
            path = environ.get("PATH_INFO", "") or environ.get("REQUEST_URI", "")
            emit_block_event(client_ip=client_ip, path=path)
            if self.monitor_only:
                return self.app(environ, start_response)
            status = "403 Forbidden"
            headers = [("Content-Type", "text/plain; charset=utf-8")]
            start_response(status, headers)
            return [self.blocked_body]

        return self.app(environ, start_response)


def wrap_flask_app(wsgi_app: Callable[..., Any], **kwargs: Any) -> TorExitBlockMiddleware:
    """
    Wrap a Flask app's wsgi_app with TorExitBlockMiddleware.
    Usage: app.wsgi_app = wrap_flask_app(app.wsgi_app, list_path="...")
    """
    return TorExitBlockMiddleware(wsgi_app, **kwargs)
