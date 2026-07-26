# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
# Activate virtual environment
source .venv/bin/activate

# Run in debug mode (uses threading instead of eventlet)
DEBUG_MODE=1 python rpi_dashboard.py

# Run in production mode locally
python rpi_dashboard.py

# Production deployment (via systemd service)
sudo systemctl restart pi-dashboard.service

# Install dependencies
pip install -r requirements.txt
```

## Architecture Overview

This is a Flask + SocketIO dashboard for monitoring and controlling a Raspberry Pi media server.

### Entry Point
- `rpi_dashboard.py` - Main application entry point (~65 lines). Initializes Flask, SocketIO, registers blueprints, and starts background threads.

### Package Structure

```
├── services/            # systemd .service files (installed via scripts/service_mod.sh)
├── routes/              # Flask blueprints for HTTP endpoints
│   ├── pages.py         # HTML page routes (/, /monitor)
│   ├── services_api.py  # Service control endpoints
│   ├── system_api.py    # System stats endpoints
│   ├── automations_api.py # Automation execution endpoints
│   ├── external_api.py  # Stock/weather API proxies
│   └── remote_machines_api.py # Remote machine power control endpoints
├── background/          # Daemon threads for monitoring
│   ├── network_monitor.py
│   ├── system_broadcaster.py
│   ├── service_broadcaster.py
│   └── internet_monitor.py
├── timeseries/          # Time-series data collection system
│   ├── config.py        # TimeseriesBase class (auto-discovery via __init_subclass__)
│   ├── command_timeseries.py # Config-driven timeseries that execute shell commands
│   ├── db.py            # SQLite storage with two-stage downsampling
│   ├── routes.py        # Timeseries API endpoints
│   └── collector.py     # Background data collection
├── utils/               # Utility functions
│   ├── subprocess_helper.py # Central subprocess.run() wrapper (tpool-safe)
│   ├── service_utils.py # systemd service status & control
│   ├── system_utils.py  # CPU, RAM, disk stats
│   ├── data_utils.py    # LTTB downsampling algorithm
│   └── remote_machine_utils.py # Remote machine status & power control
├── app_state.py         # Shared state: caches, locks, constants
├── config_loader.py     # JSON config merging (base + local overrides)
└── socketio_handlers.py # WebSocket event handlers
```

### Important RULES:
* You WILL ALWAYS keep CLAUDE.md up to date as you make changes.
* You *WILL NOT* commit secrets to git (e.g. .env).
* You will ask the user when something important is worth committing to your long term memory in the form of CLAUDE.md or similar.

### Key Patterns

**Async Modes**: Uses `eventlet` in production, `threading` in debug mode (controlled by `DEBUG_MODE` env var).

**SocketIO Sharing**: The `app_state.py` module provides `set_socketio()`/`get_socketio()` to share the SocketIO instance across modules without circular imports.

**Config Merging**: Configuration files in `config/` use a base + local override pattern. Base configs (`*.json`) are version-controlled; local overrides (`*.local.json`) are gitignored and merged at runtime.

**Timeseries Auto-Discovery**: New timeseries are automatically registered when a class inherits from `TimeseriesBase` - no manual registration needed.

**Command Timeseries**: Config-driven timeseries that execute shell commands to collect numeric data. Defined in `config/command_timeseries_config.json` (base + local override pattern). Each entry specifies `id`, `command` (argv list), `units`, and optional `name`, `category`, `timeout`, `tags`, `description`. The `CommandTimeseries` class in `timeseries/command_timeseries.py` uses `_exclude_from_discovery = True` and is instantiated manually from config, then appended to the `TIMESERIES` registry. Command paths are resolved relative to the workspace root.

**Settings per Page**: Each page has it's own settings dialog, accessible via the menu at the bottom.  Settings are relative to the page alone, and are typically stored in localStorage.

**Mobile Compatibility**: This website should be usable on both touch-based mobile browsers and Desktop machines.

**Service Management**: All monitored services are systemd units. The `services/` directory contains `.service` files for project-managed services (pi-dashboard, qbittorrent), installed via `scripts/service_mod.sh`. External services (tailscaled, smbd, etc.) are pre-existing system units referenced by `service_name` in the config. Services with `link_url` in their config show both DETAILS and LINK buttons in the UI.

**Subprocess Execution (tpool)**: All subprocess calls MUST go through `utils.subprocess_helper.run()` instead of `subprocess.run()` directly. Under eventlet, `subprocess.run()` blocks the green thread event loop because Python 3.10+ subprocess uses `selectors.EpollSelector` internally, which eventlet doesn't fully monkey-patch. The helper wraps calls in `eventlet.tpool.execute()` so they run in real OS threads and the event loop stays responsive. In debug mode (no eventlet), it falls back to plain `subprocess.run()`. This is critical — without it, any slow subprocess call (e.g. `systemctl stop tailscaled` taking several seconds) will freeze the entire webserver, blocking all HTTP requests and WebSocket broadcasts.

**Remote Machine Management**: Remote machines (e.g., PCs controlled via smart plugs + SSH) are configured in `config/remote_machine_config.json` with local overrides. They appear as service-style cards in the dashboard with online/offline status (TCP port 22 check) and power toggle (Kasa smart plug + SSH shutdown). Status is broadcast via the same `service_status` WebSocket event with `rm_` prefixed IDs. The `createServiceCard()` function accepts optional `{onToggle, onDetails}` callbacks to customize behavior for remote machines vs. systemd services. Each machine has a `shell_type` config (`linux`, `wsl`, or `cmd`; default `linux`) that controls how SSH commands are sent — WSL requires piping commands via stdin because `wsl.exe` doesn't accept the `-c` flag SSH uses.

**Chart Query Performance**: `query_range()` in `timeseries/db.py` downsamples in two stages, because materializing a whole range in Python made `max_datapoints` cap the *response* but not the *work* — a 30-day window cost the same whether you asked for 100 points or 10,000. Stage 1 buckets inside SQLite (`GROUP BY cast((timestamp-start)/width AS INT)`), emitting each bucket's **min and max** so spikes survive — a per-bucket average silently clips them (measured: a 458.9 W peak on `r16_wattage` read as 378.9 W). Extreme *values* are exact; each is paired with the bucket's first/last timestamp, so x-position can be off by at most one bucket width (~0.1 px at `_BUCKET_OVERSAMPLE = 4`). Stage 2 is the existing LTTB pass, now over a few thousand candidates. `algorithm='average'` uses per-bucket means instead, matching its requested semantics.

Bucketing is gated by `_bucketing_pays()`: aggregation costs several times more per row than a plain index scan, so it only wins when it discards most of the range. Counting the range would cost as much as the query being avoided, so cadence is estimated from a 100-row sample and extrapolated (a short sample means the range is genuinely small, so the count is exact). **Without this gate the default `max_datapoints=10000` got slower**, since 40,000 buckets exceeded the ~30,000 rows a series holds over 30 days — every bucket held ≤1 row, paying `GROUP BY` cost for zero reduction.

The index is `idx_ts_covering (timeseries_id, timestamp, value)`. Including `value` makes it *covering*, so range queries never touch the table; previously each of ~1.3M index hits needed a separate row lookup (3.74s → 1.60s on a 30-day range). It replaced `idx_timeseries_timestamp`, which duplicated the implicit index behind `UNIQUE(timeseries_id, timestamp)` and only cost disk and write throughput. `_init_db()` creates the covering index and drops the old one, so both are applied on startup. Note `_init_db()` runs from `TimeseriesDB.__init__`, and `timeseries/__init__.py` imports `.routes` which instantiates it at module level — so *importing the package with the repo as cwd mutates the live `timeseries.db`*.

Net effect (43 series): 30-day at `max_datapoints=2000` went 6.78s → 2.75s, 7-day at 10,000 went 2.15s → 1.66s. The charts-page default `maxDatapoints` was lowered 10000 → 2000 in `static/charts.js` (~2x the pixel width of a typical chart; 10,000 also made the browser render 262k points). **A saved localStorage value overrides the default**, so existing browsers keep whatever is in Settings.

**Chart Configuration**: The charts page (`/charts`) uses user-defined chart configs instead of auto-grouping by units. Each chart has a name, a list of series IDs, and a `nameManuallySet` flag. Configs are stored in localStorage as `chartConfigs` (array of `{id, name, seriesIds, nameManuallySet}`). A "Manage Charts" modal lets users create/rename/delete charts and search+add series to each. The same series can appear in multiple charts. Default chart names are auto-generated from shared units or category of contained series.

### WebSocket Events

- `system_stats` - Pushed every 2s with CPU, RAM, disk, network stats
- `service_status` - Pushed every 5s with service running states (includes remote machine status with `rm_` prefix)
- `automation_update` - Real-time output streaming from automation scripts
- `remote_machine_progress` - Step-by-step progress during remote machine start/stop operations

**Stale-tab recovery**: WebSockets can go zombie after laptop sleep / NAT timeout / mobile-tab throttling — socket.io still reports `connected` but no messages flow, and a backgrounded tab's heartbeat is throttled so it never detects the dead connection. The dashboard listens for `visibilitychange` and on tab focus pulls fresh state via HTTP (`fetchInitialStatus()` + `fetchInitialSystemStats()`), reconciling without requiring a manual refresh. Live broadcasts resume once the underlying transport recovers.

**Front-end load performance**: JS libraries are self-hosted under `static/vendor/` (socket.io 4.5.4, plotly 2.27.0) instead of loaded from a CDN — a LAN tool must not block initial paint on an external network fetch (this caused a multi-second black screen on mobile). All `<script>` tags use `defer` so HTML parses and the skeleton paints immediately; `defer` preserves execution order, so vendored libs load before the page scripts that depend on them. Static assets are cached aggressively (`SEND_FILE_MAX_AGE_DEFAULT = 30 days`) with cache-busting via the `versioned_static(filename)` Jinja helper (registered as a context processor in `rpi_dashboard.py`), which appends `?v=<file mtime>` so a changed file is re-fetched. Use `versioned_static(...)` instead of `url_for('static', ...)` for CSS/JS asset references in templates.

## Sudoers Requirements

For service control and reboot functionality:
```
$USER ALL=(ALL) NOPASSWD: /bin/systemctl start *, /bin/systemctl stop *, /bin/systemctl restart *
$USER ALL=(ALL) NOPASSWD: /sbin/reboot
```
