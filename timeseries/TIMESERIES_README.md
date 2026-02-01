# Timeseries Charting System

A comprehensive, data-driven timeseries charting framework for the Raspberry Pi Dashboard. This system makes it incredibly easy to add new timeseries data sources - just define a simple class and add it to the configuration!

## Features

- **Data-Driven Architecture**: All timeseries defined in one central location
- **Automatic Data Collection**: Background thread samples all timeseries at configurable intervals
- **SQLite Database Storage**: Persistent storage allows viewing history from any client
- **Interactive Charts**: Plotly-based interactive charts with zoom, pan, and hover details
- **Grouped Visualization**: Automatically groups timeseries by units for multi-line charts
- **Flexible Time Ranges**: Custom date pickers plus quick-select buttons (1h, 6h, 24h, 1w)
- **Auto-Refresh**: Optional automatic chart updates at configurable intervals
- **Configurable Sampling**: User-adjustable data collection rate (1-60 seconds)

## Architecture

### Package Structure

```
timeseries/
├── __init__.py      - Package exports (TimeseriesBase, timeseries_bp, start_collector, etc.)
├── config.py        - Base class and timeseries definitions (auto-discovery)
├── db.py            - SQLite database manager for timeseries data storage
├── routes.py        - Flask Blueprint with all REST API endpoints
└── collector.py     - Background thread for automatic data collection
```

**Related frontend files:**
- `templates/charts.html` - Chart visualization page template
- `static/charts.js` - Frontend chart rendering and interaction logic
- `static/charts.css` - Styling for the charts page

### Database Schema

**`timeseries_data`** table:
- `id`: Auto-increment primary key
- `timeseries_id`: Identifier for the timeseries (TEXT)
- `timestamp`: Unix timestamp in seconds (REAL)
- `value`: The data value (REAL, nullable)
- Indexed by (timeseries_id, timestamp) for fast queries

**`timeseries_settings`** table:
- `key`: Setting name (TEXT, primary key)
- `value`: Setting value (TEXT)

## Adding a New Timeseries

Create a new class in `timeseries/config.py` that inherits from `TimeseriesBase`:

```python
class MyCustomTimeseries(TimeseriesBase):
    """Description of your timeseries."""

    def getName(self) -> str:
        return "My Custom Metric"

    def getCurrentValue(self) -> Any:
        # Your logic to get the current value
        # Return None if unavailable
        try:
            value = get_my_metric()  # Your custom function
            return round(value, 2)
        except:
            return None

    def getUnits(self) -> str:
        return "psi"  # or "%", "°F", "MB", etc.
```

That's it! The class is **automatically discovered** via `__init_subclass__` - no manual registration needed.

The framework handles everything else automatically:
- Data collection at configured intervals
- Database storage
- API exposure
- Chart rendering
- Multi-series grouping by units

## Built-in Timeseries Examples

The system comes with 5 example timeseries:

1. **CPU Temperature** (°F) - From psutil sensors
2. **GPU Temperature** (°F) - From vcgencmd on Raspberry Pi
3. **CPU Usage** (%) - CPU utilization percentage
4. **RAM Usage** (%) - Memory utilization percentage
5. **Disk Usage** (%) - Root filesystem utilization

## API Endpoints

All endpoints are prefixed based on the Blueprint registration.

### GET `/charts`
Serves the timeseries charts page.

### GET `/api/timeseries/list`
Returns list of all available timeseries with metadata.

Response:
```json
[
  {
    "id": "cpu_temperature",
    "name": "CPU Temperature",
    "units": "°F"
  },
  ...
]
```

### GET `/api/timeseries/data/<timeseries_id>`
Get data for a specific timeseries.

Query Parameters:
- `start` (optional): Start timestamp (Unix seconds)
- `end` (optional): End timestamp (Unix seconds)
- `limit` (optional): Max points if no range specified (default 1000)

Response:
```json
{
  "id": "cpu_temperature",
  "name": "CPU Temperature",
  "units": "°F",
  "data": [
    {"timestamp": 1234567890.0, "value": 120.5},
    {"timestamp": 1234567895.0, "value": 121.0},
    ...
  ]
}
```

### POST `/api/timeseries/data/batch`
Get data for multiple timeseries at once.

Request:
```json
{
  "timeseries_ids": ["cpu_temperature", "gpu_temperature"],
  "start": 1234567890.0,
  "end": 1234567900.0,
  "limit": 1000
}
```

