"""Device API routes — external networked appliances (BluOS players, etc.).

Devices are a tile category distinct from services/automations/stats: each has
a `type` that maps to a backend dispatcher (utils/device_types.py) and a
frontend renderer. This blueprint exposes the device list, a status snapshot,
a command endpoint, and an artwork proxy.
"""
from flask import Blueprint, jsonify, request, Response

from config_loader import get_all_devices, get_device_config
from app_state import device_status_cache, device_status_lock
from utils.device_types import run_command, get_status_for
from utils import bluos_utils

devices_bp = Blueprint('devices', __name__)

# Commands that carry a numeric `value` payload.
_VALUE_ACTIONS = {'volume', 'seek'}


@devices_bp.route('/api/devices')
def get_devices():
    """Get all device configurations (safe fields only) for rendering.

    Includes the volume slew/cap hints the frontend needs so the slider can be
    rate-limited and capped client-side.
    """
    result = []
    for d in get_all_devices():
        result.append({
            'id': d['id'],
            'type': d.get('type'),
            'display_name': d.get('display_name', d['id'].upper()),
            'group': d.get('group'),
            'volume_max': int(d.get('volume_max', 60)),
            'volume_max_step': int(d.get('volume_max_step', 2)),
            'volume_tick_ms': int(d.get('volume_tick_ms', 250)),
        })
    return jsonify(result)


@devices_bp.route('/api/devices/status')
def get_devices_status():
    """Snapshot of the latest device statuses (for initial load / tab focus)."""
    with device_status_lock:
        return jsonify(dict(device_status_cache))


@devices_bp.route('/api/device/<device_id>/command', methods=['POST'])
def device_command(device_id):
    """Dispatch a command to a device.

    Body: {action: play|pause|toggle|next|prev|volume|seek, value?: number}.
    Volume is hard-clamped to the device's volume_max inside the dispatcher.
    Returns the fresh status for fast UI feedback.
    """
    device = get_device_config(device_id)
    if not device:
        return jsonify({'success': False, 'error': 'Unknown device'}), 404

    data = request.get_json(silent=True) or {}
    action = data.get('action')
    value = data.get('value') if action in _VALUE_ACTIONS else None

    if action in _VALUE_ACTIONS and value is None:
        return jsonify({'success': False, 'error': f"'{action}' requires a value"}), 400

    try:
        ok = run_command(device, action, value)
        if not ok:
            return jsonify({'success': False, 'error': f"Unsupported action: {action}"}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 502

    # Fetch fresh status for immediate feedback; tolerate a transient failure.
    status = None
    try:
        status = get_status_for(device)
        status['online'] = True
        with device_status_lock:
            device_status_cache[device_id] = status
    except Exception:
        pass

    return jsonify({'success': True, 'status': status})


@devices_bp.route('/api/device/<device_id>/art')
def device_art(device_id):
    """Proxy the current album artwork bytes for a device.

    Reads the current image URL from the status cache and streams the bytes,
    keeping the device address off the client and sidestepping relative-URL /
    redirect / mixed-content issues.
    """
    if not get_device_config(device_id):
        return jsonify({'error': 'Unknown device'}), 404

    with device_status_lock:
        cached = device_status_cache.get(device_id, {})
    image_url = cached.get('image')
    if not image_url:
        return jsonify({'error': 'No artwork available'}), 404

    try:
        data, content_type = bluos_utils.fetch_artwork(image_url)
    except Exception as e:
        return jsonify({'error': str(e)}), 502

    return Response(data, content_type=content_type, headers={'Cache-Control': 'no-cache'})
