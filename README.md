# block-tor-exit-nodes

Block app access from known TOR exit nodes for production. **Phased rollout:**

- **Phase 1 (immediate):** Block TOR at **Cloudflare** (security rules, same pattern as tier-1 geo-block). Covers Marketplace UI and other Cloudflare-proxied services; does **not** cover Marketplace API.
- **Phase 2 (follow-up):** Block from **Marketplace API** and other non-Cloudflare endpoints using **this repo** (fetcher + LB blocklist or reference middleware).

This repo provides Phase 2 tooling:

1. **Fetcher** – Fetches the dan.me.uk exit list, parses it, and writes a one-IP-per-line file for load balancers and the reference middleware.
2. **Reference middleware** – WSGI middleware for apps not behind Cloudflare (e.g. Marketplace API); checks client IP against the list and returns 403 when matched.

Enforcement can also be done at the **load balancer** (blocklist file) where SRE controls the LB. No allowlisting of TOR exit nodes for production.

## Requirements

- Python 3.12+

## Install

```bash
pip install -e .
# or with dev deps (pytest, flask): pip install -e ".[dev]"
```

## Environment (.env)

The project loads a `.env` file from the current working directory when the package is imported. Copy `.env.example` to `.env` and set variables as needed.

| Variable | Used by | Description |
|----------|---------|--------------|
| `TOR_LIST_OUTPUT_DIR` | Fetcher | Output directory for blocklist (default: `./data`) |
| `DD_API_KEY` | Fetcher, middleware | Datadog API key (optional; no-op if unset) |
| `TOR_LIST_PATH` | Example app | Path to blocklist file |
| `TOR_BLOCK_MONITOR_ONLY` | Example app | Set to `1` for monitor-only (log, don't 403) |
| `PORT` | Example app | Example server port (default: `3000`) |

`.env` is gitignored; use `.env.example` as a template.

## Quick start

```bash
cp .env.example .env   # optional: edit .env with your settings
tor-exit-fetch         # fetch list → data/tor-exit-nodes.txt
python example_app.py  # example server with middleware (optional)
```

## Usage

### Fetcher (cron or scheduler)

```bash
tor-exit-fetch
# or: python -m tor_exit_block.fetcher
```

Output: `data/tor-exit-nodes.txt` (or set `TOR_LIST_OUTPUT_DIR` in env or `.env`). Schedule hourly (see [docs/RUNBOOK.md](docs/RUNBOOK.md)).

### Middleware (WSGI)

Wrap any WSGI app:

```python
from tor_exit_block.middleware import TorExitBlockMiddleware

# Wrap your WSGI app
app = TorExitBlockMiddleware(
    your_wsgi_app,
    list_path="./data/tor-exit-nodes.txt",
    refresh_interval_seconds=3600,
    trusted_proxy_count=1,
)
```

**Flask:**

```python
from flask import Flask
from tor_exit_block.middleware import TorExitBlockMiddleware

app = Flask(__name__)
app.wsgi_app = TorExitBlockMiddleware(
    app.wsgi_app,
    list_path="./data/tor-exit-nodes.txt",
    refresh_interval_seconds=3600,
)
```

Options: `list_path`, `refresh_interval_seconds`, `trusted_proxy_count`, `monitor_only`, `blocked_body`, `forwarded_for_header`, `real_ip_header`. See [docs/RUNBOOK.md](docs/RUNBOOK.md).

### Load balancer blocklist

Use `data/tor-exit-nodes.txt` (one IP per line) in nginx, HAProxy, or ALB. See runbook for format notes.

## Observability (Datadog)

Set `DD_API_KEY` to emit metrics and events. Fetcher: list size, fetch success/failure, list age; events on failure. Middleware: block events (client IP, path). Configure alerts in Datadog for fetch failures and list staleness. See [docs/RUNBOOK.md](docs/RUNBOOK.md).

## Docs

- [Runbook](docs/RUNBOOK.md) – Phase 1 (Cloudflare) and Phase 2 (this repo); refresh interval, list path, disable/rollback, Datadog dashboards/alerts.
- [Architecture](docs/ARCHITECTURE.md) – Phased rollout (Cloudflare then this repo); ingest → LB blocklist and reference middleware.
- [Integration](docs/INTEGRATION.md) – How to integrate the fetcher and middleware (cron, Flask/Django, load balancer, Datadog).

## Tests

```bash
pip install -e ".[dev]"
pytest
```

- **Unit tests** (default): parser, list store, client IP, middleware, fetcher, Datadog (mocked).
- **Integration tests** (`-m integration`): real HTTP to a local stub server → fetcher writes list; real list file → middleware block/allow.
- **E2E tests** (`-m e2e`): full flow — stub server → fetch → app with middleware → blocked IP → 403, allowed IP → 200.

```bash
pytest -m "not integration and not e2e"   # unit only (fast)
pytest -m integration                     # integration only
pytest -m e2e                             # E2E only
```

## Development (mypy, black)

```bash
pip install -e ".[dev]"
black .          # format
black --check .  # check only (CI)
mypy tor_exit_block
```

CI (GitHub Actions) runs on push/PR: Black check, mypy, pytest on Python 3.12+.

## License

Internal use.
