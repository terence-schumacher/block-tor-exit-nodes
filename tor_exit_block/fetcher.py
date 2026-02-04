"""
Fetcher: fetch TOR exit list, parse, write LB file, emit Datadog metrics.

Designed for a single level of abstraction: fetch → persist → report.
"""

import os
import sys
import time
from pathlib import Path

import requests

from .parser import parse_tor_exit_list, TOR_LIST_URL
from .list_store import write_list_to_file
from .datadog import emit_fetcher_metrics

USER_AGENT = "block-tor-exit-nodes/1.0"
OUTPUT_FILENAME = "tor-exit-nodes.txt"
LAST_FETCH_FILENAME = ".last-fetch-time"
DEFAULT_OUTPUT_SUBDIR = "data"
HTTP_TIMEOUT_SECONDS = 30


def _resolve_output_dir(output_dir: str | None) -> str:
    """Return output directory from argument or env or default."""
    if output_dir:
        return output_dir
    from_env = os.environ.get("TOR_LIST_OUTPUT_DIR")
    if from_env:
        return from_env
    return str(Path.cwd() / DEFAULT_OUTPUT_SUBDIR)


def _fetch_exit_list() -> set[str]:
    """Download and parse the TOR exit list. Raises on network/parse failure."""
    resp = requests.get(
        TOR_LIST_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return parse_tor_exit_list(resp.text)


def _read_last_fetch_time_ms(file_path: Path) -> float:
    """Read last successful fetch timestamp from file. Returns 0.0 if missing or invalid."""
    if not file_path.exists():
        return 0.0
    try:
        return float(file_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return 0.0


def _persist_success(output_file: Path, last_fetch_file: Path, ips: set[str]) -> float:
    """Write list and timestamp; return current time in milliseconds."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    write_list_to_file(str(output_file), ips)
    now_ms = time.time() * 1000
    last_fetch_file.write_text(str(int(now_ms)), encoding="utf-8")
    return now_ms


def run_fetcher(
    *,
    output_dir: str | None = None,
) -> None:
    """
    Fetch TOR exit list, write blocklist file, and emit metrics.
    On failure, leaves existing file unchanged and reports failure.
    """
    resolved_dir = _resolve_output_dir(output_dir)
    output_file = Path(resolved_dir) / OUTPUT_FILENAME
    last_fetch_file = Path(resolved_dir) / LAST_FETCH_FILENAME

    success = False
    list_size = 0
    last_fetch_time_ms = _read_last_fetch_time_ms(last_fetch_file)

    try:
        ips = _fetch_exit_list()
        list_size = len(ips)
        last_fetch_time_ms = _persist_success(output_file, last_fetch_file, ips)
        success = True
        print(f"Fetched {list_size} TOR exit IPs, wrote to {output_file}", flush=True)
    except Exception as e:
        print(f"Fetcher error: {e}", file=sys.stderr, flush=True)
        last_fetch_time_ms = _read_last_fetch_time_ms(last_fetch_file)

    emit_fetcher_metrics(
        list_size=list_size,
        success=success,
        last_fetch_time_ms=last_fetch_time_ms,
    )


def main() -> None:
    """Entry point for the tor-exit-fetch CLI."""
    run_fetcher()
    sys.exit(0)


if __name__ == "__main__":
    main()
