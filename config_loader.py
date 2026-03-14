"""
Configuration loader for Raspberry Pi Dashboard.

Loads base configuration from JSON files and merges with optional local overrides.
This allows per-Pi customization while keeping common configs in git.

Base files (checked into git):
  - config/automation_config.json
  - config/service_config.json
  - config/remote_machine_config.json

Local override files (gitignored):
  - config/automation_config.local.json
  - config/service_config.local.json
  - config/remote_machine_config.local.json

Local files can:
  - Disable items: {"name": "item_name", "enabled": false}
  - Override properties: {"name": "item_name", "display_name": "NEW NAME"}
  - Add new items: {"name": "new_item", ...}
"""

import json
import os
from typing import List, Dict, Any

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')


def load_json_config(filename: str) -> Dict[str, Any]:
    """Load a JSON configuration file."""
    filepath = os.path.join(CONFIG_DIR, filename)
    if not os.path.exists(filepath):
        return {}

    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to load {filepath}: {e}")
        return {}


def merge_configs(base_items: List[Dict], local_items: List[Dict], key_field: str) -> List[Dict]:
    """
    Merge base and local configuration items.

    Args:
        base_items: List of base configuration items
        local_items: List of local override items
        key_field: Field name to use as unique identifier ('name' or 'id')

    Returns:
        Merged list with local overrides applied
    """
    # Create a dict from base items for easy lookup
    merged = {item[key_field]: item.copy() for item in base_items}

    # Apply local overrides
    for local_item in local_items:
        if key_field not in local_item:
            continue

        item_key = local_item[key_field]

        if item_key in merged:
            # Override existing item properties
            merged[item_key].update(local_item)
        else:
            # Add new item from local config
            merged[item_key] = local_item.copy()

    # Filter out disabled items and return as list
    return [item for item in merged.values() if item.get('enabled', True)]


def load_automation_config() -> List[Dict[str, Any]]:
    """
    Load automation configuration with local overrides.

    Returns:
        List of enabled automation configurations
    """
    base_config = load_json_config('automation_config.json')
    local_config = load_json_config('automation_config.local.json')

    base_items = base_config.get('automations', [])
    local_items = local_config.get('automations', [])

    return merge_configs(base_items, local_items, 'name')


def load_service_config() -> List[Dict[str, Any]]:
    """
    Load service configuration with local overrides.

    Returns:
        List of enabled service configurations
    """
    base_config = load_json_config('service_config.json')
    local_config = load_json_config('service_config.local.json')

    base_items = base_config.get('services', [])
    local_items = local_config.get('services', [])

    return merge_configs(base_items, local_items, 'id')


def load_remote_machine_config() -> List[Dict[str, Any]]:
    """
    Load remote machine configuration with local overrides.

    Returns:
        List of enabled remote machine configurations
    """
    base_config = load_json_config('remote_machine_config.json')
    local_config = load_json_config('remote_machine_config.local.json')

    base_items = base_config.get('remote_machines', [])
    local_items = local_config.get('remote_machines', [])

    return merge_configs(base_items, local_items, 'id')


# Load configurations
AUTOMATIONS = load_automation_config()
SERVICES = load_service_config()
REMOTE_MACHINES = load_remote_machine_config()

# Create lookup dictionaries
AUTOMATION_MAP = {auto['name']: auto for auto in AUTOMATIONS}
SERVICE_MAP = {service['id']: service for service in SERVICES}
REMOTE_MACHINE_MAP = {rm['id']: rm for rm in REMOTE_MACHINES}


def get_automation_config(automation_name: str) -> Dict[str, Any]:
    """Get configuration for a specific automation."""
    return AUTOMATION_MAP.get(automation_name)


def get_all_automations() -> List[Dict[str, Any]]:
    """Get all enabled automations."""
    return AUTOMATIONS


def get_service_config(service_id: str) -> Dict[str, Any]:
    """Get configuration for a specific service."""
    return SERVICE_MAP.get(service_id)


def get_all_services() -> List[Dict[str, Any]]:
    """Get all enabled services."""
    return SERVICES


def get_remote_machine_config(machine_id: str) -> Dict[str, Any]:
    """Get configuration for a specific remote machine."""
    return REMOTE_MACHINE_MAP.get(machine_id)


def get_all_remote_machines() -> List[Dict[str, Any]]:
    """Get all enabled remote machines."""
    return REMOTE_MACHINES