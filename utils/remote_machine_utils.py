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


def check_machine_online(host, port=22, timeout=0.8, retries=2, retry_delay=0.2):
    """Check if a remote machine is online via TCP connect to its SSH port.

    Retries on failure to avoid flaky offline blips.
    Total worst-case time: ~2.8s (3 * 0.8s timeout + 2 * 0.2s delay).
    """
    for attempt in range(1 + retries):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True
        except Exception:
            pass
        if attempt < retries:
            time.sleep(retry_delay)
    return False


def ssh_shutdown(host, user, shutdown_command, port=22, ssh_key=None,
                 timeout=10, shell_type='linux'):
    """Send a shutdown command to a remote machine via SSH.

    Args:
        shell_type: 'linux' (default), 'wsl', or 'cmd'. WSL requires piping
            the command via stdin because wsl.exe doesn't accept the -c flag
            that SSH uses to pass commands.

    Returns (success: bool, error_message: str).
    """
    if shell_type == 'wsl' and timeout < 30:
        timeout = 30

    cmd = [
        'ssh',
        '-o', 'StrictHostKeyChecking=accept-new',
        '-o', 'ConnectTimeout=5',
        '-o', 'BatchMode=yes',
        '-p', str(port),
    ]
    if ssh_key:
        cmd.extend(['-i', ssh_key])

    run_kwargs = dict(capture_output=True, text=True, timeout=timeout)

    if shell_type == 'wsl':
        # wsl.exe doesn't accept -c, so pipe the command via stdin instead
        cmd.extend(['-T', f'{user}@{host}'])
        run_kwargs['input'] = shutdown_command + '\nexit\n'
    else:
        cmd.extend([f'{user}@{host}', shutdown_command])

    try:
        result = _run(cmd, **run_kwargs)
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

    action_flags = {'on': '--on', 'off': '--off', 'read': '--read_state', 'wattage': '--wattage'}
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


def read_plug_wattage(plug_name=None, plug_ip=None):
    """Read current power consumption from a Kasa smart plug.

    Returns wattage as a float, or None on failure.
    """
    success, output = control_kasa_plug('wattage', plug_name=plug_name, plug_ip=plug_ip)
    if success:
        try:
            return float(output.strip())
        except (ValueError, TypeError):
            return None
    return None


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


def wait_for_power_idle(plug_name=None, plug_ip=None, threshold=5.0,
                        timeout=120, poll_interval=5, progress_fn=None):
    """Poll plug wattage until it drops below threshold (PC fully off).

    Args:
        threshold: Watts below which the PC is considered fully powered down.
        timeout: Maximum seconds to wait.
        poll_interval: Seconds between wattage reads.
        progress_fn: Optional callback(message) for status updates.

    Returns True if power dropped below threshold within the timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        watts = read_plug_wattage(plug_name=plug_name, plug_ip=plug_ip)
        elapsed = int(time.time() - start)
        if watts is not None:
            if progress_fn:
                progress_fn(f'POWER: {watts:.1f}W ({elapsed}s)')
            if watts < threshold:
                return True
        else:
            if progress_fn:
                progress_fn(f'POWER: READ FAILED ({elapsed}s)')
        time.sleep(poll_interval)
    return False
