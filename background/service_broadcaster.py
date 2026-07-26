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
from utils import (
    check_service_status,
    get_service_memory_usage,
    resolve_host,
    check_machine_online,
    read_plug_wattage,
)

# Latest remote machine statuses, written by the poller thread, read by broadcaster
_rm_status = {}
_rm_status_lock = threading.Lock()

# Latest smart-plug wattage readings, keyed by machine id (None = no reading)
_rm_watts = {}
_rm_watts_lock = threading.Lock()

# Wattage comes from a Kasa CLI call (a subprocess, seconds per read), so it's
# polled far less often than the cheap TCP online check.
_WATTAGE_POLL_INTERVAL = 15


def _poll_wattage(pool, machines):
    """Read plug wattage for every machine that has a plug configured."""
    futures = {}
    for machine in machines:
        plug_name = machine.get('plug_name')
        plug_ip = machine.get('plug_ip')
        if plug_name or plug_ip:
            futures[machine['id']] = pool.submit(
                read_plug_wattage, plug_name=plug_name, plug_ip=plug_ip,
            )

    results = {}
    for machine_id, future in futures.items():
        try:
            results[machine_id] = future.result(timeout=35)
        except Exception:
            results[machine_id] = None

    if results:
        with _rm_watts_lock:
            _rm_watts.update(results)


def _remote_machine_poller():
    """Continuously poll remote machine status in a background thread.

    Uses reduced retries (1 instead of 2) since we poll frequently —
    a missed blip will be caught on the next cycle.
    """
    pool = ThreadPoolExecutor(max_workers=4)
    last_wattage_poll = 0.0
    while True:
        try:
            machines = get_all_remote_machines()
            futures = {}
            for machine in machines:
                host = resolve_host(machine)
                if host:
                    futures[machine['id']] = pool.submit(
                        check_machine_online, host, machine.get('ssh_port', 22),
                        retries=1, retry_delay=0.15,
                    )
                else:
                    futures[machine['id']] = None

            results = {}
            for machine_id, future in futures.items():
                try:
                    results[machine_id] = future.result(timeout=5) if future else False
                except Exception:
                    results[machine_id] = False

            with _rm_status_lock:
                _rm_status.update(results)

            # Wattage on its own slower cadence so the online check stays snappy
            if time.time() - last_wattage_poll >= _WATTAGE_POLL_INTERVAL:
                last_wattage_poll = time.time()
                _poll_wattage(pool, machines)
        except Exception as e:
            print(f"Error in remote machine poller: {e}")

        time.sleep(3)


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
            with _rm_watts_lock:
                watts_snapshot = dict(_rm_watts)
            for machine in get_all_remote_machines():
                mid = machine['id']
                status[f"rm_{mid}"] = {
                    'running': rm_snapshot.get(mid, False),
                    'memory_bytes': None,
                    'type': 'remote_machine',
                    'watts': watts_snapshot.get(mid),
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
