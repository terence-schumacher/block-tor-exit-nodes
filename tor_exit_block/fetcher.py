"""Fetcher: fetch TOR exit list, parse, write LB file, emit Datadog metrics."""

import os
import sys
from pathlib import Path

import requests

from .parser import parse_tor_exit_list, TOR_LIST_URL
from .list_store import write_list_to_file
from .datadog import emit_fetcher_metrics

USER_AGENT = "block-tor-exit-nodes/1.0 (SRE-1097)"


def run_fetcher(
    *,
    output_dir: str | None = None,
) -> None:
    output_dir = output_dir or os.environ.get("TOR_LIST_OUTPUT_DIR") or str(Path.cwd() / "data")
    output_file = Path(output_dir) / "tor-exit-nodes.txt"
    last_fetch_file = Path(output_dir) / ".last-fetch-time"

    success = False
    list_size = 0
    last_fetch_time_ms = 0.0

    try:
        resp = requests.get(TOR_LIST_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        ips = parse_tor_exit_list(resp.text)
        list_size = len(ips)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        write_list_to_file(str(output_file), ips)
        last_fetch_time_ms = __import__("time").time() * 1000
        last_fetch_file.write_text(str(int(last_fetch_time_ms)), encoding="utf-8")
        success = True
        print(f"Fetched {list_size} TOR exit IPs, wrote to {output_file}", flush=True)
    except Exception as e:
        print(f"Fetcher error: {e}", file=sys.stderr, flush=True)
        if last_fetch_file.exists():
            try:
                last_fetch_time_ms = float(last_fetch_file.read_text(encoding="utf-8").strip())
            except (ValueError, OSError):
                pass

    emit_fetcher_metrics(
        list_size=list_size,
        success=success,
        last_fetch_time_ms=last_fetch_time_ms,
    )


def main() -> None:
    run_fetcher()
    sys.exit(0)


if __name__ == "__main__":
    main()
