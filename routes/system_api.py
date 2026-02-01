"""System statistics API routes."""
from flask import Blueprint, jsonify, request

import app_state
from app_state import system_stats_lock, system_stats_cache, server_config_lock
from utils import save_server_config

system_bp = Blueprint('system', __name__)


@system_bp.route('/api/system')
def get_system():
    """Get system statistics (returns cached data)."""
    with system_stats_lock:
        return jsonify(system_stats_cache.copy())


@system_bp.route('/api/server_config', methods=['GET'])
def get_server_config():
    """Get current server configuration."""
    with server_config_lock:
        return jsonify(app_state.server_config.copy())


@system_bp.route('/api/server_config', methods=['POST'])
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
                app_state.server_config['system_stats_interval'] = float(val)
                updated['system_stats_interval'] = float(val)
            else:
                return jsonify({'success': False, 'error': 'system_stats_interval must be between 0.1 and 60 seconds'}), 400

        # Validate and update service_status_interval
        if 'service_status_interval' in data:
            val = data['service_status_interval']
            if isinstance(val, (int, float)) and 1 <= val <= 300:
                app_state.server_config['service_status_interval'] = float(val)
                updated['service_status_interval'] = float(val)
            else:
                return jsonify({'success': False, 'error': 'service_status_interval must be between 1 and 300 seconds'}), 400

        # Validate and update internet_check_interval
        if 'internet_check_interval' in data:
            val = data['internet_check_interval']
            if isinstance(val, (int, float)) and 1 <= val <= 300:
                app_state.server_config['internet_check_interval'] = float(val)
                updated['internet_check_interval'] = float(val)
            else:
                return jsonify({'success': False, 'error': 'internet_check_interval must be between 1 and 300 seconds'}), 400

        # Persist to file if any changes were made
        if updated:
            save_server_config(app_state.server_config)

    return jsonify({'success': True, 'updated': updated})
