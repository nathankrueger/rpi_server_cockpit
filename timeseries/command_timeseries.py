"""
Command-based timeseries definitions.

These timeseries execute shell commands to collect data, configured
entirely via JSON in config/command_timeseries_config.json (with local
overrides). They are loaded manually (not via __init_subclass__
auto-discovery) since each config entry becomes a separate instance
of the same CommandTimeseries class.
"""

import os
from typing import Any

from .config import TimeseriesBase


class CommandTimeseries(TimeseriesBase):
    """A timeseries that collects data by executing a shell command."""

    _exclude_from_discovery = True

    def __init__(self, config: dict, workspace_root: str):
        self._id = config['id']
        self._name = config.get('name', config['id'].replace('_', ' ').title())
        self._units = config['units']
        self._category = config.get('category', 'Uncategorized')
        self._tags = config.get('tags', [])
        self._description = config.get('description', '')
        self._timeout = config.get('timeout', 10)

        # Resolve command path relative to workspace root
        cmd = list(config['command'])
        if cmd and not os.path.isabs(cmd[0]):
            cmd[0] = os.path.join(workspace_root, cmd[0])
        self._command = cmd

    def getId(self) -> str:
        return self._id

    def getName(self) -> str:
        return self._name

    def getCurrentValue(self) -> Any:
        try:
            from utils.subprocess_helper import run as subprocess_run
            result = subprocess_run(
                self._command,
                capture_output=True,
                text=True,
                timeout=self._timeout
            )
            if result.returncode == 0:
                return round(float(result.stdout.strip()), 2)
        except Exception:
            pass
        return None

    def getUnits(self) -> str:
        return self._units

    def getCategory(self) -> str:
        return self._category

    def getTags(self) -> list:
        return self._tags

    def getDescription(self) -> str:
        return self._description
