"""Remote machine status checking and power control utilities."""
import os
import socket
import time

from utils.subprocess_helper import run as _run


def resolve_host(machine_config):
    """Resolve a remote machine's host, handling 'auto' via announced IPs.

    Returns the IP string, or None if 'auto' and no IP has been announced.
    """
    host = machine_config.get('host')
    if host == 'auto':
        from app_state import announced_ips, announced_ips_lock
        with announced_ips_lock:
            return announced_ips.get(machine_config['id'])
    return host


def check_machine_online(host, port=22, timeout=2):
    """Check if a remote machine is online via TCP connect to its SSH port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def ssh_shutdown(host, user, shutdown_command, port=22, ssh_key=None, timeout=10):
    """Send a shutdown command to a remote machine via SSH.

    Returns (success: bool, error_message: str).
    """
    cmd = [
        'ssh',
        '-o', 'StrictHostKeyChecking=accept-new',
        '-o', 'ConnectTimeout=5',
        '-o', 'BatchMode=yes',
        '-p', str(port),
    ]
    if ssh_key:
        cmd.extend(['-i', ssh_key])
    cmd.extend([f'{user}@{host}', shutdown_command])

    try:
        result = _run(cmd, capture_output=True, text=True, timeout=timeout)
        # rc 255 is expected — SSH connection drops as the machine shuts down
        if result.returncode in (0, 255):
            return True, ''
        return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)


def control_kasa_plug(action, plug_name=None, plug_ip=None):
    """Control a Kasa smart plug via the existing kasa.sh script.

    Args:
        action: 'on', 'off', or 'read'
        plug_name: Device name for discovery-based lookup
        plug_ip: Direct IP address of the plug (preferred — faster)

    Returns (success: bool, output: str).
    """
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'automation_scripts', 'kasa.sh',
    )

    action_flags = {'on': '--on', 'off': '--off', 'read': '--read_state'}
    if action not in action_flags:
        return False, f'Invalid action: {action}'

    cmd = ['/bin/bash', script_path]

    if plug_ip:
        cmd.extend(['-i', plug_ip])
    elif plug_name:
        cmd.extend(['-n', plug_name])
    else:
        return False, 'No plug_name or plug_ip specified'

    cmd.append(action_flags[action])

    try:
        result = _run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def wait_for_offline(host, port=22, timeout=60, poll_interval=2):
    """Poll until the remote machine goes offline.

    Returns True if the machine went offline within the timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        if not check_machine_online(host, port):
            return True
        time.sleep(poll_interval)
    return False
