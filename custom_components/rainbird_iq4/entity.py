"""Base entities for Rain Bird IQ4."""

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


def _device_info(controller: Controller) -> DeviceInfo:
    """Describe the one device that every entity of a controller belongs to."""
    return DeviceInfo(
        identifiers={(DOMAIN, str(controller.id))},
        name=controller.name,
        manufacturer="Rain Bird",
        model="IQ4",
        hw_version=str(controller.type),
        sw_version=controller.version,
    )


def _controller_attributes(controller: Controller) -> dict[str, Any]:
    return {
        "controller_id": controller.id,
        "site_id": controller.site_id,
        "site_name": controller.site_name,
    }


class RainBirdIQ4Entity(CoordinatorEntity[RainBirdIQ4Coordinator]):
    """Entity backed by IQ4 cloud data."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RainBirdIQ4Coordinator, key: str) -> None:
        super().__init__(coordinator)
        controller = coordinator.data.controller
        self._attr_unique_id = f"{controller.id}_{key}"
        self._attr_device_info = _device_info(controller)

    @property
    def controller(self) -> Controller:
        """Return the controller from the latest cloud data."""
        return self.coordinator.data.controller

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Provide stable controller identity."""
        return _controller_attributes(self.controller)


class RainBirdIQ4LocalEntity(CoordinatorEntity[LocalCoordinator]):
    """Entity backed by local polling, named and identified from cloud data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LocalCoordinator,
        cloud_coordinator: RainBirdIQ4Coordinator,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self.cloud_coordinator = cloud_coordinator
        controller = cloud_coordinator.data.controller
        self._attr_unique_id = f"{controller.id}_{key}"
        self._attr_device_info = _device_info(controller)

    @property
    def controller(self) -> Controller:
        """Return the controller from the latest cloud data."""
        return self.cloud_coordinator.data.controller

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
        """Provide controller identity plus local polling health."""
        return _controller_attributes(self.controller) | {
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
