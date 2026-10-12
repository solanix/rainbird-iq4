"""Tests for entities that follow stations and programs added or removed in IQ4."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyrainbird_iq4.cloud.models import RuntimeAssignment, Station, StationRuntime

from tests.common import MockConfigEntry

from .conftest import BACKYARD_ID, BACKYARD_STATION_ID, CLOUD_DATA, make_entry, setup_entry

NEW_STATION_ID = 30000002
REMOVED_STATION_ID = 30000009
NEW_PROGRAM_ID = 4000004


def _unique_ids(hass: HomeAssistant, entry: MockConfigEntry) -> set[str]:
    return {
        registry_entry.unique_id
        for registry_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }


def _entity_id(hass: HomeAssistant, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", "rainbird_iq4", unique_id)
    assert entity_id is not None
    return entity_id


def _set_cloud(monkeypatch: pytest.MonkeyPatch, **changes: Any) -> None:
    monkeypatch.setitem(CLOUD_DATA, BACKYARD_ID, replace(CLOUD_DATA[BACKYARD_ID], **changes))


async def _refresh_cloud(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.cloud.async_refresh()
    await hass.async_block_till_done()


async def _reload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


async def test_new_station_appears_without_reload(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A station added in IQ4 gets an entity on the next cloud refresh."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    stations = CLOUD_DATA[BACKYARD_ID].stations
    _set_cloud(
        monkeypatch,
        stations=[*stations, Station(NEW_STATION_ID, BACKYARD_ID, "Station 002", 2, True)],
    )

    await _refresh_cloud(hass, entry)

    unique_id = f"{BACKYARD_ID}_station_{NEW_STATION_ID}"
    assert unique_id in _unique_ids(hass, entry)
    state = hass.states.get(_entity_id(hass, unique_id))
    assert state is not None
    assert state.state != STATE_UNAVAILABLE


async def test_new_assignment_adds_program_and_runtime(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A program newly assigned to a station gets program and runtime entities."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    _set_cloud(
        monkeypatch,
        runtime_assignments=[
            StationRuntime(
                BACKYARD_STATION_ID,
                (RuntimeAssignment(9, NEW_PROGRAM_ID, "D", "00:05:00", "00:05:00"),),
            )
        ],
    )

    await _refresh_cloud(hass, entry)

    unique_ids = _unique_ids(hass, entry)
    assert f"{BACKYARD_ID}_program_{NEW_PROGRAM_ID}" in unique_ids
    assert (
        f"{BACKYARD_ID}_station_{BACKYARD_STATION_ID}_program_{NEW_PROGRAM_ID}_runtime"
        in unique_ids
    )


async def test_removed_station_is_unavailable_then_removed_on_reload(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A removed station goes unavailable while running and is deleted on the next live setup."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    removed = f"{BACKYARD_ID}_station_{REMOVED_STATION_ID}"
    removed_entity_id = _entity_id(hass, removed)
    _set_cloud(
        monkeypatch,
        stations=[
            station
            for station in CLOUD_DATA[BACKYARD_ID].stations
            if station.id != REMOVED_STATION_ID
        ],
    )

    await _refresh_cloud(hass, entry)

    removed_state = hass.states.get(removed_entity_id)
    assert removed_state is not None
    assert removed_state.state == STATE_UNAVAILABLE
    assert removed in _unique_ids(hass, entry)

    await _reload(hass, entry)

    unique_ids = _unique_ids(hass, entry)
    assert removed not in unique_ids
    assert f"{BACKYARD_ID}_station_{BACKYARD_STATION_ID}" in unique_ids
    assert f"{BACKYARD_ID}_firmware_version" in unique_ids


async def test_saved_snapshot_never_removes_entities(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, cloud_available: dict[str, bool]
) -> None:
    """Setting up from the saved snapshot during an outage deletes nothing, even if stale."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    removed = f"{BACKYARD_ID}_station_{REMOVED_STATION_ID}"
    _set_cloud(
        monkeypatch,
        stations=[
            station
            for station in CLOUD_DATA[BACKYARD_ID].stations
            if station.id != REMOVED_STATION_ID
        ],
    )
    await _refresh_cloud(hass, entry)
    cloud_available["ok"] = False

    await _reload(hass, entry)

    assert entry.runtime_data.cloud.saved_data_since is not None
    assert removed in _unique_ids(hass, entry)


async def test_empty_station_list_never_removes_entities(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live response without stations is treated as suspect and deletes nothing."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    before = _unique_ids(hass, entry)
    _set_cloud(monkeypatch, stations=[])

    await _reload(hass, entry)

    assert before <= _unique_ids(hass, entry)
