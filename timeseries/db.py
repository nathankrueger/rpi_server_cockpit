"""
Database manager for timeseries data storage.

This module handles all database operations for storing and retrieving
timeseries data points and settings.
"""

import sqlite3
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional
import json


class TimeseriesDB:
    """Thread-safe SQLite database manager for timeseries data."""

    def __init__(self, db_path: str = 'timeseries.db'):
        """
        Initialize the database manager.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self.write_lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize database schema."""
        with self.write_lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()

                # Enable database optimizations for better compression and performance
                # Auto-vacuum: automatically reclaim space from deleted data
                cursor.execute('PRAGMA auto_vacuum = FULL')
                # Larger page size can improve compression ratio (4KB is good for timeseries)
                cursor.execute('PRAGMA page_size = 4096')
                # WAL mode for better concurrent access and performance
                cursor.execute('PRAGMA journal_mode = WAL')

                # Table for timeseries data points
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS timeseries_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timeseries_id TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        value REAL,
                        UNIQUE(timeseries_id, timestamp)
                    )
                ''')

                # Covering index for range queries: including `value` lets
                # SQLite answer chart queries from the index alone. Without it
                # every matching index entry needs a separate table lookup,
                # which dominated query time (3.7s -> 1.6s on a 30-day range).
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_ts_covering
                    ON timeseries_data(timeseries_id, timestamp, value)
                ''')

                # Superseded by the covering index above, and identical to the
                # implicit index behind UNIQUE(timeseries_id, timestamp), so it
                # only cost disk and write throughput.
                cursor.execute('DROP INDEX IF EXISTS idx_timeseries_timestamp')

                # Table for timeseries settings
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS timeseries_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                ''')

                # Set default sampling rate if not exists
                cursor.execute('''
                    INSERT OR IGNORE INTO timeseries_settings (key, value)
                    VALUES ('sampling_rate_ms', '5000')
                ''')

                # Table for external timeseries metadata (remote sensors, etc.)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS external_timeseries (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        units TEXT NOT NULL DEFAULT '',
                        category TEXT NOT NULL DEFAULT 'External',
                        tags TEXT NOT NULL DEFAULT '[]',
                        description TEXT NOT NULL DEFAULT '',
                        gateway TEXT DEFAULT NULL
                    )
                ''')

                conn.commit()
            finally:
                conn.close()

    def insert_datapoint(self, timeseries_id: str, value: Any, timestamp: Optional[float] = None):
        """
        Insert a single datapoint.

        Args:
            timeseries_id: ID of the timeseries
            value: The value to store (will be converted to float, None stored as NULL)
            timestamp: Unix timestamp (seconds), defaults to current time
        """
        if timestamp is None:
            timestamp = datetime.now().timestamp()

        # Convert value to float, or None if conversion fails
        if value is None:
            float_value = None
        else:
            try:
                float_value = float(value)
            except (TypeError, ValueError):
                float_value = None

        with self.write_lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO timeseries_data (timeseries_id, timestamp, value)
                    VALUES (?, ?, ?)
                ''', (timeseries_id, timestamp, float_value))
                conn.commit()
            finally:
                conn.close()

    def insert_datapoints_batch(self, datapoints: List[Dict[str, Any]]):
        """
        Insert multiple datapoints in a single transaction.

        Args:
            datapoints: List of dicts with 'timeseries_id', 'value', and optionally 'timestamp'
        """
        with self.write_lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                for dp in datapoints:
                    timeseries_id = dp['timeseries_id']
                    value = dp['value']
                    timestamp = dp.get('timestamp', datetime.now().timestamp())

                    # Convert value to float
                    if value is None:
                        float_value = None
                    else:
                        try:
                            float_value = float(value)
                        except (TypeError, ValueError):
                            float_value = None

                    cursor.execute('''
                        INSERT OR REPLACE INTO timeseries_data (timeseries_id, timestamp, value)
                        VALUES (?, ?, ?)
                    ''', (timeseries_id, timestamp, float_value))
                conn.commit()
            finally:
                conn.close()

    def query_range(self, timeseries_id: str, start_time: float, end_time: float,
                   max_points: Optional[int] = None,
                   algorithm: str = 'lttb') -> List[Dict[str, Any]]:
        """
        Query datapoints for a timeseries within a time range.

        Args:
            timeseries_id: ID of the timeseries
            start_time: Start timestamp (Unix seconds)
            end_time: End timestamp (Unix seconds)
            max_points: Optional maximum number of points to return (downsampled)
            algorithm: Downsampling algorithm - 'lttb' (preserves peaks) or 'average' (smooths outliers)

        Returns:
            List of dicts with 'timestamp' and 'value' keys
        """
        # No lock needed for reads - WAL mode handles concurrent read access
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            if max_points and max_points >= 3 and self._bucketing_pays(
                    cursor, timeseries_id, start_time, end_time, max_points):
                # Stage 1: reduce inside SQLite. Without this every row in the
                # range is shipped into Python and turned into a dict before
                # being thrown away, so max_points capped the response but not
                # the work - a 30-day window cost the same whether you asked
                # for 100 points or 10,000.
                data = self._query_bucketed(cursor, timeseries_id, start_time,
                                            end_time, max_points, algorithm)
            else:
                cursor.execute('''
                    SELECT timestamp, value
                    FROM timeseries_data
                    WHERE timeseries_id = ? AND timestamp >= ? AND timestamp <= ?
                    ORDER BY timestamp ASC
                ''', (timeseries_id, start_time, end_time))
                data = [
                    {'timestamp': row['timestamp'], 'value': row['value']}
                    for row in cursor.fetchall()
                ]

            # Stage 2: existing post-processing, now over a few thousand
            # candidate points instead of the entire range.
            if algorithm == 'average' and len(data) > 2:
                data = self._smooth_moving_average(data)

            if max_points and len(data) > max_points:
                data = self._downsample_lttb(data, max_points)

            return data
        finally:
            conn.close()

    # Stage-1 oversampling factor. LTTB picks extreme points, so handing it a
    # candidate set of per-bucket extremes at this multiple of the target gives
    # visually equivalent output to running it over the raw range.
    _BUCKET_OVERSAMPLE = 4

    # Floor on stage-1 buckets. Cost is dominated by the index scan rather than
    # the bucket count, so a small max_points can afford far finer buckets than
    # 4x - and needs them, or aggressive downsampling starts losing spikes that
    # the old full-range LTTB would have kept.
    _MIN_BUCKETS = 8000

    # Aggregating costs several times more per row than a plain index scan, so
    # bucketing only wins if it discards most of the range. Each bucket can emit
    # two points, so this is the reduction factor below which the plain path is
    # cheaper.
    _BUCKET_MIN_GAIN = 2

    # Rows sampled to estimate a series' cadence. Small enough to be free.
    _CADENCE_SAMPLE = 100

    def _bucketing_pays(self, cursor, timeseries_id: str, start_time: float,
                        end_time: float, max_points: int) -> bool:
        """
        Decide whether SQL bucketing is worth its overhead for this range.

        Counting the range outright would cost as much as the query we are
        trying to avoid, so estimate instead: sample the most recent handful of
        timestamps to get the series' cadence, and extrapolate over the span.
        A sample shorter than requested means the range is genuinely small and
        the count is exact.
        """
        span = end_time - start_time
        if span <= 0:
            return False

        cursor.execute('''
            SELECT timestamp FROM timeseries_data
            WHERE timeseries_id = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (timeseries_id, start_time, end_time, self._CADENCE_SAMPLE))
        sample = [r['timestamp'] for r in cursor.fetchall()]

        buckets = max(max_points * self._BUCKET_OVERSAMPLE, self._MIN_BUCKETS)
        if len(sample) < self._CADENCE_SAMPLE:
            estimated = len(sample)          # exact - the range holds this many
        else:
            cadence = (sample[0] - sample[-1]) / (len(sample) - 1)
            if cadence <= 0:
                return True                  # degenerate; bucketing is the safe bet
            estimated = span / cadence

        return estimated > self._BUCKET_MIN_GAIN * buckets

    def _query_bucketed(self, cursor, timeseries_id: str, start_time: float,
                        end_time: float, max_points: int,
                        algorithm: str) -> List[Dict[str, Any]]:
        """
        Reduce a range to ~max_points candidates using SQLite aggregation.

        Splits the range into buckets and collapses each one, so the number of
        rows crossing into Python is bounded by the bucket count rather than by
        how much data the range happens to contain.

        For 'lttb' each bucket contributes its minimum and maximum value, which
        keeps spikes intact - a plain per-bucket average silently clips them.
        The extreme *values* are exact; each is paired with the bucket's first
        or last timestamp, so a point's x-position can be off by at most one
        bucket width (a fraction of a pixel at this oversampling).

        Buckets holding a single row pass through untouched, so ranges smaller
        than the bucket count are returned exactly as stored.
        """
        span = end_time - start_time
        if span <= 0:
            # Degenerate range - nothing to bucket. Fall back to the plain
            # query so an exact-timestamp lookup still returns its row.
            cursor.execute('''
                SELECT timestamp, value
                FROM timeseries_data
                WHERE timeseries_id = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
            ''', (timeseries_id, start_time, end_time))
            return [{'timestamp': r['timestamp'], 'value': r['value']}
                    for r in cursor.fetchall()]

        buckets = max(max_points * self._BUCKET_OVERSAMPLE, self._MIN_BUCKETS)
        width = span / buckets

        if algorithm == 'average':
            # 'average' already asks for smoothing, so per-bucket means match
            # the requested semantics and halve the returned point count.
            cursor.execute('''
                SELECT avg(timestamp) AS t, avg(value) AS v
                FROM timeseries_data
                WHERE timeseries_id = ? AND timestamp >= ? AND timestamp <= ?
                GROUP BY cast((timestamp - ?) / ? AS INT)
                ORDER BY t
            ''', (timeseries_id, start_time, end_time, start_time, width))
            return [{'timestamp': r['t'], 'value': r['v']} for r in cursor.fetchall()]

        cursor.execute('''
            SELECT min(timestamp) AS t_first, max(timestamp) AS t_last,
                   min(value) AS v_min, max(value) AS v_max, count(*) AS n
            FROM timeseries_data
            WHERE timeseries_id = ? AND timestamp >= ? AND timestamp <= ?
            GROUP BY cast((timestamp - ?) / ? AS INT)
            ORDER BY t_first
        ''', (timeseries_id, start_time, end_time, start_time, width))

        data: List[Dict[str, Any]] = []
        for row in cursor.fetchall():
            v_min, v_max = row['v_min'], row['v_max']
            if v_min is None:
                # Bucket contained only NULL readings; keep the gap visible.
                data.append({'timestamp': row['t_first'], 'value': None})
            elif row['n'] == 1 or v_min == v_max:
                data.append({'timestamp': row['t_first'], 'value': v_min})
            else:
                data.append({'timestamp': row['t_first'], 'value': v_min})
                data.append({'timestamp': row['t_last'], 'value': v_max})
        return data

    def _downsample_lttb(self, data: List[Dict[str, Any]], threshold: int) -> List[Dict[str, Any]]:
        """
        Downsample data using the Largest Triangle Three Buckets (LTTB) algorithm.

        This algorithm preserves the visual shape of the data by selecting points that
        form the largest triangles, which captures peaks, valleys, and trends effectively.

        Args:
            data: List of datapoints with 'timestamp' and 'value' keys
            threshold: Target number of datapoints in output

        Returns:
            Downsampled list of datapoints
        """
        if len(data) <= threshold or threshold < 3:
            return data

        # Always include first and last points
        sampled = [data[0]]

        # Bucket size (number of datapoints in each bucket)
        bucket_size = (len(data) - 2) / (threshold - 2)

        point_index = 0

        for i in range(threshold - 2):
            # Calculate point average for next bucket (for area calculation)
            avg_range_start = int((i + 1) * bucket_size) + 1
            avg_range_end = min(int((i + 2) * bucket_size) + 1, len(data))

            avg_x = 0.0
            avg_y = 0.0
            avg_range_length = avg_range_end - avg_range_start

            if avg_range_length > 0:
                for j in range(avg_range_start, avg_range_end):
                    avg_x += data[j]['timestamp']
                    # Handle None values by treating them as 0 for averaging
                    avg_y += data[j]['value'] if data[j]['value'] is not None else 0
                avg_x /= avg_range_length
                avg_y /= avg_range_length
            else:
                # Edge case: use the last point
                avg_x = data[-1]['timestamp']
                avg_y = data[-1]['value'] if data[-1]['value'] is not None else 0

            # Get the range for this bucket
            range_offs = int(i * bucket_size) + 1
            range_to = int((i + 1) * bucket_size) + 1

            # Point a (previous selected point)
            point_a_x = sampled[-1]['timestamp']
            point_a_y = sampled[-1]['value'] if sampled[-1]['value'] is not None else 0

            max_area = -1.0
            max_area_point = range_offs

            # Find point in current bucket that forms largest triangle
            for j in range(range_offs, min(range_to, len(data))):
                point_val = data[j]['value'] if data[j]['value'] is not None else 0

                # Calculate triangle area
                area = abs(
                    (point_a_x - avg_x) * (point_val - point_a_y) -
                    (point_a_x - data[j]['timestamp']) * (avg_y - point_a_y)
                ) * 0.5

                if area > max_area:
                    max_area = area
                    max_area_point = j

            sampled.append(data[max_area_point])

        # Always include last point
        sampled.append(data[-1])

        return sampled

    def _smooth_moving_average(self, data: List[Dict[str, Any]], window: int = 5) -> List[Dict[str, Any]]:
        """
        Apply a centered moving average to smooth out outliers and spikes.

        Each interior point's value is replaced with the mean of its surrounding
        window. This dampens single-point spikes and short transients while
        preserving the overall trend. Point count stays the same — timestamps
        are unchanged.

        Args:
            data: List of datapoints with 'timestamp' and 'value' keys
            window: Number of points in the averaging window (must be odd, default 5)

        Returns:
            Smoothed list of datapoints (same length as input)
        """
        n = len(data)
        if n <= window:
            return data

        half = window // 2
        smoothed = []

        for i in range(n):
            start = max(0, i - half)
            end = min(n, i + half + 1)

            total = 0.0
            count = 0
            for j in range(start, end):
                val = data[j]['value']
                total += val if val is not None else 0
                count += 1

            smoothed.append({
                'timestamp': data[i]['timestamp'],
                'value': round(total / count, 4) if count > 0 else None
            })

        return smoothed

    def query_latest(self, timeseries_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Query the latest N datapoints for a timeseries.

        Args:
            timeseries_id: ID of the timeseries
            limit: Maximum number of points to return

        Returns:
            List of dicts with 'timestamp' and 'value' keys
        """
        # No lock needed for reads - WAL mode handles concurrent read access
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp, value
                FROM timeseries_data
                WHERE timeseries_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (timeseries_id, limit))

            # Reverse to get chronological order
            return list(reversed([
                {'timestamp': row['timestamp'], 'value': row['value']}
                for row in cursor.fetchall()
            ]))
        finally:
            conn.close()

    def delete_old_data(self, timeseries_id: str, older_than: float):
        """
        Delete datapoints older than a given timestamp.

        Args:
            timeseries_id: ID of the timeseries
            older_than: Unix timestamp - delete points older than this
        """
        with self.write_lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM timeseries_data
                    WHERE timeseries_id = ? AND timestamp < ?
                ''', (timeseries_id, older_than))
                conn.commit()
            finally:
                conn.close()

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value.

        Args:
            key: Setting key
            default: Default value if key doesn't exist

        Returns:
            Setting value (as string) or default
        """
        # No lock needed for reads - WAL mode handles concurrent read access
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM timeseries_settings WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row['value'] if row else default
        finally:
            conn.close()

    def set_setting(self, key: str, value: Any):
        """
        Set a setting value.

        Args:
            key: Setting key
            value: Setting value (will be converted to string)
        """
        with self.write_lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO timeseries_settings (key, value)
                    VALUES (?, ?)
                ''', (key, str(value)))
                conn.commit()
            finally:
                conn.close()

    def get_all_settings(self) -> Dict[str, str]:
        """
        Get all settings as a dictionary.

        Returns:
            Dict mapping setting keys to values
        """
        # No lock needed for reads - WAL mode handles concurrent read access
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT key, value FROM timeseries_settings')
            return {row['key']: row['value'] for row in cursor.fetchall()}
        finally:
            conn.close()

    def vacuum(self):
        """
        Compact the database and reclaim unused space.
        This is safe to run and won't lose any data.
        Should be run periodically (e.g., weekly) for maintenance.
        """
        with self.write_lock:
            conn = self._get_connection()
            try:
                print("Running VACUUM on timeseries database...")
                conn.execute('VACUUM')
                print("VACUUM completed successfully")
            finally:
                conn.close()

    def optimize_existing_database(self):
        """
        Apply optimization settings to an existing database.
        This is safe and won't lose data, but requires a VACUUM to take full effect.
        """
        with self.write_lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()

                # Check current settings
                cursor.execute('PRAGMA auto_vacuum')
                current_auto_vacuum = cursor.fetchone()[0]

                cursor.execute('PRAGMA journal_mode')
                current_journal_mode = cursor.fetchone()[0]

                print(f"Current auto_vacuum: {current_auto_vacuum}, journal_mode: {current_journal_mode}")

                # Apply WAL mode (can be changed on existing DB)
                if current_journal_mode != 'wal':
                    cursor.execute('PRAGMA journal_mode = WAL')
                    print("Enabled WAL journal mode")

                # Auto-vacuum requires VACUUM to apply (can't change on existing DB without it)
                if current_auto_vacuum != 1:  # 1 = FULL
                    cursor.execute('PRAGMA auto_vacuum = FULL')
                    print("Set auto_vacuum = FULL (requires VACUUM to take effect)")
                    # Run VACUUM to apply the auto_vacuum setting
                    cursor.execute('VACUUM')
                    print("VACUUM completed - auto_vacuum is now active")

                conn.commit()
                print("Database optimization complete")
            finally:
                conn.close()

    def get_database_size(self) -> int:
        """
        Get the current database file size in bytes.

        Returns:
            Database size in bytes
        """
        import os
        try:
            return os.path.getsize(self.db_path)
        except Exception:
            return 0

    def register_external_timeseries(self, timeseries_id: str, name: str, units: str = '',
                                      category: str = 'External', tags: List[str] = None,
                                      description: str = '', gateway: str = None) -> bool:
        """
        Register an external timeseries (e.g., from a remote sensor).

        Args:
            timeseries_id: Unique ID for this timeseries
            name: Display name
            units: Unit of measurement (e.g., "°F", "%")
            category: Category for grouping (default: "External")
            tags: List of searchable tags
            description: Human-readable description
            gateway: Optional gateway ID that provides this timeseries

        Returns:
            True if newly registered, False if already existed (updated)
        """
        if tags is None:
            tags = []

        with self.write_lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                # Check if it already exists
                cursor.execute('SELECT id FROM external_timeseries WHERE id = ?', (timeseries_id,))
                existed = cursor.fetchone() is not None

                cursor.execute('''
                    INSERT OR REPLACE INTO external_timeseries (id, name, units, category, tags, description, gateway)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (timeseries_id, name, units, category, json.dumps(tags), description, gateway))
                conn.commit()
                return not existed
            finally:
                conn.close()

    def get_external_timeseries(self, timeseries_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for an external timeseries.

        Args:
            timeseries_id: ID of the timeseries

        Returns:
            Dict with id, name, units, category, tags, description, gateway or None if not found
        """
        # No lock needed for reads - WAL mode handles concurrent read access
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, name, units, category, tags, description, gateway
                FROM external_timeseries WHERE id = ?
            ''', (timeseries_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'id': row['id'],
                    'name': row['name'],
                    'units': row['units'],
                    'category': row['category'],
                    'tags': json.loads(row['tags']),
                    'description': row['description'],
                    'gateway': row['gateway']
                }
            return None
        finally:
            conn.close()

    def list_external_timeseries(self) -> List[Dict[str, Any]]:
        """
        List all registered external timeseries.

        Returns:
            List of dicts with id, name, units, category, tags, description, gateway
        """
        # No lock needed for reads - WAL mode handles concurrent read access
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, name, units, category, tags, description, gateway
                FROM external_timeseries ORDER BY name
            ''')
            return [
                {
                    'id': row['id'],
                    'name': row['name'],
                    'units': row['units'],
                    'category': row['category'],
                    'tags': json.loads(row['tags']),
                    'description': row['description'],
                    'gateway': row['gateway']
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def delete_external_timeseries(self, timeseries_id: str) -> bool:
        """
        Delete an external timeseries registration (does not delete its data).

        Args:
            timeseries_id: ID of the timeseries to delete

        Returns:
            True if deleted, False if not found
        """
        with self.write_lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM external_timeseries WHERE id = ?', (timeseries_id,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def query_minmax(self, timeseries_id: str, start_time: float, end_time: float) -> Optional[Dict[str, Any]]:
        """
        Query min and max values for a timeseries within a time range.

        Args:
            timeseries_id: ID of the timeseries
            start_time: Start timestamp (Unix seconds)
            end_time: End timestamp (Unix seconds)

        Returns:
            Dict with 'min' and 'max' keys, or None if no data found
        """
        # No lock needed for reads - WAL mode handles concurrent read access
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT MIN(value) as min_val, MAX(value) as max_val
                FROM timeseries_data
                WHERE timeseries_id = ? AND timestamp >= ? AND timestamp <= ? AND value IS NOT NULL
            ''', (timeseries_id, start_time, end_time))

            row = cursor.fetchone()
            if row and row['min_val'] is not None:
                return {
                    'min': row['min_val'],
                    'max': row['max_val']
                }
            return None
        finally:
            conn.close()

    def query_minmax_batch(self, timeseries_ids: List[str], start_time: float, end_time: float) -> Dict[str, Dict[str, Any]]:
        """
        Query min, max, and oldest values for multiple timeseries within a time range.

        Args:
            timeseries_ids: List of timeseries IDs
            start_time: Start timestamp (Unix seconds)
            end_time: End timestamp (Unix seconds)

        Returns:
            Dict mapping timeseries_id to {'min': value, 'max': value, 'oldest': value}
        """
        results = {}
        # No lock needed for reads - WAL mode handles concurrent read access
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            for ts_id in timeseries_ids:
                # Get min and max
                cursor.execute('''
                    SELECT MIN(value) as min_val, MAX(value) as max_val
                    FROM timeseries_data
                    WHERE timeseries_id = ? AND timestamp >= ? AND timestamp <= ? AND value IS NOT NULL
                ''', (ts_id, start_time, end_time))

                row = cursor.fetchone()
                if row and row['min_val'] is not None:
                    # Get the oldest value in the range for trend calculation
                    cursor.execute('''
                        SELECT value
                        FROM timeseries_data
                        WHERE timeseries_id = ? AND timestamp >= ? AND timestamp <= ? AND value IS NOT NULL
                        ORDER BY timestamp ASC
                        LIMIT 1
                    ''', (ts_id, start_time, end_time))
                    oldest_row = cursor.fetchone()
                    oldest_val = oldest_row['value'] if oldest_row else None

                    results[ts_id] = {
                        'min': row['min_val'],
                        'max': row['max_val'],
                        'oldest': oldest_val
                    }
            return results
        finally:
            conn.close()
