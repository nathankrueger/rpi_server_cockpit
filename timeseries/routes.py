"""
Flask routes for timeseries API endpoints.

This module contains all REST API endpoints related to timeseries data
and charting functionality.
"""

from flask import Blueprint, jsonify, request, render_template
from datetime import datetime

from .config import get_all_timeseries, get_timeseries, get_timeseries_info
from .db import TimeseriesDB


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
    Includes both local (built-in) and external (registered) timeseries.

    Returns:
        JSON array of timeseries with id, name, units, category, tags, description
    """
    # Get local timeseries
    all_timeseries = get_timeseries_info()

    # Add external timeseries from database
    external = timeseries_db.list_external_timeseries()
    all_timeseries.extend(external)

    return jsonify(all_timeseries)


@timeseries_bp.route('/api/timeseries/data/<timeseries_id>')
def get_timeseries_data(timeseries_id):
    """
    Get timeseries data for a specific timeseries within a time range.
    Works with both local (built-in) and external (registered) timeseries.

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
    # Check local timeseries first
    ts = get_timeseries(timeseries_id)
    if ts:
        name = ts.getName()
        units = ts.getUnits()
    else:
        # Check external timeseries
        external = timeseries_db.get_external_timeseries(timeseries_id)
        if external:
            name = external['name']
            units = external['units']
        else:
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
        'name': name,
        'units': units,
        'data': data
    })


@timeseries_bp.route('/api/timeseries/data/batch', methods=['POST'])
def get_timeseries_data_batch():
    """
    Get data for multiple timeseries at once.
    Works with both local (built-in) and external (registered) timeseries.

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
        # Check local timeseries first
        ts = get_timeseries(ts_id)
        if ts:
            name = ts.getName()
            units = ts.getUnits()
        else:
            # Check external timeseries
            external = timeseries_db.get_external_timeseries(ts_id)
            if external:
                name = external['name']
                units = external['units']
            else:
                continue  # Skip unknown timeseries

        # Query data
        if start_time is not None and end_time is not None:
            ts_data = timeseries_db.query_range(ts_id, start_time, end_time, max_points=max_datapoints)
        else:
            ts_data = timeseries_db.query_latest(ts_id, limit)

        results.append({
            'id': ts_id,
            'name': name,
            'units': units,
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


@timeseries_bp.route('/api/timeseries/ingest', methods=['POST'])
def ingest_timeseries_data():
    """
    Ingest external timeseries data (e.g., from remote IoT sensors).
    Auto-registers the timeseries if it doesn't exist.

    Request body (single datapoint):
        {
            "id": "garage_temp",           // required: unique identifier
            "name": "Garage Temperature",  // required: display name
            "units": "°F",                 // required: unit of measurement
            "value": 72.5,                 // required: the value to record
            "timestamp": 1234567890.0,     // optional: defaults to server time
            "category": "External",        // optional: category for grouping
            "tags": ["garage", "temp"],    // optional: searchable tags
            "description": "...",          // optional: human-readable description
            "gateway": "patio_gateway"     // optional: gateway ID that provides this data
        }

    Request body (batch):
        {
            "gateway": "patio_gateway",    // optional: applies to all datapoints
            "datapoints": [
                {"id": "garage_temp", "name": "Garage Temperature", "units": "°F", "value": 72.5},
                {"id": "garage_humidity", "name": "Garage Humidity", "units": "%", "value": 45.2}
            ]
        }

    Returns:
        JSON object with success status and count of ingested points
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No JSON data provided'}), 400

    # Handle batch ingestion
    if 'datapoints' in data:
        datapoints = data['datapoints']
        if not isinstance(datapoints, list):
            return jsonify({'success': False, 'error': 'datapoints must be an array'}), 400

        # Gateway can be specified at batch level or per-datapoint
        batch_gateway = data.get('gateway')

        # Validate and process each datapoint
        for i, dp in enumerate(datapoints):
            if 'id' not in dp:
                return jsonify({'success': False, 'error': f'Missing id in datapoint {i}'}), 400
            if 'value' not in dp:
                return jsonify({'success': False, 'error': f'Missing value in datapoint {i}'}), 400
            if 'name' not in dp:
                return jsonify({'success': False, 'error': f'Missing name in datapoint {i}'}), 400
            if 'units' not in dp:
                return jsonify({'success': False, 'error': f'Missing units in datapoint {i}'}), 400

            # Check for conflict with built-in timeseries
            if get_timeseries(dp['id']):
                return jsonify({'success': False, 'error': f'ID "{dp["id"]}" in datapoint {i} conflicts with a built-in timeseries'}), 400

            # Per-datapoint gateway overrides batch gateway
            gateway = dp.get('gateway', batch_gateway)

            # Auto-register/update the external timeseries
            timeseries_db.register_external_timeseries(
                timeseries_id=dp['id'],
                name=dp['name'],
                units=dp['units'],
                category=dp.get('category', 'External'),
                tags=dp.get('tags', []),
                description=dp.get('description', ''),
                gateway=gateway
            )

        # Insert batch (remap 'id' to 'timeseries_id' for the DB method)
        db_datapoints = [
            {'timeseries_id': dp['id'], 'value': dp['value'], 'timestamp': dp.get('timestamp')}
            for dp in datapoints
        ]
        timeseries_db.insert_datapoints_batch(db_datapoints)
        return jsonify({'success': True, 'count': len(datapoints)})

    # Handle single datapoint
    timeseries_id = data.get('id')
    name = data.get('name')
    units = data.get('units')
    value = data.get('value')
    timestamp = data.get('timestamp')
    gateway = data.get('gateway')

    if not timeseries_id:
        return jsonify({'success': False, 'error': 'Missing id'}), 400
    if not name:
        return jsonify({'success': False, 'error': 'Missing name'}), 400
    if units is None:
        return jsonify({'success': False, 'error': 'Missing units'}), 400
    if value is None:
        return jsonify({'success': False, 'error': 'Missing value'}), 400

    # Check for conflict with built-in timeseries
    if get_timeseries(timeseries_id):
        return jsonify({'success': False, 'error': f'ID "{timeseries_id}" conflicts with a built-in timeseries'}), 400

    # Auto-register/update the external timeseries
    timeseries_db.register_external_timeseries(
        timeseries_id=timeseries_id,
        name=name,
        units=units,
        category=data.get('category', 'External'),
        tags=data.get('tags', []),
        description=data.get('description', ''),
        gateway=gateway
    )

    timeseries_db.insert_datapoint(timeseries_id, value, timestamp)
    return jsonify({'success': True, 'count': 1})


@timeseries_bp.route('/api/timeseries/minmax/batch', methods=['POST'])
def get_timeseries_minmax_batch():
    """
    Get min/max values for multiple timeseries within a time range.
    Works with both local (built-in) and external (registered) timeseries.

    Request body:
        {
            "timeseries_ids": ["cpu_temperature", "gpu_temperature"],
            "start": 1234567890.0,  // required
            "end": 1234567900.0     // required
        }

    Returns:
        JSON object mapping timeseries_id to {min, max} values
    """
    data = request.get_json()
    timeseries_ids = data.get('timeseries_ids', [])
    start_time = data.get('start')
    end_time = data.get('end')

    if start_time is None or end_time is None:
        return jsonify({'error': 'start and end timestamps are required'}), 400

    results = timeseries_db.query_minmax_batch(timeseries_ids, start_time, end_time)
    return jsonify(results)


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
