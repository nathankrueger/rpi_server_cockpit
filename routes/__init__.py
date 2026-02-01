"""Blueprint registration for all routes."""
from .pages import pages_bp
from .services_api import services_bp
from .system_api import system_bp
from .automations_api import automations_bp
from .external_api import external_bp


def register_blueprints(app):
    """Register all blueprints with the Flask app."""
    app.register_blueprint(pages_bp)
    app.register_blueprint(services_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(automations_bp)
    app.register_blueprint(external_bp)
