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

## Verifying the UI headless (Chromium screenshots)

Useful for checking layout/CSS without a real browser. Chromium is at
`/usr/bin/chromium` (also `chromium-browser`).

```bash
# Screenshot a page to a PNG
chromium --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage \
  --hide-scrollbars --window-size=1240,1000 \
  --screenshot=/tmp/out.png "file:///tmp/page.html"

# Dump computed layout/styles as text (read it back with grep)
chromium --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage \
  --window-size=1240,1000 --dump-dom "file:///tmp/page.html"
```

Hard-won gotchas:
- **Don't screenshot the live app directly.** The matrix-rain animation
  (continuous `requestAnimationFrame`) + the socket.io connection never let the
  page go idle, so the headless screenshot **hangs** (times out). Instead render
  a **static harness**: an HTML file that `<link>`s the real `static/style.css`
  and contains the card/tile DOM you want to check (no JS, no sockets, no
  animation). This is also faster to iterate on.
- **No external resources.** A remote `<img>`/font URL blocks page load → the
  screenshot hangs. Use `data:` URIs for placeholder images.
- **Set the theme CSS vars** the harness needs (style.css reads them, they're
  normally injected by JS): `--theme-primary`, `--theme-primary-rgb`,
  `--theme-bg-medium/dark/light`, and for groups `--group-color`,
  `--group-color-rgb`. Add `class="compact-mode"` on `<body>` to test compact
  layout (the default on mobile).
- **Flags:** `--no-sandbox --disable-gpu --disable-dev-shm-usage` are required
  here. **Avoid** `--single-process`/`--no-zygote` (they crash). A stray
  `Error: unrecognized flag --no-decommit-pooled-pages` is harmless noise.
- **Measure computed layout** by adding a `<script>` that writes
  `getBoundingClientRect()` / `getComputedStyle()` values into a `<pre>`, then
  read them via `--dump-dom` — far more reliable than eyeballing a screenshot
  for "why is this element the wrong size".

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
│   ├── remote_machines_api.py # Remote machine power control endpoints
│   └── devices_api.py   # Device (media player, etc.) status/command/art endpoints
├── background/          # Daemon threads for monitoring
│   ├── network_monitor.py
│   ├── system_broadcaster.py
│   ├── service_broadcaster.py
│   ├── internet_monitor.py
│   └── device_broadcaster.py # Polls devices, broadcasts `device_status`
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

**Config Merging**: Configuration files in `config/` use a base + local override pattern. Base configs (`*.json`) are version-controlled; local overrides (`*.local.json`) are gitignored and merged at runtime. Exception: `config/device_config.json` is itself gitignored (it holds LAN device addresses); the git-tracked schema reference is `config/device_config.json.example`.

**Devices (media players, cameras, ...)**: A tile category distinct from services/automations/stats — external networked appliances the dashboard remote-controls/views, each with a bespoke interactive tile rather than the uniform on/off card. It's a thin pluggable framework: every device in `config/device_config.json` declares a `type` that maps to (a) a backend dispatcher in `utils/device_types.py` (`DEVICE_TYPES` → `get_status` + `commands`) and (b) a frontend renderer/updater registered in `static/dashboard.js` (`DEVICE_RENDERERS` / `DEVICE_UPDATERS`). Adding a new kind of device = one new `type` entry + a renderer, no other wiring. The first type is `bluos` (BluOS/Bluesound players, `utils/bluos_utils.py` — stdlib `urllib` + `xml.etree`, REST on port 11000). Endpoints live in `routes/devices_api.py`: `GET /api/devices`, `GET /api/devices/status`, `POST /api/device/<id>/command` (`play|pause|toggle|next|prev|volume|seek`), `GET /api/device/<id>/art` (artwork proxy that streams bytes from the device, keeping its address off the client). `background/device_broadcaster.py` polls devices and pushes the `device_status` event. The DEVICES separator is the section header/collapse. `#devices-section` is `display: contents`, so the **named collapsible groups** inside it are direct items of the `.dashboard` grid — they line up in the same columns (and share the same widths) as the service cards above, flowing left-to-right and wrapping. Order is render order in `init()`: **Remote Machines** first, then **Music Players** (BluOS tiles). Group name comes from each item's `group` config field; cards inside a group (tagged `.device-group`) stack in a flex column at `width: 100%`. Device groups get **no** `align-self` override — they stretch to the row height exactly like service cards and automation groups, so a collapsed device group looks identical to any other collapsed group (a thin bar would be inconsistent), and collapsing reuses the shared `.automation-group-content.collapsed` rule. The DEVICES separator + section are hidden (`.empty-hidden`) when no devices AND no remote machines are registered. Media tiles deliberately use `.device-card`/`.media-header`/`.media-name` (NOT `.service-card`/`.service-header`) so the compact-mode grid rules — which reshape service cards and would otherwise give the header `flex: 0 0 100%` (full height in a column flex) — can't break the layout. Transport icons carry the U+FE0E text-presentation selector (`ICON_PLAY`/`ICON_PAUSE`/`ICON_PREV`/`ICON_NEXT`) so iOS renders monochrome glyphs, not color emoji. Play/pause is optimistic (icon flips instantly, sends explicit `play`/`pause`, holds the optimistic state ~4s so a stale poll can't revert it). **BluOS reports `<state>stream</state>`, not `play`, for streaming sources** (TidalConnect, internet radio), so `get_status()` computes `playing = state in ('play', 'stream')` — checking only for `'play'` makes a streaming track show a yellow LED and a ▶ icon while audio is actually playing. Overflowing title/artist text scrolls via `setScrollingText()` (a gentle ping-pong marquee that only activates when the text is wider than its container).

