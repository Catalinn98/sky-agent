"""
Normalized SAP System model returned by the SKY Agent discovery layer.

This model is shared between the agent's internal discovery logic and
the HTTP API response.  It deliberately contains ONLY connection
metadata — never business data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class SAPSystem:
    """A single SAP system discovered from the local machine."""

    display_name: str
    sid: str = ""
    host: str = ""
    system_number: str = ""
    router_string: str = ""
    connection_type: str = ""
    message_server: str = ""
    group: str = ""
    source: str = "sap_logon"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SAPLogonDiscoveryResult:
    """Aggregated result from all discovery providers."""

    count: int = 0
    systems: list[SAPSystem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "systems": [s.to_dict() for s in self.systems],
            "errors": self.errors,
        }
