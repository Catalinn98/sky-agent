#!/usr/bin/env python3
"""
SKY Local Agent – Control Tower Edition
=========================================
Runs as a Windows system tray application with a local dashboard.

  ▸ Registers the sky:// URI protocol handler (HKCU – no admin required)
  ▸ Listens on localhost:7789 for control signals from SKY Workspace
  ▸ Serves a local dashboard at http://127.0.0.1:7789/dashboard
  ▸ Shows real-time job progress, status, and notifications
  ▸ Performs ALL data validation locally — raw data never leaves the machine

Usage (dev):
    python sky_agent.py

Usage (production):
    SKYAgent.exe          — starts the tray icon + HTTP listener + dashboard
    SKYAgent.exe sky://open — invoked by the browser via the sky:// protocol
"""

import json
import logging
import os
import sys
import threading
import time
import webbrowser
import winreg
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from services.sap_logon_discovery import SAPLogonDiscoveryService
from state_manager import AgentState, StateManager
from job_manager import JobManager
from notifications import Notifier
from tray import TrayManager, AGENT_VERSION
from dashboard import DASHBOARD_HTML

# ── Configuration ──────────────────────────────────────────────────────────────

AGENT_HOST    = "127.0.0.1"
AGENT_PORT    = 7789
SKY_WORKSPACE = "https://skydatamigration.com"

ALLOWED_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://skydatamigration.com",
    "https://www.skydatamigration.com",
}

# ── Logging — dual output: console + rotating file ────────────────────────────

LOG_DIR = os.path.join(os.path.expanduser("~"), ".sky-agent", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "sky_agent.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [SKY-AGENT]  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("sky-agent")

# ── In-memory log buffer for the dashboard ─────────────────────────────────────

_log_buffer: deque[str] = deque(maxlen=200)
_log_buffer_lock = threading.Lock()


class _BufferHandler(logging.Handler):
    def emit(self, record):
        line = self.format(record)
        with _log_buffer_lock:
            _log_buffer.append(line)


_bh = _BufferHandler()
_bh.setFormatter(logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s", datefmt="%H:%M:%S"))
logging.getLogger("sky-agent").addHandler(_bh)


def _get_recent_logs(n: int = 50) -> list[str]:
    with _log_buffer_lock:
        return list(_log_buffer)[-n:]


# ── Shared Instances ──────────────────────────────────────────────────────────

state_mgr = StateManager()
notifier = Notifier()
job_mgr = JobManager(state_mgr)

# Wire notifications to job lifecycle
job_mgr.on_job_start(notifier.job_started)
job_mgr.on_job_finish(
    lambda job: (
        notifier.job_completed(job) if job.status.value == "success"
        else notifier.job_failed(job)
    )
)


# ── Protocol Registration ──────────────────────────────────────────────────────

def register_sky_protocol() -> None:
    """Register sky:// URI scheme under HKCU\\Software\\Classes (no admin needed)."""
    if sys.platform != "win32":
        return

    exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0])
    base = r"Software\Classes\sky"

    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, base, 0, winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:SKY Protocol")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            rf"{base}\shell\open\command",
            0,
            winreg.KEY_WRITE,
        ) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{exe}" "%1"')

        log.info("sky:// protocol registered for current user")
    except Exception as exc:
        log.warning("Could not register sky:// protocol: %s", exc)


# ── HTTP API ───────────────────────────────────────────────────────────────────

