"""
SAP Connection Service — real RFC connectivity for SKY Agent via SAP JCo + JPype.

Uses SAP Java Connector (JCo) called from Python through JPype, replacing the
deprecated pyrfc library. Requires:
  1. JPype1 (pip install jpype1)
  2. SAP JCo JAR + native library (sapjco3.jar + sapjco3.dll/.so)
     Download from SAP Support Portal with an S-user:
     https://support.sap.com/en/product/connectors/jco.html

JCo discovery order:
  1. Environment variable SAP_JCO_PATH (directory containing sapjco3.jar)
  2. C:\\SAP\\sapjco3  (Windows default)
  3. /opt/sap/sapjco3  (Linux default)
  4. ./lib/sapjco3      (relative to SKY Agent)

Responsibilities (all local, no cloud):
  1. Test RFC connectivity to an SAP system
  2. Read SAP system profile parameters (rsdb/dbms, dbs/hdb/schema, etc.)
  3. Return honest results — never fake or guess values
"""

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("sky_agent.sap_connection")


# ------------------------------------------------------------------
# JCo / JPype bootstrap
# ------------------------------------------------------------------

_JCO_AVAILABLE = False
_JCO_ERROR = ""

def _agent_lib_dir() -> Path:
    """Return the lib/ directory relative to the SKY Agent root."""
    return Path(__file__).resolve().parent.parent / "lib"


def _find_jco_path() -> Optional[str]:
    """Locate the directory containing sapjco3.jar."""
    candidates = [
        os.environ.get("SAP_JCO_PATH", ""),
        str(_agent_lib_dir() / "sapjco3"),   # embedded with SKY Agent
        r"C:\SAP\sapjco3",
        r"C:\SAP_JCO",
        "/opt/sap/sapjco3",
    ]
    for path in candidates:
        if path and Path(path).is_dir():
            jar = Path(path) / "sapjco3.jar"
            if jar.is_file():
                return str(Path(path).resolve())
    return None


def _find_jvm_path() -> Optional[str]:
    """
    Locate the JVM shared library (jvm.dll / libjvm.so).

    Discovery order:
      1. Embedded JRE at sky_agent/lib/jre/  (bundled with SKY Agent)
      2. JAVA_HOME environment variable
      3. JPype default discovery (registry, PATH, etc.)
    """
    import jpype  # type: ignore[import-untyped]

    # 1. Embedded JRE shipped with SKY Agent
    embedded_jre = _agent_lib_dir() / "jre"
    if embedded_jre.is_dir():
        if sys.platform == "win32":
            jvm_dll = embedded_jre / "bin" / "server" / "jvm.dll"
        else:
            jvm_dll = embedded_jre / "lib" / "server" / "libjvm.so"
        if jvm_dll.is_file():
            logger.info("Using embedded JRE: %s", embedded_jre)
            return str(jvm_dll)

    # 2. JAVA_HOME
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home and Path(java_home).is_dir():
        if sys.platform == "win32":
            jvm_dll = Path(java_home) / "bin" / "server" / "jvm.dll"
        else:
            jvm_dll = Path(java_home) / "lib" / "server" / "libjvm.so"
        if jvm_dll.is_file():
            return str(jvm_dll)

    # 3. JPype default discovery
    try:
        return jpype.getDefaultJVMPath()
    except Exception:
        return None


