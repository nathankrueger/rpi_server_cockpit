from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import subprocess
import socket
import psutil
import time
import threading
import uuid
import os
import eventlet
from datetime import datetime, timedelta
import shlex
import json
import urllib.request
import urllib.parse
import urllib.error

from config_loader import get_all_automations, get_automation_config, get_all_services, get_service_config
from process_mgmt import kill_proc_tree

# Determine async mode based on environment
DEBUG_MODE = os.environ.get('DEBUG_MODE') == '1'

# Modifies Python's standard libraries to use non-blocking, cooperative I/O (greenthreads), allowing the application to handle many
# simultaneous connections efficiently without using traditional threads.
# Only monkey patch when not in debug mode to avoid conflicts with debugpy
if not DEBUG_MODE:
    eventlet.monkey_patch()

app = Flask(__name__)
# Generate a random secret key on startup for Flask session management
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())

# Register timeseries blueprint
from timeseries_routes import timeseries_bp
app.register_blueprint(timeseries_bp)

# Use threading mode for debugging, eventlet for production
async_mode = 'threading' if DEBUG_MODE else 'eventlet'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)

# Configuration constants - CHANGE THESE AS NEEDED
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

def load_server_config():
    """Load server config from JSON file, creating with defaults if missing."""
    config = SERVER_CONFIG_DEFAULTS.copy()
    try:
        if os.path.exists(SERVER_CONFIG_FILE):
            with open(SERVER_CONFIG_FILE, 'r') as f:
                loaded = json.load(f)
                # Only use valid keys from the file
                for key in SERVER_CONFIG_DEFAULTS:
                    if key in loaded:
                        config[key] = float(loaded[key])
            print(f"Loaded server config from {SERVER_CONFIG_FILE}")
        else:
            # Create config file with defaults
            save_server_config(config)
            print(f"Created server config file with defaults at {SERVER_CONFIG_FILE}")
    except Exception as e:
        print(f"Error loading server config: {e}, using defaults")
    return config

def save_server_config(config):
    """Save server config to JSON file."""
    try:
        with open(SERVER_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"Saved server config to {SERVER_CONFIG_FILE}")
        return True
    except Exception as e:
        print(f"Error saving server config: {e}")
        return False

server_config = load_server_config()
server_config_lock = threading.Lock()

uname_cache = None

def broadcast_automation_state(automation_name, incremental_output=None):
    """Broadcast automation state to all connected clients.
    Note: This should be called WITHOUT holding automation_lock.

    Args:
        automation_name: Name of the automation
        incremental_output: If provided, only send this new output (not full output)
    """
    with automation_lock:
        state = automation_state[automation_name].copy()
        # Don't send the process object to clients
        state.pop('process', None)

        # If incremental output is provided, replace full output with just the increment
        if incremental_output is not None:
            state['output'] = incremental_output
            state['incremental'] = True
        else:
            state['incremental'] = False

    # Emit outside the lock to avoid blocking
    try:
        socketio.emit('automation_update', {
            'automation': automation_name,
            'state': state
        }, namespace='/')
    except Exception as e:
        print(f"Error broadcasting state for {automation_name}: {e}")

# Optional callbacks for service control actions
def on_service_start(service_name):
    """Called when a service is started. Add your LED control here."""
    print(f"Service started: {service_name}")
    # Example: control_led(service_name, 'green')
    pass

def on_service_stop(service_name):
    """Called when a service is stopped. Add your LED control here."""
    print(f"Service stopped: {service_name}")
    # Example: control_led(service_name, 'red')
    pass

