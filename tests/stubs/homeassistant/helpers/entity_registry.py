"""Minimal entity registry helpers."""

from __future__ import annotations

from typing import Any


def async_get(hass: Any) -> Any:
    """Return no entity registry in stub tests."""
    raise NotImplementedError


def async_entries_for_config_entry(registry: Any, config_entry_id: str) -> list[Any]:
    """Return no entries in stub tests."""
    raise NotImplementedError
