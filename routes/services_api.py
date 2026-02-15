"""Service-related API routes."""
from flask import Blueprint, jsonify, request

from config_loader import get_all_services, get_service_config
from app_state import service_status_lock, service_status_cache
from utils import check_service_status, check_process_running, control_service, control_process
from utils.subprocess_helper import run as subprocess_run

services_bp = Blueprint('services', __name__)


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


@services_bp.route('/api/services')
def get_services():
    """Get all service configurations."""
    return jsonify(get_all_services())


@services_bp.route('/api/status')
def get_status():
    """Get status of all services and connectivity (returns cached data)."""
    with service_status_lock:
        return jsonify(service_status_cache.copy())


@services_bp.route('/api/service/details/<service>')
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
        result = subprocess_run(
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


@services_bp.route('/api/control/<service>', methods=['POST'])
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
        success, error = control_service(
            service_config['service_name'],
            action,
            on_start_callback=on_service_start,
            on_stop_callback=on_service_stop
        )
    elif service_config['control_type'] == 'process':
        success, error = control_process(
            service_config['service_name'],
            action,
            on_start_callback=on_service_start,
            on_stop_callback=on_service_stop
        )
    else:
        return jsonify({'success': False, 'error': 'Invalid control type'}), 400

    return jsonify({'success': success, 'error': error})
