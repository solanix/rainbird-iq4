"""Sensors for Rain Bird IQ4."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyrainbird_iq4.cloud.models import Station
from pyrainbird_iq4.local import LocalIrrigationState, LocalRunState

from .const import DOMAIN
from .coordinator import (
    RainBirdIQ4CloudCoordinator,
    RainBirdIQ4LocalCoordinator,
    RainBirdIQ4LocalSlowCoordinator,
)
from .entity import RainBirdIQ4Entity, RainBirdIQ4LocalEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from a config entry."""
    runtime = config_entry.runtime_data
    cloud = runtime.cloud
    entities = _build_entities(cloud, runtime.local, runtime.local_slow)
    added = {entity.unique_id for entity in entities}
    async_add_entities(entities)
    if cloud.last_update_success and cloud.saved_data_since is None:
        _async_remove_stale_entities(hass, config_entry, cloud, added)
        _async_enable_reenabled_stations(hass, cloud)

    @callback
    def _async_add_new_entities() -> None:
        """Add entities for stations, programs or assignments that appeared in IQ4."""
        if not cloud.last_update_success:
            return
        _async_enable_reenabled_stations(hass, cloud)
        new = [
            entity
            for entity in _build_cloud_dynamic_entities(cloud)
            if entity.unique_id not in added
        ]
        if new:
            added.update(entity.unique_id for entity in new)
            async_add_entities(new)

    config_entry.async_on_unload(cloud.async_add_listener(_async_add_new_entities))


@callback
def _async_remove_stale_entities(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    cloud: RainBirdIQ4CloudCoordinator,
    current: set[str | None],
) -> None:
    """Remove station, program and runtime entities that no longer exist in IQ4.

    Only runs on live cloud data with at least one station, so an outage or an empty
    response never deletes entities (and their user customizations).
    """
    if not cloud.data.stations:
        return
    dynamic = re.compile(
        rf"^{cloud.controller_id}_(station_\d+(_program_\d+_runtime)?|program_\d+)$"
    )
    registry = er.async_get(hass)
    for entry in er.async_entries_for_config_entry(registry, config_entry.entry_id):
        if (
            entry.domain == "sensor"
            and dynamic.match(entry.unique_id)
            and entry.unique_id not in current
        ):
            _LOGGER.info("Removing %s: no longer present in IQ4", entry.entity_id)
            registry.async_remove(entry.entity_id)


@callback
def _async_enable_reenabled_stations(
    hass: HomeAssistant, cloud: RainBirdIQ4CloudCoordinator
) -> None:
    """Enable station entities this integration disabled once IQ4 enables the station.

    A station disabled in IQ4 gets its entity disabled at creation. Only that default is
    undone here: an entity the user disabled stays disabled, and a station disabled in IQ4
    later is left alone, so no choice of the user's is overridden. Home Assistant reloads
    the entry shortly after an entity is enabled, which adds it.
    """
    registry = er.async_get(hass)
    for station in cloud.data.stations:
        if station.is_enabled is not True:
            continue
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{cloud.controller_id}_station_{station.id}"
        )
        entry = registry.async_get(entity_id) if entity_id is not None else None
        if entry is not None and entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
            _LOGGER.info("Enabling %s: %s is now enabled in IQ4", entry.entity_id, station.name)
            registry.async_update_entity(entry.entity_id, disabled_by=None)


def _build_cloud_dynamic_entities(coordinator: RainBirdIQ4CloudCoordinator) -> list[SensorEntity]:
    """Build entities that follow IQ4 stations, programs and station assignments."""
    return [
        *(StationSensor(coordinator, station) for station in coordinator.data.stations),
        *(
            StationProgramRuntimeSensor(
                coordinator,
                station,
                assignment["program_id"],
            )
            for station in coordinator.data.stations
            for assignment in coordinator.data.program_references(station.id)
        ),
        *(ProgramSensor(coordinator, program) for program in coordinator.data.known_programs),
    ]


