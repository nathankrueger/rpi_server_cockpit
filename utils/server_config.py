"""Server configuration load/save utilities."""
import json
import os

import app_state
from app_state import SERVER_CONFIG_FILE, SERVER_CONFIG_DEFAULTS


def load_server_config():
    """Load server config from JSON file, creating with defaults if missing."""
    config = SERVER_CONFIG_DEFAULTS.copy()
    try:
        if os.path.exists(SERVER_CONFIG_FILE):
            with open(SERVER_CONFIG_FILE, 'r') as f:
                loaded = json.load(f)
                # Only use valid keys from the file
                for key in SERVER_CONFIG_DEFAULTS:
                    if key in loaded:
                        config[key] = float(loaded[key])
            print(f"Loaded server config from {SERVER_CONFIG_FILE}")
        else:
            # Create config file with defaults
            save_server_config(config)
            print(f"Created server config file with defaults at {SERVER_CONFIG_FILE}")
    except Exception as e:
        print(f"Error loading server config: {e}, using defaults")
    return config


def save_server_config(config):
    """Save server config to JSON file."""
    try:
        with open(SERVER_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"Saved server config to {SERVER_CONFIG_FILE}")
        return True
    except Exception as e:
        print(f"Error saving server config: {e}")
        return False


def init_server_config():
    """Initialize server config and store in app_state."""
    app_state.server_config = load_server_config()
    return app_state.server_config
