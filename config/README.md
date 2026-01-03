# Configuration System

This directory contains JSON-based configuration files for automations and services.

## File Structure

```
config/
├── automation_config.json              # Base automation configs (checked into git)
├── service_config.json                 # Base service configs (checked into git)
├── automation_config.local.json        # Local overrides (gitignored)
├── service_config.local.json           # Local overrides (gitignored)
├── automation_config.local.json.example # Example local overrides
└── service_config.local.json.example    # Example local overrides
```

## How It Works

### Base Configuration Files
- **automation_config.json** and **service_config.json** are checked into git
- These contain the common/default configurations shared across all Raspberry Pis
- All items have `"enabled": true` by default

### Local Override Files
- **\*.local.json** files are gitignored (never checked into git)
- Each Pi can have its own local overrides without git conflicts
- Local configs can:
  - **Disable items**: Set `"enabled": false` on any base config item
  - **Override properties**: Change display names, paths, etc.
  - **Add new items**: Define Pi-specific automations or services

### Merging Behavior
The config loader merges base + local configs:
1. Loads base configuration
2. Loads local configuration (if it exists)
3. Merges by unique key (`name` for automations, `id` for services)
4. Filters out any items with `"enabled": false`

## Usage Examples

### Disable an automation on one Pi

Create `config/automation_config.local.json`:
```json
{
  "automations": [
    {
      "name": "sync_music",
      "enabled": false
    }
  ]
}
```

### Override an automation's display name

```json
{
  "automations": [
    {
      "name": "reboot",
      "display_name": "CUSTOM REBOOT NAME"
    }
  ]
}
```

### Add a Pi-specific automation

```json
{
  "automations": [
    {
      "name": "custom_backup",
      "display_name": "BACKUP",
      "script_path": "./automation_scripts/custom_backup.sh",
      "button_text": "RUN BACKUP",
      "enabled": true
    }
  ]
}
```

### Disable a service and add a custom one

Create `config/service_config.local.json`:
```json
{
  "services": [
    {
      "id": "qbittorrent",
      "enabled": false
    },
    {
      "id": "pihole",
      "display_name": "PI-HOLE",
      "check_type": "systemd",
      "check_name": "pihole-FTL",
      "control_type": "systemd",
      "control_name": "pihole-FTL",
      "button_type": "link",
      "link_url": "http://{hostname}/admin",
      "enabled": true
    }
  ]
}
```

## Getting Started

1. Copy the example files to create your local configs:
   ```bash
   cp config/automation_config.local.json.example config/automation_config.local.json
   cp config/service_config.local.json.example config/service_config.local.json
   ```

2. Edit the local files to customize for your Pi

3. Restart the dashboard to apply changes

## Notes

- Local config files are in `.gitignore` so they won't be committed
- You can use a `"comment"` field in local configs for documentation (ignored by the loader)
- The config loader runs at application startup, so restart after changes
- If a local config has syntax errors, it will be ignored and a warning printed
