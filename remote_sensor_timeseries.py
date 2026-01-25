"""
Remote sensor timeseries wrapper for gateway-sourced sensor data.

RemoteSensorTimeseries wraps a sensor reading received from a gateway
and exposes it as a TimeseriesBase for the dashboard. Unlike local sensors,
these don't read hardware directly - they return cached values updated
by the gateway client.
"""

import threading
from typing import Any

from timeseries_config import TimeseriesBase


class RemoteSensorTimeseries(TimeseriesBase):
    """
    Timeseries wrapper for a remote sensor reading.

    Unlike local sensors, this doesn't read hardware directly.
    Instead, it returns cached values updated by the gateway client.
    The source timestamp from the original reading is preserved.
    """

    # Don't auto-register - these are created dynamically by the gateway client
    _exclude_from_discovery = True

    def __init__(
        self,
        sensor_id: str,
        node_id: str,
        name: str,
        units: str,
        sensor_class: str,
        gateway_id: str,
        is_local: bool = False,
    ):
        """
        Initialize a remote sensor timeseries.

        Args:
            sensor_id: Unique identifier (e.g., "patio_bme280_temperature")
            node_id: Node that owns this sensor (e.g., "patio")
            name: Display name of the reading (e.g., "Temperature")
            units: Units of measurement (e.g., "°F")
            sensor_class: Name of the sensor class (e.g., "BME280")
            gateway_id: Gateway this sensor is accessed through
            is_local: True if this sensor is local to the gateway (not via LoRa)
        """
        self._sensor_id = sensor_id
        self._node_id = node_id
        self._name = name
        self._units = units
        self._sensor_class = sensor_class
        self._gateway_id = gateway_id
        self._is_local = is_local

        # Cached value (updated by gateway client)
        self._value: float | None = None
        self._timestamp: float | None = None
        self._lock = threading.Lock()

    def update(self, value: float | None, timestamp: float) -> None:
        """
        Update the cached value. Called by the gateway client when new data arrives.

        Args:
            value: The new sensor value (or None if unavailable)
            timestamp: The source timestamp from the original reading
        """
        with self._lock:
            self._value = value
            self._timestamp = timestamp

    def getCurrentValue(self) -> Any:
        """Return the cached value (for real-time display)."""
        with self._lock:
            return self._value

    def getSourceTimestamp(self) -> float | None:
        """
        Return the timestamp from the source node.

        This is the time the reading was taken, not when we received it.
        Used by the collector for database storage.
        """
        with self._lock:
            return self._timestamp

    def getName(self) -> str:
        """Return display name including node ID for disambiguation."""
        return f"{self._node_id} {self._name}"

    def getId(self) -> str:
        """Return the unique sensor ID."""
        return self._sensor_id

    def getUnits(self) -> str:
        """Return the units of measurement."""
        return self._units

    def getCategory(self) -> str:
        """Return category for organization."""
        return "Remote Sensors"

    def getTags(self) -> list:
        """Return searchable tags."""
        tags = ["remote", "sensor", self._node_id, self._gateway_id]
        if self._is_local:
            tags.append("gateway-local")
        else:
            tags.append("lora")
        return tags

    def getDescription(self) -> str:
        """Return human-readable description."""
        location = "gateway-local" if self._is_local else "remote"
        return f"{self._name} from {location} {self._sensor_class} on {self._node_id}"

    # Additional properties for debugging/diagnostics

    @property
    def node_id(self) -> str:
        """The node this sensor belongs to."""
        return self._node_id

    @property
    def gateway_id(self) -> str:
        """The gateway this sensor is accessed through."""
        return self._gateway_id

    @property
    def sensor_class(self) -> str:
        """The sensor class name."""
        return self._sensor_class

    @property
    def is_local(self) -> bool:
        """Whether this sensor is local to the gateway (vs remote via LoRa)."""
        return self._is_local
