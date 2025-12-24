"""
Timeseries configuration for the Raspberry Pi Dashboard.

This module provides a base class for defining timeseries data sources
and a centralized registry of all configured timeseries.

To add a new timeseries:
1. Create a class that inherits from TimeseriesBase
2. Implement getName(), getCurrentValue(), and getUnits()
3. Add an instance to the TIMESERIES list
"""

from abc import ABC, abstractmethod
from typing import Any
import psutil


class TimeseriesBase(ABC):
    """Base class for all timeseries data sources."""

    @abstractmethod
    def getName(self) -> str:
        """
        Get the display name of this timeseries.

        Returns:
            str: Human-readable name for the timeseries
        """
        pass

    @abstractmethod
    def getCurrentValue(self) -> Any:
        """
        Get the current value of this timeseries.

        Returns:
            Any: Current value (typically float, int, or None if unavailable)
        """
        pass

    @abstractmethod
    def getUnits(self) -> str:
        """
        Get the units of measurement for this timeseries.

        Returns:
            str: Unit string (e.g., "°F", "MB", "%", "psi")
        """
        pass

    def getId(self) -> str:
        """
        Get a unique identifier for this timeseries.
        Default implementation uses name converted to snake_case.
        Override if you need a different ID.

        Returns:
            str: Unique identifier
        """
        return self.getName().lower().replace(' ', '_').replace('(', '').replace(')', '')


# Example timeseries implementations

class CPUTemperatureTimeseries(TimeseriesBase):
    """CPU temperature in Fahrenheit."""

    def getName(self) -> str:
        return "CPU Temperature"

    def getCurrentValue(self) -> Any:
        try:
            # Try to get CPU temperature from psutil
            temps = psutil.sensors_temperatures()
            if 'cpu_thermal' in temps:
                celsius = temps['cpu_thermal'][0].current
                fahrenheit = (celsius * 9/5) + 32
                return round(fahrenheit, 1)
        except:
            pass
        return None

    def getUnits(self) -> str:
        return "°F"


class GPUTemperatureTimeseries(TimeseriesBase):
    """GPU temperature in Fahrenheit."""

    def getName(self) -> str:
        return "GPU Temperature"

    def getCurrentValue(self) -> Any:
        try:
            import subprocess
            result = subprocess.run(
                ['vcgencmd', 'measure_temp'],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode == 0:
                temp_str = result.stdout.strip()
                celsius = float(temp_str.replace("temp=", "").replace("'C", ""))
                fahrenheit = (celsius * 9/5) + 32
                return round(fahrenheit, 1)
        except:
            pass
        return None

    def getUnits(self) -> str:
        return "°F"


class CPUUsageTimeseries(TimeseriesBase):
    """CPU usage percentage."""

    def getName(self) -> str:
        return "CPU Usage"

    def getCurrentValue(self) -> Any:
        try:
            return round(psutil.cpu_percent(interval=0.1), 1)
        except:
            return None

    def getUnits(self) -> str:
        return "%"


class RAMUsageTimeseries(TimeseriesBase):
    """RAM usage percentage."""

    def getName(self) -> str:
        return "RAM Usage"

    def getCurrentValue(self) -> Any:
        try:
            return round(psutil.virtual_memory().percent, 1)
        except:
            return None

    def getUnits(self) -> str:
        return "%"


class DiskUsageTimeseries(TimeseriesBase):
    """Disk usage percentage."""

    def getName(self) -> str:
        return "Disk Usage"

    def getCurrentValue(self) -> Any:
        try:
            return round(psutil.disk_usage('/').percent, 1)
        except:
            return None

    def getUnits(self) -> str:
        return "%"


# Centralized list of all timeseries - add or remove entries here
TIMESERIES = [
    CPUTemperatureTimeseries(),
    GPUTemperatureTimeseries(),
    CPUUsageTimeseries(),
    RAMUsageTimeseries(),
    DiskUsageTimeseries(),
]

# Create a dictionary for quick lookups by ID
TIMESERIES_MAP = {ts.getId(): ts for ts in TIMESERIES}


def get_timeseries(timeseries_id: str) -> TimeseriesBase:
    """Get a timeseries by its ID."""
    return TIMESERIES_MAP.get(timeseries_id)


def get_all_timeseries() -> list:
    """Get all configured timeseries."""
    return TIMESERIES


def get_timeseries_info() -> list:
    """
    Get metadata for all timeseries.

    Returns:
        list: List of dicts with id, name, and units for each timeseries
    """
    return [
        {
            'id': ts.getId(),
            'name': ts.getName(),
            'units': ts.getUnits()
        }
        for ts in TIMESERIES
    ]
