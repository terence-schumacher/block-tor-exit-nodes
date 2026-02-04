# Runbook: TOR Exit Node Blocking (SRE-1097)

## Overview

**Phased rollout:** **Phase 1** is blocking TOR at **Cloudflare** (security rules, same pattern as SRE-853 tier-1 geo-block); it covers Marketplace UI and other Cloudflare-proxied services but **not** Marketplace API. **Phase 2** is blocking from **Marketplace API** and other non-Cloudflare endpoints using **this repo** (fetcher + LB blocklist or reference middleware).

This runbook covers Phase 1 (Cloudflare) guidance and Phase 2: fetcher (list sync), load balancer blocklist, reference middleware, and Datadog observability.

---

## Phase 1: Cloudflare (outside this repo)

Phase 1 is implemented in **Cloudflare** (security rules), not in this repo. Same pattern as SRE-853 (tier-1 geo-block).

- **What to do:** Add Cloudflare security rule(s) to block requests whose client IP is in the TOR exit list. Use the same list source (dan.me.uk) or, if Cloudflare supports IP list import, sync from this repo’s fetcher output (`data/tor-exit-nodes.txt`).
- **Coverage:** Marketplace UI and any production resource that uses Cloudflare as proxy/CDN. Does **not** cover Marketplace API or services not behind Cloudflare (e.g. api.marketplace.inv.tech if not proxied).
- **Reference:** SRE-853 (tier-1 block at Cloudflare); SRE-999 (follow-up for cloud providers). Document which zones/services are covered by the TOR rule.

---

## Phase 2: This repo (Marketplace API and non-Cloudflare)

The sections below (fetcher, LB blocklist, reference middleware, Datadog) apply to **Phase 2**: blocking TOR from Marketplace API and other endpoints not behind Cloudflare, using this repo’s fetcher and either load balancer blocklist or WSGI middleware.

## List source and format

- **URL:** `https://www.dan.me.uk/torlist/?exit`
- **Format:** One IP per line (IPv4 and IPv6). Blank lines and invalid lines are skipped.
- **Refresh:** Run the fetcher on a schedule (e.g. hourly). List changes over time.
- **Fallback:** If the fetch fails, the last successful list is kept; the fetcher does not overwrite the file. Use Datadog alerts to detect fetch failures and list staleness.

## Fetcher (sync job)

### How to run (Python)

```bash
pip install -e .
tor-exit-fetch
# or: python -m tor_exit_block.fetcher
```

### Configuration

- **`TOR_LIST_OUTPUT_DIR`** (optional): Directory for output files. Default: `./data`
- Output files:
  - `{TOR_LIST_OUTPUT_DIR}/tor-exit-nodes.txt` – one IP per line (for LB blocklist and middleware)
  - `{TOR_LIST_OUTPUT_DIR}/.last-fetch-time` – timestamp of last successful fetch

### Scheduling

Schedule the fetcher (e.g. cron every hour):

```cron
0 * * * * cd /path/to/block-tor-exit-nodes && tor-exit-fetch
```

Ensure LBs and apps using the middleware can read the updated file (same path or copy).

### Disable / rollback

- **Disable blocking at LB:** Remove or comment out the blocklist rule in nginx/HAProxy/ALB config; reload.
- **Disable middleware:** Remove or comment out `TorExitBlockMiddleware` from the app; redeploy.
- **Revert list:** Restore a previous `tor-exit-nodes.txt` from backup and ensure the fetcher does not overwrite it until the next run, or run the fetcher again to get a fresh list.

## Load balancer blocklist

Where SRE controls the load balancer:

1. Use the file produced by the fetcher: `data/tor-exit-nodes.txt` (or `TOR_LIST_OUTPUT_DIR/tor-exit-nodes.txt`).
2. Configure the LB to deny requests whose client IP is in that file (e.g. return 403).
3. Reload the LB after the fetcher updates the file (or use a symlink and reload periodically).

### nginx example

The fetcher outputs one IP per line. nginx `geo` with `include` typically expects lines like `IP 1;`. Convert the file (e.g. `sed 's/^/ deny /' tor-exit-nodes.txt` for `deny IP;`) or use a map/list format your nginx version supports. Example (conceptual):

```nginx
# If using a map or allowlist of non-TOR IPs, or a script to generate "deny IP;" from tor-exit-nodes.txt
include /path/to/tor-exit-denylist.conf;
```

### One-IP-per-line format

The fetcher outputs one IP per line. LBs that support "list of IPs" (e.g. HAProxy, or nginx with a different include format) can use the file as-is. Document which LBs are in scope and how to add new ones in your environment.

## Reference middleware

For apps not behind SRE-controlled edge or LB:

1. Install: `pip install -e .` (or use this repo).
2. Wrap your WSGI app with `TorExitBlockMiddleware`:

```python
from tor_exit_block.middleware import TorExitBlockMiddleware

app = TorExitBlockMiddleware(
    your_wsgi_app,
    list_path="/path/to/tor-exit-nodes.txt",
    refresh_interval_seconds=3600,
    trusted_proxy_count=1,
    monitor_only=False,
)
```

**Flask:**

```python
from flask import Flask
from tor_exit_block.middleware import TorExitBlockMiddleware

app = Flask(__name__)
app.wsgi_app = TorExitBlockMiddleware(app.wsgi_app, list_path="/path/to/tor-exit-nodes.txt")
```

3. **list_path:** Path to the one-IP-per-line file (same as fetcher output).
4. **refresh_interval_seconds:** How often to re-read the file (default 3600 = 1 hour).
5. **trusted_proxy_count:** Number of trusted proxies for X-Forwarded-For (default 1).
6. **monitor_only:** If `True`, log would-be blocks but do not return 403 (for rollout).

### Allowlisting

There is no allowlisting of TOR exit nodes for production (per policy). Do not add bypasses.

## Datadog

### Configuration

- **`DD_API_KEY`:** Set for metrics and events. If unset, Datadog emission is skipped.
- **`DD_APP_KEY`:** Optional (required for some API operations).

### Fetcher metrics and alerts

- **Metrics:** `tor_exit_block.list_size`, `tor_exit_block.fetch_success`, `tor_exit_block.list_age_seconds`
- **Events:** On fetch failure, an event is sent: "TOR exit list fetch failure"
- **Alerts (configure in Datadog):**
  - Fetch failure: e.g. alert when `tor_exit_block.fetch_success == 0` for the last run
  - List too stale: e.g. alert when `tor_exit_block.list_age_seconds` exceeds a threshold (e.g. 2 hours)

### Middleware block events

- When a request is blocked, an event is sent: "TOR exit node block" with client IP and path (no full request bodies).
- Optional: metric for block count; alert on unusually high block rate (configure in Datadog).

### Where to find dashboards and alerts

Create (or link) a Datadog dashboard for tags `tor_exit_block` and configure alerts as above. Document the dashboard URL and alert names in your team wiki or runbook index.

## Client IP policy

- Use the same policy everywhere to avoid bypass: **X-Forwarded-For** (rightmost IP after trusted proxy count) or **X-Real-IP**, then socket remote address.
- **Trusted proxy count:** Typically 1 when the app is behind one proxy/LB; adjust per environment.

## Response when blocking

- **HTTP status:** 403
- **Body:** Generic message (e.g. "Access denied."). Do not disclose "blocked because TOR" in response body or headers.

## Architecture doc

See [ARCHITECTURE.md](./ARCHITECTURE.md) for ingest → storage → LB blocklist and reference middleware.