def _ensure_jvm() -> bool:
    """Start the JVM with JCo on the classpath if not already running."""
    global _JCO_AVAILABLE, _JCO_ERROR

    try:
        import jpype  # type: ignore[import-untyped]
    except ImportError as e:
        _JCO_ERROR = "JPype not installed. Run: pip install jpype1"
        logger.error("jpype import failed: %s (sys.executable=%s)", e, sys.executable)
        return False

    if jpype.isJVMStarted():
        _JCO_AVAILABLE = True
        return True

    jco_dir = _find_jco_path()
    if not jco_dir:
        _JCO_ERROR = (
            "SAP JCo not found. Download sapjco3.jar and native library from "
            "https://support.sap.com/en/product/connectors/jco.html and place "
            "them in C:\\SAP\\sapjco3 or set SAP_JCO_PATH environment variable."
        )
        return False

    jvm_path = _find_jvm_path()
    if not jvm_path:
        _JCO_ERROR = (
            "Java Runtime not found. Install JRE/JDK 21+ or set JAVA_HOME. "
            "Download from https://adoptium.net/temurin/releases/"
        )
        return False

    jar_path = str(Path(jco_dir) / "sapjco3.jar")

    # Ensure sapjco3.dll can be found by Java's native library loader
    current_path = os.environ.get("PATH", "")
    if jco_dir not in current_path:
        os.environ["PATH"] = jco_dir + os.pathsep + current_path

    try:
        jpype.startJVM(
            jvm_path,
            f"-Djava.class.path={jar_path}",
            f"-Djava.library.path={jco_dir}",
            convertStrings=True,
        )
        _JCO_AVAILABLE = True
        logger.info("JVM started with JCo from %s (JVM: %s)", jco_dir, jvm_path)
        return True
    except Exception as e:
        _JCO_ERROR = f"Failed to start JVM with JCo — {e}"
        logger.exception("JVM startup failed")
        return False


# ------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------

@dataclass
class SAPConnectionConfig:
    """Parameters required to connect to an SAP system via RFC."""
    name: str = ""
    host: str = ""
    system_number: str = "00"
    client: str = "100"
    user: str = ""
    password: str = ""         # session-only, never persisted
    router_string: str = ""    # optional SAP Router string


@dataclass
class SAPConnectionResult:
    """Result of an SAP connection test."""
    success: bool = False
    message: str = ""
    error_code: str = ""       # e.g. "LOGON_FAILURE", "JCO_MISSING"
    system_info: dict = field(default_factory=dict)  # populated on success


@dataclass
class SAPProfileParams:
    """SAP profile parameters relevant for DB discovery."""
    db_type: str = ""           # e.g. "HDB", "ORA", "MSS", empty if not retrieved
    db_host: str = ""           # e.g. from RFCDBHOST
    db_schema: str = ""         # e.g. from dbs/hdb/schema
    instance_number: str = ""   # from connection config
    sap_system_id: str = ""     # SID
    retrieved_params: dict = field(default_factory=dict)  # raw param dict


# ------------------------------------------------------------------
# Internal: JCo destination provider
# ------------------------------------------------------------------

_DEST_NAME = "SKY_AGENT"

_provider_registered = False

def _register_destination(config: SAPConnectionConfig) -> None:
    """Register a JCo destination with the provided connection parameters."""
    global _provider_registered
    import jpype  # type: ignore[import-untyped]

    # Access Java classes via JClass (not Python-style imports)
    DestinationDataProvider = jpype.JClass("com.sap.conn.jco.ext.DestinationDataProvider")
    Environment = jpype.JClass("com.sap.conn.jco.ext.Environment")
    Properties = jpype.JClass("java.util.Properties")

    props = Properties()
    props.setProperty(DestinationDataProvider.JCO_ASHOST, config.host.strip())
    props.setProperty(DestinationDataProvider.JCO_SYSNR, config.system_number.strip())
    props.setProperty(DestinationDataProvider.JCO_CLIENT, config.client.strip())
    props.setProperty(DestinationDataProvider.JCO_USER, config.user.strip())
    props.setProperty(DestinationDataProvider.JCO_PASSWD, config.password.strip())
    props.setProperty(DestinationDataProvider.JCO_LANG, "EN")

    if config.router_string.strip():
        props.setProperty(DestinationDataProvider.JCO_SAPROUTER, config.router_string.strip())

    # Build a provider implementing DestinationDataProvider interface
    @jpype.JImplements(DestinationDataProvider)  # type: ignore[misc]
    class _SkyDestinationProvider:
        def __init__(self, dest_props):
            self._props = dest_props

        @jpype.JOverride  # type: ignore[misc]
        def getDestinationProperties(self, name):
            return self._props

        @jpype.JOverride  # type: ignore[misc]
        def supportsEvents(self):
            return False

        @jpype.JOverride  # type: ignore[misc]
        def setDestinationDataEventListener(self, listener):
            pass

    provider = _SkyDestinationProvider(props)

    # Register only once per JVM lifetime
    if not _provider_registered:
        try:
            Environment.registerDestinationDataProvider(provider)
            _provider_registered = True
        except Exception:
            pass  # may already be registered


