"""Minimal storage helper."""

from __future__ import annotations

from typing import Any


class Store[T]:
    """In-memory stand-in for Home Assistant's JSON store."""

    def __init__(self, hass: Any, version: int, key: str) -> None:
        self.key = key
        self.data: T | None = None

    async def async_load(self) -> T | None:
        """Return saved data."""
        return self.data

    async def async_save(self, data: T) -> None:
        """Save data in memory."""
        self.data = data

    async def async_remove(self) -> None:
        """Remove saved data."""
        self.data = None
