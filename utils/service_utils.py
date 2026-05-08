"""Service status checking and control utilities."""
import psutil

from utils.subprocess_helper import run as _run


def check_service_status(service_name):
    """Check if a systemd service is active."""
    try:
        result = _run(
            ['systemctl', 'is-active', service_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.stdout.strip() == 'active'
    except Exception as e:
        print(f"Error checking {service_name}: {e}")
        return False


def get_service_memory_usage(service_name):
    """Get memory usage (RSS) in bytes for a systemd service, including child processes.

    Args:
        service_name: The systemd service unit name

    Returns:
        int: Memory usage in bytes, or None if service is not running or can't be determined
    """
    try:
        result = _run(
            ['systemctl', 'show', '-p', 'MainPID', service_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return None

        main_pid_str = result.stdout.strip().split('=')[1]
        if not main_pid_str or main_pid_str == '0':
            return None

        main_pid = int(main_pid_str)
        if main_pid == 0:
            return None

        try:
            main_process = psutil.Process(main_pid)
            total_memory = main_process.memory_info().rss

            for child in main_process.children(recursive=True):
                try:
                    total_memory += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return total_memory
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    except Exception as e:
        print(f"Error getting memory usage for {service_name}: {e}")
        return None


def control_service(service_name, action, on_start_callback=None, on_stop_callback=None):
    """Start or stop a systemd service."""
    try:
        result = _run(
            ['sudo', 'systemctl', action, service_name],
            capture_output=True,
            text=True,
            timeout=30
        )
        success = result.returncode == 0

        if success:
            if action == 'start' and on_start_callback:
                on_start_callback(service_name)
            elif action == 'stop' and on_stop_callback:
                on_stop_callback(service_name)

        return success, result.stderr if not success else ''
    except Exception as e:
        return False, str(e)
