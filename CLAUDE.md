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
│   ├── db.py            # SQLite storage with LTTB downsampling
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

**Settings per Page**: Each page has it's own settings dialog, accessible via the menu at the bottom.  Settings are relative to the page alone, and are typically stored in localStorage.

**Mobile Compatibility**: This website should be usable on both touch-based mobile browsers and Desktop machines.

**Service Management**: All monitored services are systemd units. The `services/` directory contains `.service` files for project-managed services (pi-dashboard, qbittorrent), installed via `scripts/service_mod.sh`. External services (tailscaled, smbd, etc.) are pre-existing system units referenced by `service_name` in the config. Services with `link_url` in their config show both DETAILS and LINK buttons in the UI.

**Subprocess Execution (tpool)**: All subprocess calls MUST go through `utils.subprocess_helper.run()` instead of `subprocess.run()` directly. Under eventlet, `subprocess.run()` blocks the green thread event loop because Python 3.10+ subprocess uses `selectors.EpollSelector` internally, which eventlet doesn't fully monkey-patch. The helper wraps calls in `eventlet.tpool.execute()` so they run in real OS threads and the event loop stays responsive. In debug mode (no eventlet), it falls back to plain `subprocess.run()`. This is critical — without it, any slow subprocess call (e.g. `systemctl stop tailscaled` taking several seconds) will freeze the entire webserver, blocking all HTTP requests and WebSocket broadcasts.

**Remote Machine Management**: Remote machines (e.g., PCs controlled via smart plugs + SSH) are configured in `config/remote_machine_config.json` with local overrides. They appear as service-style cards in the dashboard with online/offline status (TCP port 22 check) and power toggle (Kasa smart plug + SSH shutdown). Status is broadcast via the same `service_status` WebSocket event with `rm_` prefixed IDs. The `createServiceCard()` function accepts optional `{onToggle, onDetails}` callbacks to customize behavior for remote machines vs. systemd services. Each machine has a `shell_type` config (`linux`, `wsl`, or `cmd`; default `linux`) that controls how SSH commands are sent — WSL requires piping commands via stdin because `wsl.exe` doesn't accept the `-c` flag SSH uses.

**Chart Configuration**: The charts page (`/charts`) uses user-defined chart configs instead of auto-grouping by units. Each chart has a name, a list of series IDs, and a `nameManuallySet` flag. Configs are stored in localStorage as `chartConfigs` (array of `{id, name, seriesIds, nameManuallySet}`). A "Manage Charts" modal lets users create/rename/delete charts and search+add series to each. The same series can appear in multiple charts. Default chart names are auto-generated from shared units or category of contained series.

### WebSocket Events

- `system_stats` - Pushed every 2s with CPU, RAM, disk, network stats
- `service_status` - Pushed every 5s with service running states (includes remote machine status with `rm_` prefix)
- `automation_update` - Real-time output streaming from automation scripts
- `remote_machine_progress` - Step-by-step progress during remote machine start/stop operations

## Sudoers Requirements

For service control and reboot functionality:
```
$USER ALL=(ALL) NOPASSWD: /bin/systemctl start *, /bin/systemctl stop *, /bin/systemctl restart *
$USER ALL=(ALL) NOPASSWD: /sbin/reboot
```
