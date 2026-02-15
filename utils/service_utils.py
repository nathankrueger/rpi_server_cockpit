"""Service status checking and control utilities."""
import os
import time

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


def check_process_running(process_name):
    """Check if a process is running by name."""
    try:
        result = _run(
            ['pgrep', '-x', process_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error checking process {process_name}: {e}")
        return False


def get_service_memory_usage(service_config):
    """Get memory usage (RSS) in bytes for a service, including child processes.

    Args:
        service_config: Service configuration dict with 'check_type' and 'service_name'

    Returns:
        int: Memory usage in bytes, or None if service is not running or can't be determined
    """
    try:
        if service_config['check_type'] == 'systemd':
            # Get main PID from systemd
            service_name = service_config['service_name']
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

            # Get process and sum memory with children
            try:
                main_process = psutil.Process(main_pid)
                total_memory = main_process.memory_info().rss

                # Add memory from all child processes
                children = main_process.children(recursive=True)
                for child in children:
                    try:
                        total_memory += child.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                return total_memory
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return None

        elif service_config['check_type'] == 'process':
            # Find all processes matching the name and sum their memory
            process_name = service_config['service_name']
            total_memory = 0
            found_process = False

            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] == process_name:
                        found_process = True
                        process = psutil.Process(proc.info['pid'])
                        total_memory += process.memory_info().rss

                        # Add memory from all child processes
                        children = process.children(recursive=True)
                        for child in children:
                            try:
                                total_memory += child.memory_info().rss
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                continue
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            return total_memory if found_process else None
        else:
            return None
    except Exception as e:
        print(f"Error getting memory usage for service {service_config.get('id', 'unknown')}: {e}")
        return None


def control_service(service_name, action, on_start_callback=None, on_stop_callback=None):
    """Start or stop a systemd service."""
    try:
        result = _run(
            ['sudo', 'systemctl', action, service_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        success = result.returncode == 0

        # Trigger callbacks
        if success:
            if action == 'start' and on_start_callback:
                on_start_callback(service_name)
            elif action == 'stop' and on_stop_callback:
                on_stop_callback(service_name)

        return success, result.stderr if not success else ''
    except Exception as e:
        return False, str(e)


def control_process(process_name, action, on_start_callback=None, on_stop_callback=None):
    """Start or stop a process by name."""
    try:
        if action == 'start':
            # Check if process is already running
            if check_process_running(process_name):
                return True, 'Process is already running'

            # Use daemon helper script to properly detach the process
            # This ensures the process survives when the web server restarts
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            daemon_helper = os.path.join(script_dir, 'daemon_helper.sh')

            result = _run(
                [daemon_helper, process_name],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return False, f"Failed to start process: {result.stderr}"

            # Give the process a moment to start
            time.sleep(0.5)

            # Verify it started
            if not check_process_running(process_name):
                return False, "Process failed to start"

            if on_start_callback:
                on_start_callback(process_name)
            return True, ''
        elif action == 'stop':
            # Check if process is running before trying to stop it
            if not check_process_running(process_name):
                return True, 'Process is not running'

            result = _run(
                ['pkill', '-x', process_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            if on_stop_callback:
                on_stop_callback(process_name)
            return True, ''
    except Exception as e:
        return False, str(e)
