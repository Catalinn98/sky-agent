"""
Database Connection Service — real DB connectivity for SKY Agent.

Performs actual database connection tests using appropriate drivers.
Returns honest results — never fakes success.

Supported databases:
  - SAP HANA (hdbcli)
  - Oracle (oracledb)
  - Microsoft SQL Server (pyodbc or pymssql)
  - PostgreSQL (psycopg2)

Responsibilities (all local, no cloud):
  1. Test database connectivity with real credentials
  2. Return precise error diagnostics
  3. Query real schema metadata for target structure discovery
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("sky_agent.db_connection")


# ── Driver availability checks ──────────────────────────────────────────────

def _check_driver(db_type: str) -> tuple[bool, str]:
    """Check if the required DB driver is installed. Returns (available, message)."""
    db_type = db_type.upper().strip()

    if db_type == "HANA":
        try:
            import hdbcli.dbapi  # type: ignore[import-untyped]
            return True, ""
        except ImportError:
            return False, "HANA driver not installed. Run: pip install hdbcli"

    elif db_type == "ORACLE":
        try:
            import oracledb  # type: ignore[import-untyped]
            return True, ""
        except ImportError:
            try:
                import cx_Oracle  # type: ignore[import-untyped]
                return True, ""
            except ImportError:
                return False, "Oracle driver not installed. Run: pip install oracledb"

    elif db_type == "MSSQL":
        try:
            import pyodbc  # type: ignore[import-untyped]
            return True, ""
        except ImportError:
            try:
                import pymssql  # type: ignore[import-untyped]
                return True, ""
            except ImportError:
                return False, "MSSQL driver not installed. Run: pip install pyodbc"

    elif db_type == "POSTGRESQL":
        try:
            import psycopg2  # type: ignore[import-untyped]
            return True, ""
        except ImportError:
            return False, "PostgreSQL driver not installed. Run: pip install psycopg2-binary"

    else:
        return False, f"Unsupported database type: {db_type}"


# ------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------

@dataclass
class DBConnectionConfig:
    """Configuration for a database connection."""
    connection_name: str = ""
    db_type: str = ""          # HANA | Oracle | MSSQL | PostgreSQL
    host: str = ""
    port: str = ""
    service_name: str = ""     # database / service / SID
    schema: str = ""
    username: str = ""
    password: str = ""         # session-only, never persisted


@dataclass
class DBConnectionResult:
    """Result of a database connection test."""
    success: bool = False
    message: str = ""
    error_code: str = ""       # DRIVER_MISSING | AUTH_FAILED | UNREACHABLE | etc.
    server_info: dict = field(default_factory=dict)


@dataclass
class DiscoveredTable:
    """A single table discovered from real schema metadata."""
    table_name: str = ""
    schema_name: str = ""
    column_count: int = 0
    row_count: int = -1        # -1 means not counted
    table_type: str = ""       # TABLE | VIEW


@dataclass
class SchemaDiscoveryResult:
    """Result from a real schema metadata discovery."""
    status: str = "none"       # none | running | done | failed
    tables: list = field(default_factory=list)
    schema: str = ""
    timestamp: str = ""
    error: str = ""

    @property
    def count(self) -> int:
        return len(self.tables)


# ------------------------------------------------------------------
# Connection Test
# ------------------------------------------------------------------

def test_db_connection(config: DBConnectionConfig) -> DBConnectionResult:
    """
    Perform a real database connection test.

    Returns honest result with specific error diagnostics.
    """
    result = DBConnectionResult()

    # ── Validate inputs ──
    if not config.db_type.strip():
        result.message = "Database type is required."
        result.error_code = "MISSING_DB_TYPE"
        return result
    if not config.host.strip():
        result.message = "Host is required."
        result.error_code = "MISSING_HOST"
        return result
    if not config.port.strip():
        result.message = "Port is required."
        result.error_code = "MISSING_PORT"
        return result
    if not config.service_name.strip():
        result.message = "Database / Service Name is required."
        result.error_code = "MISSING_SERVICE"
        return result
    if not config.username.strip():
        result.message = "Username is required."
        result.error_code = "MISSING_USER"
        return result
    if not config.password.strip():
        result.message = "Password is required."
        result.error_code = "MISSING_PASSWORD"
        return result

    # ── Check driver availability ──
    db_type = config.db_type.upper().strip()
    available, driver_msg = _check_driver(db_type)
    if not available:
        result.message = driver_msg
        result.error_code = "DRIVER_MISSING"
        logger.warning("DB driver not available for %s: %s", db_type, driver_msg)
        return result

    # ── Attempt real connection ──
    try:
        if db_type == "HANA":
            result = _test_hana(config)
        elif db_type == "ORACLE":
            result = _test_oracle(config)
        elif db_type == "MSSQL":
            result = _test_mssql(config)
        elif db_type == "POSTGRESQL":
            result = _test_postgresql(config)
        else:
            result.message = f"Unsupported database type: {config.db_type}"
            result.error_code = "UNSUPPORTED_TYPE"
    except Exception as e:
        result.message = f"Unexpected error — {e}"
        result.error_code = "UNKNOWN"
        logger.exception("Unexpected error during DB connection test")

    return result


# ------------------------------------------------------------------
# Per-DB Connection Implementations
# ------------------------------------------------------------------

def _test_hana(config: DBConnectionConfig) -> DBConnectionResult:
    """Test HANA connection using hdbcli."""
    import hdbcli.dbapi  # type: ignore[import-untyped]
    result = DBConnectionResult()
    conn = None
    try:
        conn = hdbcli.dbapi.connect(
            address=config.host.strip(),
            port=int(config.port.strip()),
            user=config.username.strip(),
            password=config.password.strip(),
            databaseName=config.service_name.strip() if config.service_name.strip() else None,
        )
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE_NAME, VERSION FROM SYS.M_DATABASE")
        row = cursor.fetchone()
        cursor.close()
        result.success = True
        result.message = f"Connected to HANA — {row[0] if row else 'OK'}"
        if row:
            result.server_info = {"database_name": row[0], "version": row[1]}
    except hdbcli.dbapi.Error as e:
        error_text = str(e)
        if "authentication" in error_text.lower() or "10" in str(getattr(e, 'errorcode', '')):
            result.error_code = "AUTH_FAILED"
            result.message = f"Authentication failed — {e}"
        elif "connection" in error_text.lower() or "timeout" in error_text.lower():
            result.error_code = "UNREACHABLE"
            result.message = f"Unreachable — {e}"
        else:
            result.error_code = "DB_ERROR"
            result.message = f"HANA error — {e}"
        logger.error("HANA connection error: %s", e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return result


def _test_oracle(config: DBConnectionConfig) -> DBConnectionResult:
    """Test Oracle connection using oracledb (or cx_Oracle fallback)."""
    result = DBConnectionResult()
    conn = None
    try:
        try:
            import oracledb  # type: ignore[import-untyped]
            driver = oracledb
        except ImportError:
            import cx_Oracle as driver  # type: ignore[import-untyped,no-redef]

        dsn = driver.makedsn(
            config.host.strip(),
            int(config.port.strip()),
            service_name=config.service_name.strip(),
        )
        conn = driver.connect(
            user=config.username.strip(),
            password=config.password.strip(),
            dsn=dsn,
        )
        cursor = conn.cursor()
        cursor.execute("SELECT BANNER FROM V$VERSION WHERE ROWNUM = 1")
        row = cursor.fetchone()
        cursor.close()
        result.success = True
        result.message = f"Connected to Oracle — {row[0] if row else 'OK'}"
        if row:
            result.server_info = {"version_banner": row[0]}
    except Exception as e:
        error_text = str(e).lower()
        if "ora-01017" in error_text or "invalid" in error_text:
            result.error_code = "AUTH_FAILED"
            result.message = f"Authentication failed — {e}"
        elif "ora-12541" in error_text or "ora-12170" in error_text or "timeout" in error_text:
            result.error_code = "UNREACHABLE"
            result.message = f"Unreachable — {e}"
        else:
            result.error_code = "DB_ERROR"
            result.message = f"Oracle error — {e}"
        logger.error("Oracle connection error: %s", e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return result


def _test_mssql(config: DBConnectionConfig) -> DBConnectionResult:
    """Test MSSQL connection using pyodbc (or pymssql fallback)."""
    result = DBConnectionResult()
    conn = None
    try:
        try:
            import pyodbc  # type: ignore[import-untyped]
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={config.host.strip()},{config.port.strip()};"
                f"DATABASE={config.service_name.strip()};"
                f"UID={config.username.strip()};"
                f"PWD={config.password.strip()};"
                f"Connect Timeout=10;"
            )
            conn = pyodbc.connect(conn_str)
        except ImportError:
            import pymssql  # type: ignore[import-untyped]
            conn = pymssql.connect(
                server=config.host.strip(),
                port=config.port.strip(),
                user=config.username.strip(),
                password=config.password.strip(),
                database=config.service_name.strip(),
                login_timeout=10,
            )

        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        row = cursor.fetchone()
        cursor.close()
        result.success = True
        result.message = f"Connected to SQL Server — OK"
        if row:
            result.server_info = {"version": str(row[0])[:100]}
    except Exception as e:
        error_text = str(e).lower()
        if "login" in error_text or "password" in error_text:
            result.error_code = "AUTH_FAILED"
            result.message = f"Authentication failed — {e}"
        elif "timeout" in error_text or "connection" in error_text:
            result.error_code = "UNREACHABLE"
            result.message = f"Unreachable — {e}"
        else:
            result.error_code = "DB_ERROR"
            result.message = f"SQL Server error — {e}"
        logger.error("MSSQL connection error: %s", e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return result


def _test_postgresql(config: DBConnectionConfig) -> DBConnectionResult:
    """Test PostgreSQL connection using psycopg2."""
    import psycopg2  # type: ignore[import-untyped]
    result = DBConnectionResult()
    conn = None
    try:
        conn = psycopg2.connect(
            host=config.host.strip(),
            port=int(config.port.strip()),
            dbname=config.service_name.strip(),
            user=config.username.strip(),
            password=config.password.strip(),
            connect_timeout=10,
        )
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        row = cursor.fetchone()
        cursor.close()
        result.success = True
        result.message = f"Connected to PostgreSQL — {row[0][:60] if row else 'OK'}"
        if row:
            result.server_info = {"version": row[0]}
    except psycopg2.OperationalError as e:
        error_text = str(e).lower()
        if "password" in error_text or "authentication" in error_text:
            result.error_code = "AUTH_FAILED"
            result.message = f"Authentication failed — {e}"
        elif "timeout" in error_text or "connect" in error_text:
            result.error_code = "UNREACHABLE"
            result.message = f"Unreachable — {e}"
        else:
            result.error_code = "DB_ERROR"
            result.message = f"PostgreSQL error — {e}"
        logger.error("PostgreSQL connection error: %s", e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return result


# ------------------------------------------------------------------
# Schema Metadata Discovery
# ------------------------------------------------------------------

def discover_schema_tables(config: DBConnectionConfig) -> SchemaDiscoveryResult:
    """
    Discover real table metadata from the database schema.

    Queries actual INFORMATION_SCHEMA or system views.
    Returns only what is actually found — never fabricates objects.
    """
    now = datetime.now(timezone.utc)
    result = SchemaDiscoveryResult(
        status="running",
        schema=config.schema.strip() or config.service_name.strip(),
        timestamp=now.strftime("%Y-%m-%d %H:%M"),
    )

    # Check driver
    available, driver_msg = _check_driver(config.db_type)
    if not available:
        result.status = "failed"
        result.error = driver_msg
        return result

    db_type = config.db_type.upper().strip()
    try:
        if db_type == "HANA":
            result.tables = _discover_hana(config)
        elif db_type == "ORACLE":
            result.tables = _discover_oracle(config)
        elif db_type == "MSSQL":
            result.tables = _discover_mssql(config)
        elif db_type == "POSTGRESQL":
            result.tables = _discover_postgresql(config)
        else:
            result.status = "failed"
            result.error = f"Unsupported database type: {config.db_type}"
            return result

        result.status = "done"
        logger.info(
            "Schema discovery complete: %d tables in %s",
            result.count,
            result.schema,
        )
    except Exception as e:
        result.status = "failed"
        result.error = f"Discovery failed — {e}"
        logger.exception("Schema discovery error")

    return result


def _discover_hana(config: DBConnectionConfig) -> list[DiscoveredTable]:
    """Discover tables from HANA schema using real metadata queries."""
    import hdbcli.dbapi  # type: ignore[import-untyped]
    tables: list[DiscoveredTable] = []
    conn = hdbcli.dbapi.connect(
        address=config.host.strip(),
        port=int(config.port.strip()),
        user=config.username.strip(),
        password=config.password.strip(),
    )
    try:
        cursor = conn.cursor()
        schema = config.schema.strip() or "SAPABAP1"
        cursor.execute(
            """
            SELECT TABLE_NAME, SCHEMA_NAME, TABLE_TYPE
            FROM SYS.TABLES
            WHERE SCHEMA_NAME = ?
            ORDER BY TABLE_NAME
            """,
            (schema,)
        )
        for row in cursor.fetchall():
            t = DiscoveredTable(
                table_name=row[0],
                schema_name=row[1],
                table_type=row[2] if len(row) > 2 else "TABLE",
            )
            tables.append(t)

        # Get column counts per table
        cursor.execute(
            """
            SELECT TABLE_NAME, COUNT(*) AS COL_COUNT
            FROM SYS.TABLE_COLUMNS
            WHERE SCHEMA_NAME = ?
            GROUP BY TABLE_NAME
            """,
            (schema,)
        )
        col_map = {row[0]: row[1] for row in cursor.fetchall()}
        for t in tables:
            t.column_count = col_map.get(t.table_name, 0)

        cursor.close()
    finally:
        conn.close()
    return tables


def _discover_oracle(config: DBConnectionConfig) -> list[DiscoveredTable]:
    """Discover tables from Oracle schema using real metadata queries."""
    try:
        import oracledb  # type: ignore[import-untyped]
        driver = oracledb
    except ImportError:
        import cx_Oracle as driver  # type: ignore[import-untyped,no-redef]

    tables: list[DiscoveredTable] = []
    dsn = driver.makedsn(
        config.host.strip(),
        int(config.port.strip()),
        service_name=config.service_name.strip(),
    )
    conn = driver.connect(
        user=config.username.strip(),
        password=config.password.strip(),
        dsn=dsn,
    )
    try:
        cursor = conn.cursor()
        schema = (config.schema.strip() or config.username.strip()).upper()
        cursor.execute(
            """
            SELECT t.TABLE_NAME, t.OWNER, 'TABLE' AS TABLE_TYPE,
                   NVL(c.COL_COUNT, 0) AS COL_COUNT
            FROM ALL_TABLES t
            LEFT JOIN (
                SELECT TABLE_NAME, OWNER, COUNT(*) AS COL_COUNT
                FROM ALL_TAB_COLUMNS
                WHERE OWNER = :schema
                GROUP BY TABLE_NAME, OWNER
            ) c ON t.TABLE_NAME = c.TABLE_NAME AND t.OWNER = c.OWNER
            WHERE t.OWNER = :schema
            ORDER BY t.TABLE_NAME
            """,
            {"schema": schema},
        )
        for row in cursor.fetchall():
            tables.append(DiscoveredTable(
                table_name=row[0],
                schema_name=row[1],
                table_type=row[2],
                column_count=row[3],
            ))
        cursor.close()
    finally:
        conn.close()
    return tables


def _discover_mssql(config: DBConnectionConfig) -> list[DiscoveredTable]:
    """Discover tables from MSSQL schema using real metadata queries."""
    tables: list[DiscoveredTable] = []
    try:
        import pyodbc  # type: ignore[import-untyped]
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={config.host.strip()},{config.port.strip()};"
            f"DATABASE={config.service_name.strip()};"
            f"UID={config.username.strip()};"
            f"PWD={config.password.strip()};"
        )
        conn = pyodbc.connect(conn_str)
    except ImportError:
        import pymssql  # type: ignore[import-untyped]
        conn = pymssql.connect(
            server=config.host.strip(),
            port=config.port.strip(),
            user=config.username.strip(),
            password=config.password.strip(),
            database=config.service_name.strip(),
        )

    try:
        cursor = conn.cursor()
        schema = config.schema.strip() or "dbo"
        cursor.execute(
            """
            SELECT t.TABLE_NAME, t.TABLE_SCHEMA, t.TABLE_TYPE,
                   (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS c
                    WHERE c.TABLE_NAME = t.TABLE_NAME
                      AND c.TABLE_SCHEMA = t.TABLE_SCHEMA) AS COL_COUNT
            FROM INFORMATION_SCHEMA.TABLES t
            WHERE t.TABLE_SCHEMA = ?
            ORDER BY t.TABLE_NAME
            """,
            (schema,),
        )
        for row in cursor.fetchall():
            tables.append(DiscoveredTable(
                table_name=row[0],
                schema_name=row[1],
                table_type="TABLE" if "TABLE" in str(row[2]) else "VIEW",
                column_count=row[3],
            ))
        cursor.close()
    finally:
        conn.close()
    return tables


def _discover_postgresql(config: DBConnectionConfig) -> list[DiscoveredTable]:
    """Discover tables from PostgreSQL schema using real metadata queries."""
    import psycopg2  # type: ignore[import-untyped]
    tables: list[DiscoveredTable] = []
    conn = psycopg2.connect(
        host=config.host.strip(),
        port=int(config.port.strip()),
        dbname=config.service_name.strip(),
        user=config.username.strip(),
        password=config.password.strip(),
    )
    try:
        cursor = conn.cursor()
        schema = config.schema.strip() or "public"
        cursor.execute(
            """
            SELECT t.table_name, t.table_schema, t.table_type,
                   (SELECT COUNT(*) FROM information_schema.columns c
                    WHERE c.table_name = t.table_name
                      AND c.table_schema = t.table_schema) AS col_count
            FROM information_schema.tables t
            WHERE t.table_schema = %s
            ORDER BY t.table_name
            """,
            (schema,),
        )
        for row in cursor.fetchall():
            tables.append(DiscoveredTable(
                table_name=row[0],
                schema_name=row[1],
                table_type="TABLE" if "TABLE" in str(row[2]).upper() else "VIEW",
                column_count=row[3],
            ))
        cursor.close()
    finally:
        conn.close()
    return tables
