"""
Timeseries configuration for the Raspberry Pi Dashboard.

This module provides a base class for defining timeseries data sources
and a centralized registry of all configured timeseries.

To add a new timeseries:
1. Create a class that inherits from TimeseriesBase
2. Implement getName(), getCurrentValue(), and getUnits()
3. That's it! The class is automatically discovered and registered.

To exclude a timeseries from auto-discovery, set the class attribute:
    _exclude_from_discovery = True
"""

from abc import ABC, abstractmethod
from typing import Any
import inspect
import socket


# Cache hostname once for timeseries ID prefixing (e.g. "pi5server_cpu_temperature")
_hostname = socket.gethostname().lower().replace('-', '_')

# Registry for dynamically discovered timeseries classes
_timeseries_registry: list[type] = []


def _register_timeseries(cls: type) -> None:
    """Register a timeseries class for auto-instantiation."""
    if cls not in _timeseries_registry:
        _timeseries_registry.append(cls)


class TimeseriesBase(ABC):
    """Base class for all timeseries data sources."""

    _exclude_from_discovery: bool = False

    def __init_subclass__(cls, **kwargs):
        """Automatically register subclasses for discovery."""
        super().__init_subclass__(**kwargs)
        if not inspect.isabstract(cls) and not getattr(cls, '_exclude_from_discovery', False):
            _register_timeseries(cls)

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
        Default implementation uses hostname + name converted to snake_case.
        Override if you need a different ID.

        Returns:
            str: Unique identifier (e.g. "pi5server_cpu_temperature")
        """
        base_id = self.getName().lower().replace(' ', '_').replace('(', '').replace(')', '')
        return f"{_hostname}_{base_id}"

    def getCategory(self) -> str:
        """
        Get the category of this timeseries for organization.
        Override to provide a specific category.

        Returns:
            str: Category name (e.g., 'System', 'Network', 'Temperature')
        """
        return "Uncategorized"

    def getTags(self) -> list:
        """
        Get searchable tags for this timeseries.
        Override to provide custom tags for better search/filtering.

        Returns:
            list: List of tag strings
        """
        return []

    def getDescription(self) -> str:
        """
        Get a human-readable description of this timeseries.
        Override to provide helpful context.

        Returns:
            str: Description text
        """
        return ""


# Import server-local timeseries so they self-register via __init_subclass__
# before _discover_timeseries() runs below. This must come after TimeseriesBase
# is defined so the import can resolve it.
from . import server_timeseries  # noqa: E402, F401


def _discover_timeseries() -> list[TimeseriesBase]:
    """
    Dynamically instantiate all registered timeseries classes.

    Returns:
        list: Instances of all discovered TimeseriesBase subclasses
    """
    instances = []
    for cls in _timeseries_registry:
        try:
            instances.append(cls())
        except Exception as e:
            # Skip classes that fail to instantiate
            print(f"Warning: Failed to instantiate {cls.__name__}: {e}")
    return instances


# Dynamically populated list of all timeseries
TIMESERIES = _discover_timeseries()

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
        list: List of dicts with id, name, units, category, tags, and description for each timeseries
    """
    return [
        {
            'id': ts.getId(),
            'name': ts.getName(),
            'units': ts.getUnits(),
            'category': ts.getCategory(),
            'tags': ts.getTags(),
            'description': ts.getDescription()
        }
        for ts in TIMESERIES
    ]
