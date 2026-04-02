"""
Target Database Service — orchestrates DB connection testing, target structure
discovery, and SAP-based DB metadata detection.

Delegates real connectivity to:
  - sap_connection.py (RFC-based SAP connectivity and profile reading)
  - db_connection.py  (real database driver connectivity and schema queries)

Responsibilities (all local, no cloud):
  1. Test database connectivity for Migration Cockpit staging DB
  2. Discover target/staging metadata from the connected database
  3. Detect DB settings from SAP system profile (RFC)
  4. Store discovered structure locally in the project folder

Never fabricates values. Fields that cannot be determined are left empty.

Storage location:
  projects/<project_code>/input/target_metadata/
    - target_objects_manifest.json
    - <object_code>_target_structure.json  (per-object)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sky_agent.services.db_connection import (
    DBConnectionConfig,
    DBConnectionResult,
    DiscoveredTable,
    SchemaDiscoveryResult,
    discover_schema_tables,
    test_db_connection,
)
from sky_agent.services.sap_connection import (
    SAPConnectionConfig,
    SAPConnectionResult,
    SAPProfileParams,
    read_sap_profile_params,
    sap_dbms_to_display,
    test_sap_connection,
)

logger = logging.getLogger("sky_agent.target_db_service")


# ------------------------------------------------------------------
# Data Models (kept for backward compatibility with existing callers)
# ------------------------------------------------------------------

@dataclass
class StagingDBConfig:
    """Configuration for the Migration Cockpit staging database."""
    connection_name: str = ""
    db_type: str = ""           # HANA | Oracle | MSSQL | PostgreSQL — empty until known
    host: str = ""
    port: str = ""              # empty until known
    service_name: str = ""      # database / service name
    schema: str = ""
    username: str = ""
    password: str = ""          # never persisted — session only

    def to_db_config(self) -> DBConnectionConfig:
        """Convert to db_connection.DBConnectionConfig."""
        return DBConnectionConfig(
            connection_name=self.connection_name,
            db_type=self.db_type,
            host=self.host,
            port=self.port,
            service_name=self.service_name,
            schema=self.schema,
            username=self.username,
            password=self.password,
        )


# ------------------------------------------------------------------
# Connection Test (delegates to db_connection)
# ------------------------------------------------------------------

def test_connection(config: StagingDBConfig) -> tuple[bool, str]:
    """
    Test connectivity to the staging database using real DB drivers.

    Returns:
        (success: bool, message: str)
    """
    result = test_db_connection(config.to_db_config())
    return result.success, result.message


# ------------------------------------------------------------------
# Target Structure Discovery (delegates to db_connection)
# ------------------------------------------------------------------

def discover_target_structure(
    config: StagingDBConfig,
    project_dir: Optional[Path] = None,
) -> SchemaDiscoveryResult:
    """
    Discover real target/staging metadata from the connected database.

    Queries actual system views — returns only what is actually found.
    """
    result = discover_schema_tables(config.to_db_config())

    # Persist to project folder if successful
    if result.status == "done" and project_dir:
        _persist_discovery(project_dir, config, result)

    return result


# ------------------------------------------------------------------
# SAP Profile → DB Metadata Detection (delegates to sap_connection)
# ------------------------------------------------------------------

@dataclass
class DetectedDBSettings:
    """Fields actually retrieved from the SAP system profile via RFC."""
    db_type: str = ""       # only set if actually read from rsdb/dbms
    host: str = ""          # only set if read from RFCDBHOST / SAPDBHOST
    port: str = ""          # only set if reliably determined
    service_name: str = ""  # only set if read from profile
    schema: str = ""        # only set if read from dbs/hdb/schema
    discovered: list = field(default_factory=list)      # field names that were found
    not_discovered: list = field(default_factory=list)   # field names left empty


def detect_staging_db_from_sap(
    sap_host: str,
    sap_sys_number: str,
    sap_client: str,
    sap_user: str,
    sap_password: str,
    sap_name: str = "",
) -> tuple[DetectedDBSettings, str]:
    """
    Detect staging database settings by reading the SAP system profile via RFC.

    Connects to the SAP system and reads real profile parameters.
    Only populates fields that are actually retrieved — never guesses.

    Returns:
        (settings, error_message)  — error_message is empty on success
    """
    settings = DetectedDBSettings()

    config = SAPConnectionConfig(
        name=sap_name,
        host=sap_host,
        system_number=sap_sys_number,
        client=sap_client,
        user=sap_user,
        password=sap_password,
    )

    params, error = read_sap_profile_params(config)

    if error:
        return settings, error

    # Populate only what was actually discovered
    # DB Type
    display_type = sap_dbms_to_display(params.db_type) if params.db_type else ""
    if display_type:
        settings.db_type = display_type
        settings.discovered.append("DB type")
    else:
        settings.not_discovered.append("DB type")

    # Host
    if params.db_host:
        settings.host = params.db_host
        settings.discovered.append("host")
    else:
        settings.not_discovered.append("host")

    # Schema
    if params.db_schema:
        settings.schema = params.db_schema
        settings.discovered.append("schema")
    else:
        settings.not_discovered.append("schema")

    # Port and service_name cannot be reliably read from SAP profile
    settings.not_discovered.append("port")
    settings.not_discovered.append("database/service name")

    logger.info(
        "SAP DB detection: discovered=%s, not_discovered=%s for %s",
        settings.discovered,
        settings.not_discovered,
        sap_name or sap_host or "unknown",
    )

    return settings, ""


# ------------------------------------------------------------------
# Local Persistence
# ------------------------------------------------------------------

def _persist_discovery(
    project_dir: Path,
    config: StagingDBConfig,
    result: SchemaDiscoveryResult,
) -> None:
    """Store discovered target metadata locally in the project folder."""
    target_dir = project_dir / "input" / "target_metadata"
    target_dir.mkdir(parents=True, exist_ok=True)

    # Write manifest
    manifest = {
        "discovery_version": "2.0",
        "connection": {
            "name": config.connection_name,
            "db_type": config.db_type,
            "host": config.host,
            "port": config.port,
            "service_name": config.service_name,
            "schema": config.schema,
        },
        "discovery_timestamp": result.timestamp,
        "status": result.status,
        "table_count": result.count,
        "tables": [
            {
                "table_name": t.table_name,
                "schema_name": t.schema_name,
                "column_count": t.column_count,
                "table_type": t.table_type,
            }
            for t in result.tables
        ],
    }
    manifest_path = target_dir / "target_objects_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Write per-table structure files
    for t in result.tables:
        table_data = {
            "table_name": t.table_name,
            "schema_name": t.schema_name,
            "column_count": t.column_count,
            "row_count": t.row_count,
            "table_type": t.table_type,
            "discovered_at": result.timestamp,
            "columns": [],  # populated by deeper column-level queries
        }
        filename = f"{t.table_name.lower()}_structure.json"
        filepath = target_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(table_data, f, indent=2, ensure_ascii=False)

    logger.info("Discovery persisted to %s (%d tables)", target_dir, result.count)
