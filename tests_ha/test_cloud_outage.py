"""Tests that an IQ4 cloud outage at startup does not take local stop down with it."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pyrainbird_iq4.exceptions import RainBirdIQ4CredentialsError

from custom_components.rainbird_iq4 import saved_data
from custom_components.rainbird_iq4.const import DOMAIN
from custom_components.rainbird_iq4.coordinator import RainBirdIQ4CloudCoordinator
from tests.common import MockConfigEntry

from .conftest import (
    CLOUD_DATA,
    BACKYARD_ID,
    BACKYARD_STATION_ID,
    local_state,
    make_entry,
    setup_entry,
)

# Captured before the autouse mock replaces it, to exercise the real auth path.
REAL_CLOUD_FETCH = RainBirdIQ4CloudCoordinator._async_fetch_cloud

STATION_METADATA = "sensor.controller_200001_station_001_metadata"
IRRIGATION_STATE = "sensor.controller_200001_irrigation_state"


async def _restart_with_cloud_down(
    hass: HomeAssistant, entry: MockConfigEntry, cloud_available: dict[str, bool]
) -> None:
    """Unload a loaded entry, take the cloud down, and set it up again."""
    assert await hass.config_entries.async_unload(entry.entry_id)
    cloud_available["ok"] = False
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state


def _device_id(hass: HomeAssistant) -> str:
    return next(
        device.id
        for device in dr.async_get(hass).devices
        if (DOMAIN, str(BACKYARD_ID)) in device.identifiers
    )


async def test_successful_refresh_saves_snapshot(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A successful cloud refresh saves a snapshot that round-trips exactly."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))

    saved = hass_storage[saved_data.storage_key(entry.entry_id)]["data"]

    assert saved_data.deserialize(saved["data"]) == CLOUD_DATA[BACKYARD_ID]
    assert "password" not in str(saved)


async def test_cloud_outage_at_startup_keeps_local_stop(
    hass: HomeAssistant,
    clients: dict[str, MagicMock],
    cloud_available: dict[str, bool],
) -> None:
    """With the cloud down at startup, the saved snapshot loads the entry and stop works."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    await _restart_with_cloud_down(hass, entry, cloud_available)
    client = clients[f"host-{BACKYARD_ID}"]
    client.get_realtime_state.return_value = local_state(active=(1,))

    assert entry.state is ConfigEntryState.LOADED
    assert _state(hass, STATION_METADATA) == STATE_UNAVAILABLE
    assert _state(hass, IRRIGATION_STATE) != STATE_UNAVAILABLE

    response = await hass.services.async_call(
        DOMAIN,
        "stop_irrigation",
        {"device_id": _device_id(hass)},
        blocking=True,
        return_response=True,
    )

    client.stop_irrigation.assert_awaited_once_with()
    assert response is not None
    assert response["acknowledged"] is True


async def test_cloud_outage_at_startup_blocks_start(
    hass: HomeAssistant,
    clients: dict[str, MagicMock],
    cloud_available: dict[str, bool],
) -> None:
    """Enablement cannot be confirmed from a saved snapshot, so starts are refused."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    await _restart_with_cloud_down(hass, entry, cloud_available)

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN,
            "start_station",
            {
                "device_id": _device_id(hass),
                "station_id": BACKYARD_STATION_ID,
                "duration_minutes": 1,
            },
            blocking=True,
        )

    assert err.value.translation_key == "cloud_data_unavailable"
    clients[f"host-{BACKYARD_ID}"].start_station.assert_not_awaited()


async def test_cloud_recovery_restores_cloud_entities(
    hass: HomeAssistant, cloud_available: dict[str, bool]
) -> None:
    """Cloud entities recover on the next successful refresh without a reload."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    await _restart_with_cloud_down(hass, entry, cloud_available)
    assert entry.runtime_data.cloud.saved_data_since is not None

    cloud_available["ok"] = True
    await entry.runtime_data.cloud.async_refresh()
    await hass.async_block_till_done()

    assert _state(hass, STATION_METADATA) != STATE_UNAVAILABLE
    assert entry.runtime_data.cloud.saved_data_since is None


async def test_cloud_outage_without_snapshot_retries(
    hass: HomeAssistant, cloud_available: dict[str, bool]
) -> None:
    """Without a saved snapshot there is nothing to build entities from, so setup retries."""
    cloud_available["ok"] = False
    entry = make_entry(BACKYARD_ID)
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_cloud_only_entry_does_not_use_snapshot(
    hass: HomeAssistant, cloud_available: dict[str, bool]
) -> None:
    """A cloud-only entry has no local control to protect, so it keeps retrying."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID, local=False))
    await _restart_with_cloud_down(hass, entry, cloud_available)

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_rejected_credentials_reauth_instead_of_snapshot(hass: HomeAssistant) -> None:
    """Rejected credentials at startup ask for reauthentication, never fall back."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    assert await hass.config_entries.async_unload(entry.entry_id)

    with (
        patch.object(RainBirdIQ4CloudCoordinator, "_async_fetch_cloud", REAL_CLOUD_FETCH),
        patch(
            "custom_components.rainbird_iq4.coordinator.authenticate",
            AsyncMock(side_effect=RainBirdIQ4CredentialsError("rejected")),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_removing_entry_deletes_snapshot(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """The saved snapshot is deleted with the entry."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    assert saved_data.storage_key(entry.entry_id) in hass_storage

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert saved_data.storage_key(entry.entry_id) not in hass_storage
