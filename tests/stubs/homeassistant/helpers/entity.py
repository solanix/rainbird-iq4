"""Minimal entity base class for integration architecture tests."""

from __future__ import annotations

from typing import Any


class Entity:
    """Generic entity."""

    _attr_has_entity_name = False
    _attr_unique_id: str | None = None
    _attr_device_info: dict[str, Any] | None = None

    @property
    def unique_id(self) -> str | None:
        """Return the unique ID."""
        return self._attr_unique_id

    @property
    def device_info(self) -> dict[str, Any] | None:
        """Return the device info."""
        return self._attr_device_info
