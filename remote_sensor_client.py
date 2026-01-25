"""
Gateway client for receiving remote sensor data.

Connects to configured gateways, discovers sensors, receives data stream,
and maintains RemoteSensorTimeseries instances for the dashboard.
"""

import json
import logging
import socket
import threading
import time
from pathlib import Path
from typing import Callable

from remote_sensor_timeseries import RemoteSensorTimeseries

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# Protocol Constants (must match gateway_server.py)
# =============================================================================

MSG_TYPE_DISCOVER = "discover"
MSG_TYPE_SENSORS = "sensors"
MSG_TYPE_SUBSCRIBE = "subscribe"
MSG_TYPE_DATA = "data"


def build_message(msg_type: str, **kwargs) -> bytes:
    """Build a newline-terminated JSON message."""
    message = {"type": msg_type, **kwargs}
    return json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n"


def parse_message(data: bytes) -> dict | None:
    """Parse a JSON message."""
    try:
        return json.loads(data.strip().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


# =============================================================================
# Gateway Connection
# =============================================================================


class GatewayConnection:
    """Manages connection to a single gateway with auto-reconnect."""

    def __init__(
        self,
        host: str,
        port: int,
        on_sensors_discovered: Callable[[str, list[dict]], None],
        on_data_received: Callable[[list[dict]], None],
        reconnect_delay: float = 5.0,
    ):
        """
        Initialize gateway connection.

        Args:
            host: Gateway hostname or IP
            port: Gateway TCP port
            on_sensors_discovered: Callback(gateway_id, sensors_list) when discovery completes
            on_data_received: Callback(readings_list) when data arrives
            reconnect_delay: Seconds to wait before reconnecting on failure
        """
        self._host = host
        self._port = port
        self._on_sensors_discovered = on_sensors_discovered
        self._on_data_received = on_data_received
        self._reconnect_delay = reconnect_delay

        self._socket: socket.socket | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._gateway_id: str | None = None

    def start(self) -> None:
        """Start the background connection thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the connection thread."""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass

    @property
    def gateway_id(self) -> str | None:
        """The gateway ID (available after successful discovery)."""
        return self._gateway_id

    def _run(self) -> None:
        """Main connection loop with auto-reconnect."""
        while self._running:
            try:
                self._connect()
                self._discover()
                self._subscribe_and_stream()
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"Gateway {self._host}:{self._port} connection error: {e}")
            except Exception as e:
                logger.error(f"Gateway {self._host}:{self._port} unexpected error: {e}")
            finally:
                if self._socket:
                    try:
                        self._socket.close()
                    except Exception:
                        pass
                    self._socket = None

            if self._running:
                logger.info(
                    f"Reconnecting to {self._host}:{self._port} in {self._reconnect_delay}s"
                )
                time.sleep(self._reconnect_delay)

    def _connect(self) -> None:
        """Establish TCP connection."""
        logger.info(f"Connecting to gateway {self._host}:{self._port}")
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(30.0)
        self._socket.connect((self._host, self._port))
        logger.info(f"Connected to gateway {self._host}:{self._port}")

    def _send(self, data: bytes) -> None:
        """Send data to gateway."""
        if self._socket:
            self._socket.sendall(data)

    def _recv_line(self) -> bytes | None:
        """Receive a newline-terminated line."""
        if not self._socket:
            return None

        data = b""
        while self._running:
            chunk = self._socket.recv(1)
            if not chunk:
                return None  # Connection closed
            data += chunk
            if chunk == b"\n":
                return data

        return None

    def _discover(self) -> None:
        """Send discover request and process response."""
        self._send(build_message(MSG_TYPE_DISCOVER))

        response = self._recv_line()
        if not response:
            raise ConnectionError("No discovery response")

        message = parse_message(response)
        if not message or message.get("type") != MSG_TYPE_SENSORS:
            raise ConnectionError(f"Invalid discovery response: {response[:100]}")

        self._gateway_id = message.get("gateway_id", f"{self._host}:{self._port}")
        sensors = message.get("sensors", [])

        logger.info(
            f"Discovered {len(sensors)} sensors from gateway '{self._gateway_id}'"
        )

        # Notify callback
        self._on_sensors_discovered(self._gateway_id, sensors)

    def _subscribe_and_stream(self) -> None:
        """Subscribe to data stream and process updates."""
        self._send(build_message(MSG_TYPE_SUBSCRIBE))
        logger.info(f"Subscribed to data stream from '{self._gateway_id}'")

        while self._running:
            data = self._recv_line()
            if not data:
                raise ConnectionError("Connection closed")

            message = parse_message(data)
            if not message:
                logger.warning(f"Invalid message from gateway: {data[:100]}")
                continue

            if message.get("type") == MSG_TYPE_DATA:
                readings = message.get("readings", [])
                if readings:  # Ignore empty heartbeat messages
                    self._on_data_received(readings)


# =============================================================================
# Remote Sensor Manager
# =============================================================================


