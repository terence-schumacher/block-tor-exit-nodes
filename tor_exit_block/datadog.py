"""
Datadog metrics and events (optional; no-op if DD_API_KEY is not set).
Fetcher: list size, list age, fetch success/failure.
Middleware: block events (client IP, path, timestamp).
"""

import os
import time
import urllib.request
import urllib.error
import json

DD_API_KEY = os.environ.get("DD_API_KEY")
METRIC_PREFIX = "tor_exit_block"


def _is_configured() -> bool:
    return bool(DD_API_KEY)


def _post(url: str, data: dict[str, object]) -> bool:
    if not _is_configured():
        return True
    api_key = DD_API_KEY or ""
    try:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "DD-API-KEY": api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return bool(200 <= resp.status < 300)
    except Exception as e:
        print(f"Datadog request error: {e}", flush=True)
        return False


def gauge(name: str, value: float, tags: list[str] | None = None) -> bool:
    """Emit a gauge metric to Datadog."""
    return _post(
        "https://api.datadoghq.com/api/v1/series",
        {
            "series": [
                {
                    "metric": f"{METRIC_PREFIX}.{name}",
                    "type": "gauge",
                    "points": [[int(time.time()), value]],
                    "tags": tags or [],
                }
            ]
        },
    )


def event(
    title: str,
    text: str,
    *,
    alert_type: str = "info",
    tags: list[str] | None = None,
) -> bool:
    """Emit an event to Datadog."""
    return _post(
        "https://api.datadoghq.com/api/v1/events",
        {
            "title": title,
            "text": text,
            "alert_type": alert_type,
            "tags": tags or [],
        },
    )


def emit_fetcher_metrics(
    *,
    list_size: int,
    success: bool,
    last_fetch_time_ms: float,
) -> None:
    """Emit fetcher metrics after a run."""
    gauge("list_size", list_size)
    gauge("fetch_success", 1.0 if success else 0.0)
    age_seconds = 0.0 if success else (time.time() * 1000 - last_fetch_time_ms) / 1000
    gauge("list_age_seconds", int(age_seconds))
    if not success:
        event(
            "TOR exit list fetch failure",
            "Failed to fetch or parse TOR exit list. Check list source and network.",
            alert_type="error",
            tags=["tor_exit_block", "fetcher"],
        )


def emit_block_event(*, client_ip: str, path: str) -> None:
    """Emit a block event when middleware blocks a request."""
    event(
        "TOR exit node block",
        f"Blocked request from {client_ip} to {path}",
        tags=["tor_exit_block", "block", f"client_ip:{client_ip}"],
    )
