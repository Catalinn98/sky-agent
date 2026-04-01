"""
SKY Agent State Manager
========================
Thread-safe centralized state for the Local Agent.

States:
  STARTING → ONLINE → IDLE ↔ RUNNING_JOB
                          ↘ ERROR
                          ↘ OFFLINE
"""

from __future__ import annotations

import enum
import threading
from datetime import datetime, timezone
from typing import Callable, Optional


class AgentState(enum.Enum):
    STARTING = "starting"
    ONLINE = "online"
    IDLE = "idle"
    RUNNING_JOB = "running_job"
    ERROR = "error"
    OFFLINE = "offline"


# Colors used for tray icon per state
STATE_COLORS: dict[AgentState, tuple[int, int, int]] = {
    AgentState.STARTING: (156, 163, 175),   # gray
    AgentState.ONLINE: (34, 197, 94),        # green
    AgentState.IDLE: (234, 179, 8),          # yellow
    AgentState.RUNNING_JOB: (59, 130, 246),  # blue
    AgentState.ERROR: (239, 68, 68),         # red
    AgentState.OFFLINE: (107, 114, 128),     # dark gray
}


class StateManager:
    """Thread-safe agent state with observer callbacks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = AgentState.STARTING
        self._error_message: str = ""
        self._connected_user: str = ""
        self._connected_project: str = ""
        self._last_heartbeat: Optional[datetime] = None
        self._observers: list[Callable[[AgentState, AgentState], None]] = []

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def state(self) -> AgentState:
        with self._lock:
            return self._state

    @property
    def error_message(self) -> str:
        with self._lock:
            return self._error_message

    @property
    def connected_user(self) -> str:
        with self._lock:
            return self._connected_user

    @property
    def connected_project(self) -> str:
        with self._lock:
            return self._connected_project

    @property
    def last_heartbeat(self) -> Optional[datetime]:
        with self._lock:
            return self._last_heartbeat

    # ── State Transitions ──────────────────────────────────────────────────

    def set_state(self, new_state: AgentState, error_message: str = "") -> None:
        with self._lock:
            old = self._state
            self._state = new_state
            if new_state == AgentState.ERROR:
                self._error_message = error_message
            elif new_state != AgentState.ERROR:
                self._error_message = ""
            observers = list(self._observers)
        for cb in observers:
            try:
                cb(old, new_state)
            except Exception:
                pass

    def set_connection_info(self, user: str = "", project: str = "") -> None:
        with self._lock:
            if user:
                self._connected_user = user
            if project:
                self._connected_project = project

    def heartbeat(self) -> None:
        with self._lock:
            self._last_heartbeat = datetime.now(timezone.utc)

    # ── Observers ──────────────────────────────────────────────────────────

    def on_state_change(self, callback: Callable[[AgentState, AgentState], None]) -> None:
        with self._lock:
            self._observers.append(callback)

    # ── Snapshot ───────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self._state.value,
                "error_message": self._error_message,
                "connected_user": self._connected_user,
                "connected_project": self._connected_project,
                "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            }

    @property
    def color(self) -> tuple[int, int, int]:
        return STATE_COLORS.get(self.state, (107, 114, 128))

    @property
    def status_label(self) -> str:
        labels = {
            AgentState.STARTING: "Starting…",
            AgentState.ONLINE: "Online",
            AgentState.IDLE: "Idle",
            AgentState.RUNNING_JOB: "Running Job",
            AgentState.ERROR: f"Error: {self.error_message}",
            AgentState.OFFLINE: "Offline",
        }
        return labels.get(self.state, "Unknown")
