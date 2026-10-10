"""Run-time setting for Rain Bird IQ4 manual starts."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import RainBirdIQ4Coordinator
from .entity import RainBirdIQ4Entity

DEFAULT_DURATION_MINUTES = 5


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the duration setting when local control is configured."""
    runtime = config_entry.runtime_data
    if runtime.local is not None:
        async_add_entities([StartDurationNumber(runtime.cloud)])


class StartDurationNumber(RainBirdIQ4Entity, RestoreNumber):
    """Minutes a manual start will run; changing it never contacts the controller."""

    _attr_name = "Start duration"
    _attr_icon = "mdi:timer-outline"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 1
    _attr_native_max_value = 30
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator: RainBirdIQ4Coordinator) -> None:
        super().__init__(coordinator, "start_duration")
        self._attr_native_value = DEFAULT_DURATION_MINUTES

    @property
    def available(self) -> bool:
        """A local setting stays usable during cloud outages."""
        return True

    async def async_set_native_value(self, value: float) -> None:
        """Store a whole number of minutes."""
        self._attr_native_value = int(value)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the previous duration within the allowed range."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) is not None and (
            last.native_value is not None and 1 <= last.native_value <= 30
        ):
            self._attr_native_value = int(last.native_value)