def check_service_status(service_name):
    """Check if a systemd service is active."""
    try:
        result = subprocess.run(
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
        result = subprocess.run(
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
            result = subprocess.run(
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
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
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

def check_internet_connectivity():
    """Check internet connectivity by pinging google.com, fallback to amazon.com."""
    hosts = ['8.8.8.8', '1.1.1.1']  # Google DNS and Cloudflare DNS

    for host in hosts:
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-W', '2', host],
                capture_output=True,
                timeout=3
            )
            if result.returncode == 0:
                return True
        except Exception:
            continue
    return False

def network_speed_monitor():
    """Background thread that continuously monitors network speed.
    Updates the network_stats_cache every NETWORK_MONITOR_INTERVAL seconds.
    """
    print(f"Network speed monitor started (interval: {NETWORK_MONITOR_INTERVAL}s)")

    while True:
        try:
            net_io_start = psutil.net_io_counters(pernic=True).get(NETWORK_INTERFACE)
            if net_io_start:
                time.sleep(NETWORK_MONITOR_INTERVAL)
                net_io_end = psutil.net_io_counters(pernic=True).get(NETWORK_INTERFACE)

                # Calculate bytes per interval
                upload_bytes = net_io_end.bytes_sent - net_io_start.bytes_sent
                download_bytes = net_io_end.bytes_recv - net_io_start.bytes_recv

                # Convert to Mbps (bytes per interval -> bytes per second -> Mbps)
                upload_mbps = f'{(upload_bytes / NETWORK_MONITOR_INTERVAL) * 8 / (1024**2):0.2f}'
                download_mbps = f'{(download_bytes / NETWORK_MONITOR_INTERVAL) * 8 / (1024**2):0.2f}'

                # Update cache with thread safety
                with network_stats_lock:
                    network_stats_cache['upload_mbps'] = upload_mbps
                    network_stats_cache['download_mbps'] = download_mbps
                    network_stats_cache['last_update'] = time.time()
            else:
                # Interface not found, sleep and retry
                time.sleep(NETWORK_MONITOR_INTERVAL)
        except Exception as e:
            print(f"Error in network speed monitor: {e}")
            time.sleep(NETWORK_MONITOR_INTERVAL)

def system_stats_broadcaster():
    """Background thread that collects system stats and broadcasts to all clients."""
    print("System stats broadcaster started")

    while True:
        try:
            stats = get_system_stats()
            with system_stats_lock:
                system_stats_cache.update(stats)
            socketio.emit('system_stats', stats, namespace='/')
        except Exception as e:
            print(f"Error in system stats broadcaster: {e}")
        # Read interval from config each iteration (allows runtime changes)
        with server_config_lock:
            interval = server_config['system_stats_interval']
        time.sleep(interval)

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
            socketio.emit('service_status', status, namespace='/')
        except Exception as e:
            print(f"Error in service status broadcaster: {e}")
        # Read interval from config each iteration (allows runtime changes)
        with server_config_lock:
            interval = server_config['service_status_interval']
        time.sleep(interval)

def internet_connectivity_monitor():
    """Background thread that checks internet connectivity independently."""
    print("Internet connectivity monitor started")

    while True:
        try:
            connected = check_internet_connectivity()
            with internet_status_lock:
                internet_status_cache['connected'] = connected
        except Exception as e:
            print(f"Error in internet connectivity monitor: {e}")
        # Read interval from config each iteration (allows runtime changes)
        with server_config_lock:
            interval = server_config['internet_check_interval']
        time.sleep(interval)

def get_uname() -> str:
    global uname_cache
    if not uname_cache:
        uname_cache = subprocess.run(
            ['uname', '-r'],
            capture_output=True,
            text=True,
            timeout=2
        ).stdout.strip()
    return uname_cache

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

def control_service(service_name, action):
    """Start or stop a systemd service."""
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', action, service_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        success = result.returncode == 0
        
        # Trigger callbacks
        if success:
            if action == 'start':
                on_service_start(service_name)
            elif action == 'stop':
                on_service_stop(service_name)
        
        return success, result.stderr if not success else ''
    except Exception as e:
        return False, str(e)

def control_process(process_name, action):
    """Start or stop a process by name."""
    try:
        if action == 'start':
            # Check if process is already running
            if check_process_running(process_name):
                return True, 'Process is already running'

            # Use daemon helper script to properly detach the process
            # This ensures the process survives when the web server restarts
            script_dir = os.path.dirname(os.path.abspath(__file__))
            daemon_helper = os.path.join(script_dir, 'daemon_helper.sh')

            result = subprocess.run(
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
                return False, f"Process failed to start"

            on_service_start(process_name)
            return True, ''
        elif action == 'stop':
            # Check if process is running before trying to stop it
            if not check_process_running(process_name):
                return True, 'Process is not running'

            result = subprocess.run(
                ['pkill', '-x', process_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            on_service_stop(process_name)
            return True, ''
    except Exception as e:
        return False, str(e)

@app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('index.html')

@app.route('/monitor')
def monitor():
    """Serve the system monitor page."""
    return render_template('monitor.html')

@app.route('/api/services')
def get_services():
    """Get all service configurations."""
    return jsonify(get_all_services())

@app.route('/api/status')
def get_status():
    """Get status of all services and connectivity (returns cached data)."""
    with service_status_lock:
        return jsonify(service_status_cache.copy())

@app.route('/api/system')
def get_system():
    """Get system statistics (returns cached data)."""
    with system_stats_lock:
        return jsonify(system_stats_cache.copy())

@app.route('/api/server_config', methods=['GET'])
def get_server_config():
    """Get current server configuration."""
    with server_config_lock:
        return jsonify(server_config.copy())

@app.route('/api/server_config', methods=['POST'])
def set_server_config():
    """Update server configuration."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    updated = {}
    with server_config_lock:
        # Validate and update system_stats_interval
        if 'system_stats_interval' in data:
            val = data['system_stats_interval']
            if isinstance(val, (int, float)) and 0.1 <= val <= 60:
                server_config['system_stats_interval'] = float(val)
                updated['system_stats_interval'] = float(val)
            else:
                return jsonify({'success': False, 'error': 'system_stats_interval must be between 0.1 and 60 seconds'}), 400

        # Validate and update service_status_interval
        if 'service_status_interval' in data:
            val = data['service_status_interval']
            if isinstance(val, (int, float)) and 1 <= val <= 300:
                server_config['service_status_interval'] = float(val)
                updated['service_status_interval'] = float(val)
            else:
                return jsonify({'success': False, 'error': 'service_status_interval must be between 1 and 300 seconds'}), 400

        # Validate and update internet_check_interval
        if 'internet_check_interval' in data:
            val = data['internet_check_interval']
            if isinstance(val, (int, float)) and 1 <= val <= 300:
                server_config['internet_check_interval'] = float(val)
                updated['internet_check_interval'] = float(val)
            else:
                return jsonify({'success': False, 'error': 'internet_check_interval must be between 1 and 300 seconds'}), 400

        # Persist to file if any changes were made
        if updated:
            save_server_config(server_config)

    return jsonify({'success': True, 'updated': updated})

@app.route('/api/automations')
def get_automations():
    """Get all automation configurations."""
    return jsonify({'automations': get_all_automations()})

@app.route('/api/service/details/<service>')
def get_service_details(service):
    """Get detailed status for a systemd service."""
    # Get service configuration
    service_config = get_service_config(service)
    if not service_config:
        return jsonify({'success': False, 'error': 'Invalid service'}), 400

    # Only systemd services support details view
    if service_config['check_type'] != 'systemd':
        return jsonify({'success': False, 'error': 'Service does not support details view'}), 400

    try:
        # Use service_name from config
        service_name = service_config['service_name']
        result = subprocess.run(
            ['systemctl', 'status', service_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        # Return the full output regardless of return code
        return jsonify({
            'success': True,
            'output': result.stdout,
            'service': service
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'service': service
        })

@app.route('/api/control/<service>', methods=['POST'])
def control(service):
    """Control a service (start/stop)."""
    data = request.get_json()
    action = data.get('action')  # 'start' or 'stop'

    if action not in ['start', 'stop']:
        return jsonify({'success': False, 'error': 'Invalid action'}), 400

    # Get service configuration
    service_config = get_service_config(service)
    if not service_config:
        return jsonify({'success': False, 'error': 'Invalid service'}), 400

    # Control based on service type
    if service_config['control_type'] == 'systemd':
        success, error = control_service(service_config['service_name'], action)
    elif service_config['control_type'] == 'process':
        success, error = control_process(service_config['service_name'], action)
    else:
        return jsonify({'success': False, 'error': 'Invalid control type'}), 400

    return jsonify({'success': success, 'error': error})

@app.route('/api/automation/<automation_name>', methods=['POST'])
def run_automation(automation_name):
    """Run an automation script in the background."""
    print(f"Received request to run automation: {automation_name}")

    # Get automation config
    automation_config = get_automation_config(automation_name)

    if not automation_config:
        print(f"Invalid automation name: {automation_name}")
        return jsonify({'success': False, 'error': 'Invalid automation'}), 400

    # Check if automation is already running
    with automation_lock:
        if automation_state[automation_name]['running']:
            print(f"Automation {automation_name} is already running")
            return jsonify({
                'success': False,
                'error': 'Automation already running'
            }), 400

    # Get arguments from request body
    data = request.get_json() or {}
    args = data.get('args', '').strip()

    script_path = automation_config['script_path']
    job_id = str(uuid.uuid4())
    print(f"Starting automation {automation_name} with job_id {job_id}" + (f" and args: {args}" if args else ""))

    def run_script():
        try:
            # Initialize the automation state
            with automation_lock:
                automation_state[automation_name] = {
                    'job_id': job_id,
                    'running': True,
                    'output': 'Starting...\n',
                    'return_code': None,
                    'process': None
                }
            broadcast_automation_state(automation_name)

            # Build command with arguments if provided
            if args:
                # Use shlex to safely split arguments
                try:
                    arg_list = shlex.split(args)
                    cmd = ['/bin/bash', script_path] + arg_list
                except ValueError as e:
                    # If argument parsing fails, add error to output
                    with automation_lock:
                        automation_state[automation_name]['output'] += f"ERROR: Invalid arguments: {str(e)}\n"
                        automation_state[automation_name]['running'] = False
                        automation_state[automation_name]['return_code'] = -1
                        automation_state[automation_name]['completed_at'] = datetime.now().strftime('%H:%M:%S %m/%d/%y')
                    broadcast_automation_state(automation_name)
                    return
            else:
                cmd = ['/bin/bash', script_path]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            with automation_lock:
                automation_state[automation_name]['process'] = process

            # Read output line by line and broadcast updates
            for line in process.stdout:
                with automation_lock:
                    automation_state[automation_name]['output'] += line
                # Broadcast incremental update outside the lock
                broadcast_automation_state(automation_name, incremental_output=line)

            process.wait()

            with automation_lock:
                automation_state[automation_name]['running'] = False
                automation_state[automation_name]['return_code'] = process.returncode
                automation_state[automation_name]['process'] = None
                automation_state[automation_name]['completed_at'] = datetime.now().strftime('%H:%M:%S %m/%d/%y')
            broadcast_automation_state(automation_name)

        except Exception as e:
            with automation_lock:
                automation_state[automation_name]['output'] += f"\n\nERROR: {str(e)}\n"
                automation_state[automation_name]['running'] = False
                automation_state[automation_name]['return_code'] = -1
                automation_state[automation_name]['process'] = None
                automation_state[automation_name]['completed_at'] = datetime.now().strftime('%H:%M:%S %m/%d/%y')
            broadcast_automation_state(automation_name)

    # Start the script in a background thread/greenthread
    if DEBUG_MODE:
        # Use regular threading in debug mode
        thread = threading.Thread(target=run_script, daemon=True)
        thread.start()
    else:
        # Use eventlet greenthreads in production
        eventlet.spawn(run_script)

    # Give it a tiny moment to initialize
    time.sleep(0.1)

    response = jsonify({
        'success': True,
        'job_id': job_id,
        'message': f'{automation_name} started'
    })
    print(f"Returning success response for {automation_name}")
    return response

@app.route('/api/automation/<automation_name>/status')
def get_automation_status(automation_name):
    """Get the current status and output of an automation."""
    if automation_name not in automation_state:
        return jsonify({
            'success': False,
            'error': 'Invalid automation'
        }), 404

    with automation_lock:
        state = automation_state[automation_name].copy()
        # Don't send the process object
        state.pop('process', None)

        return jsonify({
            'success': True,
            **state
        })

@app.route('/api/stocks/daily-change', methods=['POST'])
def get_stock_daily_change():
    """Get daily percentage changes for stock symbols over the last 30 trading days."""
    try:
        data = request.get_json()
        symbols = data.get('symbols', [])

        if not symbols:
            return jsonify({'success': False, 'error': 'No symbols provided'}), 400

        stock_data = {}

        for symbol in symbols:
            try:
                # Use Yahoo Finance API to get stock data
                # Get last 60 days to ensure we have at least 30 trading days
                end_date = datetime.now()
                start_date = end_date - timedelta(days=60)

                period1 = int(start_date.timestamp())
                period2 = int(end_date.timestamp())

                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={period1}&period2={period2}&interval=1d"

                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    result = json.loads(response.read().decode())

                if 'chart' in result and 'result' in result['chart'] and result['chart']['result']:
                    chart_data = result['chart']['result'][0]
                    timestamps = chart_data['timestamp']
                    quotes = chart_data['indicators']['quote'][0]
                    close_prices = quotes['close']

                    # Calculate daily percentage changes
                    dates = []
                    percent_changes = []

                    for i in range(1, len(close_prices)):
                        if close_prices[i] is not None and close_prices[i-1] is not None:
                            prev_close = close_prices[i-1]
                            curr_close = close_prices[i]
                            pct_change = ((curr_close - prev_close) / prev_close) * 100

                            dates.append(datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d'))
                            percent_changes.append(round(pct_change, 2))

                    # Keep only last 30 data points
                    stock_data[symbol] = {
                        'dates': dates[-30:],
                        'percent_changes': percent_changes[-30:]
                    }
                else:
                    stock_data[symbol] = {
                        'dates': [],
                        'percent_changes': [],
                        'error': 'No data available'
                    }

            except Exception as e:
                print(f"Error fetching data for {symbol}: {e}")
                stock_data[symbol] = {
                    'dates': [],
                    'percent_changes': [],
                    'error': str(e)
                }

        return jsonify({'success': True, 'data': stock_data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/weather', methods=['POST'])
def get_weather():
    """Get weather data for a given location using wttr.in service."""
    try:
        data = request.get_json()
        location = data.get('location', '')

        if not location:
            return jsonify({'success': False, 'error': 'No location provided'}), 400

        # Use wttr.in API (free, no API key required)
        # Format: wttr.in/Location?format=j1 for JSON
        encoded_location = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded_location}?format=j1"

        req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            weather_data = json.loads(response.read().decode())

        # Extract current weather
        current = weather_data['current_condition'][0]
        temp_f = current['temp_F']
        condition = current['weatherDesc'][0]['value']

        # Get location name from nearest area
        location_name = weather_data['nearest_area'][0]['areaName'][0]['value']
        region = weather_data['nearest_area'][0].get('region', [{}])[0].get('value', '')
        country = weather_data['nearest_area'][0].get('country', [{}])[0].get('value', '')

        full_location = f"{location_name}"
        if region:
            full_location += f", {region}"
        if country and country != "United States of America":
            full_location += f", {country}"

        return jsonify({
            'success': True,
            'temperature': float(temp_f),
            'condition': condition,
            'location': full_location
        })

    except Exception as e:
        print(f"Error fetching weather: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/automation/<automation_name>/cancel', methods=['POST'])
def cancel_automation(automation_name):
    """Cancel a running automation."""
    if automation_name not in automation_state:
        return jsonify({
            'success': False,
            'error': 'Invalid automation'
        }), 404

    with automation_lock:
        state = automation_state[automation_name]

        if not state['running']:
            return jsonify({
                'success': False,
                'error': 'Automation not running'
            })

        # Get the process reference
        process: subprocess.Popen = state.get('process')
        if not process:
            return jsonify({
                'success': False,
                'error': 'Process not found'
            })

    # Kill the process outside the lock to avoid blocking
    try:
        kill_proc_tree(process.pid)

        # Update state
        with automation_lock:
            state['output'] += "\n\n=== CANCELLED BY USER ===\n"
            state['running'] = False
            state['return_code'] = -999  # Special code for cancelled
            state['process'] = None
            state['completed_at'] = datetime.now().strftime('%H:%M:%S %m/%d/%y')

        # Broadcast outside the lock
        broadcast_automation_state(automation_name)

        return jsonify({
            'success': True,
            'message': 'Automation cancelled'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@socketio.on('connect')
def handle_connect():
    """Handle client connection - send current automation states."""
    print('Client connected')
    # Send current state of all automations to the newly connected client
    with automation_lock:
        for automation_name, state in automation_state.items():
            state_copy = state.copy()
            state_copy.pop('process', None)
            # Mark as full update (not incremental)
            state_copy['incremental'] = False
            emit('automation_update', {
                'automation': automation_name,
                'state': state_copy
            })

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    print('Client disconnected')

@socketio.on('request_automation_state')
def handle_request_state(data):
    """Handle explicit request for automation state."""
    automation_name = data.get('automation')
    if automation_name and automation_name in automation_state:
        with automation_lock:
            state = automation_state[automation_name].copy()
            state.pop('process', None)
            emit('automation_update', {
                'automation': automation_name,
                'state': state
            })

# Start the network speed monitor thread
# This daemon thread runs in the background and updates network stats cache
network_monitor_thread = threading.Thread(target=network_speed_monitor, daemon=True)
network_monitor_thread.start()

# Start the system stats broadcaster thread
# This daemon thread collects system stats and pushes them to all connected clients
system_stats_thread = threading.Thread(target=system_stats_broadcaster, daemon=True)
system_stats_thread.start()

# Start the service status broadcaster thread
# This daemon thread checks service status and pushes updates to all connected clients
service_status_thread = threading.Thread(target=service_status_broadcaster, daemon=True)
service_status_thread.start()

# Start the internet connectivity monitor thread
# This runs separately to avoid blocking other status checks when internet is slow/down
internet_monitor_thread = threading.Thread(target=internet_connectivity_monitor, daemon=True)
internet_monitor_thread.start()

# Start the timeseries data collector thread
from timeseries_collector import start_collector
start_collector()

# Create a WSGI application wrapper for gunicorn
# This allows gunicorn to serve the Flask-SocketIO app
def create_app():
    return app

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)