# ------------------------------------------------------------------
# Internal: call an RFC function via JCo
# ------------------------------------------------------------------

def _jco_call(config: SAPConnectionConfig, function_name: str, import_params: Optional[dict] = None) -> dict:
    """
    Call an SAP RFC function module via JCo and return the export parameters as a dict.

    Raises exceptions on connection/logon/ABAP errors.
    """
    import jpype  # type: ignore[import-untyped]
    JCoDestinationManager = jpype.JClass("com.sap.conn.jco.JCoDestinationManager")

    _register_destination(config)

    dest = JCoDestinationManager.getDestination(_DEST_NAME)
    repo = dest.getRepository()
    function = repo.getFunction(function_name)

    if function is None:
        raise RuntimeError(f"Function module '{function_name}' not found in SAP system")

    # Set import parameters
    if import_params:
        imports = function.getImportParameterList()
        for key, value in import_params.items():
            imports.setValue(key, str(value))

    # Execute
    function.execute(dest)

    # Read export parameters into a Python dict
    exports = function.getExportParameterList()
    result = {}
    if exports is not None:
        metadata = exports.getListMetaData()
        for i in range(metadata.getFieldCount()):
            field_name = str(metadata.getName(i))
            try:
                # Try to get structure (nested)
                struct = exports.getStructure(field_name)
                if struct is not None:
                    struct_dict = {}
                    struct_meta = struct.getMetaData()
                    for j in range(struct_meta.getFieldCount()):
                        sname = str(struct_meta.getName(j))
                        struct_dict[sname] = str(struct.getString(sname))
                    result[field_name] = struct_dict
                    continue
            except Exception:
                pass
            try:
                result[field_name] = str(exports.getString(field_name))
            except Exception:
                pass

    return result


# ------------------------------------------------------------------
# Internal: clean JCo error messages for UI display
# ------------------------------------------------------------------

def _clean_jco_error(error_text: str) -> str:
    """
    Extract a clean, user-friendly message from verbose JCo exception text.

    JCo errors contain multi-line diagnostic dumps. This extracts only
    the meaningful parts for display in the UI.
    """
    import re

    # Extract the key error reason from JCo verbose output
    lines = error_text.strip().split("\n")
    first_line = lines[0].strip() if lines else error_text

    # Try to extract the short error from JCoException format:
    # "com.sap.conn.jco.JCoException: (102) JCO_ERROR_COMMUNICATION: ..."
    match = re.search(r"JCO_ERROR_\w+:\s*(.+?)(?:\s*connection parameters:|$)", first_line, re.IGNORECASE)
    if match:
        reason = match.group(1).strip()
    else:
        reason = first_line

    # Look for specific detail lines in the full error
    details = {}
    for line in lines:
        line = line.strip()
        if line.startswith("ERROR"):
            details["error"] = line.replace("ERROR", "").strip()
        elif line.startswith("ERRNO TEXT"):
            details["errno"] = line.replace("ERRNO TEXT", "").strip()

    # Build clean message
    if "WSAECONNREFUSED" in error_text:
        host_match = re.search(r"ASHOST=(\S+)\s+SYSNR=(\S+)", error_text)
        if host_match:
            return f"Connection refused at {host_match.group(1)}:{_sysnr_to_port(host_match.group(2))}. Check if SAP is running and the port is open."
        return "Connection refused. Check if SAP Gateway is running and the port is open."

    if "WSAETIMEDOUT" in error_text or "timed out" in error_text.lower():
        host_match = re.search(r"ASHOST=(\S+)\s+SYSNR=(\S+)", error_text)
        if host_match:
            return f"Connection timed out to {host_match.group(1)}:{_sysnr_to_port(host_match.group(2))}. Check host, firewall, and network."
        return "Connection timed out. Check host address, firewall, and network connectivity."

    if "WSAEHOSTUNREACH" in error_text or "host unreachable" in error_text.lower():
        return "Host unreachable. Check host address and network connectivity."

    if details.get("error"):
        return details["error"]

    # Fallback: return the reason extracted from first line, truncated
    if len(reason) > 150:
        reason = reason[:147] + "..."
    return reason


