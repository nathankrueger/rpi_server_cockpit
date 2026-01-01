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
        self.lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize database schema."""
        with self.lock:
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

                # Index for efficient querying by timeseries_id and timestamp
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_timeseries_timestamp
                    ON timeseries_data(timeseries_id, timestamp)
                ''')

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

        with self.lock:
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
        with self.lock:
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
                   max_points: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Query datapoints for a timeseries within a time range.

        Args:
            timeseries_id: ID of the timeseries
            start_time: Start timestamp (Unix seconds)
            end_time: End timestamp (Unix seconds)
            max_points: Optional maximum number of points to return (uses LTTB downsampling if set)

        Returns:
            List of dicts with 'timestamp' and 'value' keys
        """
        with self.lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
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

                # Apply downsampling if needed
                if max_points and len(data) > max_points:
                    data = self._downsample_lttb(data, max_points)

                return data
            finally:
                conn.close()

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

    def query_latest(self, timeseries_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Query the latest N datapoints for a timeseries.

        Args:
            timeseries_id: ID of the timeseries
            limit: Maximum number of points to return

        Returns:
            List of dicts with 'timestamp' and 'value' keys
        """
        with self.lock:
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
        with self.lock:
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
        with self.lock:
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
        with self.lock:
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
        with self.lock:
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
        with self.lock:
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
        with self.lock:
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
