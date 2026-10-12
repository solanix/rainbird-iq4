"""Tests for sensor presentation against real Home Assistant."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyrainbird_iq4.cloud.models import (
    RuntimeAssignment,
    ScheduledProgram,
    ScheduledTime,
    StationRuntime,
)
from pyrainbird_iq4.local import LocalIrrigationState
from syrupy.assertion import SnapshotAssertion

from custom_components.rainbird_iq4.models import build_effective_programs

from .conftest import BACKYARD_ID, BACKYARD_STATION_ID, CLOUD_DATA, make_entry, setup_entry


async def test_remaining_runtime_shows_whole_seconds(hass: HomeAssistant) -> None:
    """Remaining runtime displays as whole seconds and reads 0 while idle."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    entity_id = "sensor.controller_200001_remaining_runtime"

    entry = er.async_get(hass).async_get(entity_id)
    state = hass.states.get(entity_id)

    assert entry is not None
    assert entry.options["sensor"]["suggested_display_precision"] == 0
    assert state is not None
    assert state.state == "0"


async def test_entity_ids_and_names(hass: HomeAssistant, snapshot: SnapshotAssertion) -> None:
    """Entity IDs and names are stable; dashboards depend on these IDs."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))

    entities = {}
    for registry_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        state = hass.states.get(registry_entry.entity_id)
        entities[registry_entry.entity_id] = {
            "unique_id": registry_entry.unique_id,
            "disabled_by": registry_entry.disabled_by,
            "friendly_name": state.attributes["friendly_name"] if state else None,
            "original_name": registry_entry.original_name,
        }

    assert dict(sorted(entities.items())) == snapshot


async def test_unscheduled_assigned_programs_have_entities(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After setup, assigned-but-unscheduled programs read Not scheduled, not unavailable."""
    monkeypatch.setitem(
        CLOUD_DATA,
        BACKYARD_ID,
        replace(
            CLOUD_DATA[BACKYARD_ID],
            scheduled_programs=[
                ScheduledProgram(4000001, "Program A", (ScheduledTime(time(5, 0), 0),))
            ],
            effective_programs=build_effective_programs(
                [],
                [ScheduledProgram(4000001, "Program A", (ScheduledTime(time(5, 0), 0),))],
            ),
            runtime_assignments=[
                StationRuntime(
                    BACKYARD_STATION_ID,
                    (
                        RuntimeAssignment(1, 4000001, "A", "00:10:00", "00:10:00"),
                        RuntimeAssignment(2, 4000002, "B", "00:07:00", "00:07:00"),
                        RuntimeAssignment(3, 4000003, "C", "00:10:00", "00:10:00"),
                    ),
                )
            ],
        ),
    )
    await setup_entry(hass, make_entry(BACKYARD_ID))

    states = {
        program: hass.states.get(f"sensor.controller_200001_program_{program}")
        for program in ("a", "b", "c")
    }

    assert {program: state.state for program, state in states.items() if state} == {
        "a": "05:00",
        "b": "Not scheduled",
        "c": "Not scheduled",
    }
    assert states["c"] is not None
    assert states["c"].attributes["effective"] is False


async def test_entity_presentation(hass: HomeAssistant, snapshot: SnapshotAssertion) -> None:
    """Categories, device classes, units and enum options are pinned for dashboards."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))

    presentation = {}
    for registry_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        state = hass.states.get(registry_entry.entity_id)
        presentation[registry_entry.entity_id] = {
            "entity_category": registry_entry.entity_category,
            "device_class": registry_entry.original_device_class,
            "unit": registry_entry.unit_of_measurement,
            "translation_key": registry_entry.translation_key,
            "options": state.attributes.get("options") if state else None,
        }

    assert dict(sorted(presentation.items())) == snapshot


async def test_every_translation_key_has_icon_and_states(hass: HomeAssistant) -> None:
    """Each entity has an icon source, and enum states have translated names."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    component = Path(__file__).parents[1] / "custom_components" / "rainbird_iq4"
    icons = json.loads((component / "icons.json").read_text())["entity"]
    strings = json.loads((component / "strings.json").read_text())["entity"]

    for registry_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        key = registry_entry.translation_key
        assert key is not None, registry_entry.entity_id
        # A device class supplies state-based icons, so no icons.json entry is needed.
        assert key in icons[registry_entry.domain] or registry_entry.original_device_class, (
            registry_entry.entity_id
        )
        if registry_entry.original_device_class == SensorDeviceClass.ENUM:
            state = hass.states.get(registry_entry.entity_id)
            assert state is not None
            for option in state.attributes["options"]:
                assert option in strings[registry_entry.domain][key]["state"]


async def test_inconclusive_irrigation_state_is_unknown(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """Inconclusive controller evidence shows as Home Assistant's unknown state."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    clients[f"host-{BACKYARD_ID}"].get_realtime_state.return_value = LocalIrrigationState(
        irrigation_enabled=None,
        active_terminals=(),
        available_terminals=None,
        rain_sensor_active=None,
        rain_delay_days=None,
        queue=None,
    )

    await entry.runtime_data.local.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get("sensor.controller_200001_irrigation_state")
    assert state is not None
    assert state.state == STATE_UNKNOWN
