"""
Shared application state: caches, locks, constants.

This module centralizes all shared state to avoid circular imports.
Other modules import from here to access shared caches and locks.
"""
import os
import threading

from config_loader import get_all_automations

# Determine async mode based on environment
DEBUG_MODE = os.environ.get('DEBUG_MODE') == '1'

# Configuration constants
NETWORK_INTERFACE = 'wlan0'  # Network interface to monitor
DISK_MOUNT_POINT = '/'       # Disk mount point to monitor
NETWORK_MONITOR_INTERVAL = 0.1  # Network speed monitoring interval in seconds (100ms)

# Store automation state server-side - dynamically initialized from config
# Structure: {automation_name: {'job_id': str, 'running': bool, 'output': str, 'return_code': int, 'process': subprocess.Popen}}
automation_state = {
    auto['name']: {'job_id': None, 'running': False, 'output': '', 'return_code': None, 'process': None}
    for auto in get_all_automations()
}
automation_lock = threading.Lock()

# Cached network speed stats (updated by background thread)
network_stats_cache = {
    'upload_mbps': 0.0,
    'download_mbps': 0.0,
    'network_interface': NETWORK_INTERFACE,
    'last_update': None
}
network_stats_lock = threading.Lock()

# Cached system stats (updated by background thread, pushed via WebSocket)
system_stats_cache = {}
system_stats_lock = threading.Lock()

# Cached service status (updated by background thread, pushed via WebSocket)
service_status_cache = {}
service_status_lock = threading.Lock()

# Cached internet connectivity (updated by separate background thread)
internet_status_cache = {'connected': False}
internet_status_lock = threading.Lock()

# Server configuration (mutable at runtime via API, persisted to JSON file)
SERVER_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config', 'server_config.local.json')
SERVER_CONFIG_DEFAULTS = {
    'system_stats_interval': 2.0,  # seconds
    'service_status_interval': 5.0,  # seconds
    'internet_check_interval': 5.0,  # seconds
}

# Server config will be initialized by utils/server_config.py
server_config = None
server_config_lock = threading.Lock()

# SocketIO instance (set by main app, used by routes that need to emit)
_socketio = None


def set_socketio(sio):
    """Set the SocketIO instance for use by other modules."""
    global _socketio
    _socketio = sio


def get_socketio():
    """Get the SocketIO instance."""
    return _socketio
