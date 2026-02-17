"""Flask application factory."""

import os
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask
from flask_socketio import SocketIO

socketio = SocketIO()


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load config
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "web365-clawbot-secret-key")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit

    # Set up logging
    _configure_logging(app)

    # Register blueprints / routes
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    # Initialize SocketIO
    socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")

    # Register WebSocket handlers
    from app import websocket  # noqa: F401

    app.logger.info("Web365 ClawBot application initialized")
    return app


def _configure_logging(app):
    """Configure file and console logging."""
    log_dir = os.path.dirname(os.getenv("LOG_FILE", "logs/app.log"))
    os.makedirs(log_dir, exist_ok=True)

    file_handler = RotatingFileHandler(
        os.getenv("LOG_FILE", "logs/app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
    )
    app.logger.addHandler(file_handler)
    app.logger.setLevel(getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
