"""
Datadog metrics and events (optional; no-op if DD_API_KEY is not set).

Fetcher: list size, list age, fetch success/failure.
Middleware: block events (client IP, path).
"""

import json
import os
import time
import urllib.request

DD_API_KEY = os.environ.get("DD_API_KEY")
METRIC_PREFIX = "tor_exit_block"
DATADOG_SERIES_URL = "https://api.datadoghq.com/api/v1/series"
DATADOG_EVENTS_URL = "https://api.datadoghq.com/api/v1/events"
HTTP_TIMEOUT_SECONDS = 10
HTTP_SUCCESS_MIN = 200
HTTP_SUCCESS_MAX_EXCLUSIVE = 300


def _is_configured() -> bool:
    """Return True if Datadog API key is set."""
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
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            return bool(HTTP_SUCCESS_MIN <= resp.status < HTTP_SUCCESS_MAX_EXCLUSIVE)
    except Exception as e:
        print(f"Datadog request error: {e}", flush=True)
        return False


def gauge(name: str, value: float, tags: list[str] | None = None) -> bool:
    """Emit a gauge metric to Datadog."""
    return _post(
        DATADOG_SERIES_URL,
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
        DATADOG_EVENTS_URL,
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
