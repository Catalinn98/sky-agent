"""
Project Scaffolding Service — creates and manages local project folder structures.

Called when SKY Workspace sends a project_init command containing:
  - project_id, project_name, project_code
  - systems (source + target)
  - selected data objects

This service:
  1. Creates the normalized folder tree
  2. Generates manifest files
  3. Generates per-object configuration files
  4. Prepares runtime/output directories

No raw SAP data is created here — only configuration and structure.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from sky_agent.object_catalog.registry import ObjectCatalog

logger = logging.getLogger("sky_agent.project_scaffold")

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

MANIFEST_VERSION = "1.0"

_FOLDER_TREE = [
    "input/object_configuration",
    "input/mapping_rules",
    "input/connection_profiles",
    "input/target_metadata",
    "output/extraction_files/current",
    "output/extraction_files/archive",
    "output/load_files/current",
    "output/load_files/archive",
    "output/preload_validation",
    "output/postload_validation",
    "output/temp",
    "runtime/job_state",
    "runtime/cache",
    "manifest",
    "logs",
]


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def scaffold_project(
    base_dir: Path,
    project_id: str,
    project_name: str,
    project_code: str,
    systems: list[dict],
    selected_objects: list[str],
    catalog: Optional[ObjectCatalog] = None,
    execution_mode: str = "file_based",
) -> Path:
    """
    Create a full local project structure.

    Args:
        base_dir: Root directory for all projects (e.g. ~/sky_projects/).
        project_id: UUID from SKY Workspace.
        project_name: Human-readable name.
        project_code: Short code used as folder name (e.g. "PRJ_001").
        systems: List of system dicts with keys:
            system_id, system_name, system_type, role ("source"|"target"),
            client, host (optional metadata — NO credentials).
        selected_objects: List of object_code strings from the catalog.
        catalog: ObjectCatalog instance (auto-created if None).
        execution_mode: "file_based" or "staging_tables".

    Returns:
        Path to the created project folder.
    """
    catalog = catalog or ObjectCatalog()
    project_dir = base_dir / project_code
    now = datetime.now(timezone.utc).isoformat()

    # 1. Create folder tree
    _create_folders(project_dir)

    # 2. Classify systems
    source_systems = [s for s in systems if s.get("role") == "source"]
    target_systems = [s for s in systems if s.get("role") == "target"]

    # 3. Generate manifests
    _write_project_manifest(project_dir, project_id, project_name, project_code, now, execution_mode)
    _write_systems_manifest(project_dir, systems, now)
    _write_objects_manifest(project_dir, selected_objects, source_systems, target_systems, catalog, now)
    _write_jobs_manifest(project_dir, now)

    # 4. Generate object configuration files
    for obj_code in selected_objects:
        for src in source_systems:
            for tgt in target_systems:
                _write_object_config(
                    project_dir, obj_code, src, tgt, catalog
                )

    # 5. Generate connection profiles (metadata only)
    for system in systems:
        _write_connection_profile(project_dir, system)

    logger.info("Project scaffolded: %s → %s", project_code, project_dir)
    return project_dir


# ------------------------------------------------------------------
# Folder Creation
# ------------------------------------------------------------------

def _create_folders(project_dir: Path) -> None:
    for rel_path in _FOLDER_TREE:
        (project_dir / rel_path).mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------
# Manifest Writers
# ------------------------------------------------------------------

def _write_project_manifest(
    project_dir: Path,
    project_id: str,
    project_name: str,
    project_code: str,
    now: str,
    execution_mode: str = "file_based",
) -> None:
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "project_id": project_id,
        "project_name": project_name,
        "project_code": project_code,
        "execution_mode": execution_mode,
        "created_at": now,
        "updated_at": now,
        "status": "initialized",
        "agent_version": "1.0.0",
    }
    _write_json(project_dir / "manifest" / "project_manifest.json", manifest)


def _write_systems_manifest(
    project_dir: Path,
    systems: list[dict],
    now: str,
) -> None:
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "updated_at": now,
        "systems": [
            {
                "system_id": s["system_id"],
                "system_name": s["system_name"],
                "system_type": s["system_type"],
                "role": s["role"],
                "client": s.get("client", ""),
                "host": s.get("host", ""),
                "description": s.get("description", ""),
            }
            for s in systems
        ],
    }
    _write_json(project_dir / "manifest" / "systems_manifest.json", manifest)


def _write_objects_manifest(
    project_dir: Path,
    selected_objects: list[str],
    source_systems: list[dict],
    target_systems: list[dict],
    catalog: ObjectCatalog,
    now: str,
) -> None:
    entries = []
    for obj_code in selected_objects:
        defn = catalog.get(obj_code)
        config_files = []
        for src in source_systems:
            for tgt in target_systems:
                config_files.append(
                    _object_config_filename(obj_code, src, tgt)
                )
        entries.append({
            "object_code": obj_code,
            "display_name": defn["display_name"] if defn else obj_code,
            "category": defn.get("category", "unknown") if defn else "unknown",
            "module": defn.get("module", "") if defn else "",
            "configuration_files": config_files,
            "status": "configured",
        })

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "updated_at": now,
        "object_count": len(entries),
        "objects": entries,
    }
    _write_json(project_dir / "manifest" / "objects_manifest.json", manifest)


def _write_jobs_manifest(project_dir: Path, now: str) -> None:
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "updated_at": now,
        "jobs": [],
    }
    _write_json(project_dir / "manifest" / "jobs_manifest.json", manifest)


# ------------------------------------------------------------------
# Object Configuration Writer
# ------------------------------------------------------------------

def _object_config_filename(
    obj_code: str, src: dict, tgt: dict
) -> str:
    src_label = f"SRC_{src['system_type']}"
    tgt_label = f"TGT_{tgt['system_type']}"
    return f"{src_label}__{tgt_label}__{obj_code}.yaml"


def _write_object_config(
    project_dir: Path,
    obj_code: str,
    src: dict,
    tgt: dict,
    catalog: ObjectCatalog,
) -> None:
    defn = catalog.get(obj_code)
    filename = _object_config_filename(obj_code, src, tgt)

    config = {
        "object_code": obj_code,
        "catalog_reference": f"object_catalog/objects/{obj_code}.yaml",
        "source_system": {
            "system_id": src["system_id"],
            "system_name": src["system_name"],
            "system_type": src["system_type"],
            "client": src.get("client", ""),
        },
        "target_system": {
            "system_id": tgt["system_id"],
            "system_name": tgt["system_name"],
            "system_type": tgt["system_type"],
            "client": tgt.get("client", ""),
        },
        "active_tables": _build_active_tables(defn),
        "filters": _build_default_filters(defn),
        "parameters": {
            "language": "EN",
            "max_rows": 0,
            "batch_size": 10000,
        },
        "validation_profile": {
            "preload": defn.get("default_validations", []) if defn else [],
            "postload": [
                "postload_record_count_check",
                "postload_key_match_check",
            ],
        },
        "output": {
            "file_type": "csv",
            "delimiter": "|",
            "encoding": "utf-8",
            "naming_pattern": f"{obj_code}_{{table}}_{{timestamp}}",
        },
    }

    path = project_dir / "input" / "object_configuration" / filename
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    logger.debug("Object config written: %s", filename)


def _build_active_tables(defn: Optional[dict]) -> list[dict]:
    if not defn:
        return []
    return [
        {"table_name": t["table_name"], "enabled": True}
        for t in defn.get("source_tables", [])
    ]


def _build_default_filters(defn: Optional[dict]) -> list[dict]:
    if not defn:
        return []
    return [
        {
            "table": f["table"],
            "field": f["field"],
            "operator": f["operator"],
            "value": f["value"],
        }
        for f in defn.get("default_filters", [])
    ]


# ------------------------------------------------------------------
# Connection Profile Writer
# ------------------------------------------------------------------

def _write_connection_profile(project_dir: Path, system: dict) -> None:
    profile = {
        "system_id": system["system_id"],
        "system_name": system["system_name"],
        "system_type": system["system_type"],
        "role": system["role"],
        "host": system.get("host", ""),
        "client": system.get("client", ""),
        "description": system.get("description", ""),
        "note": "Connection credentials are managed by SAP Logon. This file contains metadata only.",
    }
    filename = f"{system['system_id']}.yaml"
    path = project_dir / "input" / "connection_profiles" / filename
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(profile, f, default_flow_style=False, sort_keys=False)


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.debug("Manifest written: %s", path.name)
