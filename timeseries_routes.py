"""
Flask routes for timeseries API endpoints.

This module contains all REST API endpoints related to timeseries data
and charting functionality.
"""

from flask import Blueprint, jsonify, request, render_template
from datetime import datetime
from timeseries_config import get_all_timeseries, get_timeseries, get_timeseries_info
from timeseries_db import TimeseriesDB


# Create a Blueprint for timeseries routes
timeseries_bp = Blueprint('timeseries', __name__)

# Initialize database (will be shared across all requests)
timeseries_db = TimeseriesDB('timeseries.db')


@timeseries_bp.route('/charts')
def charts_page():
    """Serve the timeseries charts page."""
    return render_template('charts.html')


@timeseries_bp.route('/api/timeseries/list')
def list_timeseries():
    """
    Get list of all available timeseries with metadata.

    Returns:
        JSON array of timeseries with id, name, and units
    """
    return jsonify(get_timeseries_info())


@timeseries_bp.route('/api/timeseries/data/<timeseries_id>')
def get_timeseries_data(timeseries_id):
    """
    Get timeseries data for a specific timeseries within a time range.

    Query parameters:
        start: Start timestamp (Unix seconds) - optional
        end: End timestamp (Unix seconds) - optional
        limit: Max number of points if no range specified - optional (default 1000)

    Returns:
        JSON object with:
            - id: timeseries ID
            - name: timeseries name
            - units: timeseries units
            - data: array of {timestamp, value} objects
    """
    ts = get_timeseries(timeseries_id)
    if not ts:
        return jsonify({'error': 'Timeseries not found'}), 404

    start_time = request.args.get('start', type=float)
    end_time = request.args.get('end', type=float)
    limit = request.args.get('limit', default=1000, type=int)

    # Query data based on parameters
    if start_time is not None and end_time is not None:
        data = timeseries_db.query_range(timeseries_id, start_time, end_time)
    else:
        data = timeseries_db.query_latest(timeseries_id, limit)

    return jsonify({
        'id': timeseries_id,
        'name': ts.getName(),
        'units': ts.getUnits(),
        'data': data
    })


@timeseries_bp.route('/api/timeseries/data/batch', methods=['POST'])
def get_timeseries_data_batch():
    """
    Get data for multiple timeseries at once.

    Request body:
        {
            "timeseries_ids": ["cpu_temperature", "gpu_temperature"],
            "start": 1234567890.0,  // optional
            "end": 1234567900.0,    // optional
            "limit": 1000,          // optional (for latest query)
            "max_datapoints": 10000 // optional (for downsampling with LTTB)
        }

    Returns:
        JSON array of timeseries data objects
    """
    data = request.get_json()
    timeseries_ids = data.get('timeseries_ids', [])
    start_time = data.get('start')
    end_time = data.get('end')
    limit = data.get('limit', 1000)
    max_datapoints = data.get('max_datapoints')

    results = []
    for ts_id in timeseries_ids:
        ts = get_timeseries(ts_id)
        if not ts:
            continue

        # Query data
        if start_time is not None and end_time is not None:
            ts_data = timeseries_db.query_range(ts_id, start_time, end_time, max_points=max_datapoints)
        else:
            ts_data = timeseries_db.query_latest(ts_id, limit)

        results.append({
            'id': ts_id,
            'name': ts.getName(),
            'units': ts.getUnits(),
            'data': ts_data
        })

    return jsonify(results)


@timeseries_bp.route('/api/timeseries/current')
def get_current_values():
    """
    Get current values for all timeseries (live data, not from database).

    Returns:
        JSON array of current values
    """
    results = []
    for ts in get_all_timeseries():
        value = ts.getCurrentValue()
        results.append({
            'id': ts.getId(),
            'name': ts.getName(),
            'units': ts.getUnits(),
            'value': value,
            'timestamp': datetime.now().timestamp()
        })

    return jsonify(results)


@timeseries_bp.route('/api/timeseries/settings', methods=['GET'])
def get_timeseries_settings():
    """
    Get all timeseries settings.

    Returns:
        JSON object with all settings
    """
    settings = timeseries_db.get_all_settings()

    # Convert to appropriate types
    return jsonify({
        'sampling_rate_ms': int(settings.get('sampling_rate_ms', 5000)),
    })


@timeseries_bp.route('/api/timeseries/settings', methods=['POST'])
def update_timeseries_settings():
    """
    Update timeseries settings.

    Request body:
        {
            "sampling_rate_ms": 5000
        }

    Returns:
        JSON object with success status
    """
    data = request.get_json()

    # Validate and save sampling rate
    if 'sampling_rate_ms' in data:
        sampling_rate = data['sampling_rate_ms']
        if not isinstance(sampling_rate, int) or sampling_rate < 100 or sampling_rate > 3600000:
            return jsonify({'success': False, 'error': 'Invalid sampling rate (must be 100-3600000 ms)'}), 400
        timeseries_db.set_setting('sampling_rate_ms', sampling_rate)

    return jsonify({'success': True})


@timeseries_bp.route('/api/timeseries/collect', methods=['POST'])
def collect_data_now():
    """
    Immediately collect and store current values for all timeseries.
    This is independent of the automatic sampling interval.

    Returns:
        JSON object with success status and timestamp
    """
    timestamp = datetime.now().timestamp()
    datapoints = []

    for ts in get_all_timeseries():
        try:
            value = ts.getCurrentValue()
            if value is not None:
                datapoints.append({
                    'timeseries_id': ts.getId(),
                    'value': value,
                    'timestamp': timestamp
                })
        except Exception as e:
            print(f"Error collecting data for {ts.getId()}: {e}")

    # Insert all datapoints
    if datapoints:
        timeseries_db.insert_datapoints_batch(datapoints)

    return jsonify({
        'success': True,
        'timestamp': timestamp,
        'count': len(datapoints)
    })


def get_timeseries_db():
    """Get the timeseries database instance (for use by background threads)."""
    return timeseries_db
