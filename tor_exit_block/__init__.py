"""
Block TOR exit nodes.

- Fetcher: run via `tor-exit-fetch` or `python -m tor_exit_block.fetcher`
- Middleware: use TorExitBlockMiddleware (WSGI) or wrap_flask_app (Flask)
"""

from .parser import parse_tor_exit_list, is_valid_ip, TOR_LIST_URL
from .list_store import read_list_from_file, write_list_to_file
from .client_ip import get_client_ip, ClientIpOptions
from .middleware import TorExitBlockMiddleware, wrap_flask_app

__all__ = [
    "parse_tor_exit_list",
    "is_valid_ip",
    "TOR_LIST_URL",
    "read_list_from_file",
    "write_list_to_file",
    "get_client_ip",
    "ClientIpOptions",
    "TorExitBlockMiddleware",
    "wrap_flask_app",
]
