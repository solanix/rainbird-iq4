"""Tests that two controllers' entries never affect each other."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pyrainbird.exceptions import RainbirdConnectionError  # type: ignore[import-untyped]

from custom_components.rainbird_iq4.const import DOMAIN

from .conftest import BACKYARD_ID, BACKYARD_STATION_ID, OTHER_ID, make_entry, setup_entry


def _device_id(hass: HomeAssistant, controller_id: int) -> str:
    return next(
        device.id
        for device in dr.async_get(hass).devices
        if (DOMAIN, str(controller_id)) in device.identifiers
    )


def _irrigation_state(hass: HomeAssistant, controller_id: int) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{controller_id}_irrigation_state"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state


async def test_local_outage_on_one_controller_leaves_the_other(
    hass: HomeAssistant, clients: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """One controller's failing local polls never mark the other's entities unavailable."""
    # No grace period, so the failing controller goes unavailable at once.
    monkeypatch.setattr(
        "custom_components.rainbird_iq4.coordinator.LOCAL_REALTIME_GRACE", timedelta(0)
    )
    backyard = await setup_entry(hass, make_entry(BACKYARD_ID))
    other = await setup_entry(hass, make_entry(OTHER_ID))
    clients[f"host-{OTHER_ID}"].get_realtime_state.side_effect = RainbirdConnectionError()

    await other.runtime_data.local.async_refresh()
    await backyard.runtime_data.local.async_refresh()
    await hass.async_block_till_done()

    assert other.runtime_data.local.consecutive_failures == 1
    assert backyard.runtime_data.local.consecutive_failures == 0
    assert _irrigation_state(hass, OTHER_ID) == STATE_UNAVAILABLE
    assert _irrigation_state(hass, BACKYARD_ID) != STATE_UNAVAILABLE


async def test_unloading_one_controller_keeps_the_other_controllable(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """Closing one entry's connection leaves the other's start path open."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    other = await setup_entry(hass, make_entry(OTHER_ID))
    backyard_device = _device_id(hass, BACKYARD_ID)

    assert await hass.config_entries.async_unload(other.entry_id)
    response = await hass.services.async_call(
        DOMAIN,
        "start_station",
        {"device_id": backyard_device, "station_id": BACKYARD_STATION_ID, "duration_minutes": 1},
        blocking=True,
        return_response=True,
    )

    assert response is not None
    assert response["verified"] is True
    assert clients[f"host-{BACKYARD_ID}"].start_station.await_count == 1
    clients[f"host-{OTHER_ID}"].start_station.assert_not_awaited()