def _build_entities(
    coordinator: RainBirdIQ4CloudCoordinator,
    local_coordinator: RainBirdIQ4LocalCoordinator | None = None,
    slow_coordinator: RainBirdIQ4LocalSlowCoordinator | None = None,
) -> list[SensorEntity]:
    """Build entities supported by the current controller snapshot."""
    entities: list[SensorEntity] = [
        FirmwareVersionSensor(coordinator),
        StationCountSensor(coordinator),
        ProgramsUsedSensor(coordinator),
        ProgramSummarySensor(coordinator),
        *_build_cloud_dynamic_entities(coordinator),
    ]
    if local_coordinator is not None:
        entities.extend(
            [
                IrrigationStateSensor(local_coordinator, coordinator),
                ActiveStationSensor(local_coordinator, coordinator),
                ActiveProgramSensor(local_coordinator, coordinator),
                QueueZonesRemainingSensor(local_coordinator, coordinator),
                RemainingRuntimeSensor(local_coordinator, coordinator),
            ]
        )
    if slow_coordinator is not None:
        entities.append(LocalRainDelaySensor(slow_coordinator, coordinator))
    elif coordinator.data.controller.rain_delay is not None:
        entities.append(RainDelaySensor(coordinator))
    return entities


class FirmwareVersionSensor(RainBirdIQ4Entity, SensorEntity):
    """Expose the controller firmware version."""

    _attr_translation_key = "firmware_version"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RainBirdIQ4CloudCoordinator) -> None:
        super().__init__(coordinator, "firmware_version")

    @property
    def native_value(self) -> str:
        """Return the firmware version."""
        return str(self.controller.version)


class StationCountSensor(RainBirdIQ4Entity, SensorEntity):
    """Expose the controller station count."""

    _attr_translation_key = "station_count"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RainBirdIQ4CloudCoordinator) -> None:
        super().__init__(coordinator, "station_count")

    @property
    def native_value(self) -> int:
        """Return the number of stations."""
        return len(self.coordinator.data.stations)


class ProgramsUsedSensor(RainBirdIQ4Entity, SensorEntity):
    """Expose the program count used."""

    _attr_translation_key = "programs_used_count"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RainBirdIQ4CloudCoordinator) -> None:
        super().__init__(coordinator, "programs_used_count")

    @property
    def native_value(self) -> int:
        """Return the programs used count from the controller metadata."""
        return int(self.controller.programs_used_count)


class RainDelaySensor(RainBirdIQ4Entity, SensorEntity):
    """Expose rain delay when supplied by cloud metadata."""

    _attr_translation_key = "rain_delay"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.DAYS

    def __init__(self, coordinator: RainBirdIQ4CloudCoordinator) -> None:
        super().__init__(coordinator, "rain_delay")

    @property
    def native_value(self) -> int | None:
        """Return rain-delay days, including zero for no delay."""
        rain_delay = self.coordinator.data.controller.rain_delay
        return int(rain_delay) if rain_delay is not None else None


class LocalRainDelaySensor(RainBirdIQ4LocalEntity, SensorEntity):
    """Expose locally refreshed rain delay using the existing unique ID."""

    _attr_translation_key = "rain_delay"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.DAYS

    def __init__(
        self,
        coordinator: RainBirdIQ4LocalSlowCoordinator,
        cloud_coordinator: RainBirdIQ4CloudCoordinator,
    ) -> None:
        super().__init__(coordinator, cloud_coordinator, "rain_delay")

    @property
    def native_value(self) -> int | None:
        """Return local rain-delay days, including zero."""
        state = getattr(self.coordinator, "data", None)
        return int(state.rain_delay_days) if state is not None else None

    @property
    def available(self) -> bool:
        """Return whether the latest slow poll supplied rain delay."""
        return self._commands_available("rain_delay")


