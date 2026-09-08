"""Tests for entity unique IDs and stable device IDs."""

from __future__ import annotations

from dataclasses import replace
from datetime import time

from pyrainbird_iq4.cloud.models import (
    Controller,
    RuntimeAssignment,
    ScheduledProgram,
    ScheduledTime,
    Station,
    StationRuntime,
)
from pyrainbird_iq4.local import (
    LocalCurrentQueue,
    LocalIrrigationState,
    LocalQueueState,
)

from custom_components.rainbird_iq4.binary_sensor import (
    IrrigationEnabledBinarySensor,
    RainSensorActiveBinarySensor,
)
from custom_components.rainbird_iq4.binary_sensor import (
    _build_entities as build_binary_sensor_entities,
)
from custom_components.rainbird_iq4.const import DOMAIN
from custom_components.rainbird_iq4.coordinator import RainBirdIQ4Data, build_effective_programs
from custom_components.rainbird_iq4.entity import RainBirdIQ4Entity
from custom_components.rainbird_iq4.sensor import (
    ActiveProgramSensor,
    ActiveStationSensor,
    IrrigationStateSensor,
    LocalRainDelaySensor,
    ProgramSensor,
    QueueZonesRemainingSensor,
    RainDelaySensor,
    RemainingRuntimeSensor,
    StationProgramRuntimeSensor,
    StationSensor,
    _build_entities,
)


def _make_controller() -> Controller:
    return Controller(
        id=42,
        name="North Lawn",
        type=2,
        site_id=7,
        site_name="Family",
        station_count=5,
        programs_used_count=3,
        mac_address="CC",
        version="9.9",
        is_mqtt=True,
        latitude=0.0,
        longitude=0.0,
        rain_delay=7,
        simultaneous_stations=2,
        is_shutdown=False,
        satellite_enabled=True,
    )


def test_entity_unique_ids():
    """Entity unique IDs are stable and controller-scoped."""
    controller = _make_controller()
    data = RainBirdIQ4Data(
        controller=controller,
        connected=True,
        connection_status=None,
        stale=False,
        stations=[],
        programs=[],
        scheduled_programs=[],
        runtime_assignments=[],
        effective_programs=[],
    )
    coordinator = type(
        "Coordinator",
        (),
        {"data": data, "last_update_success": True},
    )()

    entity = RainBirdIQ4Entity(coordinator, "firmware_version")

    assert entity.unique_id == "42_firmware_version"
    assert entity.device_info["identifiers"] == {(DOMAIN, "42")}


def test_device_identifiers_are_stable():
    """Device identifiers use the IQ4 controller ID."""
    controller = _make_controller()
    assert str(controller.id) == "42"
    assert (DOMAIN, str(controller.id)) == (DOMAIN, "42")


def _make_entity_coordinator():
    controller = _make_controller()
    stations = [
        Station(101, controller.id, "Front lawn", 1),
        Station(102, controller.id, "Station 002", 2),
        Station(103, controller.id, "Station 003", 3),
        Station(110, controller.id, "Back beds", 10),
    ]
    scheduled_programs = [
        ScheduledProgram(4000001, "Program A", (ScheduledTime(time(5), 0),)),
        ScheduledProgram(4000002, "Program B", (ScheduledTime(time(19, 40), 0),)),
    ]
    runtime_assignments = [
        StationRuntime(
            101,
            (
                RuntimeAssignment(1, 4000001, "A", "00:10:00", "00:10:00"),
                RuntimeAssignment(2, 9999999, "C", "00:03:00", "00:03:00"),
            ),
        ),
        StationRuntime(
            110,
            (RuntimeAssignment(3, 4000002, "B", "00:07:00", "00:07:00"),),
        ),
    ]
    data = RainBirdIQ4Data(
        controller=controller,
        connected=True,
        connection_status=None,
        stale=False,
        stations=stations,
        programs=[],
        scheduled_programs=scheduled_programs,
        runtime_assignments=runtime_assignments,
        effective_programs=build_effective_programs([], scheduled_programs),
    )
    return type("Coordinator", (), {"data": data, "last_update_success": True})()


