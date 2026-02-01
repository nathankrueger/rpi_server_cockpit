"""System statistics collection utilities."""
import socket
import subprocess
import time

import psutil

from app_state import DISK_MOUNT_POINT, NETWORK_INTERFACE, network_stats_lock, network_stats_cache

# Cache for uname result
_uname_cache = None


def get_uname() -> str:
    """Get kernel version string."""
    global _uname_cache
    if not _uname_cache:
        _uname_cache = subprocess.run(
            ['uname', '-r'],
            capture_output=True,
            text=True,
            timeout=2
        ).stdout.strip()
    return _uname_cache


def get_top_cpu_processes(n=5):
    """Get top N processes by CPU usage using ps command (non-blocking).

    Uses ps which gives a coherent snapshot of CPU usage across all processes.
    """
    try:
        # ps aux sorted by CPU, get top n+1 (skip header)
        result = subprocess.run(
            ['ps', '-eo', 'pid,pcpu,comm', '--sort=-pcpu', '--no-headers'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return []

        processes = []
        for line in result.stdout.strip().split('\n')[:n]:
            if not line.strip():
                continue
            parts = line.split(None, 2)  # Split into 3 parts max
            if len(parts) >= 3:
                pid, cpu, name = parts
                processes.append({
                    'name': name,
                    'pid': int(pid),
                    'cpu_percent': round(float(cpu), 1)
                })
        return processes
    except Exception as e:
        print(f"Error getting top CPU processes: {e}")
        return []


def get_system_stats():
    """Get CPU, RAM, disk, and network statistics."""
    stats = {}

    stats['uname'] = get_uname()

    # CPU Usage - overall and per-core (non-blocking)
    # interval=None returns CPU usage since last call (or since module import on first call)
    stats['cpu_percent'] = psutil.cpu_percent(interval=None)
    stats['cpu_per_core'] = psutil.cpu_percent(interval=None, percpu=True)

    # CPU Temperature (convert C to F)
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            cpu_temp_c = float(f.read().strip()) / 1000.0
            cpu_temp_f = (cpu_temp_c * 9/5) + 32
            stats['cpu_temp'] = round(cpu_temp_f, 1)
    except Exception as e:
        stats['cpu_temp'] = None
        print(f"Error reading CPU temperature: {e}")

    # GPU Temperature (convert C to F)
    try:
        result = subprocess.run(
            ['vcgencmd', 'measure_temp'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            # Parse output like "temp=46.6'C"
            temp_str = result.stdout.strip().split('=')[1].split("'")[0]
            gpu_temp_c = float(temp_str)
            gpu_temp_f = (gpu_temp_c * 9/5) + 32
            stats['gpu_temp'] = round(gpu_temp_f, 1)
        else:
            stats['gpu_temp'] = None
    except Exception as e:
        stats['gpu_temp'] = None
        print(f"Error reading GPU temperature: {e}")

    # RAM Usage
    ram = psutil.virtual_memory()
    stats['ram_percent'] = ram.percent
    stats['ram_used_gb'] = round(ram.used / (1024**3), 2)
    stats['ram_total_gb'] = round(ram.total / (1024**3), 2)

    # Disk Usage for specified mount point
    try:
        disk = psutil.disk_usage(DISK_MOUNT_POINT)
        stats['disk_percent'] = disk.percent
        stats['disk_free_gb'] = round(disk.free / (1024**3), 2)
        stats['disk_total_gb'] = round(disk.total / (1024**3), 2)
        stats['disk_mount'] = DISK_MOUNT_POINT
    except Exception as e:
        stats['disk_percent'] = 0
        stats['disk_free_gb'] = 0
        stats['disk_total_gb'] = 0
        stats['disk_mount'] = DISK_MOUNT_POINT
        print(f"Error reading disk stats: {e}")

    # Network Speed - read from cache (updated by background thread)
    with network_stats_lock:
        stats['upload_mbps'] = network_stats_cache['upload_mbps']
        stats['download_mbps'] = network_stats_cache['download_mbps']
        stats['network_interface'] = network_stats_cache['network_interface']

    # Get hostname and IP address
    try:
        stats['hostname'] = socket.gethostname()
        # Try to get IP for the specified interface
        addrs = psutil.net_if_addrs().get(NETWORK_INTERFACE, [])
        ipv4_addr = next((addr.address for addr in addrs if addr.family == socket.AF_INET), 'N/A')
        stats['ip_address'] = ipv4_addr
    except Exception as e:
        stats['hostname'] = 'Unknown'
        stats['ip_address'] = 'N/A'
        print(f"Error reading hostname/IP: {e}")

    # Get system uptime
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        stats['uptime'] = f"{days}d {hours}h {minutes}m"
    except Exception as e:
        stats['uptime'] = 'Unknown'
        print(f"Error reading uptime: {e}")

    # Get top CPU processes
    stats['top_cpu_processes'] = get_top_cpu_processes(5)

    return stats
