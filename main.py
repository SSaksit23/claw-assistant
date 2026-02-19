"""Main entry point for the Web365 ClawBot application."""

# CRITICAL: eventlet monkey-patch must happen before ANY other imports.
# Without this, all blocking I/O (HTTP, DNS, file) freezes the event loop
# and kills WebSocket heartbeats, causing "Connection failed" in the UI.
import eventlet
eventlet.monkey_patch(os=True, select=True, socket=True, thread=True, time=True)

import os
import sys
import logging

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from config import Config
from app import create_app, socketio

logger = logging.getLogger(__name__)


def main():
    """Start the Flask-SocketIO server."""
    app = create_app()

    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = Config.FLASK_PORT
    debug = Config.FLASK_DEBUG

    print("")
    print("=" * 50)
    print("  Web365 ClawBot - Multi-Agent System")
    print("=" * 50)
    print(f"  Server:  http://localhost:{port}")
    print(f"  Debug:   {debug}")
    print(f"  n8n:     {'Enabled' if Config.N8N_ENABLED else 'Disabled (direct mode)'}")
    print("=" * 50)
    print("  API Endpoints:")
    print(f"  POST /api/expenses      - Create expense")
    print(f"  POST /api/batch-expenses - Batch process")
    print(f"  POST /api/parse         - Parse file")
    print(f"  GET  /api/packages      - List packages")
    print("=" * 50)
    print("")

    # use_reloader=False is required with eventlet -- the Werkzeug reloader
    # spawns a child process that races the parent for the same port.
    socketio.run(app, host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    main()
