"""SocketIO event handlers."""
from flask_socketio import emit

from app_state import automation_state, automation_lock


def register_socketio_handlers(socketio):
    """Register all SocketIO event handlers."""

    @socketio.on('connect')
    def handle_connect():
        """Handle client connection - send current automation states."""
        print('Client connected')
        # Send current state of all automations to the newly connected client
        with automation_lock:
            for automation_name, state in automation_state.items():
                state_copy = state.copy()
                state_copy.pop('process', None)
                # Mark as full update (not incremental)
                state_copy['incremental'] = False
                emit('automation_update', {
                    'automation': automation_name,
                    'state': state_copy
                })

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        print('Client disconnected')

    @socketio.on('request_automation_state')
    def handle_request_state(data):
        """Handle explicit request for automation state."""
        automation_name = data.get('automation')
        if automation_name and automation_name in automation_state:
            with automation_lock:
                state = automation_state[automation_name].copy()
                state.pop('process', None)
                emit('automation_update', {
                    'automation': automation_name,
                    'state': state
                })
