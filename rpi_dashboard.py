from flask import Flask, render_template, jsonify, request
import subprocess
import psutil
import time

app = Flask(__name__)

# Configuration constants - CHANGE THESE AS NEEDED
NETWORK_INTERFACE = 'wlan0'  # Network interface to monitor
DISK_MOUNT_POINT = '/'       # Disk mount point to monitor

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

def get_system_stats():
    """Get CPU, RAM, disk, and network statistics."""
    stats = {}
    
    # CPU Usage
    stats['cpu_percent'] = psutil.cpu_percent(interval=1)
    
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
    
    # Network Speed for specified interface
    try:
        net_io_start = psutil.net_io_counters(pernic=True).get(NETWORK_INTERFACE)
        if net_io_start:
            time.sleep(1)  # Wait 1 second to measure speed
            net_io_end = psutil.net_io_counters(pernic=True).get(NETWORK_INTERFACE)
            
            # Calculate bytes per second
            upload_speed = (net_io_end.bytes_sent - net_io_start.bytes_sent)
            download_speed = (net_io_end.bytes_recv - net_io_start.bytes_recv)
            
            # Convert to Mbps
            stats['upload_mbps'] = round(upload_speed * 8 / (1024**2), 2)
            stats['download_mbps'] = round(download_speed * 8 / (1024**2), 2)
            stats['network_interface'] = NETWORK_INTERFACE
        else:
            stats['upload_mbps'] = 0
            stats['download_mbps'] = 0
            stats['network_interface'] = NETWORK_INTERFACE
    except Exception as e:
        stats['upload_mbps'] = 0
        stats['download_mbps'] = 0
        stats['network_interface'] = NETWORK_INTERFACE
        print(f"Error reading network stats: {e}")
    
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

def control_qbittorrent(action):
    """Start or stop qbittorrent-nox process."""
    try:
        if action == 'start':
            # Start qbittorrent-nox in the background
            subprocess.Popen(
                ['qbittorrent-nox'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            on_service_start('qbittorrent-nox')
            return True, ''
        elif action == 'stop':
            result = subprocess.run(
                ['pkill', '-x', 'qbittorrent-nox'],
                capture_output=True,
                text=True,
                timeout=5
            )
            on_service_stop('qbittorrent-nox')
            return True, ''
    except Exception as e:
        return False, str(e)

@app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """Get status of all services and connectivity."""
    status = {
        'tailscaled': check_service_status('tailscaled'),
        'minidlnad': check_service_status('minidlna'),
        'smbd': check_service_status('smbd'),
        'qbittorrent': check_process_running('qbittorrent-nox'),
        'internet': check_internet_connectivity()
    }
    return jsonify(status)

@app.route('/api/system')
def get_system():
    """Get system statistics."""
    return jsonify(get_system_stats())

@app.route('/api/control/<service>', methods=['POST'])
def control(service):
    """Control a service (start/stop)."""
    data = request.get_json()
    action = data.get('action')  # 'start' or 'stop'
    
    if action not in ['start', 'stop']:
        return jsonify({'success': False, 'error': 'Invalid action'}), 400
    
    valid_services = ['tailscaled', 'minidlnad', 'smbd']
    internal_names = {'minidlnad':'minidlna'}
    
    if service in valid_services:
        service = service if service not in internal_names else internal_names[service]
        success, error = control_service(service, action)
    elif service == 'qbittorrent':
        success, error = control_qbittorrent(action)
    else:
        return jsonify({'success': False, 'error': 'Invalid service'}), 400
    
    return jsonify({'success': success, 'error': error})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)