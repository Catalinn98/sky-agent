"""
Object Catalog Registry — loads and indexes all object definitions from YAML.

Usage:
    catalog = ObjectCatalog()
    obj = catalog.get("cost_center")
    tables = catalog.get_tables("cost_center")
    all_codes = catalog.list_objects()
"""

from pathlib import Path
from typing import Optional

import yaml


_CATALOG_DIR = Path(__file__).parent


class ObjectCatalog:
    """Central registry for SAP data object definitions."""

    def __init__(self, catalog_dir: Optional[Path] = None):
        self._dir = catalog_dir or _CATALOG_DIR / "objects"
        self._definitions: dict[str, dict] = {}
        self._validations: dict[str, dict] = {}
        self._load_objects()
        self._load_validations()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_objects(self) -> None:
        if not self._dir.exists():
            return
        for path in sorted(self._dir.glob("*.yaml")):
            with open(path, "r", encoding="utf-8") as f:
                definition = yaml.safe_load(f)
            if definition and "object_code" in definition:
                self._definitions[definition["object_code"]] = definition

    def _load_validations(self) -> None:
        validations_dir = self._dir.parent / "validations"
        if not validations_dir.exists():
            return
        for path in sorted(validations_dir.glob("*.yaml")):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and "validation_code" in data:
                self._validations[data["validation_code"]] = data

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, object_code: str) -> Optional[dict]:
        """Return full object definition or None."""
        return self._definitions.get(object_code)

    def get_tables(self, object_code: str) -> list[dict]:
        """Return table list for an object."""
        obj = self.get(object_code)
        return obj.get("source_tables", []) if obj else []

    def get_joins(self, object_code: str) -> list[dict]:
        """Return join definitions for an object."""
        obj = self.get(object_code)
        return obj.get("join_logic", []) if obj else []

    def get_default_validations(self, object_code: str) -> list[str]:
        """Return default validation codes for an object."""
        obj = self.get(object_code)
        return obj.get("default_validations", []) if obj else []

    def get_validation(self, validation_code: str) -> Optional[dict]:
        """Return a validation definition."""
        return self._validations.get(validation_code)

    def list_objects(self) -> list[str]:
        """Return all available object codes."""
        return list(self._definitions.keys())

    def list_by_category(self, category: str) -> list[str]:
        """Return object codes filtered by category."""
        return [
            code
            for code, defn in self._definitions.items()
            if defn.get("category") == category
        ]

    def list_categories(self) -> list[str]:
        """Return all unique categories."""
        return sorted(
            {defn.get("category", "") for defn in self._definitions.values()}
            - {""}
        )
