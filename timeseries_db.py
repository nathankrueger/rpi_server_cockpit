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

    def query_range(self, timeseries_id: str, start_time: float, end_time: float) -> List[Dict[str, Any]]:
        """
        Query datapoints for a timeseries within a time range.

        Args:
            timeseries_id: ID of the timeseries
            start_time: Start timestamp (Unix seconds)
            end_time: End timestamp (Unix seconds)

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

                return [
                    {'timestamp': row['timestamp'], 'value': row['value']}
                    for row in cursor.fetchall()
                ]
            finally:
                conn.close()

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
