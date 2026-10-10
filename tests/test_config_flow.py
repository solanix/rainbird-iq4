"""Tests for config-flow helpers; the flows themselves are tested in tests_ha."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest
from pyrainbird_iq4.cloud.models import (
    ConnectionStatus,
    Controller,
    ScheduledProgram,
    ScheduledTime,
)

from custom_components.rainbird_iq4.config_flow import _preferred_controller_order


@pytest.fixture
def controller_a() -> Controller:
    return Controller(
        id=101,
        name="West Yard",
        type=1,
        site_id=5,
        site_name="Home",
        station_count=4,
        programs_used_count=2,
        mac_address="AA",
        version="1.0",
        is_mqtt=True,
        latitude=0.0,
        longitude=0.0,
        rain_delay=0,
        simultaneous_stations=1,
        is_shutdown=False,
        satellite_enabled=True,
    )


@pytest.fixture
def controller_b() -> Controller:
    return Controller(
        id=102,
        name="Back Yard",
        type=1,
        site_id=5,
        site_name="Home",
        station_count=6,
        programs_used_count=3,
        mac_address="BB",
        version="2.0",
        is_mqtt=True,
        latitude=0.0,
        longitude=0.0,
        rain_delay=0,
        simultaneous_stations=1,
        is_shutdown=False,
        satellite_enabled=True,
    )


async def test_connected_controller_preference(controller_a, controller_b):
    """Connected controllers are prioritized in selection ordering."""
    controllers = [controller_a, controller_b]
    statuses = {
        controller_a.id: ConnectionStatus(controller_a.id, False, "2024-01-01T00:00:00Z"),
        controller_b.id: ConnectionStatus(controller_b.id, True, "2024-01-01T00:00:00Z"),
    }

    ordered = _preferred_controller_order(controllers, statuses)

    assert ordered[0].id == controller_b.id
    assert ordered[1].id == controller_a.id


def test_mqtt_schedule_derived_programs():
    """MQTT schedules should count as effective programs when the catalog is empty."""
    from custom_components.rainbird_iq4.coordinator import build_effective_programs

    scheduled = [
        ScheduledProgram(
            program_id=77,
            program_name="Program C",
            scheduled_times=(ScheduledTime(time(6, 30), 1, "2024-01-01T06:30:00"),),
        )
    ]

    effective = build_effective_programs([], scheduled)

    assert effective[0]["source"] == "scheduled"
    assert effective[0]["id"] == 77
    assert effective[0]["name"] == "Program C"


def test_disconnected_stale_controller_handling():
    """Missing timestamps show stale/disconnected status."""
    from custom_components.rainbird_iq4.coordinator import _is_stale

    assert _is_stale(None) is True
    assert _is_stale(ConnectionStatus(1, False, "")) is True
    status = ConnectionStatus(1, False, "2024-01-01T00:00:00Z")
    assert _is_stale(status, now=datetime(2024, 1, 1, 0, 10, tzinfo=UTC)) is False
    assert _is_stale(status, now=datetime(2024, 1, 1, 0, 16, tzinfo=UTC)) is True