class IrrigationStateSensor(RainBirdIQ4LocalEntity, SensorEntity):
    """Expose the conservative local irrigation state."""

    _attr_translation_key = "irrigation_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        LocalRunState.IDLE.value,
        LocalRunState.RUNNING.value,
        LocalRunState.PAUSED.value,
    ]

    def __init__(
        self,
        coordinator: RainBirdIQ4LocalCoordinator,
        cloud_coordinator: RainBirdIQ4CloudCoordinator,
    ) -> None:
        super().__init__(coordinator, cloud_coordinator, "irrigation_state")

    @property
    def native_value(self) -> str | None:
        """Return idle/running/paused; inconclusive evidence is HA's unknown state."""
        state: LocalIrrigationState | None = getattr(self.coordinator, "data", None)
        if state is None or state.state is LocalRunState.UNKNOWN:
            return None
        return state.state.value

    @property
    def available(self) -> bool:
        """Remain available when either queue or active-terminal evidence exists."""
        state = getattr(self.coordinator, "data", None)
        return bool(
            super().available
            and state is not None
            and not {
                "active_terminals",
                "current_queue_page_0",
            }.issubset(state.failed_commands)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the typed current and queued local records."""
        attributes = super().extra_state_attributes
        state = getattr(self.coordinator, "data", None)
        if state is not None:
            attributes["active_terminals"] = list(state.active_terminals)
            attributes["queue"] = asdict(state.queue) if state.queue is not None else None
        return attributes


class ActiveStationSensor(RainBirdIQ4LocalEntity, SensorEntity):
    """Resolve the active local terminal to cloud station metadata."""

    _attr_translation_key = "active_station"

    def __init__(
        self,
        coordinator: RainBirdIQ4LocalCoordinator,
        cloud_coordinator: RainBirdIQ4CloudCoordinator,
    ) -> None:
        super().__init__(coordinator, cloud_coordinator, "active_station")

    @property
    def _active_terminal(self) -> int | None:
        state = getattr(self.coordinator, "data", None)
        terminal = state.active_terminal if state is not None else None
        return int(terminal) if terminal is not None else None

    @property
    def available(self) -> bool:
        """Require active-mask or running queue-zone evidence."""
        state = getattr(self.coordinator, "data", None)
        return bool(
            super().available
            and state is not None
            and "active_terminals" not in state.failed_commands
        )

    @property
    def native_value(self) -> str | None:
        """Return Idle, a resolved station name, or a multiple-terminal summary."""
        state = getattr(self.coordinator, "data", None)
        if state is None:
            return None
        if state.state is LocalRunState.IDLE:
            return "Idle"
        terminal = state.active_terminal
        if terminal is None and len(state.active_terminals) > 1:
            return f"Multiple terminals: {', '.join(map(str, state.active_terminals))}"
        if terminal is None:
            return "Unknown"
        station = next(
            (
                station
                for station in self.cloud_coordinator.data.stations
                if station.terminal == terminal
            ),
            None,
        )
        return station.name if station is not None else f"Station {terminal:03d}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the active terminal and stable Rain Bird station ID."""
        attributes = super().extra_state_attributes
        terminal = self._active_terminal
        station = next(
            (
                station
                for station in self.cloud_coordinator.data.stations
                if station.terminal == terminal
            ),
            None,
        )
        attributes["terminal"] = terminal
        attributes["terminal_number"] = terminal
        attributes["station_id"] = station.id if station else None
        attributes["station_name"] = station.name if station else None
        attributes["station_enabled"] = station.is_enabled if station else None
        return attributes


class QueueZonesRemainingSensor(RainBirdIQ4LocalEntity, SensorEntity):
    """Expose the page-zero zones-remaining count when supplied."""

    _attr_translation_key = "queue_zones_remaining"

    def __init__(
        self,
        coordinator: RainBirdIQ4LocalCoordinator,
        cloud_coordinator: RainBirdIQ4CloudCoordinator,
    ) -> None:
        super().__init__(coordinator, cloud_coordinator, "queue_zones_remaining")

    @property
    def native_value(self) -> int | None:
        """Return the explicit queue count without deriving it from assignments."""
        state = getattr(self.coordinator, "data", None)
        if state is None or state.queue is None or state.queue.current is None:
            return None
        remaining = state.queue.current.zones_remaining
        return int(remaining) if remaining is not None else None

    @property
    def available(self) -> bool:
        """Require a successful current-queue page-zero command."""
        return self._commands_available("current_queue_page_0")


class ActiveProgramSensor(RainBirdIQ4LocalEntity, SensorEntity):
    """Resolve the page-one local program number to the cloud catalog."""

    _attr_translation_key = "active_program"

    def __init__(
        self,
        coordinator: RainBirdIQ4LocalCoordinator,
        cloud_coordinator: RainBirdIQ4CloudCoordinator,
    ) -> None:
        super().__init__(coordinator, cloud_coordinator, "active_program")

    @property
    def _program(self) -> dict[str, Any] | None:
        state = getattr(self.coordinator, "data", None)
        number = state.active_program_number if state is not None else None
        return next(
            (
                program
                for program in self.cloud_coordinator.data.effective_programs
                if program.get("protocol_program_number") == number
            ),
            None,
        )

    @property
    def native_value(self) -> str | None:
        """Return Idle, Manual, a resolved catalog name, or Unknown."""
        state = getattr(self.coordinator, "data", None)
        if state is None:
            return None
        if state.state is LocalRunState.IDLE:
            return "Idle"
        number = state.active_program_number
        if number == 0:
            return "Manual"
        program = self._program
        return str(program["name"]) if program is not None else "Unknown"

    @property
    def available(self) -> bool:
        """Require queue page one while running and page zero while idle."""
        state = getattr(self.coordinator, "data", None)
        if state is None or not super().available:
            return False
        command = (
            "current_queue_page_1"
            if state.state is LocalRunState.RUNNING
            else "current_queue_page_0"
        )
        return command not in state.failed_commands

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose raw protocol numbers and a resolved stable cloud ID."""
        attributes = super().extra_state_attributes
        state = getattr(self.coordinator, "data", None)
        program = self._program
        attributes["protocol_program_number"] = (
            state.active_program_number if state is not None else None
        )
        attributes["program_id"] = program["id"] if program is not None else None
        attributes["queue_mode_code"] = (
            state.queue.current.program_code
            if state is not None and state.queue is not None and state.queue.current is not None
            else None
        )
        return attributes


class RemainingRuntimeSensor(RainBirdIQ4LocalEntity, SensorEntity):
    """Expose the matching active-terminal queue runtime."""

    _attr_translation_key = "remaining_runtime"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: RainBirdIQ4LocalCoordinator,
        cloud_coordinator: RainBirdIQ4CloudCoordinator,
    ) -> None:
        super().__init__(coordinator, cloud_coordinator, "remaining_runtime")

    @property
    def native_value(self) -> int | None:
        """Return seconds only when queue data matches the active terminal."""
        state = getattr(self.coordinator, "data", None)
        if state is None:
            return None
        if state.state is LocalRunState.IDLE:
            return 0
        remaining = state.remaining_runtime_seconds
        return int(remaining) if remaining is not None else None

    @property
    def available(self) -> bool:
        """Require page one while running and page zero for confirmed idle."""
        state = getattr(self.coordinator, "data", None)
        if state is None or not super().available:
            return False
        command = (
            "current_queue_page_1"
            if state.state is LocalRunState.RUNNING
            else "current_queue_page_0"
        )
        return command not in state.failed_commands


class ProgramSummarySensor(RainBirdIQ4Entity, SensorEntity):
    """Provide a useful summary of stations and programs."""

    _attr_translation_key = "program_summary"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RainBirdIQ4CloudCoordinator) -> None:
        super().__init__(coordinator, "program_summary")

    @property
    def native_value(self) -> str:
        """Return a concise summary."""
        stations = self.coordinator.data.stations
        programs = self.coordinator.data.effective_programs
        return f"{len(stations)} stations / {len(programs)} effective programs"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose stable IDs and normalized scheduled times for future entities."""
        attributes = super().extra_state_attributes
        attributes["programs"] = self.coordinator.data.effective_programs
        attributes["station_ids"] = [station.id for station in self.coordinator.data.stations]
        return attributes


def _duration_seconds(value: str) -> int:
    """Convert an IQ4 HH:MM:SS runtime to seconds."""
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


class StationSensor(RainBirdIQ4Entity, SensorEntity):
    """Expose physical station metadata and effective-program assignments."""

    _attr_translation_key = "station_metadata"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RainBirdIQ4CloudCoordinator, station: Station) -> None:
        super().__init__(coordinator, f"station_{station.id}")
        self._station_id = station.id
        self._station_name = station.name
        self._attr_entity_registry_enabled_default = station.is_enabled is not False
        self._attr_name = f"{station.name} metadata"

    @property
    def name(self) -> str:
        """Return the latest integration-provided cloud station name."""
        station = self._station
        return f"{station.name if station is not None else self._station_name} metadata"

    @property
    def _station(self) -> Station | None:
        """Return the station from the latest cloud snapshot when present."""
        return self.coordinator.data.station(self._station_id)

    @property
    def available(self) -> bool:
        """Return whether this station still exists in the cloud snapshot."""
        return bool(super().available and self._station is not None)

    @property
    def _effective_assignments(self) -> list[dict[str, Any]]:
        return [reference for reference in self._program_references if reference["effective"]]

    @property
    def _program_references(self) -> list[dict[str, Any]]:
        """Return all programs referenced by this station's runtime assignments."""
        return self.coordinator.data.program_references(self._station_id)

    @property
    def _effective_assignment_attributes(self) -> list[dict[str, Any]]:
        """Return the established effective-assignment attribute shape."""
        return [
            {
                key: reference[key]
                for key in (
                    "program_id",
                    "program_name",
                    "adjusted_runtime",
                    "base_runtime",
                )
            }
            for reference in self._effective_assignments
        ]

    @property
    def native_value(self) -> int | None:
        """Return the number of assigned effective programs."""
        return len(self._effective_assignments) if self._station is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose station identity and effective program runtimes."""
        attributes = super().extra_state_attributes
        station = self._station
        attributes.update(
            {
                "station_id": self._station_id,
                "station_name": station.name if station is not None else None,
                "station_enabled": station.is_enabled if station is not None else None,
                "terminal": station.terminal if station is not None else None,
                "terminal_number": station.terminal if station is not None else None,
                "assigned_effective_programs": self._effective_assignment_attributes,
                "assigned_effective_program_count": len(self._effective_assignments),
                "program_references": self._program_references,
            }
        )
        return attributes


class StationProgramRuntimeSensor(RainBirdIQ4Entity, SensorEntity):
    """Expose one station runtime assignment without implying a schedule."""

    _attr_translation_key = "station_program_runtime"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # Program entities already list every station runtime; one sensor per pair is opt-in.
    _attr_entity_registry_enabled_default = False
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(
        self, coordinator: RainBirdIQ4CloudCoordinator, station: Station, program_id: int
    ) -> None:
        super().__init__(
            coordinator,
            f"station_{station.id}_program_{program_id}_runtime",
        )
        self._station_id = station.id
        self._program_id = program_id
        program = next(
            (
                program
                for program in coordinator.data.effective_programs
                if program["id"] == program_id
            ),
            None,
        )
        reference = coordinator.data.program_reference(station.id, program_id)
        station_name = station.name
        short_name = reference["program_name"] if reference is not None else ""
        program_name = (
            program["name"]
            if program is not None
            else f"Program {short_name}"
            if short_name
            else f"Program {program_id}"
        )
        self._attr_name = f"{station_name} {program_name} runtime"
        self._station_name = station.name
        self._runtime_name_suffix = f"{program_name} runtime"
        self._terminal = station.terminal

    @property
    def name(self) -> str:
        """Return a default name using the latest cloud station name."""
        station = self.coordinator.data.station(self._station_id)
        station_name = station.name if station is not None else self._station_name
        return f"{station_name} {self._runtime_name_suffix}"

    @property
    def _assignment(self) -> dict[str, Any] | None:
        """Return the current runtime reference when it still exists."""
        return self.coordinator.data.program_reference(self._station_id, self._program_id)

    @property
    def available(self) -> bool:
        """Return whether this specific runtime reference still exists."""
        return bool(
            super().available
            and self.coordinator.data.station(self._station_id) is not None
            and self._assignment is not None
        )

    @property
    def native_value(self) -> int | None:
        """Return the adjusted runtime for this station/program pair."""
        assignment = self._assignment
        return _duration_seconds(assignment["adjusted_runtime"]) if assignment is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Preserve stable station/program IDs and both runtime forms."""
        attributes = super().extra_state_attributes
        station = self.coordinator.data.station(self._station_id)
        assignment = self._assignment
        attributes.update(
            {
                "station_id": self._station_id,
                "station_name": station.name if station is not None else self._station_name,
                "station_enabled": station.is_enabled if station is not None else None,
                "terminal": station.terminal if station is not None else self._terminal,
                "terminal_number": station.terminal if station is not None else self._terminal,
            }
        )
        if assignment is not None:
            attributes.update(assignment)
        else:
            attributes["program_id"] = self._program_id
        return attributes