class RemoteSensorManager:
    """
    Manages all gateway connections and remote sensor timeseries.

    This is the main entry point for integrating remote sensors with the dashboard.
    """

    def __init__(self):
        self._connections: list[GatewayConnection] = []
        self._timeseries: dict[str, RemoteSensorTimeseries] = {}
        self._lock = threading.Lock()
        self._db = None  # Will be set when starting

    def load_config(self, config_path: str = "config/gateways.local.json") -> None:
        """Load gateway configuration from file."""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Gateway config not found: {config_path}")
            return

        with open(path) as f:
            config = json.load(f)

        gateways = config.get("gateways", [])
        reconnect_delay = config.get("reconnect_delay_sec", 5.0)

        for gw_config in gateways:
            host = gw_config.get("host")
            port = gw_config.get("port", 5000)

            if not host:
                logger.warning("Gateway config missing 'host', skipping")
                continue

            connection = GatewayConnection(
                host=host,
                port=port,
                on_sensors_discovered=self._on_sensors_discovered,
                on_data_received=self._on_data_received,
                reconnect_delay=reconnect_delay,
            )
            self._connections.append(connection)
            logger.info(f"Configured gateway: {host}:{port}")

    def start(self) -> None:
        """Start all gateway connections."""
        # Get database reference for direct inserts
        try:
            from timeseries_routes import get_timeseries_db
            self._db = get_timeseries_db()
        except ImportError:
            logger.warning("Could not import timeseries_routes, database writes disabled")

        for connection in self._connections:
            connection.start()

        logger.info(f"Started {len(self._connections)} gateway connection(s)")

    def stop(self) -> None:
        """Stop all gateway connections."""
        for connection in self._connections:
            connection.stop()
        logger.info("Stopped all gateway connections")

    def get_timeseries(self) -> list[RemoteSensorTimeseries]:
        """Get all discovered remote sensor timeseries."""
        with self._lock:
            return list(self._timeseries.values())

    def _on_sensors_discovered(self, gateway_id: str, sensors: list[dict]) -> None:
        """Callback when a gateway reports its sensors."""
        for sensor_info in sensors:
            sensor_id = sensor_info.get("id")
            if not sensor_id:
                continue

            with self._lock:
                if sensor_id not in self._timeseries:
                    # Create new timeseries
                    ts = RemoteSensorTimeseries(
                        sensor_id=sensor_id,
                        node_id=sensor_info.get("node_id", "unknown"),
                        name=sensor_info.get("name", sensor_id),
                        units=sensor_info.get("units", ""),
                        sensor_class=sensor_info.get("sensor_class", "Unknown"),
                        gateway_id=gateway_id,
                        is_local=sensor_info.get("is_local", False),
                    )
                    self._timeseries[sensor_id] = ts

                    # Register with the timeseries system
                    self._register_timeseries(ts)

                    logger.info(f"Discovered new sensor: {sensor_id}")

    def _on_data_received(self, readings: list[dict]) -> None:
        """Callback when a gateway sends data update."""
        datapoints = []

        for reading in readings:
            sensor_id = reading.get("id")
            value = reading.get("value")
            timestamp = reading.get("ts")

            if not sensor_id or timestamp is None:
                continue

            with self._lock:
                ts = self._timeseries.get(sensor_id)
                if ts:
                    # Update the timeseries cache
                    ts.update(value, timestamp)

                    # Prepare datapoint for database insert
                    if value is not None:
                        datapoints.append({
                            "timeseries_id": sensor_id,
                            "value": value,
                            "timestamp": timestamp,
                        })

        # Insert into database with source timestamps
        if datapoints and self._db:
            try:
                self._db.insert_datapoints_batch(datapoints)
            except Exception as e:
                logger.error(f"Database insert error: {e}")

    def _register_timeseries(self, ts: RemoteSensorTimeseries) -> None:
        """Register a timeseries with the global TIMESERIES list."""
        try:
            from timeseries_config import TIMESERIES, TIMESERIES_MAP

            if ts.getId() not in TIMESERIES_MAP:
                TIMESERIES.append(ts)
                TIMESERIES_MAP[ts.getId()] = ts
                logger.debug(f"Registered timeseries: {ts.getId()}")
        except ImportError:
            logger.warning("Could not import timeseries_config for registration")


# =============================================================================
# Module-level API
# =============================================================================

_remote_sensor_manager: RemoteSensorManager | None = None


def start_remote_sensors(config_path: str = "config/gateways.local.json") -> None:
    """
    Start the remote sensor manager.

    Call this during dashboard startup to enable remote sensors.

    Args:
        config_path: Path to gateways.json configuration file
    """
    global _remote_sensor_manager

    if _remote_sensor_manager is not None:
        logger.warning("Remote sensor manager already started")
        return

    _remote_sensor_manager = RemoteSensorManager()
    _remote_sensor_manager.load_config(config_path)
    _remote_sensor_manager.start()

    logger.info("Remote sensor manager started")


def stop_remote_sensors() -> None:
    """Stop the remote sensor manager."""
    global _remote_sensor_manager

    if _remote_sensor_manager:
        _remote_sensor_manager.stop()
        _remote_sensor_manager = None
        logger.info("Remote sensor manager stopped")


def get_remote_timeseries() -> list[RemoteSensorTimeseries]:
    """Get all remote sensor timeseries."""
    if _remote_sensor_manager:
        return _remote_sensor_manager.get_timeseries()
    return []
