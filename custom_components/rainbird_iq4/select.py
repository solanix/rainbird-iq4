"""Station picker for Rain Bird IQ4 manual starts."""

from __future__ import annotations

from collections import Counter
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from pyrainbird_iq4.cloud.models import Station

from .coordinator import RainBirdIQ4CloudCoordinator
from .entity import RainBirdIQ4Entity

ATTR_STATION_ID = "station_id"
ATTR_TERMINAL = "terminal"

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the station picker when local control is configured."""
    runtime = config_entry.runtime_data
    if runtime.local is not None:
        async_add_entities([StartStationSelect(runtime.cloud)])


class StartStationSelect(RainBirdIQ4Entity, RestoreEntity, SelectEntity):
    """Choose which cloud-enabled station a manual start targets.

    Selecting only stores the choice; it never contacts the controller.
    """

    _attr_translation_key = "start_station"

    def __init__(self, coordinator: RainBirdIQ4CloudCoordinator) -> None:
        super().__init__(coordinator, "start_station_select")
        self._selected_station_id: int | None = None

    def _stations_by_option(self) -> dict[str, Station]:
        """Map option labels to enabled stations; duplicate cloud names get a terminal suffix."""
        stations = sorted(self.coordinator.data.enabled_stations, key=lambda item: item.terminal)
        name_counts = Counter(station.name for station in stations)
        return {
            (
                station.name
                if name_counts[station.name] == 1
                else f"{station.name} (terminal {station.terminal})"
            ): station
            for station in stations
        }

    def _selected(self) -> tuple[str, Station] | None:
        return next(
            (
                (option, station)
                for option, station in self._stations_by_option().items()
                if station.id == self._selected_station_id
            ),
            None,
        )

    @property
    def options(self) -> list[str]:
        """Return only stations IQ4 reports as enabled."""
        return list(self._stations_by_option())

    @property
    def current_option(self) -> str | None:
        """Return the chosen station while it is still enabled."""
        selected = self._selected()
        return selected[0] if selected is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the stable station ID for scripts calling start_station."""
        selected = self._selected()
        return super().extra_state_attributes | {
            ATTR_STATION_ID: selected[1].id if selected is not None else None,
            ATTR_TERMINAL: selected[1].terminal if selected is not None else None,
        }

    async def async_select_option(self, option: str) -> None:
        """Remember the chosen station by its stable cloud ID."""
        self._selected_station_id = self._stations_by_option()[option].id
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the previous choice by station ID, never by name."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            station_id = last_state.attributes.get(ATTR_STATION_ID)
            if isinstance(station_id, int) and not isinstance(station_id, bool):
                self._selected_station_id = station_id
