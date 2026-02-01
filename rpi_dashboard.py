"""
Raspberry Pi Dashboard - Main Entry Point

This is the top-level application file that:
1. Initializes Flask and SocketIO
2. Registers all blueprints
3. Starts background threads
4. Provides the WSGI application entry point
"""
import os

from flask import Flask
from flask_socketio import SocketIO

from app_state import DEBUG_MODE, set_socketio
from utils import init_server_config
from routes import register_blueprints
from socketio_handlers import register_socketio_handlers
from background import start_all_background_threads

# Monkey patch for eventlet (only in production)
# Must be done before importing anything that uses sockets
if not DEBUG_MODE:
    import eventlet
    eventlet.monkey_patch()

# Create Flask app
app = Flask(__name__)
# Generate a random secret key on startup for Flask session management
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())

# Create SocketIO with appropriate async mode
async_mode = 'threading' if DEBUG_MODE else 'eventlet'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)

# Store socketio instance in app_state for use by other modules
set_socketio(socketio)

# Initialize server config
init_server_config()

# Register all blueprints (routes)
register_blueprints(app)

# Register timeseries blueprint
from timeseries import timeseries_bp
app.register_blueprint(timeseries_bp)

# Register SocketIO event handlers
register_socketio_handlers(socketio)

# Start all background monitoring threads
start_all_background_threads()

# Start timeseries data collector
from timeseries import start_collector
start_collector()


def create_app():
    """WSGI application wrapper for gunicorn deployment."""
    return app


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