def _sysnr_to_port(sysnr: str) -> str:
    """Convert SAP system number to gateway port (e.g. '00' → '3300')."""
    try:
        return f"33{int(sysnr):02d}"
    except ValueError:
        return f"33{sysnr}"


# ------------------------------------------------------------------
# Connection Test
# ------------------------------------------------------------------

def test_sap_connection(config: SAPConnectionConfig) -> SAPConnectionResult:
    """
    Perform a real RFC connection test to an SAP system using JCo via JPype.

    Returns an honest result — success, specific error, or dependency-missing.
    """
    result = SAPConnectionResult()

    # ── Validate inputs ──
    if not config.host.strip():
        result.message = "Host is required."
        result.error_code = "MISSING_HOST"
        return result
    if not config.system_number.strip():
        result.message = "System Number is required."
        result.error_code = "MISSING_SYSNR"
        return result
    if not config.client.strip():
        result.message = "Client is required."
        result.error_code = "MISSING_CLIENT"
        return result
    if not config.user.strip():
        result.message = "Username is required."
        result.error_code = "MISSING_USER"
        return result
    if not config.password.strip():
        result.message = "Password is required."
        result.error_code = "MISSING_PASSWORD"
        return result

    # ── Ensure JVM + JCo ──
    if not _ensure_jvm():
        result.message = _JCO_ERROR
        result.error_code = "JCO_MISSING"
        logger.warning("JCo not available: %s", _JCO_ERROR)
        return result

    # ── Attempt real RFC connection ──
    try:
        # Call RFC_SYSTEM_INFO — lightweight, no side effects
        export = _jco_call(config, "RFC_SYSTEM_INFO")
        rfcsi = export.get("RFCSI_EXPORT", {})

        if isinstance(rfcsi, dict):
            sid = rfcsi.get("RFCSYSID", "SAP")
            host = rfcsi.get("RFCHOST", config.host)
            result.success = True
            result.message = f"Connected to {sid} ({host})"
            result.system_info = {
                "sid": rfcsi.get("RFCSYSID", ""),
                "host": rfcsi.get("RFCHOST", ""),
                "db_host": rfcsi.get("RFCDBHOST", ""),
                "db_sys": rfcsi.get("RFCDBSYS", ""),
                "kernel": rfcsi.get("RFCKERNRL", ""),
                "codepage": rfcsi.get("RFCCHARTYP", ""),
            }
            logger.info("SAP connection successful: SID=%s host=%s", sid, host)
        else:
            result.success = True
            result.message = f"Connected to SAP at {config.host}"

    except Exception as e:
        error_text = str(e)
        clean_msg = _clean_jco_error(error_text)
        error_lower = error_text.lower()

        if "logon" in error_lower or "password" in error_lower or "authentication" in error_lower:
            result.message = f"Authentication failed — {clean_msg}"
            result.error_code = "LOGON_FAILURE"
        elif "communication" in error_lower or "connect" in error_lower or "reach" in error_lower:
            result.message = f"Unreachable — {clean_msg}"
            result.error_code = "COMMUNICATION_ERROR"
        elif "not found" in error_lower:
            result.message = f"SAP function error — {clean_msg}"
            result.error_code = "ABAP_ERROR"
        else:
            result.message = f"Connection error — {clean_msg}"
            result.error_code = "UNKNOWN"
        logger.error("SAP connection error: %s", e)

    return result


