"""Network speed monitoring background thread."""
import time

import psutil

from app_state import (
    NETWORK_INTERFACE_FALLBACK,
    NETWORK_INTERFACE_RECHECK_INTERVAL,
    NETWORK_MONITOR_INTERVAL,
    network_stats_cache,
    network_stats_lock,
)
from utils.network_utils import get_primary_interface


def network_speed_monitor():
    """Background thread that continuously monitors network speed.
    Updates the network_stats_cache every NETWORK_MONITOR_INTERVAL seconds.

    The monitored interface is re-detected periodically so the dashboard follows
    the interface actually carrying traffic (e.g. a USB wifi dongle taking over
    from onboard wifi) instead of a hardcoded name.
    """
    print(f"Network speed monitor started (interval: {NETWORK_MONITOR_INTERVAL}s)")

    interface = None
    last_interface_check = 0.0

    while True:
        try:
            now = time.time()
            if now - last_interface_check >= NETWORK_INTERFACE_RECHECK_INTERVAL:
                last_interface_check = now
                detected = get_primary_interface(interface or NETWORK_INTERFACE_FALLBACK)
                if detected != interface:
                    if interface is not None:
                        print(f"Primary network interface changed: {interface} -> {detected}")
                    interface = detected
                    with network_stats_lock:
                        network_stats_cache['network_interface'] = interface

            # Sample the same interface at both ends so a mid-loop switch can't
            # produce a bogus delta.
            net_io_start = psutil.net_io_counters(pernic=True).get(interface)
            if net_io_start:
                time.sleep(NETWORK_MONITOR_INTERVAL)
                net_io_end = psutil.net_io_counters(pernic=True).get(interface)

                # Calculate bytes per interval
                upload_bytes = net_io_end.bytes_sent - net_io_start.bytes_sent
                download_bytes = net_io_end.bytes_recv - net_io_start.bytes_recv

                # Convert to Mbps (bytes per interval -> bytes per second -> Mbps)
                upload_mbps = f'{(upload_bytes / NETWORK_MONITOR_INTERVAL) * 8 / (1024**2):0.2f}'
                download_mbps = f'{(download_bytes / NETWORK_MONITOR_INTERVAL) * 8 / (1024**2):0.2f}'

                # Update cache with thread safety
                with network_stats_lock:
                    network_stats_cache['upload_mbps'] = upload_mbps
                    network_stats_cache['download_mbps'] = download_mbps
                    network_stats_cache['last_update'] = time.time()
            else:
                # Interface not found, sleep and retry
                time.sleep(NETWORK_MONITOR_INTERVAL)
        except Exception as e:
            print(f"Error in network speed monitor: {e}")
            time.sleep(NETWORK_MONITOR_INTERVAL)
