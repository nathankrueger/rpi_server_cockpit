"""
Server-local timeseries definitions.

These timeseries collect data directly from the host machine
(CPU/GPU temperature, CPU/RAM/Disk usage). They are automatically
discovered and registered via TimeseriesBase.__init_subclass__.
"""

from typing import Any
import psutil

from .config import TimeseriesBase


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

    def getCategory(self) -> str:
        return "Temperature"

    def getTags(self) -> list:
        return ["cpu", "temperature", "thermal", "system"]

    def getDescription(self) -> str:
        return "Current CPU core temperature"


class GPUTemperatureTimeseries(TimeseriesBase):
    """GPU temperature in Fahrenheit."""

    def getName(self) -> str:
        return "GPU Temperature"

    def getCurrentValue(self) -> Any:
        try:
            from utils.subprocess_helper import run as subprocess_run
            result = subprocess_run(
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

    def getCategory(self) -> str:
        return "Temperature"

    def getTags(self) -> list:
        return ["gpu", "temperature", "thermal", "graphics"]

    def getDescription(self) -> str:
        return "Current GPU core temperature"


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

    def getCategory(self) -> str:
        return "System Resources"

    def getTags(self) -> list:
        return ["cpu", "usage", "performance", "system", "load"]

    def getDescription(self) -> str:
        return "CPU utilization percentage"


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

    def getCategory(self) -> str:
        return "System Resources"

    def getTags(self) -> list:
        return ["ram", "memory", "usage", "system"]

    def getDescription(self) -> str:
        return "RAM memory utilization percentage"


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

    def getCategory(self) -> str:
        return "Storage"

    def getTags(self) -> list:
        return ["disk", "storage", "usage", "filesystem"]

    def getDescription(self) -> str:
        return "Root filesystem disk usage percentage"
