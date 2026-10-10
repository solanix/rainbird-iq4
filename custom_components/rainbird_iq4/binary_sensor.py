"""Binary sensors for Rain Bird IQ4."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import RainBirdIQ4Coordinator, RainBirdIQ4LocalSlowCoordinator
from .entity import RainBirdIQ4Entity, RainBirdIQ4LocalEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities from a config entry."""
    runtime = config_entry.runtime_data
    async_add_entities(_build_entities(runtime.cloud, runtime.local_slow))


def _build_entities(
    cloud_coordinator: RainBirdIQ4Coordinator,
    local_coordinator: RainBirdIQ4LocalSlowCoordinator | None = None,
) -> list[BinarySensorEntity]:
    """Build cloud and optional local binary sensors."""
    entities: list[BinarySensorEntity] = [ControllerConnectedBinarySensor(cloud_coordinator)]
    if local_coordinator is not None:
        entities.extend(
            [
                IrrigationEnabledBinarySensor(local_coordinator, cloud_coordinator),
                RainSensorActiveBinarySensor(local_coordinator, cloud_coordinator),
            ]
        )
    return entities


class ControllerConnectedBinarySensor(RainBirdIQ4Entity, BinarySensorEntity):
    """Represent whether the selected controller is connected."""

    _attr_translation_key = "controller_connected"

    def __init__(self, coordinator: RainBirdIQ4Coordinator) -> None:
        super().__init__(coordinator, "connected")

    @property
    def is_on(self) -> bool:
        """Return whether the controller reports as connected."""
        return bool(self.coordinator.data.connected)

    @property
    def extra_state_attributes(self):
        """Expose whether the last connection report is stale."""
        attributes = super().extra_state_attributes
        attributes["stale"] = self.coordinator.data.stale
        return attributes


class IrrigationEnabledBinarySensor(RainBirdIQ4LocalEntity, BinarySensorEntity):
    """Represent the controller AUTO/enabled flag, not active watering."""

    _attr_translation_key = "irrigation_enabled"
    _attr_icon = "mdi:water-check"

    def __init__(
        self,
        coordinator: RainBirdIQ4LocalSlowCoordinator,
        cloud_coordinator: RainBirdIQ4Coordinator,
    ) -> None:
        super().__init__(coordinator, cloud_coordinator, "irrigation_enabled")

    @property
    def is_on(self) -> bool | None:
        """Return whether irrigation is enabled at the controller."""
        state = getattr(self.coordinator, "data", None)
        return state.irrigation_enabled if state is not None else None

    @property
    def available(self) -> bool:
        """Return whether the slow poll supplied the enabled flag."""
        return self._commands_available("irrigation_enabled")


class RainSensorActiveBinarySensor(RainBirdIQ4LocalEntity, BinarySensorEntity):
    """Represent the local rain-sensor input."""

    _attr_translation_key = "rain_sensor_active"
    _attr_icon = "mdi:weather-pouring"

    def __init__(
        self,
        coordinator: RainBirdIQ4LocalSlowCoordinator,
        cloud_coordinator: RainBirdIQ4Coordinator,
    ) -> None:
        super().__init__(coordinator, cloud_coordinator, "rain_sensor_active")

    @property
    def is_on(self) -> bool | None:
        """Return whether the physical rain sensor is active."""
        state = getattr(self.coordinator, "data", None)
        return state.rain_sensor_active if state is not None else None

    @property
    def available(self) -> bool:
        """Return whether the slow poll supplied the rain-sensor value."""
        return self._commands_available("rain_sensor")
