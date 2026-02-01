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
│   ├── service_utils.py # systemd/process control
│   ├── system_utils.py  # CPU, RAM, disk stats
│   └── data_utils.py    # LTTB downsampling algorithm
├── app_state.py         # Shared state: caches, locks, constants
├── config_loader.py     # JSON config merging (base + local overrides)
└── socketio_handlers.py # WebSocket event handlers
```

### Key Patterns

**Async Modes**: Uses `eventlet` in production, `threading` in debug mode (controlled by `DEBUG_MODE` env var).

**SocketIO Sharing**: The `app_state.py` module provides `set_socketio()`/`get_socketio()` to share the SocketIO instance across modules without circular imports.

**Config Merging**: Configuration files in `config/` use a base + local override pattern. Base configs (`*.json`) are version-controlled; local overrides (`*.local.json`) are gitignored and merged at runtime.

**Timeseries Auto-Discovery**: New timeseries are automatically registered when a class inherits from `TimeseriesBase` - no manual registration needed.

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
