"""
Job model for the SKY Local Agent.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


class JobStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """Represents a single agent job (extraction, validation, etc.)."""

    name: str
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    project: str = ""
    status: JobStatus = JobStatus.PENDING
    progress: int = 0          # 0-100
    records_processed: int = 0
    errors_count: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: str = ""

    def start(self) -> None:
        self.status = JobStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def update_progress(self, progress: int, records: int = 0, errors: int = 0) -> None:
        self.progress = min(progress, 100)
        self.records_processed = records
        self.errors_count = errors

    def complete(self, records: int = 0) -> None:
        self.status = JobStatus.SUCCESS
        self.progress = 100
        self.records_processed = records
        self.finished_at = datetime.now(timezone.utc)

    def fail(self, message: str = "") -> None:
        self.status = JobStatus.FAILED
        self.error_message = message
        self.finished_at = datetime.now(timezone.utc)

    @property
    def duration_seconds(self) -> Optional[float]:
        if not self.started_at:
            return None
        end = self.finished_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    @property
    def duration_display(self) -> str:
        secs = self.duration_seconds
        if secs is None:
            return "—"
        if secs < 60:
            return f"{secs:.0f}s"
        mins = int(secs // 60)
        remaining = int(secs % 60)
        return f"{mins}m {remaining}s"

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "project": self.project,
            "status": self.status.value,
            "progress": self.progress,
            "records_processed": self.records_processed,
            "errors_count": self.errors_count,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration": self.duration_display,
            "error_message": self.error_message,
        }
