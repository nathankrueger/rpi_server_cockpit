"""Internet connectivity monitoring background thread."""
import time

from app_state import (
    internet_status_cache,
    internet_status_lock,
    server_config_lock,
)
import app_state
from utils import check_internet_connectivity


def internet_connectivity_monitor():
    """Background thread that checks internet connectivity independently."""
    print("Internet connectivity monitor started")

    while True:
        try:
            connected = check_internet_connectivity()
            with internet_status_lock:
                internet_status_cache['connected'] = connected
        except Exception as e:
            print(f"Error in internet connectivity monitor: {e}")
        # Read interval from config each iteration (allows runtime changes)
        with server_config_lock:
            interval = app_state.server_config['internet_check_interval']
        time.sleep(interval)
