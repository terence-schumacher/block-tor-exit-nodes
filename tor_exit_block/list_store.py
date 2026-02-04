"""
Read/write one-IP-per-line blocklist file.

Same format as produced by the fetcher; safe for use by load balancers and middleware.
"""

import os

ENCODING = "utf-8"


def read_list_from_file(file_path: str) -> set[str]:
    """
    Read the TOR exit list from a one-IP-per-line file.
    Returns empty set if file does not exist or path is not a file.
    """
    if not file_path or not os.path.isfile(file_path):
        return set()
    with open(file_path, encoding=ENCODING) as f:
        return {line.strip() for line in f if line.strip()}


def write_list_to_file(file_path: str, ips: set[str]) -> None:
    """Write the IP set to a one-IP-per-line file. Creates parent directories if needed."""
    if not file_path:
        raise ValueError("file_path must be non-empty")
    parent = os.path.dirname(file_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    lines = sorted(ips)
    with open(file_path, "w", encoding=ENCODING) as f:
        f.write("\n".join(lines) + "\n")