**Rate-limited volume ("lowpass")**: The media-player volume slider is slew-rate limited so an errant fling can't blast a powerful stereo. Behavior is "release stops the climb": the thumb crawls under the finger at a capped step rate (`volume_max_step` per `volume_tick_ms`) and freezes on release; incoming `device_status` only reflects into the slider when the user isn't dragging. There is also a hard cap `volume_max` (default 60) enforced both as the slider's `max` and as a server-side clamp in `utils/device_types.py` so no client (UI, stale tab, raw curl) can exceed it.

**Timeseries Auto-Discovery**: New timeseries are automatically registered when a class inherits from `TimeseriesBase` - no manual registration needed.

**Command Timeseries**: Config-driven timeseries that execute shell commands to collect numeric data. Defined in `config/command_timeseries_config.json` (base + local override pattern). Each entry specifies `id`, `command` (argv list), `units`, and optional `name`, `category`, `timeout`, `tags`, `description`. The `CommandTimeseries` class in `timeseries/command_timeseries.py` uses `_exclude_from_discovery = True` and is instantiated manually from config, then appended to the `TIMESERIES` registry. Command paths are resolved relative to the workspace root.

**Settings per Page**: Each page has it's own settings dialog, accessible via the menu at the bottom.  Settings are relative to the page alone, and are typically stored in localStorage.

**Mobile Compatibility**: This website should be usable on both touch-based mobile browsers and Desktop machines.

**Service Management**: All monitored services are systemd units. The `services/` directory contains `.service` files for project-managed services (pi-dashboard, qbittorrent), installed via `scripts/service_mod.sh`. External services (tailscaled, smbd, etc.) are pre-existing system units referenced by `service_name` in the config. Services with `link_url` in their config show both DETAILS and LINK buttons in the UI.

**Primary Network Interface**: The interface whose speed and IP the dashboard reports is **detected, not hardcoded** — `get_primary_interface()` in `utils/network_utils.py` parses `/proc/net/route` and picks the interface owning the default route with the **lowest metric**. The Pi has both onboard wifi (`wlan0`) and a USB WiFi 6 dongle (`wlan1`); both hold a default route and both have an IP, so a hardcoded `wlan0` reported the wrong NIC's throughput and address once the dongle (metric 50 vs 700) took over the traffic. `network_speed_monitor()` re-detects every `NETWORK_INTERFACE_RECHECK_INTERVAL` (5s) and writes the name into `network_stats_cache['network_interface']`, which is the single source of truth — `get_system_stats()` reads it for the IP lookup so the address always matches the reported speeds. Both counter samples in a loop iteration use the same interface, so a mid-loop switch can't yield a bogus delta. `app_state.NETWORK_INTERFACE_FALLBACK` ('wlan0') is used only when there is no default route (offline / link down), and seeds the cache at import time — **detection can't live in `app_state`**, since importing `utils.network_utils` there pulls in `utils/__init__` → `utils/server_config.py` → back into the partially-initialized `app_state`. Parsing procfs directly (rather than shelling out to `ip route`) keeps this subprocess-free and cheap enough to poll.

**Subprocess Execution (tpool)**: All subprocess calls MUST go through `utils.subprocess_helper.run()` instead of `subprocess.run()` directly. Under eventlet, `subprocess.run()` blocks the green thread event loop because Python 3.10+ subprocess uses `selectors.EpollSelector` internally, which eventlet doesn't fully monkey-patch. The helper wraps calls in `eventlet.tpool.execute()` so they run in real OS threads and the event loop stays responsive. In debug mode (no eventlet), it falls back to plain `subprocess.run()`. This is critical — without it, any slow subprocess call (e.g. `systemctl stop tailscaled` taking several seconds) will freeze the entire webserver, blocking all HTTP requests and WebSocket broadcasts.

