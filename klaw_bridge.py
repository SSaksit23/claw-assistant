"""
klaw ↔ ClawBot bridge.

This module is the integration layer between klaw (Go-based agent
orchestrator) and the Python ClawBot agents. It provides:

1. An HTTP server that klaw can POST tasks to
2. Agent registration/discovery endpoints
3. Health check endpoints
4. Result streaming back to klaw

klaw dispatches tasks via HTTP → this bridge → Python agent → result JSON → klaw

Usage:
    python klaw_bridge.py                      # start bridge on :9100
    python klaw_bridge.py --port 9200          # custom port
    python klaw_bridge.py --register           # register agents with klaw controller
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from config import Config

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [klaw-bridge] %(levelname)s: %(message)s",
)
logger = logging.getLogger("klaw_bridge")

PYTHON = sys.executable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

AGENT_MAP = {
    "accounting-agent": "accounting",
    "data-analysis-agent": "data_analysis",
    "market-analysis-agent": "market_analysis",
    "executive-agent": "executive",
    "admin-agent": "admin",
}

jobs: dict[str, dict] = {}
job_lock = threading.Lock()


def _run_agent_process(job_id: str, agent_key: str, task_json: str, file_path: str = None):
    """Run a ClawBot agent in a subprocess and capture the result."""
    cmd = [
        PYTHON, "-m", "agents.cli_runner",
        "--agent", agent_key,
        "--task", task_json,
    ]
    if file_path:
        cmd.extend(["--file", file_path])

    logger.info("Job %s: starting agent=%s", job_id, agent_key)

    with job_lock:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["started_at"] = datetime.now().isoformat()

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=300,
        )

        with job_lock:
            jobs[job_id]["exit_code"] = proc.returncode
            jobs[job_id]["stderr"] = proc.stderr[-2000:] if proc.stderr else ""
            jobs[job_id]["completed_at"] = datetime.now().isoformat()

            if proc.returncode == 0:
                try:
                    jobs[job_id]["result"] = json.loads(proc.stdout)
                    jobs[job_id]["status"] = "completed"
                except json.JSONDecodeError:
                    jobs[job_id]["result"] = {"raw_output": proc.stdout[-2000:]}
                    jobs[job_id]["status"] = "completed"
            else:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["error"] = proc.stderr[-500:] if proc.stderr else "Non-zero exit"

        logger.info("Job %s: finished status=%s exit=%d", job_id, jobs[job_id]["status"], proc.returncode)

    except subprocess.TimeoutExpired:
        with job_lock:
            jobs[job_id]["status"] = "timeout"
            jobs[job_id]["error"] = "Agent exceeded 300s timeout"
        logger.error("Job %s: timed out", job_id)

    except Exception as e:
        with job_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)
        logger.error("Job %s: exception %s", job_id, e, exc_info=True)


class BridgeHandler(BaseHTTPRequestHandler):
    """HTTP handler for klaw → ClawBot bridge."""

    def _send_json(self, code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self._send_json(200, {
                "status": "healthy",
                "agents": list(AGENT_MAP.keys()),
                "uptime": time.time(),
            })

        elif parsed.path == "/agents":
            agents = []
            for klaw_name, cli_name in AGENT_MAP.items():
                agents.append({
                    "name": klaw_name,
                    "cli_key": cli_name,
                    "status": "idle",
                })
            self._send_json(200, {"agents": agents})

        elif parsed.path.startswith("/jobs/"):
            job_id = parsed.path.split("/jobs/", 1)[1].rstrip("/")
            with job_lock:
                job = jobs.get(job_id)
            if job:
                self._send_json(200, job)
            else:
                self._send_json(404, {"error": f"Job {job_id} not found"})

        elif parsed.path == "/jobs":
            with job_lock:
                summary = {
                    jid: {"status": j["status"], "agent": j["agent"]}
                    for jid, j in jobs.items()
                }
            self._send_json(200, {"jobs": summary})

        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/dispatch":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)

            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON body"})
                return

            agent_name = payload.get("agent", "")
            if agent_name not in AGENT_MAP:
                self._send_json(400, {
                    "error": f"Unknown agent: {agent_name}",
                    "available": list(AGENT_MAP.keys()),
                })
                return

            agent_key = AGENT_MAP[agent_name]
            task_json = json.dumps(payload.get("task", {}))
            file_path = payload.get("file_path")

            job_id = f"{agent_key}_{int(time.time()*1000)}"

            with job_lock:
                jobs[job_id] = {
                    "id": job_id,
                    "agent": agent_name,
                    "task": payload.get("task", {}),
                    "status": "queued",
                    "created_at": datetime.now().isoformat(),
                }

            thread = threading.Thread(
                target=_run_agent_process,
                args=(job_id, agent_key, task_json, file_path),
                daemon=True,
            )
            thread.start()

            self._send_json(202, {
                "job_id": job_id,
                "status": "queued",
                "poll_url": f"/jobs/{job_id}",
            })

        elif parsed.path == "/dispatch/sync":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)

            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON body"})
                return

            agent_name = payload.get("agent", "")
            if agent_name not in AGENT_MAP:
                self._send_json(400, {"error": f"Unknown agent: {agent_name}"})
                return

            agent_key = AGENT_MAP[agent_name]
            task_json = json.dumps(payload.get("task", {}))
            file_path = payload.get("file_path")

            cmd = [
                PYTHON, "-m", "agents.cli_runner",
                "--agent", agent_key,
                "--task", task_json,
            ]
            if file_path:
                cmd.extend(["--file", file_path])

            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    cwd=PROJECT_ROOT, timeout=300,
                )
                if proc.returncode == 0:
                    try:
                        result = json.loads(proc.stdout)
                    except json.JSONDecodeError:
                        result = {"raw_output": proc.stdout[-2000:]}
                    self._send_json(200, result)
                else:
                    self._send_json(500, {
                        "error": "Agent failed",
                        "stderr": proc.stderr[-500:],
                    })
            except subprocess.TimeoutExpired:
                self._send_json(504, {"error": "Agent timed out (300s)"})

        else:
            self._send_json(404, {"error": "Not found"})

    def log_message(self, format, *args):
        logger.debug("%s %s", self.address_string(), format % args)


def register_with_klaw(controller_url: str, bridge_url: str):
    """Register this bridge's agents with a klaw controller."""
    import requests

    for klaw_name in AGENT_MAP:
        yaml_path = os.path.join(PROJECT_ROOT, "klaw_agents", f"{klaw_name}.yaml")
        if not os.path.exists(yaml_path):
            logger.warning("Definition file not found: %s", yaml_path)
            continue

        try:
            with open(yaml_path, "r") as f:
                definition = f.read()

            resp = requests.post(
                f"{controller_url}/api/agents",
                json={
                    "name": klaw_name,
                    "bridge_url": bridge_url,
                    "definition": definition,
                },
                timeout=10,
            )
            logger.info("Registered %s → %s (HTTP %d)", klaw_name, controller_url, resp.status_code)

        except Exception as e:
            logger.error("Failed to register %s: %s", klaw_name, e)


def main():
    parser = argparse.ArgumentParser(description="klaw ↔ ClawBot bridge server")
    parser.add_argument("--port", type=int, default=9100, help="Bridge HTTP port (default: 9100)")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--register", action="store_true", help="Register agents with klaw controller")
    parser.add_argument("--controller", default="http://localhost:9090", help="klaw controller URL")
    args = parser.parse_args()

    if args.register:
        bridge_url = f"http://localhost:{args.port}"
        register_with_klaw(args.controller, bridge_url)
        return

    server = HTTPServer((args.host, args.port), BridgeHandler)
    print(f"""
{'='*55}
  klaw <-> ClawBot Bridge
{'='*55}
  Bridge:     http://localhost:{args.port}
  Health:     http://localhost:{args.port}/health
  Agents:     http://localhost:{args.port}/agents
  Dispatch:   POST http://localhost:{args.port}/dispatch
{'='*55}
  Available agents:""")
    for klaw_name, cli_name in AGENT_MAP.items():
        print(f"    {klaw_name:30s} -> {cli_name}")
    print(f"{'='*55}\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Bridge shutting down")
        server.server_close()


if __name__ == "__main__":
    main()
