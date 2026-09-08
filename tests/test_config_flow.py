"""Tests for the Rain Bird IQ4 config flow."""

from __future__ import annotations

from datetime import UTC, datetime, time
from unittest.mock import AsyncMock, patch

import pytest
from pyrainbird_iq4.cloud.models import (
    ConnectionStatus,
    Controller,
    ScheduledProgram,
    ScheduledTime,
)
from pyrainbird_iq4.exceptions import (
    RainBirdIQ4ConnectionError,
    RainBirdIQ4CredentialsError,
)

from custom_components.rainbird_iq4.config_flow import (
    RainBirdIQ4ConfigFlow,
    RainBirdIQ4OptionsFlow,
    _preferred_controller_order,
)
from custom_components.rainbird_iq4.const import (
    CONF_LOCAL_HOST,
    CONF_LOCAL_PASSWORD,
    DOMAIN,
)


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


async def test_successful_config_flow(hass, controller_a):
    """User can authenticate, discover a controller, and create an entry."""
    with patch(
        "custom_components.rainbird_iq4.config_flow.validate_input",
        AsyncMock(
            return_value=(
                [controller_a],
                {
                    controller_a.id: ConnectionStatus(
                        controller_a.id,
                        True,
                        "2024-01-01T00:00:00Z",
                    )
                },
            )
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
            data={"username": "user", "password": "pass"},
        )

    assert result["type"] == "create_entry"
    assert result["title"] == "West Yard (Home)"
    assert result["data"]["controller_id"] == controller_a.id
    assert "username" in result["data"]
    assert "password" in result["data"]


async def test_bad_authentication(hass):
    """Authentication errors map to invalid_auth."""
    with patch(
        "custom_components.rainbird_iq4.config_flow.validate_input",
        AsyncMock(side_effect=RainBirdIQ4CredentialsError("bad auth")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
            data={"username": "bad", "password": "bad"},
        )

    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_auth"


async def test_connection_failure(hass):
    """Connection errors map to cannot_connect."""
    with patch(
        "custom_components.rainbird_iq4.config_flow.validate_input",
        AsyncMock(side_effect=RainBirdIQ4ConnectionError("offline")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
            data={"username": "user", "password": "pass"},
        )

    assert result["type"] == "form"
    assert result["errors"]["base"] == "cannot_connect"


async def test_multiple_controller_selection(controller_a, controller_b, hass):
    """Multiple controllers present a selection form."""
    flow = RainBirdIQ4ConfigFlow()
    flow.hass = hass
    flow._controllers = [controller_a, controller_b]
    flow._statuses = {
        controller_a.id: ConnectionStatus(controller_a.id, True, "2024-01-01T00:00:00Z"),
        controller_b.id: ConnectionStatus(controller_b.id, False, "2024-01-01T00:00:00Z"),
    }

    result = await flow.async_step_select_controller()

    assert result["type"] == "form"
    assert result["step_id"] == "select_controller"


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


async def test_local_options_preserve_pin_and_can_disable_polling() -> None:
    """Editing the LAN host need not redisclose the stored controller PIN."""
    entry = type(
        "Entry",
        (),
        {
            "options": {
                CONF_LOCAL_HOST: "192.0.2.10",
                CONF_LOCAL_PASSWORD: "stored-pin",
            }
        },
    )()
    flow = RainBirdIQ4OptionsFlow(entry)

    updated = await flow.async_step_init(
        {CONF_LOCAL_HOST: "backyard.local", CONF_LOCAL_PASSWORD: ""}
    )
    disabled = await flow.async_step_init({CONF_LOCAL_HOST: "", CONF_LOCAL_PASSWORD: ""})

    assert updated["data"] == {
        CONF_LOCAL_HOST: "backyard.local",
        CONF_LOCAL_PASSWORD: "stored-pin",
    }
    assert disabled["data"] == {}


async def test_local_options_reject_host_without_pin() -> None:
    """Local polling cannot be silently configured without authentication."""
    entry = type("Entry", (), {"options": {}})()
    flow = RainBirdIQ4OptionsFlow(entry)

    result = await flow.async_step_init(
        {CONF_LOCAL_HOST: "backyard.local", CONF_LOCAL_PASSWORD: ""}
    )

    assert result["type"] == "form"
    assert result["errors"] is not None
    assert result["errors"]["base"] == "local_credentials_required"
