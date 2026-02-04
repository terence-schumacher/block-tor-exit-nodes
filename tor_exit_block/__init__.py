"""
Block TOR exit nodes.

- Fetcher: run via `tor-exit-fetch` or `python -m tor_exit_block.fetcher`
- Middleware: use TorExitBlockMiddleware (WSGI) or TorExitBlockASGIMiddleware / add_tor_exit_block_middleware (FastAPI/ASGI)
"""

from dotenv import load_dotenv

load_dotenv()

from .parser import parse_tor_exit_list, is_valid_ip, TOR_LIST_URL
from .list_store import read_list_from_file, write_list_to_file
from .client_ip import get_client_ip, ClientIpOptions
from .middleware import (
    TorExitBlockMiddleware,
    TorExitBlockASGIMiddleware,
    add_tor_exit_block_middleware,
)

__all__ = [
    "parse_tor_exit_list",
    "is_valid_ip",
    "TOR_LIST_URL",
    "read_list_from_file",
    "write_list_to_file",
    "get_client_ip",
    "ClientIpOptions",
    "TorExitBlockMiddleware",
    "TorExitBlockASGIMiddleware",
    "add_tor_exit_block_middleware",
]
