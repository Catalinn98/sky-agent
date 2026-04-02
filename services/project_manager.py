"""
Project Manager — loads and manages existing local projects.

Works with the folder structure created by project_scaffold.
Provides read/update operations on manifests and config files.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("sky_agent.project_manager")


class ProjectManager:
    """Manages a single local project's manifests and state."""

    def __init__(self, project_dir: Path):
        self._dir = project_dir
        self._manifest_dir = project_dir / "manifest"

    # ------------------------------------------------------------------
    # Manifest readers
    # ------------------------------------------------------------------

    def get_project_manifest(self) -> dict:
        return self._read_json(self._manifest_dir / "project_manifest.json")

    def get_systems_manifest(self) -> dict:
        return self._read_json(self._manifest_dir / "systems_manifest.json")

    def get_objects_manifest(self) -> dict:
        return self._read_json(self._manifest_dir / "objects_manifest.json")

    def get_jobs_manifest(self) -> dict:
        return self._read_json(self._manifest_dir / "jobs_manifest.json")

    # ------------------------------------------------------------------
    # Object configuration
    # ------------------------------------------------------------------

    def get_object_config(self, config_filename: str) -> dict:
        path = self._dir / "input" / "object_configuration" / config_filename
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def list_object_configs(self) -> list[str]:
        config_dir = self._dir / "input" / "object_configuration"
        return sorted(p.name for p in config_dir.glob("*.yaml"))

    # ------------------------------------------------------------------
    # Job recording
    # ------------------------------------------------------------------

    def record_job(
        self,
        job_id: str,
        job_type: str,
        object_code: str,
        status: str,
        records_processed: int = 0,
        errors: int = 0,
        details: Optional[dict] = None,
    ) -> None:
        """Append a job entry to jobs_manifest.json."""
        manifest = self.get_jobs_manifest()
        now = datetime.now(timezone.utc).isoformat()

        entry = {
            "job_id": job_id,
            "job_type": job_type,
            "object_code": object_code,
            "status": status,
            "records_processed": records_processed,
            "errors": errors,
            "timestamp": now,
            "details": details or {},
        }
        manifest["jobs"].append(entry)
        manifest["updated_at"] = now
        self._write_json(self._manifest_dir / "jobs_manifest.json", manifest)

    # ------------------------------------------------------------------
    # Output paths
    # ------------------------------------------------------------------

    def extraction_current_dir(self) -> Path:
        return self._dir / "output" / "extraction_files" / "current"

    def extraction_archive_dir(self) -> Path:
        return self._dir / "output" / "extraction_files" / "archive"

    def load_files_current_dir(self) -> Path:
        return self._dir / "output" / "load_files" / "current"

    def load_files_archive_dir(self) -> Path:
        return self._dir / "output" / "load_files" / "archive"

    def preload_validation_dir(self) -> Path:
        return self._dir / "output" / "preload_validation"

    def postload_validation_dir(self) -> Path:
        return self._dir / "output" / "postload_validation"

    def temp_dir(self) -> Path:
        return self._dir / "output" / "temp"

    def logs_dir(self) -> Path:
        return self._dir / "logs"

    # ------------------------------------------------------------------
    # Runtime state
    # ------------------------------------------------------------------

    def write_job_state(self, job_id: str, state: dict) -> None:
        path = self._dir / "runtime" / "job_state" / f"{job_id}.json"
        self._write_json(path, state)

    def read_job_state(self, job_id: str) -> Optional[dict]:
        path = self._dir / "runtime" / "job_state" / f"{job_id}.json"
        if path.exists():
            return self._read_json(path)
        return None

    # ------------------------------------------------------------------
    # Archive support
    # ------------------------------------------------------------------

    def archive_extraction_files(self, run_label: str) -> Path:
        """Move current extraction files to a timestamped archive subfolder."""
        current = self.extraction_current_dir()
        archive_run = self.extraction_archive_dir() / run_label
        archive_run.mkdir(parents=True, exist_ok=True)

        for f in current.iterdir():
            if f.is_file():
                f.rename(archive_run / f.name)

        logger.info("Archived extraction files to %s", archive_run)
        return archive_run

    def archive_load_files(self, run_label: str) -> Path:
        """Move current load files to a timestamped archive subfolder."""
        current = self.load_files_current_dir()
        archive_run = self.load_files_archive_dir() / run_label
        archive_run.mkdir(parents=True, exist_ok=True)

        for f in current.iterdir():
            if f.is_file():
                f.rename(archive_run / f.name)

        logger.info("Archived load files to %s", archive_run)
        return archive_run

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _read_json(path: Path) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
