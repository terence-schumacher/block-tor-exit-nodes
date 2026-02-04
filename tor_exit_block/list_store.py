"""Read/write one-IP-per-line list file."""

import os


def read_list_from_file(file_path: str) -> set[str]:
    """
    Read the TOR exit list from a one-IP-per-line file (same format as written by fetcher).
    Returns empty set if file does not exist.
    """
    if not os.path.isfile(file_path):
        return set()
    with open(file_path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def write_list_to_file(file_path: str, ips: set[str]) -> None:
    """Write the IP set to a one-IP-per-line file for load balancer blocklist and middleware."""
    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
    lines = sorted(ips)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
