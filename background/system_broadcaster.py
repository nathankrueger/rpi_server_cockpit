"""System stats broadcasting background thread."""
import time

from app_state import (
    system_stats_cache,
    system_stats_lock,
    server_config_lock,
    get_socketio,
)
import app_state
from utils import get_system_stats


def system_stats_broadcaster():
    """Background thread that collects system stats and broadcasts to all clients."""
    print("System stats broadcaster started")

    while True:
        try:
            stats = get_system_stats()
            with system_stats_lock:
                system_stats_cache.update(stats)
            socketio = get_socketio()
            if socketio:
                socketio.emit('system_stats', stats, namespace='/')
        except Exception as e:
            print(f"Error in system stats broadcaster: {e}")
        # Read interval from config each iteration (allows runtime changes)
        with server_config_lock:
            interval = app_state.server_config['system_stats_interval']
        time.sleep(interval)