def test_station_entity_preserves_ids_terminal_and_effective_runtimes() -> None:
    """Station entities separate effective programs from runtime references."""
    coordinator = _make_entity_coordinator()
    entity = StationSensor(coordinator, coordinator.data.stations[0])

    assert entity.unique_id == "42_station_101"
    assert entity.device_info is not None
    assert entity.device_info["identifiers"] == {(DOMAIN, "42")}
    assert entity.native_value == 1
    assert entity.extra_state_attributes["station_id"] == 101
    assert entity.extra_state_attributes["station_name"] == "Front lawn"
    assert entity.extra_state_attributes["terminal_number"] == 1
    assert entity.extra_state_attributes["assigned_effective_programs"] == [
        {
            "program_id": 4000001,
            "program_name": "A",
            "adjusted_runtime": "00:10:00",
            "base_runtime": "00:10:00",
        }
    ]
    assert entity.extra_state_attributes["assigned_effective_program_count"] == 1
    assert entity.extra_state_attributes["program_references"] == [
        {
            "program_id": 4000001,
            "program_name": "A",
            "adjusted_runtime": "00:10:00",
            "base_runtime": "00:10:00",
            "reference_source": "station_runtime_assignment",
            "effective": True,
            "scheduled": True,
        },
        {
            "program_id": 9999999,
            "program_name": "C",
            "adjusted_runtime": "00:03:00",
            "base_runtime": "00:03:00",
            "reference_source": "station_runtime_assignment",
            "effective": False,
            "scheduled": False,
        },
    ]


def test_iq4_station_rename_updates_default_names_without_changing_identity() -> None:
    """A cloud rename changes defaults while stable IDs prevent duplicates."""
    coordinator = _make_entity_coordinator()
    station = coordinator.data.stations[0]
    metadata = StationSensor(coordinator, station)
    runtime = StationProgramRuntimeSensor(coordinator, station, 4000001)
    metadata_unique_id = metadata.unique_id
    runtime_unique_id = runtime.unique_id

    coordinator.data.stations[0] = Station(101, 42, "Front Lawn Renamed", 1)

    assert metadata.name == "Front Lawn Renamed metadata"
    assert runtime.name == "Front Lawn Renamed Program A runtime"
    assert metadata.unique_id == metadata_unique_id
    assert runtime.unique_id == runtime_unique_id


def test_duplicate_station_names_remain_distinct_by_station_id() -> None:
    """Duplicate human-readable names cannot collide in the entity registry."""
    coordinator = _make_entity_coordinator()
    first = StationSensor(coordinator, Station(201, 42, "Front Lawn", 1))
    second = StationSensor(coordinator, Station(202, 42, "Front Lawn", 2))

    assert first.name == second.name == "Front Lawn metadata"
    assert first.unique_id == "42_station_201"
    assert second.unique_id == "42_station_202"


def test_active_terminal_uses_latest_cloud_station_name() -> None:
    """Local terminal identity resolves through current cloud station metadata."""
    cloud = _make_entity_coordinator()
    cloud.data.stations[1] = Station(102, 42, "Front Lawn", 2)
    local = _local_entity_coordinator(state=_local_state(active=(2,)))

    entity = ActiveStationSensor(local, cloud)

    assert entity.native_value == "Front Lawn"
    assert entity.extra_state_attributes["controller_id"] == 42
    assert entity.extra_state_attributes["station_id"] == 102
    assert entity.extra_state_attributes["terminal"] == 2
    assert entity.extra_state_attributes["station_name"] == "Front Lawn"


def test_station_program_runtime_is_not_summed_across_programs() -> None:
    """Each station/program pair is a distinct duration measurement."""
    coordinator = _make_entity_coordinator()
    station = coordinator.data.stations[0]

    entity = StationProgramRuntimeSensor(coordinator, station, 4000001)

    assert entity.unique_id == "42_station_101_program_4000001_runtime"
    assert entity.native_value == 600
    assert entity._attr_device_class == "duration"
    assert entity._attr_native_unit_of_measurement == "s"
    assert entity.extra_state_attributes == {
        "controller_id": 42,
        "site_id": 7,
        "site_name": "Family",
        "station_id": 101,
        "station_name": "Front lawn",
        "terminal": 1,
        "terminal_number": 1,
        "program_id": 4000001,
        "program_name": "A",
        "adjusted_runtime": "00:10:00",
        "base_runtime": "00:10:00",
        "reference_source": "station_runtime_assignment",
        "effective": True,
        "scheduled": True,
    }


def test_program_c_runtime_reference_is_retained_without_schedule_promotion() -> None:
    """Program C remains a neutral runtime reference, not an effective program."""
    coordinator = _make_entity_coordinator()
    station = coordinator.data.stations[0]

    runtime = StationProgramRuntimeSensor(coordinator, station, 9999999)
    program_entities = [
        ProgramSensor(coordinator, program) for program in coordinator.data.effective_programs
    ]

    assert runtime.unique_id == "42_station_101_program_9999999_runtime"
    assert runtime.native_value == 180
    assert runtime.available is True
    assert runtime.extra_state_attributes["program_name"] == "C"
    assert runtime.extra_state_attributes["reference_source"] == ("station_runtime_assignment")
    assert runtime.extra_state_attributes["effective"] is False
    assert runtime.extra_state_attributes["scheduled"] is False
    assert all(
        entity.extra_state_attributes["program_id"] != 9999999 for entity in program_entities
    )


