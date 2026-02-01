"""Background thread management."""
import threading

from .network_monitor import network_speed_monitor
from .system_broadcaster import system_stats_broadcaster
from .service_broadcaster import service_status_broadcaster
from .internet_monitor import internet_connectivity_monitor

_threads = []


def start_all_background_threads():
    """Start all background monitoring threads."""
    global _threads

    thread_configs = [
        ('Network Monitor', network_speed_monitor),
        ('System Stats Broadcaster', system_stats_broadcaster),
        ('Service Status Broadcaster', service_status_broadcaster),
        ('Internet Connectivity Monitor', internet_connectivity_monitor),
    ]

    for name, target in thread_configs:
        thread = threading.Thread(target=target, daemon=True, name=name)
        thread.start()
        _threads.append(thread)
        print(f"Started background thread: {name}")
