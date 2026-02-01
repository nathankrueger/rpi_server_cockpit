"""Network speed monitoring background thread."""
import time

import psutil

from app_state import (
    NETWORK_INTERFACE,
    NETWORK_MONITOR_INTERVAL,
    network_stats_cache,
    network_stats_lock,
)


def network_speed_monitor():
    """Background thread that continuously monitors network speed.
    Updates the network_stats_cache every NETWORK_MONITOR_INTERVAL seconds.
    """
    print(f"Network speed monitor started (interval: {NETWORK_MONITOR_INTERVAL}s)")

    while True:
        try:
            net_io_start = psutil.net_io_counters(pernic=True).get(NETWORK_INTERFACE)
            if net_io_start:
                time.sleep(NETWORK_MONITOR_INTERVAL)
                net_io_end = psutil.net_io_counters(pernic=True).get(NETWORK_INTERFACE)

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
