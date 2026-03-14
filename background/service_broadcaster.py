"""Service status broadcasting background thread."""
import time
import threading
from concurrent.futures import ThreadPoolExecutor

from config_loader import get_all_services, get_all_remote_machines
from app_state import (
    service_status_cache,
    service_status_lock,
    internet_status_lock,
    internet_status_cache,
    server_config_lock,
    get_socketio,
)
import app_state
from utils import check_service_status, get_service_memory_usage, resolve_host, check_machine_online

# Latest remote machine statuses, written by the poller thread, read by broadcaster
_rm_status = {}
_rm_status_lock = threading.Lock()


def _remote_machine_poller():
    """Continuously poll remote machine status in a background thread."""
    pool = ThreadPoolExecutor(max_workers=4)
    while True:
        machines = get_all_remote_machines()
        futures = {}
        for machine in machines:
            host = resolve_host(machine)
            if host:
                futures[machine['id']] = pool.submit(
                    check_machine_online, host, machine.get('ssh_port', 22)
                )
            else:
                futures[machine['id']] = None

        results = {}
        for machine_id, future in futures.items():
            results[machine_id] = future.result() if future else False

        with _rm_status_lock:
            _rm_status.update(results)

        time.sleep(5)


def start_remote_machine_poller():
    """Start the remote machine poller daemon thread."""
    t = threading.Thread(target=_remote_machine_poller, daemon=True)
    t.start()


def service_status_broadcaster():
    """Background thread that checks service status and broadcasts to all clients."""
    print("Service status broadcaster started")

    while True:
        try:
            status = {}
            for service in get_all_services():
                is_running = check_service_status(service['service_name'])
                memory_bytes = get_service_memory_usage(service['service_name']) if is_running else None
                status[service['id']] = {
                    'running': is_running,
                    'memory_bytes': memory_bytes
                }

            # Read latest remote machine statuses (non-blocking)
            with _rm_status_lock:
                rm_snapshot = dict(_rm_status)
            for machine in get_all_remote_machines():
                mid = machine['id']
                status[f"rm_{mid}"] = {
                    'running': rm_snapshot.get(mid, False),
                    'memory_bytes': None,
                    'type': 'remote_machine',
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
