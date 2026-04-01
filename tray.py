"""
Enhanced System Tray — color-coded icon, dynamic menu, live status.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import webbrowser
from typing import Optional

import pystray
from PIL import Image, ImageDraw, ImageFont

from state_manager import AgentState, StateManager
from job_manager import JobManager
from notifications import Notifier

log = logging.getLogger("sky-agent")

AGENT_VERSION = "2.0.0"
SKY_WORKSPACE = "https://skydatamigration.com"
DASHBOARD_URL = "http://127.0.0.1:7789/dashboard"
LOG_DIR = os.path.join(os.path.expanduser("~"), ".sky-agent", "logs")


def _make_icon(color: tuple[int, int, int], letter: str = "S") -> Image.Image:
    """Create a 64x64 tray icon with the given background color."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=color)
    try:
        font = ImageFont.truetype("arialbd.ttf", 36)
        draw.text((32, 32), letter, fill="white", font=font, anchor="mm")
    except Exception:
        draw.text((22, 20), letter, fill="white")
    return img


class TrayManager:
    """Manages the system tray icon with dynamic state."""

    def __init__(
        self,
        state: StateManager,
        jobs: JobManager,
        notifier: Notifier,
    ) -> None:
        self._state = state
        self._jobs = jobs
        self._notifier = notifier
        self._icon: Optional[pystray.Icon] = None

        # Observe state changes to update icon
        self._state.on_state_change(self._on_state_change)

    # ── Icon Lifecycle ────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the tray icon (blocks — call from main thread)."""
        self._icon = pystray.Icon(
            "SKY Agent",
            _make_icon(self._state.color),
            "SKY Local Agent",
            self._build_menu(),
        )
        self._notifier.set_icon(self._icon)
        log.info("System tray icon active — right-click for menu")
        self._icon.run()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    # ── Menu ──────────────────────────────────────────────────────────────

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                f"SKY Local Agent  v{AGENT_VERSION}",
                None,
                enabled=False,
            ),
            pystray.MenuItem(
                lambda _: f"Status: {self._state.status_label}",
                None,
                enabled=False,
            ),
            pystray.MenuItem(
                lambda _: self._job_status_text(),
                None,
                enabled=False,
                visible=lambda _: self._state.state == AgentState.RUNNING_JOB,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open SKY Workspace", self._on_open_workspace),
            pystray.MenuItem(
                "Open Local Dashboard",
                self._on_open_dashboard,
                default=True,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Restart Agent", self._on_restart),
            pystray.MenuItem("View Logs", self._on_view_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_exit),
        )

    def _job_status_text(self) -> str:
        job = self._jobs.active_job
        if not job:
            return ""
        return f"Running: {job.name} ({job.progress}%)"

    # ── Menu Callbacks ────────────────────────────────────────────────────

    def _on_open_workspace(self, icon, item):
        webbrowser.open(SKY_WORKSPACE)

    def _on_open_dashboard(self, icon, item):
        webbrowser.open(DASHBOARD_URL)

    def _on_restart(self, icon, item):
        log.info("Restart requested via tray menu")
        exe = sys.executable
        os.execv(exe, [exe] + sys.argv)

    def _on_view_logs(self, icon, item):
        os.makedirs(LOG_DIR, exist_ok=True)
        log_file = os.path.join(LOG_DIR, "sky_agent.log")
        if os.path.exists(log_file):
            os.startfile(log_file)
        else:
            webbrowser.open(DASHBOARD_URL + "#logs")

    def _on_exit(self, icon, item):
        log.info("Exit requested — shutting down")
        icon.stop()
        os._exit(0)

    # ── State Observer ────────────────────────────────────────────────────

    def _on_state_change(self, old: AgentState, new: AgentState) -> None:
        if self._icon is None:
            return
        self._icon.icon = _make_icon(self._state.color)
        self._icon.menu = self._build_menu()
        log.info("Tray updated: %s → %s", old.value, new.value)