def test_effective_program_entities_expose_schedule_and_station_runtimes() -> None:
    """MQTT schedule-derived programs expose useful read-only data."""
    coordinator = _make_entity_coordinator()
    entities = [
        ProgramSensor(coordinator, program) for program in coordinator.data.effective_programs
    ]

    assert [entity.unique_id for entity in entities] == [
        "42_program_4000001",
        "42_program_4000002",
    ]
    assert [entity.native_value for entity in entities] == ["05:00", "19:40"]
    for entity in entities:
        assert entity.device_info is not None
        assert entity.device_info["identifiers"] == {(DOMAIN, "42")}
    assert entities[0].extra_state_attributes["scheduled_start_times"] == ["05:00"]
    assert entities[0].extra_state_attributes["participating_stations"] == [101]
    assert entities[0].extra_state_attributes["station_runtimes"] == [
        {
            "station_id": 101,
            "station_name": "Front lawn",
            "terminal": 1,
            "terminal_number": 1,
            "adjusted_runtime": "00:10:00",
            "base_runtime": "00:10:00",
        }
    ]
    assert all(entity.extra_state_attributes["program_name"] != "C" for entity in entities)


def test_program_entity_survives_effective_catalog_removal_and_return() -> None:
    """An existing Program B entity becomes unavailable and later recovers."""
    coordinator = _make_entity_coordinator()
    program_b = coordinator.data.effective_programs[1]
    entity = ProgramSensor(coordinator, program_b)
    unique_id = entity.unique_id

    coordinator.data = replace(
        coordinator.data,
        effective_programs=[coordinator.data.effective_programs[0]],
    )

    assert entity.available is False
    assert entity.native_value is None
    assert entity.unique_id == unique_id
    assert entity.extra_state_attributes["program_id"] == 4000002
    assert entity.extra_state_attributes["program_name"] == "Program B"
    assert entity.extra_state_attributes["effective"] is False
    assert entity.extra_state_attributes["scheduled"] is False
    assert entity.extra_state_attributes["scheduled_start_times"] == []

    coordinator.data = replace(
        coordinator.data,
        effective_programs=[coordinator.data.effective_programs[0], program_b],
    )

    assert entity.available is True
    assert entity.native_value == "19:40"
    assert entity.unique_id == unique_id


def test_program_entity_supports_present_program_without_start_time() -> None:
    """A catalog record with no starts remains available as not scheduled."""
    coordinator = _make_entity_coordinator()
    program_b = {**coordinator.data.effective_programs[1], "scheduled_times": []}
    coordinator.data = replace(
        coordinator.data,
        effective_programs=[coordinator.data.effective_programs[0], program_b],
    )
    entity = ProgramSensor(coordinator, program_b)

    assert entity.available is True
    assert entity.native_value == "Not scheduled"
    assert entity.extra_state_attributes["effective"] is True
    assert entity.extra_state_attributes["scheduled"] is False


def test_runtime_entity_survives_assignment_removal_and_return() -> None:
    """A station/program runtime becomes unavailable and recovers in place."""
    coordinator = _make_entity_coordinator()
    station = coordinator.data.stations[-1]
    runtime = coordinator.data.runtime_assignments[-1]
    entity = StationProgramRuntimeSensor(coordinator, station, 4000002)
    unique_id = entity.unique_id

    coordinator.data = replace(
        coordinator.data,
        runtime_assignments=[
            *coordinator.data.runtime_assignments[:-1],
            StationRuntime(station.id, ()),
        ],
    )

    assert entity.available is False
    assert entity.native_value is None
    assert entity.unique_id == unique_id
    assert entity.extra_state_attributes["program_id"] == 4000002

    coordinator.data = replace(
        coordinator.data,
        runtime_assignments=[*coordinator.data.runtime_assignments[:-1], runtime],
    )

    assert entity.available is True
    assert entity.native_value == 420
    assert entity.unique_id == unique_id


def test_station_entity_survives_station_removal_and_return() -> None:
    """Station metadata becomes unavailable instead of raising on removal."""
    coordinator = _make_entity_coordinator()
    station = coordinator.data.stations[0]
    entity = StationSensor(coordinator, station)
    unique_id = entity.unique_id

    coordinator.data = replace(
        coordinator.data,
        stations=coordinator.data.stations[1:],
    )

    assert entity.available is False
    assert entity.native_value is None
    assert entity.unique_id == unique_id
    assert entity.extra_state_attributes["station_id"] == station.id

    coordinator.data = replace(
        coordinator.data,
        stations=[station, *coordinator.data.stations],
    )

    assert entity.available is True
    assert entity.native_value == 1
    assert entity.unique_id == unique_id


