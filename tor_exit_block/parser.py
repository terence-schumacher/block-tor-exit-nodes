"""
Parse dan.me.uk TOR exit list format: one IP per line (IPv4 or IPv6).

Blank lines and invalid entries are skipped. No deduplication beyond set semantics.
"""

import ipaddress

TOR_LIST_URL = "https://www.dan.me.uk/torlist/?exit"


def is_valid_ip(ip: str) -> bool:
    """Return True if the string is a valid IPv4 or IPv6 address."""
    if not ip or not ip.strip():
        return False
    try:
        ipaddress.ip_address(ip.strip())
        return True
    except ValueError:
        return False


def parse_tor_exit_list(body: str) -> set[str]:
    """
    Parse dan.me.uk TOR exit list format: one IP per line.
    Blank lines and invalid entries are skipped.
    """
    result: set[str] = set()
    for line in body.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        if is_valid_ip(trimmed):
            result.add(trimmed)
    return result
