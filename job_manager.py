"""
Job Manager — tracks active job and maintains history.

Thread-safe. Notifies the StateManager on job lifecycle transitions.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from models.job import Job, JobStatus
from state_manager import AgentState, StateManager

log = logging.getLogger("sky-agent")

MAX_HISTORY = 20


class JobManager:
    def __init__(self, state: StateManager) -> None:
        self._state = state
        self._lock = threading.Lock()
        self._active: Optional[Job] = None
        self._history: deque[Job] = deque(maxlen=MAX_HISTORY)
        self._on_start_callbacks: list = []
        self._on_finish_callbacks: list = []

    # ── Callbacks ──────────────────────────────────────────────────────────

    def on_job_start(self, cb) -> None:
        self._on_start_callbacks.append(cb)

    def on_job_finish(self, cb) -> None:
        self._on_finish_callbacks.append(cb)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start_job(self, name: str, project: str = "", job_id: str = "") -> Job:
        job = Job(name=name, project=project)
        if job_id:
            job.job_id = job_id
        job.start()

        with self._lock:
            self._active = job

        self._state.set_state(AgentState.RUNNING_JOB)
        log.info("JOB STARTED  →  %s  (id=%s)", name, job.job_id)

        for cb in self._on_start_callbacks:
            try:
                cb(job)
            except Exception:
                pass

        return job

    def update_progress(self, progress: int, records: int = 0, errors: int = 0) -> None:
        with self._lock:
            if self._active:
                self._active.update_progress(progress, records, errors)

    def _post_job_state(self) -> None:
        """After a job ends, pick ONLINE or IDLE based on recent heartbeat."""
        last = self._state.last_heartbeat
        if last and (datetime.now(timezone.utc) - last).total_seconds() < 30:
            self._state.set_state(AgentState.ONLINE)
        else:
            self._state.set_state(AgentState.IDLE)

    def complete_job(self, records: int = 0) -> Optional[Job]:
        with self._lock:
            job = self._active
            if not job:
                return None
            job.complete(records)
            self._history.appendleft(job)
            self._active = None

        self._post_job_state()
        log.info("JOB COMPLETED  →  %s  (%d records)", job.name, records)

        for cb in self._on_finish_callbacks:
            try:
                cb(job)
            except Exception:
                pass

        return job

    def fail_job(self, message: str = "") -> Optional[Job]:
        with self._lock:
            job = self._active
            if not job:
                return None
            job.fail(message)
            self._history.appendleft(job)
            self._active = None

        self._state.set_state(AgentState.ERROR, error_message=f"Job failed: {message}")
        log.error("JOB FAILED  →  %s  (%s)", job.name, message)

        for cb in self._on_finish_callbacks:
            try:
                cb(job)
            except Exception:
                pass

        return job

    # ── Queries ────────────────────────────────────────────────────────────

    @property
    def active_job(self) -> Optional[Job]:
        with self._lock:
            return self._active

    @property
    def history(self) -> list[Job]:
        with self._lock:
            return list(self._history)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active_job": self._active.to_dict() if self._active else None,
                "history": [j.to_dict() for j in list(self._history)[:5]],
            }