def test_rain_delay_entity_maps_zero_and_is_omitted_when_unsupported() -> None:
    """Zero is valid, while a missing API field does not create an unknown entity."""
    coordinator = _make_entity_coordinator()
    coordinator.data = replace(
        coordinator.data,
        controller=replace(coordinator.data.controller, rain_delay=0),
    )

    entities = _build_entities(coordinator)
    rain_delay = next(entity for entity in entities if isinstance(entity, RainDelaySensor))
    assert rain_delay.native_value == 0

    coordinator.data = replace(
        coordinator.data,
        controller=replace(coordinator.data.controller, rain_delay=None),
    )
    assert not any(isinstance(entity, RainDelaySensor) for entity in _build_entities(coordinator))


def _local_entity_coordinator(
    *,
    state: LocalIrrigationState | None = None,
    successful: bool = True,
):
    return type(
        "LocalCoordinator",
        (),
        {"data": state, "last_update_success": successful},
    )()


def _local_state(
    *,
    active: tuple[int, ...] = (),
    rain_sensor: bool = False,
    rain_delay: int = 0,
    remaining_seconds: int = 42,
    page_one_program: int = 0,
    page_zero_program: int | None = None,
    zones_remaining: int = 0,
) -> LocalIrrigationState:
    running = bool(active)
    zones = LocalQueueState.from_responses(
        {
            "program": {
                "program": page_zero_program
                if page_zero_program is not None
                else (4 if running else 0),
                "running": running,
                "zonesRemaining": zones_remaining,
            }
        },
        {
            "zones": [
                {
                    "program": page_one_program,
                    "zone": active[0],
                    "seconds": remaining_seconds,
                }
            ]
            if running
            else []
        },
    )
    return LocalIrrigationState(
        irrigation_enabled=True,
        active_terminals=active,
        available_terminals=(1, 3, 10),
        rain_sensor_active=rain_sensor,
        rain_delay_days=rain_delay,
        queue=zones,
    )


def test_idle_local_entities_preserve_enabled_semantics() -> None:
    """Enabled remains separate from the conservative idle run state."""
    cloud = _make_entity_coordinator()
    local = _local_entity_coordinator(state=_local_state(rain_sensor=True, rain_delay=3))

    enabled = IrrigationEnabledBinarySensor(local, cloud)
    rain_sensor = RainSensorActiveBinarySensor(local, cloud)
    irrigation = IrrigationStateSensor(local, cloud)
    active_station = ActiveStationSensor(local, cloud)
    queue_remaining = QueueZonesRemainingSensor(local, cloud)
    rain_delay = LocalRainDelaySensor(local, cloud)

    assert enabled.is_on is True
    assert rain_sensor.is_on is True
    assert irrigation.native_value == "idle"
    assert active_station.native_value == "Idle"
    assert active_station.extra_state_attributes["terminal_number"] is None
    assert queue_remaining.native_value == 0
    assert rain_delay.native_value == 3


def test_all_realtime_entities_are_built_when_local_is_configured() -> None:
    """A local coordinator registers every read-only realtime sensor."""
    cloud = _make_entity_coordinator()
    local = _local_entity_coordinator(state=_local_state())

    entity_types = {type(entity).__name__ for entity in _build_entities(cloud, local, local)}

    assert {
        "IrrigationStateSensor",
        "ActiveStationSensor",
        "ActiveProgramSensor",
        "RemainingRuntimeSensor",
        "QueueZonesRemainingSensor",
        "LocalRainDelaySensor",
    } <= entity_types
    binary_entity_types = {
        type(entity).__name__ for entity in build_binary_sensor_entities(cloud, local)
    }
    assert {
        "ControllerConnectedBinarySensor",
        "IrrigationEnabledBinarySensor",
        "RainSensorActiveBinarySensor",
    } == binary_entity_types


def test_active_terminal_resolves_cloud_station_metadata() -> None:
    """A single local terminal resolves to its cloud station ID and name."""
    cloud = _make_entity_coordinator()
    local = _local_entity_coordinator(state=_local_state(active=(3,)))

    entity = ActiveStationSensor(local, cloud)

    assert entity.native_value == "Station 003"
    assert entity.extra_state_attributes["terminal_number"] == 3
    assert entity.extra_state_attributes["station_id"] == 103

    remaining = RemainingRuntimeSensor(local, cloud)
    assert remaining.native_value == 42


