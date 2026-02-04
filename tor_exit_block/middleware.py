"""
WSGI and ASGI middleware: block requests whose client IP is in the TOR exit list.

Returns 403 with a generic body and emits a block event to Datadog when configured.
Use TorExitBlockMiddleware for WSGI (e.g. Gunicorn); use TorExitBlockASGIMiddleware
or add_tor_exit_block_middleware() for FastAPI/ASGI.
"""

import os
import time
from pathlib import Path
from typing import Any, Callable

from .list_store import read_list_from_file
from .client_ip import get_client_ip, ClientIpOptions
from .datadog import emit_block_event

# Type alias for ASGI scope (scope["type"] == "http").
ASGIScope = dict[str, Any]
ASGIReceive = Callable[..., Any]
ASGISend = Callable[..., Any]

DEFAULT_403_BODY = "Access denied."
DEFAULT_LIST_PATH = str(Path.cwd() / "data" / "tor-exit-nodes.txt")
CONTENT_TYPE_PLAIN_UTF8 = "text/plain; charset=utf-8"
STATUS_FORBIDDEN = "403 Forbidden"

# Module-level cache for the blocklist (path + mtime invalidation).
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
            request_path = environ.get("PATH_INFO", "") or environ.get("REQUEST_URI", "")
            emit_block_event(client_ip=client_ip, path=request_path)
            if self.monitor_only:
                return self.app(environ, start_response)
            start_response(STATUS_FORBIDDEN, [("Content-Type", CONTENT_TYPE_PLAIN_UTF8)])
            return [self.blocked_body]

        return self.app(environ, start_response)


def _scope_to_headers_and_remote(scope: ASGIScope) -> tuple[dict[str, str], str]:
    """Build (headers, remote_addr) from ASGI scope for get_client_ip."""
    headers: dict[str, str] = {}
    for raw_name, raw_value in scope.get("headers", []):
        try:
            name = raw_name.decode("latin-1").strip().lower()
            value = raw_value.decode("latin-1").strip()
            if name and value:
                headers[name] = value
        except (UnicodeDecodeError, AttributeError):
            continue
    client = scope.get("client")
    remote_addr = (client[0] or "") if isinstance(client, (list, tuple)) and client else ""
    return headers, remote_addr


class TorExitBlockASGIMiddleware:
    """
    ASGI middleware that blocks requests whose client IP is in the TOR exit list.
    Use with FastAPI, Starlette, or any ASGI app.
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
            _cached_path = None
        return _load_set(self.list_path)

    async def __call__(
        self,
        scope: ASGIScope,
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        ips = self._maybe_refresh()
        headers, remote_addr = _scope_to_headers_and_remote(scope)
        client_ip = get_client_ip(
            environ=None,
            headers=headers,
            remote_addr=remote_addr,
            options=self.options,
        )
        if not client_ip:
            await self.app(scope, receive, send)
            return

        if client_ip in ips:
            request_path = scope.get("path", "") or (
                scope.get("raw_path", b"").decode("utf-8") if scope.get("raw_path") else ""
            )
            emit_block_event(client_ip=client_ip, path=request_path)
            if self.monitor_only:
                await self.app(scope, receive, send)
                return
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [[b"content-type", CONTENT_TYPE_PLAIN_UTF8.encode("utf-8")]],
                }
            )
            await send({"type": "http.response.body", "body": self.blocked_body})
            return

        await self.app(scope, receive, send)


def add_tor_exit_block_middleware(
    fastapi_app: Any,
    *,
    list_path: str | None = None,
    refresh_interval_seconds: int = 3600,
    trusted_proxy_count: int = 1,
    monitor_only: bool = False,
    blocked_body: str | None = None,
    forwarded_for_header: str = "x-forwarded-for",
    real_ip_header: str = "x-real-ip",
) -> None:
    """
    Add TorExitBlockASGIMiddleware to a FastAPI (or Starlette) app.
    Usage: add_tor_exit_block_middleware(app, list_path="...")
    """
    fastapi_app.add_middleware(
        TorExitBlockASGIMiddleware,
        list_path=list_path,
        refresh_interval_seconds=refresh_interval_seconds,
        trusted_proxy_count=trusted_proxy_count,
        monitor_only=monitor_only,
        blocked_body=blocked_body,
        forwarded_for_header=forwarded_for_header,
        real_ip_header=real_ip_header,
    )
