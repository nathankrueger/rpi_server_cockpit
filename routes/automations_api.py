"""Automation API routes."""
import shlex
import subprocess
import threading
import time
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request

from config_loader import get_all_automations, get_automation_config
from app_state import (
    automation_state,
    automation_lock,
    DEBUG_MODE,
    get_socketio,
)
from process_mgmt import kill_proc_tree

# Import eventlet only if not in debug mode
if not DEBUG_MODE:
    import eventlet

automations_bp = Blueprint('automations', __name__)


def broadcast_automation_state(automation_name, incremental_output=None):
    """Broadcast automation state to all connected clients.
    Note: This should be called WITHOUT holding automation_lock.

    Args:
        automation_name: Name of the automation
        incremental_output: If provided, only send this new output (not full output)
    """
    with automation_lock:
        state = automation_state[automation_name].copy()
        # Don't send the process object to clients
        state.pop('process', None)

        # If incremental output is provided, replace full output with just the increment
        if incremental_output is not None:
            state['output'] = incremental_output
            state['incremental'] = True
        else:
            state['incremental'] = False

    # Emit outside the lock to avoid blocking
    try:
        socketio = get_socketio()
        if socketio:
            socketio.emit('automation_update', {
                'automation': automation_name,
                'state': state
            }, namespace='/')
    except Exception as e:
        print(f"Error broadcasting state for {automation_name}: {e}")


@automations_bp.route('/api/automations')
def get_automations():
    """Get all automation configurations."""
    return jsonify({'automations': get_all_automations()})


@automations_bp.route('/api/automation/<automation_name>', methods=['POST'])
def run_automation(automation_name):
    """Run an automation script in the background."""
    print(f"Received request to run automation: {automation_name}")

    # Get automation config
    automation_config = get_automation_config(automation_name)

    if not automation_config:
        print(f"Invalid automation name: {automation_name}")
        return jsonify({'success': False, 'error': 'Invalid automation'}), 400

    # Check if automation is already running
    with automation_lock:
        if automation_state[automation_name]['running']:
            print(f"Automation {automation_name} is already running")
            return jsonify({
                'success': False,
                'error': 'Automation already running'
            }), 400

    # Get arguments from request body
    data = request.get_json() or {}
    args = data.get('args', '').strip()

    script_path = automation_config['script_path']
    job_id = str(uuid.uuid4())
    print(f"Starting automation {automation_name} with job_id {job_id}" + (f" and args: {args}" if args else ""))

    def run_script():
        try:
            # Initialize the automation state
            with automation_lock:
                automation_state[automation_name] = {
                    'job_id': job_id,
                    'running': True,
                    'output': 'Starting...\n',
                    'return_code': None,
                    'process': None
                }
            broadcast_automation_state(automation_name)

            # Build command with arguments if provided
            if args:
                # Use shlex to safely split arguments
                try:
                    arg_list = shlex.split(args)
                    cmd = ['/bin/bash', script_path] + arg_list
                except ValueError as e:
                    # If argument parsing fails, add error to output
                    with automation_lock:
                        automation_state[automation_name]['output'] += f"ERROR: Invalid arguments: {str(e)}\n"
                        automation_state[automation_name]['running'] = False
                        automation_state[automation_name]['return_code'] = -1
                        automation_state[automation_name]['completed_at'] = datetime.now().strftime('%H:%M:%S %m/%d/%y')
                    broadcast_automation_state(automation_name)
                    return
            else:
                cmd = ['/bin/bash', script_path]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            with automation_lock:
                automation_state[automation_name]['process'] = process

            # Read output line by line and broadcast updates
            for line in process.stdout:
                with automation_lock:
                    automation_state[automation_name]['output'] += line
                # Broadcast incremental update outside the lock
                broadcast_automation_state(automation_name, incremental_output=line)

            process.wait()

            with automation_lock:
                automation_state[automation_name]['running'] = False
                automation_state[automation_name]['return_code'] = process.returncode
                automation_state[automation_name]['process'] = None
                automation_state[automation_name]['completed_at'] = datetime.now().strftime('%H:%M:%S %m/%d/%y')
            broadcast_automation_state(automation_name)

        except Exception as e:
            with automation_lock:
                automation_state[automation_name]['output'] += f"\n\nERROR: {str(e)}\n"
                automation_state[automation_name]['running'] = False
                automation_state[automation_name]['return_code'] = -1
                automation_state[automation_name]['process'] = None
                automation_state[automation_name]['completed_at'] = datetime.now().strftime('%H:%M:%S %m/%d/%y')
            broadcast_automation_state(automation_name)

    # Start the script in a background thread/greenthread
    if DEBUG_MODE:
        # Use regular threading in debug mode
        thread = threading.Thread(target=run_script, daemon=True)
        thread.start()
    else:
        # Use eventlet greenthreads in production
        eventlet.spawn(run_script)

    # Give it a tiny moment to initialize
    time.sleep(0.1)

    response = jsonify({
        'success': True,
        'job_id': job_id,
        'message': f'{automation_name} started'
    })
    print(f"Returning success response for {automation_name}")
    return response


@automations_bp.route('/api/automation/<automation_name>/status')
def get_automation_status(automation_name):
    """Get the current status and output of an automation."""
    if automation_name not in automation_state:
        return jsonify({
            'success': False,
            'error': 'Invalid automation'
        }), 404

    with automation_lock:
        state = automation_state[automation_name].copy()
        # Don't send the process object
        state.pop('process', None)

        return jsonify({
            'success': True,
            **state
        })


@automations_bp.route('/api/automation/<automation_name>/cancel', methods=['POST'])
def cancel_automation(automation_name):
    """Cancel a running automation."""
    if automation_name not in automation_state:
        return jsonify({
            'success': False,
            'error': 'Invalid automation'
        }), 404

    with automation_lock:
        state = automation_state[automation_name]

        if not state['running']:
            return jsonify({
                'success': False,
                'error': 'Automation not running'
            })

        # Get the process reference
        process: subprocess.Popen = state.get('process')
        if not process:
            return jsonify({
                'success': False,
                'error': 'Process not found'
            })

    # Kill the process outside the lock to avoid blocking
    try:
        kill_proc_tree(process.pid)

        # Update state
        with automation_lock:
            state['output'] += "\n\n=== CANCELLED BY USER ===\n"
            state['running'] = False
            state['return_code'] = -999  # Special code for cancelled
            state['process'] = None
            state['completed_at'] = datetime.now().strftime('%H:%M:%S %m/%d/%y')

        # Broadcast outside the lock
        broadcast_automation_state(automation_name)

        return jsonify({
            'success': True,
            'message': 'Automation cancelled'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })
