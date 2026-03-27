"""
SAP Logon Discovery Service — reads SAP GUI system entries from Windows.

Discovers SAP systems by scanning real configuration files stored on
the local machine by SAP GUI for Windows:

  1.  SAPUILandscape.xml  (modern format, SAP GUI 7.40+)
  2.  saplogon.ini        (legacy INI format)

The service uses a *provider* pattern so additional sources can be
added later without touching the core orchestration.

SECURITY: Only connection metadata is read — no business data is
accessed, transmitted, or stored.
"""

from __future__ import annotations

import abc
import configparser
import logging
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

log = logging.getLogger("sky-agent")

# Import the model — when running as part of the agent package tree
try:
    from models.sap_system import SAPSystem, SAPLogonDiscoveryResult
except ImportError:
    from sky_agent.models.sap_system import SAPSystem, SAPLogonDiscoveryResult


# ═══════════════════════════════════════════════════════════════════════════════
# Provider base class
# ═══════════════════════════════════════════════════════════════════════════════

class SAPLogonProvider(abc.ABC):
    """Abstract base for a SAP Logon configuration reader."""

    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @abc.abstractmethod
    def discover(self) -> List[SAPSystem]: ...

    @abc.abstractmethod
    def is_available(self) -> bool: ...


# ═══════════════════════════════════════════════════════════════════════════════
# Provider 1 — SAPUILandscape.xml  (modern format)
# ═══════════════════════════════════════════════════════════════════════════════

class SAPUILandscapeProvider(SAPLogonProvider):
    """
    Reads the SAPUILandscape.xml file created by SAP GUI 7.40+.

    Default user-level path:
        %APPDATA%\\SAP\\Common\\SAPUILandscape.xml

    The XML structure uses the namespace
        urn:sap-com:document:sap:business:landscape
    and contains <Service> elements inside <Services>.

    Each <Service> may have attributes:
        name, systemid, server, mshost, sncname, routerstring, etc.
    and a child <Memo> with a text description.
    """

    # Well-known search paths (user-level, then machine-level)
    _SEARCH_PATHS: list[str] = [
        os.path.join(os.environ.get("APPDATA", ""), "SAP", "Common", "SAPUILandscape.xml"),
        os.path.join(os.environ.get("PROGRAMDATA", ""), "SAP", "SAPUILandscape.xml"),
    ]

    _NS = {"sap": "urn:sap-com:document:sap:business:landscape"}

    def __init__(self) -> None:
        self._xml_path: str | None = None
        for p in self._SEARCH_PATHS:
            if p and os.path.isfile(p):
                self._xml_path = p
                break
        # Also check Windows registry for a custom path
        if self._xml_path is None:
            self._xml_path = self._path_from_registry()

    @property
    def name(self) -> str:
        return "SAPUILandscape.xml"

    def is_available(self) -> bool:
        return self._xml_path is not None and os.path.isfile(self._xml_path)

    def discover(self) -> List[SAPSystem]:
        if not self.is_available():
            return []

        systems: list[SAPSystem] = []
        try:
            tree = ET.parse(self._xml_path)
            root = tree.getroot()
        except ET.ParseError as exc:
            log.warning("Failed to parse %s: %s", self._xml_path, exc)
            return []

        # The XML may or may not use a namespace.
        # Try namespace-aware first, then fallback to plain tags.
        services = root.findall(".//sap:Services/sap:Service", self._NS)
        if not services:
            services = root.findall(".//{urn:sap-com:document:sap:business:landscape}Service")
        if not services:
            # Fallback: no namespace at all (some exports lack it)
            services = root.findall(".//Services/Service")
        if not services:
            services = root.findall(".//Service")

        for svc in services:
            display_name = (
                svc.get("name", "")
                or svc.get("description", "")
                or svc.get("uuid", "")
            )
            if not display_name:
                continue

            # Instance number may be embedded in the server string or explicit
            sys_number = svc.get("systemNumber", svc.get("systemnr", ""))

            # Parse server — may be "host:port" format
            raw_server = svc.get("server", "")
            host = raw_server
            if ":" in raw_server and not sys_number:
                host_part, port_part = raw_server.rsplit(":", 1)
                host = host_part
                # SAP GUI uses port 32XX where XX is the instance number
                try:
                    port = int(port_part)
                    if 3200 <= port <= 3299:
                        sys_number = f"{port - 3200:02d}"
                except ValueError:
                    pass

            # Determine connection type
            conn_type = svc.get("type", "")
            if not conn_type:
                if svc.get("mshost"):
                    conn_type = "group"
                elif raw_server:
                    conn_type = "direct"

            memo_el = svc.find("sap:Memo", self._NS)
            if memo_el is None:
                memo_el = svc.find("Memo")

            systems.append(SAPSystem(
                display_name=display_name.strip(),
                sid=svc.get("systemid", svc.get("sid", "")).strip(),
                host=host.strip(),
                system_number=sys_number.strip(),
                router_string=svc.get("routerstring", svc.get("saprouter", "")).strip(),
                connection_type=conn_type.strip(),
                message_server=svc.get("mshost", "").strip(),
                group=svc.get("group", svc.get("groupselection", "")).strip(),
                source="sap_logon",
            ))

        log.info("SAPUILandscape: discovered %d systems from %s",
                 len(systems), self._xml_path)
        return systems

    @staticmethod
    def _path_from_registry() -> str | None:
        """Check the Windows registry for a custom SAPUILandscape.xml path."""
        if os.name != "nt":
            return None
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\SAP\SAPLogon\Options",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "LandscapeFileOnServer")
                if val and os.path.isfile(val):
                    return val
        except (OSError, FileNotFoundError):
            pass
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"Software\SAP\SAPLogon\Options",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "LandscapeFileOnServer")
                if val and os.path.isfile(val):
                    return val
        except (OSError, FileNotFoundError):
            pass
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Provider 2 — saplogon.ini  (legacy format)
# ═══════════════════════════════════════════════════════════════════════════════

class SAPLogonIniProvider(SAPLogonProvider):
    """
    Reads the legacy saplogon.ini file used by older SAP GUI installations.

    The file location is normally stored in the Windows registry at:
        HKCU\\Software\\SAP\\SAPLogon\\Options  →  IniFile

    Fallback paths:
        %APPDATA%\\SAP\\Common\\saplogon.ini
        %WINDIR%\\saplogon.ini

    The INI uses numbered suffix sections for each entry:
        [Description]   → Item1, Item2, ...
        [MSSysName]     → Item1, Item2, ...   (SID)
        [Server]        → Item1, Item2, ...   (app server host)
        [Router]        → Item1, Item2, ...
        [SystemNumber]  → Item1, Item2, ...
        [Database]      → Item1, Item2, ...
        [MessageServer] → Item1, Item2, ...
        [Group]         → Item1, Item2, ...
    """

    _FALLBACK_PATHS: list[str] = [
        os.path.join(os.environ.get("APPDATA", ""), "SAP", "Common", "saplogon.ini"),
        os.path.join(os.environ.get("WINDIR", ""), "saplogon.ini"),
    ]

    def __init__(self) -> None:
        self._ini_path: str | None = self._path_from_registry()
        if self._ini_path is None:
            for p in self._FALLBACK_PATHS:
                if p and os.path.isfile(p):
                    self._ini_path = p
                    break

    @property
    def name(self) -> str:
        return "saplogon.ini"

    def is_available(self) -> bool:
        return self._ini_path is not None and os.path.isfile(self._ini_path)

    def discover(self) -> List[SAPSystem]:
        if not self.is_available():
            return []

        config = configparser.RawConfigParser()
        try:
            config.read(self._ini_path, encoding="utf-8")
        except Exception:
            try:
                config.read(self._ini_path, encoding="latin-1")
            except Exception as exc:
                log.warning("Failed to read %s: %s", self._ini_path, exc)
                return []

        # Determine how many entries exist
        descriptions = self._section_items(config, "Description")
        if not descriptions:
            log.info("saplogon.ini: no entries in [Description]")
            return []

        servers = self._section_items(config, "Server")
        sys_numbers = self._section_items(config, "SystemNumber")
        sids = self._section_items(config, "MSSysName")
        routers = self._section_items(config, "Router")
        msg_servers = self._section_items(config, "MessageServer")
        groups = self._section_items(config, "Group")

        systems: list[SAPSystem] = []
        for i, desc in enumerate(descriptions):
            if not desc:
                continue

            host = servers[i] if i < len(servers) else ""
            msg_srv = msg_servers[i] if i < len(msg_servers) else ""

            conn_type = ""
            if msg_srv:
                conn_type = "group"
            elif host:
                conn_type = "direct"

            systems.append(SAPSystem(
                display_name=desc.strip(),
                sid=sids[i].strip() if i < len(sids) else "",
                host=(host or msg_srv).strip(),
                system_number=sys_numbers[i].strip() if i < len(sys_numbers) else "",
                router_string=routers[i].strip() if i < len(routers) else "",
                connection_type=conn_type,
                message_server=msg_srv.strip(),
                group=groups[i].strip() if i < len(groups) else "",
                source="sap_logon",
            ))

        log.info("saplogon.ini: discovered %d systems from %s",
                 len(systems), self._ini_path)
        return systems

    @staticmethod
    def _section_items(config: configparser.RawConfigParser, section: str) -> list[str]:
        """Extract ordered Item1..ItemN values from an INI section."""
        if not config.has_section(section):
            return []
        items: list[tuple[int, str]] = []
        for key, val in config.items(section):
            # Keys are like "item1", "item2", ...
            lower = key.lower()
            if lower.startswith("item"):
                try:
                    idx = int(lower[4:])
                    items.append((idx, val))
                except ValueError:
                    continue
        items.sort(key=lambda x: x[0])
        return [v for _, v in items]

    @staticmethod
    def _path_from_registry() -> str | None:
        """Look up the saplogon.ini path from the Windows registry."""
        if os.name != "nt":
            return None
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\SAP\SAPLogon\Options",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "IniFile")
                if val and os.path.isfile(val):
                    return val
        except (OSError, FileNotFoundError):
            pass
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Discovery Service — orchestrates all providers
# ═══════════════════════════════════════════════════════════════════════════════

class SAPLogonDiscoveryService:
    """
    Orchestrates SAP Logon discovery across all registered providers.

    Usage:
        service = SAPLogonDiscoveryService()
        result = service.discover()
        print(result.to_dict())
    """

    def __init__(self, providers: list[SAPLogonProvider] | None = None) -> None:
        if providers is not None:
            self._providers = providers
        else:
            # Default: modern first, then legacy
            self._providers: list[SAPLogonProvider] = [
                SAPUILandscapeProvider(),
                SAPLogonIniProvider(),
            ]

    def discover(self) -> SAPLogonDiscoveryResult:
        """Run all providers and return a merged, deduplicated result."""
        result = SAPLogonDiscoveryResult()
        seen_names: set[str] = set()
        any_available = False

        for provider in self._providers:
            if not provider.is_available():
                log.info("Provider '%s' not available — skipping", provider.name)
                continue

            any_available = True
            try:
                systems = provider.discover()
                for sys in systems:
                    # Deduplicate by display_name (case-insensitive)
                    key = sys.display_name.lower()
                    if key not in seen_names:
                        seen_names.add(key)
                        result.systems.append(sys)
            except Exception as exc:
                msg = f"Provider '{provider.name}' failed: {exc}"
                log.error(msg)
                result.errors.append(msg)

        if not any_available:
            result.errors.append(
                "SAP GUI / SAP Logon is not installed or no configuration files were found on this machine."
            )

        result.count = len(result.systems)
        return result
