"""
Notifications — Windows system notifications via pystray.

Uses pystray's built-in notify() method for cross-platform balloon tips.
"""

from __future__ import annotations

import logging
from typing import Optional

import pystray

from models.job import Job

log = logging.getLogger("sky-agent")


class Notifier:
    """Sends Windows balloon / toast notifications through the tray icon."""

    def __init__(self) -> None:
        self._icon: Optional[pystray.Icon] = None

    def set_icon(self, icon: pystray.Icon) -> None:
        self._icon = icon

    def notify(self, title: str, message: str) -> None:
        if self._icon is None:
            log.warning("Notifier: no tray icon set, skipping notification")
            return
        try:
            self._icon.notify(message, title)
            log.info("NOTIFY  →  %s: %s", title, message)
        except Exception as exc:
            log.warning("Notification failed: %s", exc)

    # ── Convenience Methods ────────────────────────────────────────────────

    def job_started(self, job: Job) -> None:
        self.notify("SKY Agent", f"Job started — {job.name}")

    def job_completed(self, job: Job) -> None:
        rows = f"{job.records_processed:,}" if job.records_processed else "0"
        self.notify("SKY Agent", f"Job completed — {rows} rows processed")

    def job_failed(self, job: Job) -> None:
        msg = job.error_message or "unknown error"
        self.notify("SKY Agent", f"Job failed — {msg}")

    def agent_online(self) -> None:
        self.notify("SKY Agent", "Local Agent is online and ready")

    def agent_error(self, message: str) -> None:
        self.notify("SKY Agent", f"Error — {message}")
