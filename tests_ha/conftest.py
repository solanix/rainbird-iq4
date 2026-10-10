"""Fixtures for tests that run against a real Home Assistant Core checkout.

Run from the Home Assistant Core checkout so its pytest plugins and fixtures load:

    cd /workspaces/home-assistant-core
    python3 -m pytest -c pyproject.toml -p tests.conftest /workspaces/ha-rainbird-iq4/tests_ha
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pyrainbird_iq4.cloud.models import Controller, Station
from pyrainbird_iq4.local import LocalCurrentQueue, LocalIrrigationState, LocalQueueState

import custom_components

CUSTOM_COMPONENTS = str(Path(__file__).parents[1] / "custom_components")
# HA's test config owns the custom_components package; load this integration ahead of it.
custom_components.__path__.insert(0, CUSTOM_COMPONENTS)

from custom_components.rainbird_iq4.const import (  # noqa: E402
    CONF_CONTROLLER_ID,
    CONF_LOCAL_HOST,
    CONF_LOCAL_PASSWORD,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.rainbird_iq4.coordinator import RainBirdIQ4Data  # noqa: E402
from tests.common import MockConfigEntry  # noqa: E402

BACKYARD_ID = 200001
OTHER_ID = 700001
BACKYARD_STATION_ID = 30000001
OTHER_STATION_ID = 99000001


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow HA to load custom integrations."""


def controller(controller_id: int) -> Controller:
    return Controller(
        id=controller_id,
        name=f"Controller {controller_id}",
        type=57,
        site_id=1,
        site_name="Site",
        station_count=3,
        programs_used_count=0,
        mac_address="AA:AA",
        version="3.11.0",
        is_mqtt=True,
        latitude=0.0,
        longitude=0.0,
        rain_delay=0,
        simultaneous_stations=1,
        is_shutdown=False,
        satellite_enabled=True,
    )


def cloud_data(controller_id: int, stations: list[Station]) -> RainBirdIQ4Data:
    return RainBirdIQ4Data(
        controller=controller(controller_id),
        connected=True,
        connection_status=None,
        stale=False,
        stations=stations,
        programs=[],
        scheduled_programs=[],
        runtime_assignments=[],
        effective_programs=[],
    )


CLOUD_DATA = {
    BACKYARD_ID: cloud_data(
        BACKYARD_ID,
        [
            Station(BACKYARD_STATION_ID, BACKYARD_ID, "Station 001", 1, True),
            Station(30000008, BACKYARD_ID, "Station 008", 8, False),
            Station(30000009, BACKYARD_ID, "Station 009", 9, None),
        ],
    ),
    OTHER_ID: cloud_data(OTHER_ID, [Station(OTHER_STATION_ID, OTHER_ID, "Other 001", 1, True)]),
}


def local_state(
    *, active: tuple[int, ...] = (), rain_sensor_active: bool | None = False
) -> LocalIrrigationState:
    running = bool(active)
    return LocalIrrigationState(
        irrigation_enabled=True,
        active_terminals=active,
        available_terminals=tuple(range(1, 11)),
        rain_sensor_active=rain_sensor_active,
        rain_delay_days=0,
        queue=LocalQueueState(
            current=LocalCurrentQueue(4 if running else 0, running, None, None, None, 0),
            zones=(),
        ),
    )


def make_client() -> MagicMock:
    """Return a local client double; tests assert on its write methods."""
    client = MagicMock()
    client.get_realtime_state = AsyncMock(return_value=local_state())
    client.get_slow_state = AsyncMock(return_value=local_state())
    client.start_station = AsyncMock()
    client.stop_irrigation = AsyncMock()
    client.wait_for_station_active = AsyncMock(return_value=True)
    client.wait_for_idle = AsyncMock(return_value=True)
    return client


def make_entry(controller_id: int, *, local: bool = True) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"Controller {controller_id}",
        unique_id=str(controller_id),
        data={
            CONF_USERNAME: "user",
            CONF_PASSWORD: "secret",
            CONF_CONTROLLER_ID: controller_id,
        },
        options=(
            {CONF_LOCAL_HOST: f"host-{controller_id}", CONF_LOCAL_PASSWORD: "pin"} if local else {}
        ),
    )


@pytest.fixture
def clients() -> dict[str, MagicMock]:
    """Local client doubles keyed by configured host."""
    return {f"host-{BACKYARD_ID}": make_client(), f"host-{OTHER_ID}": make_client()}


@pytest.fixture
def cloud_available() -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture(autouse=True)
def mock_io(clients: dict[str, MagicMock], cloud_available: dict[str, bool]) -> Generator[None]:
    """Replace every cloud and local network path with offline doubles."""

    async def fetch_cloud(self: Any) -> RainBirdIQ4Data:
        if not cloud_available["ok"]:
            from homeassistant.helpers.update_coordinator import UpdateFailed  # noqa: PLC0415

            raise UpdateFailed("cloud down")
        return CLOUD_DATA[self.controller_id]

    async def connect(_session: Any, host: str, _password: str, **_: Any) -> MagicMock:
        return clients[host]

    with (
        patch(
            "custom_components.rainbird_iq4.coordinator.RainBirdIQ4Coordinator._async_update_data",
            fetch_cloud,
        ),
        patch(
            "custom_components.rainbird_iq4.coordinator.RainBirdIQ4LocalClient.connect",
            AsyncMock(side_effect=connect),
        ),
    ):
        yield


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
