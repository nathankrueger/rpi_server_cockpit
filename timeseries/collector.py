"""
Background timeseries data collector.

This module runs a background thread that periodically samples all configured
timeseries and stores the data in the database.
"""

import threading
import time

import app_state
from app_state import server_config_lock
from .config import get_all_timeseries
from .routes import get_timeseries_db


class TimeseriesCollector:
    """Background thread for collecting timeseries data."""

    def __init__(self):
        """Initialize the collector."""
        self.running = False
        self.thread = None
        self.db = None

    def start(self):
        """Start the background collection thread."""
        if self.running:
            print("Timeseries collector is already running")
            return

        self.running = True
        self.db = get_timeseries_db()
        self.thread = threading.Thread(target=self._collection_loop, daemon=True)
        self.thread.start()
        print("Timeseries collector started")

    def stop(self):
        """Stop the background collection thread."""
        if not self.running:
            return

        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("Timeseries collector stopped")

    def _collection_loop(self):
        """Main collection loop."""
        while self.running:
            try:
                # Get sampling interval from server config
                with server_config_lock:
                    sampling_rate_seconds = app_state.server_config['timeseries_sampling_interval']

                # Collect data from all timeseries
                datapoints = []
                for ts in get_all_timeseries():
                    try:
                        value = ts.getCurrentValue()
                        datapoints.append({
                            'timeseries_id': ts.getId(),
                            'value': value
                        })
                    except Exception as e:
                        print(f"Error collecting data from {ts.getName()}: {e}")

                # Batch insert all datapoints
                if datapoints:
                    self.db.insert_datapoints_batch(datapoints)

            except Exception as e:
                print(f"Error in timeseries collection loop: {e}")

            # Sleep for the configured sampling rate
            time.sleep(sampling_rate_seconds)


# Global collector instance
_collector = None


def start_collector():
    """Start the global timeseries collector."""
    global _collector
    if _collector is None:
        _collector = TimeseriesCollector()
    _collector.start()


def stop_collector():
    """Stop the global timeseries collector."""
    global _collector
    if _collector is not None:
        _collector.stop()