class ProgramSensor(RainBirdIQ4Entity, SensorEntity):
    """Expose a controller program, scheduled or merely assigned to stations."""

    _attr_translation_key = "program"

    def __init__(self, coordinator: RainBirdIQ4CloudCoordinator, program: dict[str, Any]) -> None:
        super().__init__(coordinator, f"program_{program['id']}")
        self._program_id = program["id"]
        self._attr_name = program["name"]
        self._program_name = program["name"]

    @property
    def _program(self) -> dict[str, Any] | None:
        """Return the program from the latest cloud snapshot."""
        return next(
            (
                program
                for program in self.coordinator.data.known_programs
                if program["id"] == self._program_id
            ),
            None,
        )

    @property
    def _effective(self) -> bool:
        return any(
            program["id"] == self._program_id
            for program in self.coordinator.data.effective_programs
        )

    @property
    def available(self) -> bool:
        """Return whether the program is still scheduled or assigned to a station."""
        return bool(super().available and self._program is not None)

    @property
    def native_value(self) -> str | None:
        """Return the first scheduled start time."""
        program = self._program
        if program is None:
            return None
        times = program.get("scheduled_times", [])
        return times[0]["time_of_day"][:5] if times else "Not scheduled"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose schedule, participating stations, and station runtimes."""
        attributes = super().extra_state_attributes
        program = self._program
        station_by_id = {station.id: station for station in self.coordinator.data.stations}
        station_runtimes = []
        for runtime in self.coordinator.data.runtime_assignments:
            station = station_by_id.get(runtime.station_id)
            if station is None or station.is_enabled is not True:
                continue
            for assignment in runtime.assignments:
                if assignment.program_id == self._program_id:
                    station_runtimes.append(
                        {
                            "station_id": runtime.station_id,
                            "station_name": station.name if station else "",
                            "station_enabled": station.is_enabled if station else None,
                            "terminal": station.terminal if station else None,
                            "terminal_number": station.terminal if station else None,
                            "adjusted_runtime": assignment.adjusted_run_time,
                            "base_runtime": assignment.base_run_time,
                        }
                    )
        attributes.update(
            {
                "program_id": self._program_id,
                "program_name": program["name"] if program is not None else self._program_name,
                "effective": self._effective,
                "scheduled": bool(program and program.get("scheduled_times")),
                "scheduled_start_times": [
                    start["time_of_day"][:5]
                    for start in (program.get("scheduled_times", []) if program is not None else [])
                ],
                "participating_stations": [runtime["station_id"] for runtime in station_runtimes],
                "station_runtimes": station_runtimes,
            }
        )
        return attributes