class AgentHandler(BaseHTTPRequestHandler):
    """
    HTTP API for the SKY Local Agent — Control Tower Edition.

    Existing endpoints (unchanged API contract):
        GET  /ping               – liveness check
        GET  /open               – bring SKY Workspace to foreground
        GET  /status             – current agent status
        GET  /sap-logon/systems  – discover SAP Logon entries
        POST /run-job            – accept a validation job

    New endpoints (local dashboard):
        GET  /dashboard          – local Control Tower UI
        GET  /api/state          – full state snapshot (polled by dashboard)
        GET  /api/test-sap       – test SAP connection
        POST /api/sample-extraction – run a sample extraction job
    """

    def log_message(self, fmt, *args):  # noqa: D102  – suppress default log
        pass

    # ── CORS ───────────────────────────────────────────────────────────────────

    def _cors(self) -> None:
        origin = self.headers.get("Origin", "")
        allow = origin if origin in ALLOWED_ORIGINS else "https://skydatamigration.com"
        self.send_header("Access-Control-Allow-Origin", allow)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")
        if self.headers.get("Access-Control-Request-Private-Network"):
            self.send_header("Access-Control-Allow-Private-Network", "true")

    def _json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _html(self, content: str, status: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Routes ─────────────────────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        # ── Existing API endpoints (unchanged contract) ────────────────────
        if self.path == "/ping":
            state_mgr.heartbeat()
            # Workspace is actively communicating → mark as Online
            if state_mgr.state == AgentState.IDLE:
                state_mgr.set_state(AgentState.ONLINE)
            log.info("PING  ← SKY Workspace (agent detection)")
            self._json({
                "status":    "ok",
                "agent":     "SKY Local Agent",
                "version":   AGENT_VERSION,
                "timestamp": self._now(),
            })

        elif self.path == "/open":
            log.info("OPEN  ← SKY Workspace — opening browser")
            webbrowser.open(SKY_WORKSPACE)
            self._json({"status": "ok", "action": "opened", "timestamp": self._now()})

        elif self.path == "/status":
            self._json({
                "status":    state_mgr.state.value,
                "version":   AGENT_VERSION,
                "port":      AGENT_PORT,
                "workspace": SKY_WORKSPACE,
                "timestamp": self._now(),
            })

        elif self.path == "/sap-logon/systems":
            log.info("SAP-LOGON  ← scanning local SAP Logon configuration")
            try:
                service = SAPLogonDiscoveryService()
                result = service.discover()
                self._json(result.to_dict())
            except Exception as exc:
                log.error("SAP Logon discovery failed: %s", exc)
                self._json({
                    "count": 0,
                    "systems": [],
                    "errors": [f"Discovery failed: {exc}"],
                }, 500)

        # ── New: Dashboard & API ───────────────────────────────────────────
        elif self.path == "/dashboard":
            self._html(DASHBOARD_HTML)

        elif self.path == "/api/state":
            state_mgr.heartbeat()
            self._json({
                "version": AGENT_VERSION,
                "state": state_mgr.snapshot(),
                "jobs": job_mgr.snapshot(),
                "health": {
                    "http_api": True,
                    "sap_connection": None,  # unknown until tested
                },
                "logs": _get_recent_logs(50),
            })

        elif self.path == "/api/test-sap":
            log.info("TEST-SAP  ← testing SAP connection")
            try:
                service = SAPLogonDiscoveryService()
                result = service.discover()
                status = "ok" if result.count > 0 else "no_systems"
                self._json({
                    "status": status,
                    "systems_found": result.count,
                    "errors": result.errors,
                })
            except Exception as exc:
                log.error("SAP connection test failed: %s", exc)
                self._json({
                    "status": "error",
                    "systems_found": 0,
                    "errors": [str(exc)],
                }, 500)

        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/run-job":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}

            job_name = payload.get("name", payload.get("job_type", "Unnamed Job"))
            project = payload.get("project", "?")
            job_id = payload.get("job_id", "")

            log.info("JOB   ← project=%s  job_id=%s", project, job_id)

            # Start tracking the job
            job = job_mgr.start_job(name=job_name, project=project, job_id=job_id)
            state_mgr.set_connection_info(project=project)

            self._json({
                "status": "accepted",
                "job_id": job.job_id,
                "timestamp": self._now(),
            })

        elif self.path == "/api/sample-extraction":
            log.info("SAMPLE-EXTRACTION  ← running sample job")
            job = job_mgr.start_job(name="Sample Extraction (Debug)", project="debug")

            # Simulate a sample extraction in a background thread
            def _simulate():
                try:
                    for i in range(1, 11):
                        time.sleep(0.5)
                        job_mgr.update_progress(
                            progress=i * 10,
                            records=i * 100,
                            errors=1 if i == 7 else 0,
                        )
                    job_mgr.complete_job(records=1000)
                except Exception as exc:
                    job_mgr.fail_job(str(exc))

            threading.Thread(target=_simulate, daemon=True).start()
            self._json({"status": "accepted", "job_id": job.job_id})

        elif self.path == "/run-job/progress":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
            job_mgr.update_progress(
                progress=payload.get("progress", 0),
                records=payload.get("records", 0),
                errors=payload.get("errors", 0),
            )
            self._json({"status": "ok"})

        elif self.path == "/run-job/complete":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
            job_mgr.complete_job(records=payload.get("records", 0))
            self._json({"status": "ok"})

        elif self.path == "/run-job/fail":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
            job_mgr.fail_job(message=payload.get("message", "Unknown error"))
            self._json({"status": "ok"})

        else:
            self._json({"error": "not found"}, 404)


def _run_server() -> None:
    server = HTTPServer((AGENT_HOST, AGENT_PORT), AgentHandler)
    log.info("HTTP API   →  http://%s:%d", AGENT_HOST, AGENT_PORT)
    log.info("Dashboard  →  http://%s:%d/dashboard", AGENT_HOST, AGENT_PORT)
    server.serve_forever()


HEARTBEAT_TIMEOUT = 30  # seconds without ping → revert to Idle


def _heartbeat_watchdog() -> None:
    """Background thread: if no /ping received for 30s, revert ONLINE → IDLE."""
    while True:
        time.sleep(10)
        if state_mgr.state != AgentState.ONLINE:
            continue
        last = state_mgr.last_heartbeat
        if last is None:
            continue
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        if elapsed > HEARTBEAT_TIMEOUT:
            log.info("No workspace ping for %ds — reverting to Idle", int(elapsed))
            state_mgr.set_state(AgentState.IDLE)


# ── Entry Point ────────────────────────────────────────────────────────────────

def main() -> None:
    # Handle sky:// protocol invocation from the browser (e.g. sky://open)
    if len(sys.argv) > 1 and sys.argv[1].startswith("sky://"):
        log.info("Protocol invoked: %s", sys.argv[1])
        try:
            import urllib.request
            urllib.request.urlopen(
                f"http://{AGENT_HOST}:{AGENT_PORT}/open", timeout=2
            )
        except Exception:
            webbrowser.open(SKY_WORKSPACE)
        return

    log.info("SKY Local Agent v%s starting…", AGENT_VERSION)
    state_mgr.set_state(AgentState.STARTING)

    register_sky_protocol()

    # HTTP server in a background thread
    threading.Thread(target=_run_server, daemon=True).start()

    # Heartbeat watchdog (reverts ONLINE → IDLE if workspace stops pinging)
    threading.Thread(target=_heartbeat_watchdog, daemon=True).start()

    # Mark agent as idle after server starts (will go ONLINE on first /ping)
    time.sleep(0.5)
    state_mgr.set_state(AgentState.IDLE)
    log.info("Agent started — waiting for workspace connection")

    # Create tray manager and run (blocks — must be on main thread)
    tray = TrayManager(state_mgr, job_mgr, notifier)

    # Notify the user that the agent is ready
    def _delayed_notify():
        time.sleep(1)
        notifier.agent_online()
    threading.Thread(target=_delayed_notify, daemon=True).start()

    tray.run()


if __name__ == "__main__":
    main()
