"""
Resolve client IP from request, honoring X-Forwarded-For / X-Real-IP with trusted proxy count.
Use same policy everywhere to avoid bypass.
"""

from typing import Any


class ClientIpOptions:
    """Options for client IP resolution."""

    def __init__(
        self,
        *,
        trusted_proxy_count: int = 1,
        forwarded_for_header: str = "x-forwarded-for",
        real_ip_header: str = "x-real-ip",
    ):
        self.trusted_proxy_count = max(0, trusted_proxy_count)
        self.forwarded_for_header = forwarded_for_header.lower()
        self.real_ip_header = real_ip_header.lower()


def get_client_ip(
    environ: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    remote_addr: str | None = None,
    options: ClientIpOptions | None = None,
) -> str:
    """
    Return the client IP for the request.
    Order: X-Forwarded-For (rightmost after trusted proxies), then X-Real-IP, then REMOTE_ADDR.

    Can be called with WSGI environ, or with headers/remote_addr explicitly (e.g. for Flask request).
    """
    opts = options or ClientIpOptions()
    if environ is not None:
        # WSGI: HTTP_X_FORWARDED_FOR -> x-forwarded-for
        headers = {}
        for k, v in environ.items():
            if k.startswith("HTTP_") and isinstance(v, str):
                name = k[5:].replace("_", "-").lower()
                headers[name] = v
        remote_addr = environ.get("REMOTE_ADDR", "") or ""
    else:
        headers = headers or {}
        remote_addr = remote_addr or ""

    # Normalize header names for lookup
    headers_lower = {k.lower(): v for k, v in headers.items()}

    forwarded_for = headers_lower.get(opts.forwarded_for_header)
    if forwarded_for:
        ips = [s.strip() for s in forwarded_for.split(",")]
        idx = max(0, len(ips) - 1 - opts.trusted_proxy_count)
        if 0 <= idx < len(ips) and ips[idx]:
            return ips[idx]

    real_ip = headers_lower.get(opts.real_ip_header)
    if real_ip:
        return (real_ip.strip() or remote_addr) or ""

    return remote_addr or ""
