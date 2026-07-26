"""Device status broadcasting background thread.

Polls every configured device (BluOS players, etc.) by dispatching on its
`type`, caches the result, and pushes it to all clients over the `device_status`
WebSocket event. One offline/erroring device is reported as offline without
killing the loop.
"""
import time

from config_loader import get_all_devices
from app_state import (
    device_status_cache,
    device_status_lock,
    server_config_lock,
    get_socketio,
)
import app_state
from utils.device_types import get_status_for


def device_status_broadcaster():
    """Background thread that polls devices and broadcasts to all clients."""
    print("Device status broadcaster started")

    while True:
        try:
            status = {}
            for device in get_all_devices():
                device_id = device['id']
                try:
                    info = get_status_for(device)
                    info['online'] = True
                    status[device_id] = info
                except Exception as e:
                    status[device_id] = {'online': False, 'error': str(e)}

            with device_status_lock:
                device_status_cache.update(status)
            socketio = get_socketio()
            if socketio:
                socketio.emit('device_status', status, namespace='/')
        except Exception as e:
            print(f"Error in device status broadcaster: {e}")
        # Read interval from config each iteration (allows runtime changes)
        with server_config_lock:
            interval = app_state.server_config['device_status_interval']
        time.sleep(interval)