**Remote Machine Management**: Remote machines (e.g., PCs controlled via smart plugs + SSH) are configured in `config/remote_machine_config.json` with local overrides. They appear as service-style cards rendered under the **Devices** section, inside a "Remote Machines" group (`renderRemoteMachines()` appends into `#devices-section`; `init()` clears that section once, then renders remote machines *before* the device tiles so their group comes first) with online/offline status (TCP port 22 check) and power toggle (Kasa smart plug + SSH shutdown). Status is broadcast via the same `service_status` WebSocket event with `rm_` prefixed IDs. Each `rm_*` entry also carries a `watts` field — the machine's live smart-plug draw, rendered in the card as `ONLINE (25.6 W)` / `OFFLINE (0.0 W)` (shown in both states; omitted entirely when the machine has no plug configured or no reading has landed yet). Wattage comes from a Kasa CLI call (`read_plug_wattage()`, a subprocess taking ~1s per plug), so `_remote_machine_poller()` reads it on its own slower cadence (`_WATTAGE_POLL_INTERVAL`, 15s) instead of every 3s alongside the cheap TCP online check — meaning the wattage figure can lag the online state by up to ~15s. The `createServiceCard()` function accepts optional `{onToggle, onDetails}` callbacks to customize behavior for remote machines vs. systemd services. Each machine has a `shell_type` config (`linux`, `wsl`, or `cmd`; default `linux`) that controls how SSH commands are sent — WSL requires piping commands via stdin because `wsl.exe` doesn't accept the `-c` flag SSH uses.

**Chart Query Performance**: `query_range()` in `timeseries/db.py` downsamples in two stages, because materializing a whole range in Python made `max_datapoints` cap the *response* but not the *work* — a 30-day window cost the same whether you asked for 100 points or 10,000. Stage 1 buckets inside SQLite (`GROUP BY cast((timestamp-start)/width AS INT)`), emitting each bucket's **min and max** so spikes survive — a per-bucket average silently clips them (measured: a 458.9 W peak on `r16_wattage` read as 378.9 W). Extreme *values* are exact; each is paired with the bucket's first/last timestamp, so x-position can be off by at most one bucket width (~0.1 px at `_BUCKET_OVERSAMPLE = 4`). Stage 2 is the existing LTTB pass, now over a few thousand candidates. `algorithm='average'` uses per-bucket means instead, matching its requested semantics.

Bucketing is gated by `_bucketing_pays()`: aggregation costs several times more per row than a plain index scan, so it only wins when it discards most of the range. Counting the range would cost as much as the query being avoided, so cadence is estimated from a 100-row sample and extrapolated (a short sample means the range is genuinely small, so the count is exact). **Without this gate the default `max_datapoints=10000` got slower**, since 40,000 buckets exceeded the ~30,000 rows a series holds over 30 days — every bucket held ≤1 row, paying `GROUP BY` cost for zero reduction.

The index is `idx_ts_covering (timeseries_id, timestamp, value)`. Including `value` makes it *covering*, so range queries never touch the table; previously each of ~1.3M index hits needed a separate row lookup (3.74s → 1.60s on a 30-day range). It replaced `idx_timeseries_timestamp`, which duplicated the implicit index behind `UNIQUE(timeseries_id, timestamp)` and only cost disk and write throughput. `_init_db()` creates the covering index and drops the old one, so both are applied on startup. Note `_init_db()` runs from `TimeseriesDB.__init__`, and `timeseries/__init__.py` imports `.routes` which instantiates it at module level — so *importing the package with the repo as cwd mutates the live `timeseries.db`*.

Net effect (43 series): 30-day at `max_datapoints=2000` went 6.78s → 2.75s, 7-day at 10,000 went 2.15s → 1.66s. The charts-page default `maxDatapoints` was lowered 10000 → 2000 in `static/charts.js` (~2x the pixel width of a typical chart; 10,000 also made the browser render 262k points). **A saved localStorage value overrides the default**, so existing browsers keep whatever is in Settings.

**Chart Configuration**: The charts page (`/charts`) uses user-defined chart configs instead of auto-grouping by units. Each chart has a name, a list of series IDs, and a `nameManuallySet` flag. Configs are stored in localStorage as `chartConfigs` (array of `{id, name, seriesIds, nameManuallySet}`). A "Manage Charts" modal lets users create/rename/delete charts and search+add series to each. The same series can appear in multiple charts. Default chart names are auto-generated from shared units or category of contained series.

### WebSocket Events

- `system_stats` - Pushed every 2s with CPU, RAM, disk, network stats
- `service_status` - Pushed every 5s with service running states (includes remote machine status with `rm_` prefix)
- `device_status` - Pushed every 2s with device status (BluOS players, etc.): state, track, volume, seek position, album art URL, online flag
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
