"""Minimal data update coordinator for tests."""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from homeassistant.exceptions import HomeAssistantError

T = TypeVar("T")


class UpdateFailed(HomeAssistantError):
    """Raised when an update fails."""


class DataUpdateCoordinator[T]:
    """Simple coordinator stub used by tests."""

    def __init__(
        self,
        hass: Any,
        logger: logging.Logger,
        *,
        config_entry: Any = None,
        name: str,
        update_interval: Any = None,
    ) -> None:
        self.hass = hass
        self.logger = logger
        self.config_entry = config_entry
        self.name = name
        self.update_interval = update_interval
        self.data: T
        self.last_update_success = True

    async def async_config_entry_first_refresh(self) -> None:
        """Refresh data once for the initial setup."""
        self.data = await self._async_update_data()

    async def async_refresh(self) -> None:
        """Refresh while retaining the previous snapshot on failure."""
        try:
            self.data = await self._async_update_data()
        except UpdateFailed:
            self.last_update_success = False
        else:
            self.last_update_success = True

    async def _async_update_data(self) -> T:
        """Implement in subclasses."""
        raise NotImplementedError


class CoordinatorEntity[T]:
    """Minimal coordinator-backed entity."""

    _attr_unique_id: str | None = None
    _attr_device_info: dict[str, Any] | None = None

    def __init__(self, coordinator: T) -> None:
        self.coordinator = coordinator

    @property
    def unique_id(self) -> str | None:
        return self._attr_unique_id

    @property
    def device_info(self) -> dict[str, Any] | None:
        return self._attr_device_info

    @property
    def available(self) -> bool:
        return bool(getattr(self.coordinator, "last_update_success", False))
