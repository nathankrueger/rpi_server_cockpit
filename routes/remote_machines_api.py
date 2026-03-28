"""Remote machine API routes for power control via smart plug + SSH."""
import threading
import time

from flask import Blueprint, jsonify, request

from config_loader import get_all_remote_machines, get_remote_machine_config
import app_state
from app_state import (
    remote_machine_operations,
    remote_machine_ops_lock,
    DEBUG_MODE,
    get_socketio,
)
from utils import (
    resolve_host,
    check_machine_online,
    ssh_shutdown,
    control_kasa_plug,
    wait_for_offline,
    wait_for_power_idle,
)

if not DEBUG_MODE:
    import eventlet

remote_machines_bp = Blueprint('remote_machines', __name__)


def _emit_progress(machine_id, message):
    """Emit a progress update for a remote machine operation."""
    socketio = get_socketio()
    if socketio:
        socketio.emit('remote_machine_progress', {
            'machine_id': machine_id,
            'message': message,
        }, namespace='/')


# --- Remote machine config/control endpoints ---

@remote_machines_bp.route('/api/remote_machines')
def get_machines():
    """Get all remote machine configurations (safe fields only)."""
    machines = get_all_remote_machines()
    result = []
    for m in machines:
        result.append({
            'id': m['id'],
            'display_name': m.get('display_name', m['id'].upper()),
            'group': m.get('group'),
            'link_url': m.get('link_url'),
            'type': 'remote_machine',
        })
    return jsonify(result)


@remote_machines_bp.route('/api/remote_machine/control/<machine_id>', methods=['POST'])
def control_machine(machine_id):
    """Control a remote machine (start/stop)."""
    data = request.get_json()
    action = data.get('action')

    if action not in ('start', 'stop'):
        return jsonify({'success': False, 'error': 'Invalid action'}), 400

    config = get_remote_machine_config(machine_id)
    if not config:
        return jsonify({'success': False, 'error': 'Unknown machine'}), 404

    # Prevent concurrent operations on the same machine
    with remote_machine_ops_lock:
        if machine_id in remote_machine_operations:
            return jsonify({
                'success': False,
                'error': f'Operation already in progress: {remote_machine_operations[machine_id]}',
            }), 409
        remote_machine_operations[machine_id] = 'starting' if action == 'start' else 'stopping'

    def do_start():
        try:
            plug_name = config.get('plug_name')
            plug_ip = config.get('plug_ip')

            # Power cycle: off → wait → on
            # If PC was shut down normally the plug is still on,
            # so just calling "on" would be a no-op. Cycling ensures boot.
            _emit_progress(machine_id, 'CYCLING POWER...')
            control_kasa_plug('off', plug_name=plug_name, plug_ip=plug_ip)
            time.sleep(3)

            success, output = control_kasa_plug('on', plug_name=plug_name, plug_ip=plug_ip)
            if success:
                _emit_progress(machine_id, 'PLUG ON — BOOTING...')
            else:
                print(f"Failed to turn on plug for {machine_id}: {output}")
                _emit_progress(machine_id, 'PLUG ON FAILED')
        finally:
            with remote_machine_ops_lock:
                remote_machine_operations.pop(machine_id, None)

    def do_stop():
        try:
            host = resolve_host(config)
            if not host:
                print(f"Cannot stop {machine_id}: no host configured")
                _emit_progress(machine_id, 'NO HOST — CANNOT SHUTDOWN')
                return
            user = config['ssh_user']
            port = config.get('ssh_port', 22)
            ssh_key = config.get('ssh_key')
            shutdown_cmd = config.get('shutdown_command', 'shutdown.exe /s /t 0')
            shell_type = config.get('shell_type', 'linux')
            timeout = config.get('shutdown_timeout', 60)
            plug_name = config.get('plug_name')
            plug_ip = config.get('plug_ip')

            # Step 1: Graceful shutdown via SSH
            _emit_progress(machine_id, 'SENDING SHUTDOWN...')
            success, error = ssh_shutdown(host, user, shutdown_cmd, port, ssh_key,
                                          shell_type=shell_type)
            if not success:
                print(f"SSH shutdown failed for {machine_id}: {error}")
                _emit_progress(machine_id, 'SSH FAILED — WAITING...')

            # Step 2: Wait for SSH port to close (machine shutting down)
            _emit_progress(machine_id, 'WAITING FOR SHUTDOWN...')
            wait_for_offline(host, port, timeout)

            # Step 3: Wait for power draw to drop (safe to cut power)
            # This prevents cutting power during Windows updates etc.
            _emit_progress(machine_id, 'MONITORING POWER...')
            power_idle = wait_for_power_idle(
                plug_name=plug_name, plug_ip=plug_ip,
                threshold=5.0, timeout=120, poll_interval=5,
                progress_fn=lambda msg: _emit_progress(machine_id, msg),
            )

            if not power_idle:
                # PC is still drawing significant power — do NOT cut it
                print(f"Machine {machine_id} still drawing power after timeout, "
                      f"refusing to cut plug (possible update in progress)")
                _emit_progress(machine_id, 'STILL DRAWING POWER — PLUG LEFT ON')
                return

            # Step 4: Power is idle, safe to turn off plug
            _emit_progress(machine_id, 'TURNING OFF PLUG...')
            success, output = control_kasa_plug('off', plug_name=plug_name, plug_ip=plug_ip)
            if success:
                _emit_progress(machine_id, 'OFFLINE')
            else:
                print(f"Failed to turn off plug for {machine_id}: {output}")
                _emit_progress(machine_id, 'PLUG OFF FAILED')
        finally:
            with remote_machine_ops_lock:
                remote_machine_operations.pop(machine_id, None)

    # Run in background
    target = do_start if action == 'start' else do_stop
    if DEBUG_MODE:
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
    else:
        eventlet.spawn(target)

    return jsonify({'success': True, 'message': f'{action} initiated for {machine_id}'})


@remote_machines_bp.route('/api/remote_machine/details/<machine_id>')
def get_machine_details(machine_id):
    """Get detailed status for a remote machine."""
    config = get_remote_machine_config(machine_id)
    if not config:
        return jsonify({'success': False, 'error': 'Unknown machine'}), 404

    host = resolve_host(config)
    port = config.get('ssh_port', 22)
    is_online = check_machine_online(host, port) if host else False

    with remote_machine_ops_lock:
        current_op = remote_machine_operations.get(machine_id)

    lines = [
        f"Remote Machine: {config.get('display_name', machine_id)}",
        f"Host: {host or 'NOT CONFIGURED'}:{port}",
        f"Status: {'ONLINE' if is_online else 'OFFLINE'}",
        f"SSH User: {config.get('ssh_user', 'N/A')}",
    ]
    if current_op:
        lines.append(f"Operation in progress: {current_op}")
    if config.get('plug_name'):
        lines.append(f"Smart Plug: {config['plug_name']}")
    if config.get('plug_ip'):
        lines.append(f"Smart Plug IP: {config['plug_ip']}")

    return jsonify({'success': True, 'output': '\n'.join(lines), 'service': machine_id})