# ------------------------------------------------------------------
# Profile Parameter Retrieval (for DB discovery)
# ------------------------------------------------------------------

def read_sap_profile_params(config: SAPConnectionConfig) -> tuple[SAPProfileParams, str]:
    """
    Read SAP profile parameters to discover database metadata.

    Retrieves parameters like rsdb/dbms, dbs/hdb/schema, SAPDBHOST, etc.
    Returns only what was actually read — never guesses or fabricates values.

    Returns:
        (params, error_message)  — error_message is empty on success
    """
    params = SAPProfileParams()

    if not _ensure_jvm():
        return params, (
            f"SAP JCo not available. {_JCO_ERROR} "
            "Database settings must be entered manually."
        )

    try:
        # 1. Get system info for basic DB host / DB system
        export = _jco_call(config, "RFC_SYSTEM_INFO")
        rfcsi = export.get("RFCSI_EXPORT", {})

        if isinstance(rfcsi, dict):
            params.sap_system_id = rfcsi.get("RFCSYSID", "")
            params.db_host = rfcsi.get("RFCDBHOST", "")
            params.instance_number = config.system_number.strip()

            db_sys = rfcsi.get("RFCDBSYS", "")
            if db_sys:
                params.db_type = db_sys

            params.retrieved_params["RFCDBHOST"] = params.db_host
            params.retrieved_params["RFCDBSYS"] = db_sys
            params.retrieved_params["RFCSYSID"] = params.sap_system_id

        # 2. Try to read individual profile parameters
        _profile_keys = [
            "rsdb/dbms",
            "dbs/hdb/schema",
            "SAPDBHOST",
            "dbs/hdb/dbname",
            "dbs/ora/tnsname",
            "dbs/mss/server",
        ]
        for key in _profile_keys:
            try:
                result = _jco_call(config, "TH_GET_PARAMETER", {"PARAMETER": key})
                value = result.get("VALUE", "").strip()
                if value:
                    params.retrieved_params[key] = value
                    if key == "rsdb/dbms":
                        params.db_type = value
                    elif key == "dbs/hdb/schema":
                        params.db_schema = value
                    elif key == "SAPDBHOST" and not params.db_host:
                        params.db_host = value
            except Exception:
                # Parameter not available or function not accessible — skip
                pass

        logger.info(
            "SAP profile read: db_type=%s, db_host=%s, schema=%s, sid=%s",
            params.db_type or "<not found>",
            params.db_host or "<not found>",
            params.db_schema or "<not found>",
            params.sap_system_id or "<not found>",
        )
        return params, ""

    except Exception as e:
        error_text = str(e)
        clean_msg = _clean_jco_error(error_text)
        error_lower = error_text.lower()
        if "logon" in error_lower or "password" in error_lower:
            return params, f"SAP authentication failed — {clean_msg}"
        elif "communication" in error_lower or "connect" in error_lower:
            return params, f"Cannot connect to SAP system — {clean_msg}"
        else:
            logger.exception("Error reading SAP profile parameters")
            return params, f"Error reading SAP parameters — {clean_msg}"


# ------------------------------------------------------------------
# DB Type Mapping (SAP DBMS code → display name)
# ------------------------------------------------------------------

SAP_DBMS_TO_DISPLAY = {
    "HDB": "HANA",
    "ORA": "Oracle",
    "MSS": "MSSQL",
    "ADA": "MaxDB",
    "DB6": "DB2",
    "SYB": "Sybase",
    "PG":  "PostgreSQL",
}


def sap_dbms_to_display(dbms_code: str) -> str:
    """Convert SAP DBMS code (e.g. 'HDB') to display name (e.g. 'HANA')."""
    return SAP_DBMS_TO_DISPLAY.get(dbms_code.upper().strip(), "")
