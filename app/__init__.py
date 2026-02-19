"""Flask application factory."""

import os
import sys
import logging
from datetime import timedelta
from logging.handlers import RotatingFileHandler

from flask import Flask
from flask_socketio import SocketIO

socketio = SocketIO()


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "web365-clawbot-secret-key")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit

    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    is_production = os.getenv("FLASK_ENV", "production") == "production"
    app.config["SESSION_COOKIE_SECURE"] = is_production

    _configure_logging(app)

    from app.routes import main_bp
    app.register_blueprint(main_bp)

    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="eventlet",
        ping_timeout=120,
        ping_interval=25,
    )

    from app import websocket  # noqa: F401

    app.logger.info("Web365 ClawBot application initialized")
    return app


def _configure_logging(app):
    """Configure file and console logging with safe unicode handling."""
    log_dir = os.path.dirname(os.getenv("LOG_FILE", "logs/app.log"))
    os.makedirs(log_dir, exist_ok=True)

    # File handler (UTF-8, no encoding issues)
    file_handler = RotatingFileHandler(
        os.getenv("LOG_FILE", "logs/app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
    )

    # Console handler with safe encoding for Windows
    console_handler = logging.StreamHandler(
        stream=open(sys.stdout.fileno(), mode="w", encoding="utf-8", errors="replace", closefd=False)
    )
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
