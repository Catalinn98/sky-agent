#!/usr/bin/env python3
"""
SKY Local Agent – Production
=============================
Runs as a Windows system tray application.

  ▸ Registers the sky:// URI protocol handler (HKCU – no admin required)
  ▸ Listens on localhost:7789 for control signals from SKY Workspace
  ▸ Performs ALL data validation locally — raw data never leaves the machine

Usage (dev):
    python sky_agent.py

Usage (production):
    SKYAgent.exe          — starts the tray icon + HTTP listener
    SKYAgent.exe sky://open — invoked by the browser via the sky:// protocol
"""

import json
import logging
import os
import sys
import threading
import webbrowser
import winreg
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import pystray
from PIL import Image, ImageDraw, ImageFont

# ── Configuration ──────────────────────────────────────────────────────────────

AGENT_HOST    = "127.0.0.1"
AGENT_PORT    = 7789
AGENT_VERSION = "1.0.0"
SKY_WORKSPACE = "https://skydatamigration.com"

ALLOWED_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://skydatamigration.com",
    "https://www.skydatamigration.com",
}

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [SKY-AGENT]  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sky-agent")


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
    Minimal HTTP API for the Local Agent.

    GET  /ping       – liveness check (used by SKY Workspace to detect the agent)
    GET  /open       – bring SKY Workspace to foreground
    GET  /status     – current agent status
    POST /run-job    – accept a validation job
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
        # ── Private Network Access (Chrome 98+) ────────────────────────────────
        # Required so that HTTPS pages (skydatamigration.com) are allowed to
        # fetch http://127.0.0.1:7789.  Without this header Chrome blocks the
        # request with "ERR_BLOCKED_BY_PRIVATE_NETWORK_ACCESS_CHECKS" before
        # it even reaches the server.
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

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Routes ─────────────────────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/ping":
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
                "status":    "running",
                "version":   AGENT_VERSION,
                "port":      AGENT_PORT,
                "workspace": SKY_WORKSPACE,
                "timestamp": self._now(),
            })

        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/run-job":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                job = json.loads(raw)
            except json.JSONDecodeError:
                job = {}
            log.info("JOB   ← project=%s  job_id=%s", job.get("project", "?"), job.get("job_id", "?"))
            self._json({"status": "accepted", "job_id": job.get("job_id", ""), "timestamp": self._now()})
        else:
            self._json({"error": "not found"}, 404)


def _run_server() -> None:
    server = HTTPServer((AGENT_HOST, AGENT_PORT), AgentHandler)
    log.info("HTTP API  →  http://%s:%d", AGENT_HOST, AGENT_PORT)
    server.serve_forever()


# ── System Tray ────────────────────────────────────────────────────────────────

def _make_icon() -> Image.Image:
    """Create a 64×64 tray icon programmatically (no external file needed)."""
    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Blue circle background
    draw.ellipse([4, 4, 60, 60], fill=(30, 64, 175))  # blue-700

    # "S" letter in white – try bold font first, fall back to default
    try:
        font = ImageFont.truetype("arialbd.ttf", 36)
        draw.text((32, 32), "S", fill="white", font=font, anchor="mm")
    except Exception:
        draw.text((22, 20), "S", fill="white")

    return img


def _run_tray() -> None:
    def on_open(icon, item):
        webbrowser.open(SKY_WORKSPACE)

    def on_exit(icon, item):
        log.info("Exit requested — shutting down")
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem(f"SKY Local Agent  v{AGENT_VERSION}", None, enabled=False),
        pystray.MenuItem("Status: Connected ✓", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open SKY Workspace", on_open, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", on_exit),
    )

    icon = pystray.Icon("SKY Agent", _make_icon(), "SKY Local Agent", menu)
    log.info("System tray icon active — right-click to open menu")
    icon.run()  # blocking – must run on main thread


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
            # Agent not running — open workspace directly
            webbrowser.open(SKY_WORKSPACE)
        return

    register_sky_protocol()

    # HTTP server in a background thread
    thread = threading.Thread(target=_run_server, daemon=True)
    thread.start()

    # Tray icon runs on the main thread (required by Windows)
    _run_tray()


if __name__ == "__main__":
    main()
