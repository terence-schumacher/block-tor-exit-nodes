# Integration Guide

This document describes how to integrate the TOR exit block **fetcher** and **middleware** into existing systems: schedulers, WSGI/ASGI apps, load balancers, and observability.

---

## Prerequisites

- **Python 3.12+**
- Network access to `https://www.dan.me.uk/torlist/?exit` from the host that runs the fetcher
- (Optional) Datadog API key (`DD_API_KEY`) for metrics and events

## Environment and .env

The package loads a **`.env` file** from the current working directory when `tor_exit_block` is first imported. Use this for local development or any run where you want to avoid exporting variables in the shell.

1. Copy `.env.example` to `.env`.
2. Set variables in `.env` (see table in [README](../README.md#environment-env)).
3. Run `tor-exit-fetch` or your app; variables are applied automatically.

`.env` is gitignored. In production, set environment variables normally (e.g. systemd, container env, or a secret manager); `.env` is optional and not required.

---

## 1. Fetcher integration

The fetcher downloads the TOR exit list, parses it, and writes a one-IP-per-line file used by load balancers and the middleware.

### Install

```bash
pip install -e .
# or from repo root: pip install .
```

### Run once

```bash
tor-exit-fetch
# or
python -m tor_exit_block.fetcher
```

Output (by default):

- `./data/tor-exit-nodes.txt` – blocklist (one IP per line)
- `./data/.last-fetch-time` – timestamp of last successful fetch

### Configuration (environment)

| Variable               | Description                          | Default      |
|------------------------|--------------------------------------|--------------|
| `TOR_LIST_OUTPUT_DIR`  | Directory for output files          | `./data`     |
| `DD_API_KEY`           | Datadog API key (metrics/events)     | (none; no-op)|

### Schedule (cron, systemd, or scheduler)

**Cron (hourly):**

```cron
0 * * * * cd /path/to/app && tor-exit-fetch
```

**Systemd timer:** Create a service and timer that runs `tor-exit-fetch` (e.g. every hour). Point `WorkingDirectory` to where you want `data/` to live.

**CI/CD or internal scheduler:** Invoke `tor-exit-fetch` (or `python -m tor_exit_block.fetcher`) on a schedule. Ensure the output directory is shared or copied to where the LB or app reads the list.

### Failure behavior

- On fetch or parse failure, the existing `tor-exit-nodes.txt` is **not** overwritten.
- Metrics and (if `DD_API_KEY` is set) a failure event are emitted so you can alert on fetch failures or list staleness.

---

## 2. Middleware integration (WSGI apps)

Use the middleware for apps that are **not** behind a load balancer that already enforces the blocklist (e.g. Marketplace API, internal APIs).

### Wrap a generic WSGI app

```python
from tor_exit_block.middleware import TorExitBlockMiddleware

app = TorExitBlockMiddleware(
    your_wsgi_app,
    list_path="/path/to/tor-exit-nodes.txt",
    refresh_interval_seconds=3600,
    trusted_proxy_count=1,
)
```

### Flask

```python
from flask import Flask
from tor_exit_block.middleware import TorExitBlockMiddleware

app = Flask(__name__)
# ... routes ...

app.wsgi_app = TorExitBlockMiddleware(
    app.wsgi_app,
    list_path="/path/to/tor-exit-nodes.txt",
    refresh_interval_seconds=3600,
    trusted_proxy_count=1,
)
```

### Django (WSGI)

In your WSGI module (e.g. `project/wsgi.py`):

```python
import os
from django.core.wsgi import get_wsgi_application
from tor_exit_block.middleware import TorExitBlockMiddleware

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
django_app = get_wsgi_application()

app = TorExitBlockMiddleware(
    django_app,
    list_path=os.environ.get("TOR_LIST_PATH", "/var/data/tor-exit-nodes.txt"),
    refresh_interval_seconds=3600,
    trusted_proxy_count=1,
)
```

### Middleware options

| Option                     | Description                                      | Default   |
|----------------------------|--------------------------------------------------|-----------|
| `list_path`                | Path to one-IP-per-line blocklist file          | `./data/tor-exit-nodes.txt` |
| `refresh_interval_seconds` | How often to re-read the list from disk         | 3600      |
| `trusted_proxy_count`      | Number of trusted proxies for X-Forwarded-For   | 1         |
| `monitor_only`             | If `True`, log blocks but do not return 403     | False     |
| `blocked_body`             | Response body when blocking                     | "Access denied." |
| `forwarded_for_header`     | Header name for forwarded-for                   | "x-forwarded-for" |
| `real_ip_header`           | Header name for real IP                         | "x-real-ip" |

### List file path

Use the **same** path (or a copy) as the fetcher output so the middleware reads the updated list after each successful fetch. If the file is missing, the middleware treats the blocklist as empty (all requests allowed).

---

## 3. Load balancer integration

Where you control the load balancer (nginx, HAProxy, ALB, etc.):

1. Use the file produced by the fetcher: `tor-exit-nodes.txt` (one IP per line).
2. Configure the LB to deny requests whose **client IP** is in that file (e.g. return 403).
3. Reload or refresh the LB config when the fetcher updates the file (or use a symlink and periodic reload).

Client IP policy should match the rest of the stack: same trusted proxy count and header handling (X-Forwarded-For / X-Real-IP) to avoid bypass.

See [RUNBOOK.md](RUNBOOK.md) for nginx/HAProxy notes and one-IP-per-line format.

---

## 4. Observability (Datadog)

- **Fetcher:** Set `DD_API_KEY` so the fetcher can emit metrics (`tor_exit_block.list_size`, `tor_exit_block.fetch_success`, `tor_exit_block.list_age_seconds`) and a failure event on fetch/parse errors.
- **Middleware:** With `DD_API_KEY` set, each block emits an event ("TOR exit node block") with client IP and path.

Configure alerts in Datadog for fetch failures and list staleness. See [RUNBOOK.md](RUNBOOK.md) for metric names and suggested alerts.

---

## 5. Rollout and rollback

- **Monitor-only:** Use `monitor_only=True` to log would-be blocks without returning 403. Switch to `monitor_only=False` when ready to enforce.
- **Disable middleware:** Remove or comment out `TorExitBlockMiddleware` and redeploy.
- **Disable fetcher:** Stop the cron/timer/scheduler job. Existing list file remains until you replace or remove it.
- **Revert list:** Restore a previous `tor-exit-nodes.txt` from backup, or run the fetcher again to refresh.

---

## 6. Related docs

- [RUNBOOK.md](RUNBOOK.md) – Phase 1 (Cloudflare) and Phase 2 operations, config, and Datadog.
- [ARCHITECTURE.md](ARCHITECTURE.md) – High-level flow and components.
