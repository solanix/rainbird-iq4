"""Pin every entity state and attribute so refactors cannot change what dashboards see."""

from __future__ import annotations

from dataclasses import replace
from datetime import time

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyrainbird_iq4.cloud.models import (
    RuntimeAssignment,
    ScheduledProgram,
    ScheduledTime,
    Station,
    StationRuntime,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.rainbird_iq4.models import build_effective_programs

from .conftest import BACKYARD_ID, BACKYARD_STATION_ID, CLOUD_DATA, make_entry, setup_entry

SCHEDULED = [ScheduledProgram(4000001, "Program A", (ScheduledTime(time(5, 0), 0),))]


@pytest.mark.freeze_time("2026-10-11T06:00:00+00:00")
async def test_all_entity_states_and_attributes(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, snapshot: SnapshotAssertion
) -> None:
    """States and attributes for a controller with programs, assignments and mixed stations."""
    monkeypatch.setitem(
        CLOUD_DATA,
        BACKYARD_ID,
        replace(
            CLOUD_DATA[BACKYARD_ID],
            stations=[
                *CLOUD_DATA[BACKYARD_ID].stations,
                Station(30000002, BACKYARD_ID, "Station 002", 2, True),
            ],
            scheduled_programs=SCHEDULED,
            effective_programs=build_effective_programs([], SCHEDULED),
            runtime_assignments=[
                StationRuntime(
                    BACKYARD_STATION_ID,
                    (RuntimeAssignment(1, 4000003, "C", "00:10:00", "00:10:00"),),
                ),
                StationRuntime(
                    30000002,
                    (
                        RuntimeAssignment(2, 4000001, "A", "00:23:15", "00:15:00"),
                        RuntimeAssignment(3, 4000002, "B", "00:09:09", "00:10:00"),
                    ),
                ),
                StationRuntime(
                    30000008,
                    (RuntimeAssignment(4, 4000001, "A", "00:05:00", "00:05:00"),),
                ),
            ],
        ),
    )
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
            registry.async_update_entity(registry_entry.entity_id, disabled_by=None)
    # Enabled-by-default entities are pinned elsewhere; enable all so every attribute is covered.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    states = {}
    for registry_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        state = hass.states.get(registry_entry.entity_id)
        states[registry_entry.entity_id] = (
            {"state": state.state, "attributes": dict(state.attributes)} if state else None
        )

    assert dict(sorted(states.items())) == snapshot