### GET `/api/timeseries/current`
Get current (live) values for all timeseries (not from database).

### GET `/api/timeseries/settings`
Get all timeseries settings.

### POST `/api/timeseries/settings`
Update timeseries settings.

Request:
```json
{
  "sampling_rate_ms": 5000
}
```

## Configuration

### Sampling Rate

The data collection rate can be configured in the Charts page settings modal:
- **Range**: 1,000 - 60,000 ms (1 second - 1 minute)
- **Default**: 5,000 ms (5 seconds)
- **Storage**: Server-side in SQLite database

### Auto-Refresh Rate

Chart auto-refresh interval can be configured in the Charts page settings modal:
- **Range**: 5 - 300 seconds
- **Default**: 30 seconds
- **Storage**: Client-side in localStorage

## Advanced Customization

### Custom ID Generation

By default, the timeseries ID is generated from the name (lowercase, underscores, no special chars). You can override this:

```python
class MyTimeseries(TimeseriesBase):
    def getId(self) -> str:
        return "my_custom_id"

    def getName(self) -> str:
        return "My Custom Metric"

    # ... other methods
```

### Complex Value Retrieval

The `getCurrentValue()` method can perform any operation:

```python
def getCurrentValue(self) -> Any:
    try:
        # Read from a file
        with open('/sys/class/hwmon/hwmon0/temp1_input', 'r') as f:
            millidegrees = int(f.read().strip())
            celsius = millidegrees / 1000.0
            fahrenheit = (celsius * 9/5) + 32
            return round(fahrenheit, 1)
    except:
        return None  # Return None if unavailable
```

```python
def getCurrentValue(self) -> Any:
    try:
        # Call an external API
        response = requests.get('http://localhost:8080/api/stats', timeout=1)
        data = response.json()
        return data['pressure']
    except:
        return None
```

### Data Retention

You can manually clean up old data using the database manager:

```python
from timeseries import get_timeseries_db
from datetime import datetime, timedelta

db = get_timeseries_db()

# Delete data older than 30 days
thirty_days_ago = (datetime.now() - timedelta(days=30)).timestamp()
db.delete_old_data('cpu_temperature', thirty_days_ago)
```

## User Interface

### Charts Page (`/charts`)

The charts page provides:

1. **Series Selection**: Checkboxes grouped by units
2. **Time Range**:
   - Custom datetime pickers for start/end
   - Quick range buttons (1h, 6h, 24h, 1 week)
3. **Chart Updates**: Manual update button
4. **Auto-Refresh**: Toggle for automatic chart updates
5. **Settings**: Configure sampling rate and auto-refresh interval

### Chart Features

- **Interactive**: Zoom, pan, hover for details
- **Multi-Series**: Multiple timeseries on one chart (grouped by units)
- **Color-Coded**: Different colors for each series with legend
- **Responsive**: Adapts to screen size
- **Matrix Theme**: Matches the main dashboard aesthetic

## Navigation

- **Homepage → Charts**: Click the 📊 button at bottom-right of homepage
- **Charts → Homepage**: Click the 🏠 button at bottom-right of charts page

## Performance Considerations

- **Database Size**: SQLite can handle millions of datapoints efficiently
- **Query Performance**: Indexed by (timeseries_id, timestamp) for fast range queries
- **Memory Usage**: Charts load data on-demand, not all history at once
- **Sampling Rate**: Lower rates (longer intervals) reduce database growth

## Troubleshooting

### Charts show "No data available"

1. Check that the timeseries collector is running (should start automatically)
2. Verify data is being collected: Check the `timeseries.db` file exists and is growing
3. Ensure the selected time range includes collected data

### Value shows as NULL in database

- The `getCurrentValue()` method returned `None` or raised an exception
- Check the implementation of your timeseries class
- Verify any external dependencies (files, APIs, sensors) are available

### Collector not sampling at configured rate

- The collector reads the sampling rate from the database each loop
- Changes to sampling rate in settings take effect on the next collection cycle
- Verify the database is writable

## Future Enhancements

Potential additions (not yet implemented):

- Data export (CSV, JSON)
- Custom alerts/thresholds
- Statistical aggregations (min, max, avg over periods)
- Automatic data retention policies
- Chart templates/presets
- Real-time streaming updates via WebSocket
