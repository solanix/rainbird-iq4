"""Base entity for Rain Bird IQ4."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pyrainbird_iq4.cloud.models import Controller

from .const import DOMAIN
from .coordinator import (
    RainBirdIQ4Coordinator,
    RainBirdIQ4LocalCoordinator,
    RainBirdIQ4LocalSlowCoordinator,
)

LocalCoordinator = RainBirdIQ4LocalCoordinator | RainBirdIQ4LocalSlowCoordinator


class RainBirdIQ4Entity(CoordinatorEntity[RainBirdIQ4Coordinator]):
    """Base entity for all controllers."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RainBirdIQ4Coordinator, key: str) -> None:
        super().__init__(coordinator)
        self.coordinator: RainBirdIQ4Coordinator = coordinator
        self.controller: Controller = coordinator.data.controller
        self._key = key
        self._attr_unique_id = f"{self.controller.id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self.controller.id))},
            name=self.controller.name,
            manufacturer="Rain Bird",
            model="IQ4",
            hw_version=str(self.controller.type),
            sw_version=self.controller.version,
        )

    @property
    def available(self) -> bool:
        """Return whether the cloud source refreshed successfully."""
        return bool(super().available)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Provide stable extra state attributes."""
        return {
            "controller_id": self.controller.id,
            "site_id": self.controller.site_id,
            "site_name": self.controller.site_name,
        }


class RainBirdIQ4LocalEntity(CoordinatorEntity[LocalCoordinator]):
    """Base entity backed by the independently refreshed local source."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LocalCoordinator,
        cloud_coordinator: RainBirdIQ4Coordinator,
        key: str,
    ) -> None:
        """Subscribe to local updates while retaining cloud station metadata."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.cloud_coordinator = cloud_coordinator
        self.controller = cloud_coordinator.data.controller
        self._attr_unique_id = f"{self.controller.id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self.controller.id))},
            name=self.controller.name,
            manufacturer="Rain Bird",
            model="IQ4",
            hw_version=str(self.controller.type),
            sw_version=self.controller.version,
        )

    @property
    def available(self) -> bool:
        """Return whether local realtime data is currently available."""
        return bool(super().available and getattr(self.coordinator, "data", None) is not None)

    def _commands_available(self, *commands: str) -> bool:
        """Return whether the current partial snapshot contains command results."""
        state = getattr(self.coordinator, "data", None)
        return bool(
            super().available
            and state is not None
            and not state.failed_commands.intersection(commands)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Provide stable cloud identity on a locally updated entity."""
        return {
            "controller_id": self.controller.id,
            "site_id": self.controller.site_id,
            "site_name": self.controller.site_name,
            "last_successful_update": (
                last_update.isoformat()
                if (last_update := getattr(self.coordinator, "last_successful_update", None))
                is not None
                else None
            ),
            "consecutive_failures": getattr(self.coordinator, "consecutive_failures", 0),
            "poll_interval_seconds": (
                int(interval.total_seconds())
                if (interval := getattr(self.coordinator, "update_interval", None)) is not None
                else None
            ),
        }
