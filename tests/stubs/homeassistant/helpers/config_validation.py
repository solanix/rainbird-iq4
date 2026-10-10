"""Minimal config validation helpers."""

from __future__ import annotations

from typing import Any


def string(value: Any) -> str:
    """Coerce a value to a string."""
    return str(value)


def config_entry_only_config_schema(domain: str) -> Any:
    """Return a schema placeholder for config-entry-only integrations."""
    return None