def test_manual_zone_two_resolves_and_exposes_remaining_runtime() -> None:
    """The observed Zone 2 queue sample drives realtime HA entities."""
    cloud = _make_entity_coordinator()
    local = _local_entity_coordinator(state=_local_state(active=(2,), remaining_seconds=39))

    active_station = ActiveStationSensor(local, cloud)
    remaining = RemainingRuntimeSensor(local, cloud)

    assert active_station.native_value == "Station 002"
    assert active_station.extra_state_attributes["terminal_number"] == 2
    assert active_station.extra_state_attributes["station_id"] == 102
    assert remaining.native_value == 39


def test_observed_program_a_and_b_resolve_from_page_one() -> None:
    """Observed page-one numbers resolve without using page-zero mode codes."""
    cloud = _make_entity_coordinator()
    program_a = _local_entity_coordinator(
        state=_local_state(
            active=(2,),
            remaining_seconds=1836,
            page_one_program=1,
            page_zero_program=0,
            zones_remaining=7,
        )
    )
    program_b = _local_entity_coordinator(
        state=_local_state(
            active=(5,),
            remaining_seconds=950,
            page_one_program=2,
            page_zero_program=0,
            zones_remaining=1,
        )
    )

    active_a = ActiveProgramSensor(program_a, cloud)
    active_b = ActiveProgramSensor(program_b, cloud)

    assert active_a.native_value == "Program A"
    assert active_a.extra_state_attributes == {
        "controller_id": 42,
        "site_id": 7,
        "site_name": "Family",
        "last_successful_update": None,
        "consecutive_failures": 0,
        "poll_interval_seconds": None,
        "protocol_program_number": 1,
        "program_id": 4000001,
        "queue_mode_code": 0,
    }
    assert RemainingRuntimeSensor(program_a, cloud).native_value == 1836
    assert QueueZonesRemainingSensor(program_a, cloud).native_value == 7
    assert active_b.native_value == "Program B"
    assert active_b.extra_state_attributes["program_id"] == 4000002
    assert RemainingRuntimeSensor(program_b, cloud).native_value == 950
    assert QueueZonesRemainingSensor(program_b, cloud).native_value == 1


def test_active_program_manual_idle_and_unknown_are_conservative() -> None:
    """Manual and unknown codes never become invented configured programs."""
    cloud = _make_entity_coordinator()
    manual = ActiveProgramSensor(_local_entity_coordinator(state=_local_state(active=(2,))), cloud)
    idle = ActiveProgramSensor(_local_entity_coordinator(state=_local_state()), cloud)
    unknown = ActiveProgramSensor(
        _local_entity_coordinator(
            state=_local_state(active=(2,), page_one_program=3, page_zero_program=0)
        ),
        cloud,
    )

    assert manual.native_value == "Manual"
    assert manual.extra_state_attributes["queue_mode_code"] == 4
    assert idle.native_value == "Idle"
    assert unknown.native_value == "Unknown"
    assert unknown.extra_state_attributes["protocol_program_number"] == 3
    assert unknown.extra_state_attributes["program_id"] is None


def test_local_entities_follow_idle_running_idle_updates() -> None:
    """Realtime entities read every new local snapshot without a cloud refresh."""
    cloud = _make_entity_coordinator()
    local = _local_entity_coordinator(state=_local_state())
    irrigation = IrrigationStateSensor(local, cloud)
    active_station = ActiveStationSensor(local, cloud)
    remaining = RemainingRuntimeSensor(local, cloud)

    assert (irrigation.native_value, active_station.native_value, remaining.native_value) == (
        "idle",
        "Idle",
        0,
    )

    local.data = _local_state(active=(3,))
    assert (irrigation.native_value, active_station.native_value, remaining.native_value) == (
        "running",
        "Station 003",
        42,
    )

    local.data = _local_state()
    assert (irrigation.native_value, active_station.native_value, remaining.native_value) == (
        "idle",
        "Idle",
        0,
    )


def test_source_specific_entity_availability() -> None:
    """Cloud and local entities reflect their own source availability."""
    cloud = _make_entity_coordinator()
    local = _local_entity_coordinator(state=_local_state())
    cloud_entity = StationSensor(cloud, cloud.data.stations[0])
    local_entity = IrrigationStateSensor(local, cloud)

    cloud.last_update_success = False
    assert cloud_entity.available is False
    assert local_entity.available is True

    cloud.last_update_success = True
    local.last_update_success = False
    assert cloud_entity.available is True
    assert local_entity.available is False
