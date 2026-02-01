"""Service status broadcasting background thread."""
import time

from config_loader import get_all_services
from app_state import (
    service_status_cache,
    service_status_lock,
    internet_status_lock,
    internet_status_cache,
    server_config_lock,
    get_socketio,
)
import app_state
from utils import check_service_status, check_process_running, get_service_memory_usage


def service_status_broadcaster():
    """Background thread that checks service status and broadcasts to all clients."""
    print("Service status broadcaster started")

    while True:
        try:
            status = {}
            for service in get_all_services():
                if service['check_type'] == 'systemd':
                    is_running = check_service_status(service['service_name'])
                    memory_bytes = get_service_memory_usage(service) if is_running else None
                    status[service['id']] = {
                        'running': is_running,
                        'memory_bytes': memory_bytes
                    }
                elif service['check_type'] == 'process':
                    is_running = check_process_running(service['service_name'])
                    memory_bytes = get_service_memory_usage(service) if is_running else None
                    status[service['id']] = {
                        'running': is_running,
                        'memory_bytes': memory_bytes
                    }

            # Add internet status from its own cache
            with internet_status_lock:
                status['internet'] = internet_status_cache['connected']

            with service_status_lock:
                service_status_cache.update(status)
            socketio = get_socketio()
            if socketio:
                socketio.emit('service_status', status, namespace='/')
        except Exception as e:
            print(f"Error in service status broadcaster: {e}")
        # Read interval from config each iteration (allows runtime changes)
        with server_config_lock:
            interval = app_state.server_config['service_status_interval']
        time.sleep(interval)
