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
├── routes/              # Flask blueprints for HTTP endpoints
│   ├── pages.py         # HTML page routes (/, /monitor)
│   ├── services_api.py  # Service control endpoints
│   ├── system_api.py    # System stats endpoints
│   ├── automations_api.py # Automation execution endpoints
│   └── external_api.py  # Stock/weather API proxies
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
│   ├── service_utils.py # systemd/process control
│   ├── system_utils.py  # CPU, RAM, disk stats
│   └── data_utils.py    # LTTB downsampling algorithm
├── app_state.py         # Shared state: caches, locks, constants
├── config_loader.py     # JSON config merging (base + local overrides)
└── socketio_handlers.py # WebSocket event handlers
```

### Important RULES:
* You WILL ALWAYS keep CLAUDE.md up to date as you make changes.
* You *WILL NOT* commit secrets to git (e.g. .env).
* You will as the user when something important is worth committing to your long term memory in the form of CLAUDE.md or similar.

### Key Patterns

**Async Modes**: Uses `eventlet` in production, `threading` in debug mode (controlled by `DEBUG_MODE` env var).

**SocketIO Sharing**: The `app_state.py` module provides `set_socketio()`/`get_socketio()` to share the SocketIO instance across modules without circular imports.

**Config Merging**: Configuration files in `config/` use a base + local override pattern. Base configs (`*.json`) are version-controlled; local overrides (`*.local.json`) are gitignored and merged at runtime.

**Timeseries Auto-Discovery**: New timeseries are automatically registered when a class inherits from `TimeseriesBase` - no manual registration needed.

**Settings per Page**: Each page has it's own settings dialog, accessible via the menu at the bottom.  Settings are relative to the page alone, and are typically stored in localStorage.

**Mobile Compatibility**: This website should be usable on both touch-based mobile browsers and Desktop machines.

**Subprocess Execution (tpool)**: All subprocess calls MUST go through `utils.subprocess_helper.run()` instead of `subprocess.run()` directly. Under eventlet, `subprocess.run()` blocks the green thread event loop because Python 3.10+ subprocess uses `selectors.EpollSelector` internally, which eventlet doesn't fully monkey-patch. The helper wraps calls in `eventlet.tpool.execute()` so they run in real OS threads and the event loop stays responsive. In debug mode (no eventlet), it falls back to plain `subprocess.run()`. This is critical — without it, any slow subprocess call (e.g. `systemctl stop tailscaled` taking several seconds) will freeze the entire webserver, blocking all HTTP requests and WebSocket broadcasts.

### WebSocket Events

- `system_stats` - Pushed every 2s with CPU, RAM, disk, network stats
- `service_status` - Pushed every 5s with service running states
- `automation_update` - Real-time output streaming from automation scripts

## Sudoers Requirements

For service control and reboot functionality:
```
$USER ALL=(ALL) NOPASSWD: /bin/systemctl start *, /bin/systemctl stop *, /bin/systemctl restart *
$USER ALL=(ALL) NOPASSWD: /sbin/reboot
```
