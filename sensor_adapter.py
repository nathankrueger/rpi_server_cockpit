"""
Adapter module to expose data_log Sensors as Timeseries.

This module uses reflection to discover all Sensor classes from the data_log
package and wraps each sensor reading as a Timeseries. Since Sensors return
tuples (multiple values), each tuple element becomes a separate Timeseries.

New sensors added to data_log are automatically discovered without any code
changes to this module.
"""

from typing import Any
from timeseries_config import TimeseriesBase

# Sentinel to track if sensors have been loaded
_sensors_loaded = False
_sensor_timeseries: list[TimeseriesBase] = []
_initialization_errors: list[str] = []


class SensorTimeseries(TimeseriesBase):
    """
    Wraps a single value from a data_log Sensor as a Timeseries.

    Since Sensors can return multiple values (e.g., temperature, pressure, humidity),
    this class wraps one specific index of the sensor's read() tuple.
    """

    def __init__(self, sensor, index: int, name: str, units: str, sensor_class_name: str):
        """
        Args:
            sensor: An initialized Sensor instance
            index: Which tuple index to read from sensor.read()
            name: The name for this timeseries (from sensor.get_names()[index])
            units: The units for this timeseries (from sensor.get_units()[index])
            sensor_class_name: Name of the sensor class for categorization
        """
        self._sensor = sensor
        self._index = index
        self._name = name
        self._units = units
        self._sensor_class_name = sensor_class_name

    def getName(self) -> str:
        return self._name

    def getCurrentValue(self) -> Any:
        try:
            values = self._sensor.read()
            return values[self._index]
        except Exception:
            return None

    def getUnits(self) -> str:
        return self._units

    def getId(self) -> str:
        # Create a unique ID combining sensor class and value name
        base = f"{self._sensor_class_name}_{self._name}"
        return base.lower().replace(' ', '_').replace('(', '').replace(')', '')

    def getCategory(self) -> str:
        return "Sensors"

    def getTags(self) -> list:
        return ["sensor", "hardware", self._sensor_class_name.lower()]

    def getDescription(self) -> str:
        return f"{self._name} from {self._sensor_class_name} sensor"


def _create_timeseries_from_sensor(sensor_class) -> list[SensorTimeseries]:
    """
    Create Timeseries instances from a Sensor class.

    Instantiates the sensor, initializes it, and creates one Timeseries
    per value in the sensor's read() tuple.

    Args:
        sensor_class: A Sensor subclass type

    Returns:
        List of SensorTimeseries instances, one per sensor value
    """
    timeseries_list = []

    try:
        # Instantiate and initialize the sensor
        sensor = sensor_class()
        sensor.init()

        # Get metadata
        names = sensor.get_names()
        units = sensor.get_units()
        class_name = sensor_class.__name__

        # Create a Timeseries for each value the sensor provides
        for i, (name, unit) in enumerate(zip(names, units)):
            ts = SensorTimeseries(
                sensor=sensor,
                index=i,
                name=name,
                units=unit,
                sensor_class_name=class_name
            )
            timeseries_list.append(ts)

    except Exception as e:
        error_msg = f"Failed to initialize {sensor_class.__name__}: {e}"
        _initialization_errors.append(error_msg)
        print(f"[sensor_adapter] {error_msg}")

    return timeseries_list


def load_sensor_timeseries() -> list[TimeseriesBase]:
    """
    Discover and load all Sensors from data_log as Timeseries.

    Uses reflection to find all Sensor subclasses, instantiates them,
    and wraps each sensor value as a Timeseries.

    Returns:
        List of Timeseries instances wrapping all discovered sensors
    """
    global _sensors_loaded, _sensor_timeseries, _initialization_errors

    if _sensors_loaded:
        return _sensor_timeseries

    _sensor_timeseries = []
    _initialization_errors = []

    try:
        import inspect
        import sensors as sensors_module
        from sensors import Sensor

        # Discover all Sensor subclasses via reflection
        sensor_classes = []
        for name, obj in inspect.getmembers(sensors_module, inspect.isclass):
            if issubclass(obj, Sensor) and obj is not Sensor:
                sensor_classes.append(obj)

        print(f"[sensor_adapter] Discovered {len(sensor_classes)} sensor class(es)")

        for sensor_class in sensor_classes:
            timeseries = _create_timeseries_from_sensor(sensor_class)
            _sensor_timeseries.extend(timeseries)
            if timeseries:
                print(f"[sensor_adapter] Loaded {sensor_class.__name__}: {len(timeseries)} timeseries")

    except ImportError as e:
        error_msg = f"sensors module not installed: {e}"
        _initialization_errors.append(error_msg)
        print(f"[sensor_adapter] {error_msg}")
        print("[sensor_adapter] Run: pip install -e /path/to/data_log")

    except Exception as e:
        error_msg = f"Error loading sensors: {e}"
        _initialization_errors.append(error_msg)
        print(f"[sensor_adapter] {error_msg}")

    _sensors_loaded = True
    print(f"[sensor_adapter] Total sensor timeseries loaded: {len(_sensor_timeseries)}")

    return _sensor_timeseries


def get_sensor_timeseries() -> list[TimeseriesBase]:
    """
    Get all sensor-based Timeseries instances.

    Call load_sensor_timeseries() first, or this will return an empty list.
    """
    return _sensor_timeseries


def get_initialization_errors() -> list[str]:
    """
    Get any errors that occurred during sensor initialization.

    Useful for diagnostics when sensors fail to load.
    """
    return _initialization_errors
