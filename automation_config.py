"""
Automation configuration for the Raspberry Pi Dashboard.

Each automation should have:
- name: Unique identifier (used in URLs and state management)
- display_name: Name shown to users
- script_path: Path to the bash script to execute
- button_text: Text displayed on the action button
"""

AUTOMATIONS = [
    {
        'name': 'sync_music',
        'display_name': 'SYNC MUSIC',
        'script_path': './automation_scripts/sync_music.sh',
        'button_text': 'RUN SYNC'
    },
    {
        'name': 'reboot',
        'display_name': 'REBOOT',
        'script_path': './automation_scripts/reboot.sh',
        'button_text': 'REBOOT'
    },
    {
        'name': 'update_os',
        'display_name': 'UPDATE OS',
        'script_path': './automation_scripts/update_os.sh',
        'button_text': 'UPDATE'
    },
    {
        'name': 'stress_test',
        'display_name': 'STRESS TEST',
        'script_path': './automation_scripts/make_heat.sh',
        'button_text': 'GO'
    },
    {
        'name': 'proc_list',
        'display_name': 'PROCESS LIST',
        'script_path': './automation_scripts/proc_list.sh',
        'button_text': 'LIST PROCESSES'
    },
    {
        'name': 'restart_webserver',
        'display_name': 'RESTART WEBSERVER',
        'script_path': './automation_scripts/restart_webserver.sh',
        'button_text': 'RESTART'
    }
]

# Create a dictionary for quick lookups
AUTOMATION_MAP = {auto['name']: auto for auto in AUTOMATIONS}

def get_automation_config(automation_name):
    return AUTOMATION_MAP.get(automation_name)

def get_all_automations():
    return AUTOMATIONS