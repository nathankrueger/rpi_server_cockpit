from flask import Flask, render_template, jsonify, request
import subprocess
import socket
import psutil
import time
import threading
import uuid
from collections import defaultdict

app = Flask(__name__)

# Configuration constants - CHANGE THESE AS NEEDED
NETWORK_INTERFACE = 'wlan0'  # Network interface to monitor
DISK_MOUNT_POINT = '/'       # Disk mount point to monitor

# Store running automation processes and their output
running_automations = {}
automation_outputs = defaultdict(str)
automation_lock = threading.Lock()

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

@app.route('/api/service/details/<service>')
def get_service_details(service):
    """Get detailed status for a systemd service."""
    valid_services = ['tailscaled', 'minidlnad', 'smbd']
    internal_names = {'minidlnad':'minidlna'}
    
    if service not in valid_services:
        return jsonify({'success': False, 'error': 'Invalid service'}), 400
    
    try:
        service_name = service if service not in internal_names else internal_names[service]
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
    
    valid_services = ['tailscaled', 'minidlnad', 'smbd']
    
    if service in valid_services:
        success, error = control_service(service, action)
    elif service == 'qbittorrent':
        success, error = control_qbittorrent(action)
    else:
        return jsonify({'success': False, 'error': 'Invalid service'}), 400
    
    return jsonify({'success': success, 'error': error})

@app.route('/api/automation/<automation_name>', methods=['POST'])
def run_automation(automation_name):
    """Run an automation script in the background."""
    # Map automation names to their script files
    automation_scripts = {
        'sync_music': './automation_scripts/sync_music.sh',
        'reboot': './automation_scripts/reboot.sh',
        'update_os': './automation_scripts/update_os.sh'
    }
    
    if automation_name not in automation_scripts:
        return jsonify({'success': False, 'error': 'Invalid automation'}), 400
    
    script_path = automation_scripts[automation_name]
    job_id = str(uuid.uuid4())
    
    def run_script():
        try:
            # Initialize the job info immediately
            with automation_lock:
                running_automations[job_id] = {
                    'name': automation_name,
                    'running': True,
                    'return_code': None
                }
                automation_outputs[job_id] = ''
            
            process = subprocess.Popen(
                ['/bin/bash', script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            with automation_lock:
                running_automations[job_id]['process'] = process
            
            # Read output line by line
            for line in process.stdout:
                with automation_lock:
                    automation_outputs[job_id] += line
            
            process.wait()
            
            with automation_lock:
                running_automations[job_id]['running'] = False
                running_automations[job_id]['return_code'] = process.returncode
                
        except Exception as e:
            with automation_lock:
                automation_outputs[job_id] += f"\n\nERROR: {str(e)}\n"
                if job_id in running_automations:
                    running_automations[job_id]['running'] = False
                    running_automations[job_id]['return_code'] = -1
    
    # Start the script in a background thread
    thread = threading.Thread(target=run_script, daemon=True)
    thread.start()
    
    # Give it a tiny moment to initialize
    time.sleep(0.1)
    
    return jsonify({
        'success': True,
        'job_id': job_id,
        'message': f'{automation_name} started'
    })

@app.route('/api/automation/<automation_name>/status/<job_id>')
def get_automation_status(automation_name, job_id):
    """Get the current status and output of a running automation."""
    with automation_lock:
        if job_id not in running_automations:
            return jsonify({
                'success': False,
                'error': 'Job not found'
            }), 404
        
        job_info = running_automations[job_id]
        output = automation_outputs[job_id]
        
        return jsonify({
            'success': True,
            'running': job_info['running'],
            'output': output,
            'return_code': job_info.get('return_code', None)
        })

@app.route('/api/automation/<automation_name>/cancel/<job_id>', methods=['POST'])
def cancel_automation(automation_name, job_id):
    """Cancel a running automation."""
    with automation_lock:
        if job_id not in running_automations:
            return jsonify({
                'success': False,
                'error': 'Job not found'
            }), 404
        
        job_info = running_automations[job_id]
        
        if not job_info['running']:
            return jsonify({
                'success': False,
                'error': 'Job already completed'
            })
        
        # Try to kill the process
        try:
            if 'process' in job_info:
                process = job_info['process']
                process.terminate()
                # Give it a moment to terminate gracefully
                time.sleep(0.5)
                if process.poll() is None:
                    # Force kill if still running
                    process.kill()
                
                automation_outputs[job_id] += "\n\n=== CANCELLED BY USER ===\n"
                job_info['running'] = False
                job_info['return_code'] = -999  # Special code for cancelled
                
                return jsonify({
                    'success': True,
                    'message': 'Job cancelled'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Process not found'
                })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)