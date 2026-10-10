"""Tests for the admin-only Rain Bird IQ4 control actions against real Home Assistant."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError, Unauthorized
from homeassistant.helpers import device_registry as dr

from custom_components.rainbird_iq4.const import DOMAIN
from tests.common import MockConfigEntry, MockUser

from .conftest import (
    OTHER_ID,
    OTHER_STATION_ID,
    BACKYARD_ID,
    BACKYARD_STATION_ID,
    local_state,
    make_entry,
    setup_entry,
)

BACKYARD_HOST = f"host-{BACKYARD_ID}"
OTHER_HOST = f"host-{OTHER_ID}"


def _device_id(hass: HomeAssistant, controller_id: int) -> str:
    return next(
        device.id
        for device in dr.async_get(hass).devices
        if (DOMAIN, str(controller_id)) in device.identifiers
    )


def _assert_no_writes(*clients: MagicMock) -> None:
    for client in clients:
        client.start_station.assert_not_awaited()
        client.stop_irrigation.assert_not_awaited()


async def _start(hass: HomeAssistant, data: dict[str, Any], context: Context | None = None) -> Any:
    return await hass.services.async_call(
        DOMAIN, "start_station", data, blocking=True, return_response=True, context=context
    )


async def _stop(hass: HomeAssistant, device_id: str, context: Context | None = None) -> Any:
    return await hass.services.async_call(
        DOMAIN,
        "stop_irrigation",
        {"device_id": device_id},
        blocking=True,
        return_response=True,
        context=context,
    )


async def test_setup_and_reload_never_write(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """Setup registers both actions and neither setup nor reload sends a control command."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))

    assert hass.services.has_service(DOMAIN, "start_station")
    assert hass.services.has_service(DOMAIN, "stop_irrigation")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    _assert_no_writes(*clients.values())


async def test_start_station_verified(hass: HomeAssistant, clients: dict[str, MagicMock]) -> None:
    """An admin start on an enabled station sends one write and reports verification."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    device_id = _device_id(hass, BACKYARD_ID)

    response = await _start(
        hass,
        {"device_id": device_id, "station_id": BACKYARD_STATION_ID, "duration_minutes": 5},
    )

    clients[BACKYARD_HOST].start_station.assert_awaited_once_with(1, 5)
    assert response == {
        "acknowledged": True,
        "verified": True,
        "no_op": False,
        "station_id": BACKYARD_STATION_ID,
        "terminal": 1,
    }


async def test_start_station_unconfirmed_is_reported_not_retried(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """An acknowledged start that is not observed running is reported as unverified."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    clients[BACKYARD_HOST].wait_for_station_active.return_value = False

    response = await _start(
        hass,
        {
            "device_id": _device_id(hass, BACKYARD_ID),
            "station_id": BACKYARD_STATION_ID,
            "duration_minutes": 1,
        },
    )

    assert clients[BACKYARD_HOST].start_station.await_count == 1
    assert response["acknowledged"] is True
    assert response["verified"] is False


async def test_start_station_ambiguous_write(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """A write timeout is surfaced as ambiguous after exactly one attempt."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    clients[BACKYARD_HOST].start_station.side_effect = TimeoutError()

    with pytest.raises(HomeAssistantError) as err:
        await _start(
            hass,
            {
                "device_id": _device_id(hass, BACKYARD_ID),
                "station_id": BACKYARD_STATION_ID,
                "duration_minutes": 1,
            },
        )

    assert err.value.translation_key == "write_outcome_ambiguous"
    assert clients[BACKYARD_HOST].start_station.await_count == 1


@pytest.mark.parametrize(
    ("service", "extra"),
    [
        pytest.param(
            "start_station",
            {"station_id": BACKYARD_STATION_ID, "duration_minutes": 1},
            id="start",
        ),
        pytest.param("stop_irrigation", {}, id="stop"),
    ],
)
async def test_non_admin_is_rejected(
    hass: HomeAssistant,
    hass_read_only_user: MockUser,
    clients: dict[str, MagicMock],
    service: str,
    extra: dict[str, Any],
) -> None:
    """Non-admin users cannot call either control action."""
    await setup_entry(hass, make_entry(BACKYARD_ID))

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            service,
            {"device_id": _device_id(hass, BACKYARD_ID)} | extra,
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )

    _assert_no_writes(*clients.values())


@pytest.mark.parametrize(
    "duration",
    [
        pytest.param(0, id="zero"),
        pytest.param(31, id="too-long"),
        pytest.param(True, id="bool"),
        pytest.param(1.5, id="fractional"),
        pytest.param("5", id="string"),
    ],
)
async def test_start_station_schema_rejects_duration(
    hass: HomeAssistant, clients: dict[str, MagicMock], duration: Any
) -> None:
    """Durations that are not whole minutes from 1 to 30 never reach the controller."""
    await setup_entry(hass, make_entry(BACKYARD_ID))

    with pytest.raises(vol.Invalid):
        await _start(
            hass,
            {
                "device_id": _device_id(hass, BACKYARD_ID),
                "station_id": BACKYARD_STATION_ID,
                "duration_minutes": duration,
            },
        )

    _assert_no_writes(*clients.values())


@pytest.mark.parametrize(
    ("station_id", "translation_key"),
    [
        pytest.param(OTHER_STATION_ID, "station_not_found", id="cross-controller"),
        pytest.param(30000008, "station_not_enabled", id="disabled"),
        pytest.param(30000009, "station_not_enabled", id="enabled-unknown"),
    ],
)
async def test_start_station_rejects_ineligible_station(
    hass: HomeAssistant,
    clients: dict[str, MagicMock],
    station_id: int,
    translation_key: str,
) -> None:
    """Only enabled stations belonging to the selected controller can start."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    await setup_entry(hass, make_entry(OTHER_ID))

    with pytest.raises(ServiceValidationError) as err:
        await _start(
            hass,
            {
                "device_id": _device_id(hass, BACKYARD_ID),
                "station_id": station_id,
                "duration_minutes": 1,
            },
        )

    assert err.value.translation_key == translation_key
    _assert_no_writes(*clients.values())


async def test_start_station_blocked_by_rain_sensor(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """An active rain sensor read during preflight blocks the start."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    clients[BACKYARD_HOST].get_slow_state.return_value = local_state(rain_sensor_active=True)

    with pytest.raises(HomeAssistantError) as err:
        await _start(
            hass,
            {
                "device_id": _device_id(hass, BACKYARD_ID),
                "station_id": BACKYARD_STATION_ID,
                "duration_minutes": 1,
            },
        )

    assert err.value.translation_key == "rain_sensor_active"
    _assert_no_writes(*clients.values())


async def test_start_station_requires_current_cloud_data(
    hass: HomeAssistant, clients: dict[str, MagicMock], cloud_available: dict[str, bool]
) -> None:
    """Enablement cannot be confirmed from a failed cloud refresh."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    cloud_available["ok"] = False
    await entry.runtime_data.cloud.async_refresh()

    with pytest.raises(HomeAssistantError) as err:
        await _start(
            hass,
            {
                "device_id": _device_id(hass, BACKYARD_ID),
                "station_id": BACKYARD_STATION_ID,
                "duration_minutes": 1,
            },
        )

    assert err.value.translation_key == "cloud_data_unavailable"
    _assert_no_writes(*clients.values())


async def test_stop_running_without_cloud(
    hass: HomeAssistant, clients: dict[str, MagicMock], cloud_available: dict[str, bool]
) -> None:
    """Stop works during a cloud outage and sends exactly one command."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    cloud_available["ok"] = False
    await entry.runtime_data.cloud.async_refresh()
    clients[BACKYARD_HOST].get_realtime_state.return_value = local_state(active=(1,))

    response = await _stop(hass, _device_id(hass, BACKYARD_ID))

    clients[BACKYARD_HOST].stop_irrigation.assert_awaited_once_with()
    assert response["acknowledged"] is True
    assert response["verified"] is True
    assert response["no_op"] is False


async def test_stop_idle_is_no_op(hass: HomeAssistant, clients: dict[str, MagicMock]) -> None:
    """A confirmed-idle controller receives no stop command."""
    await setup_entry(hass, make_entry(BACKYARD_ID))

    response = await _stop(hass, _device_id(hass, BACKYARD_ID))

    _assert_no_writes(*clients.values())
    assert response["no_op"] is True
    assert response["verified"] is True


async def test_stop_targets_only_selected_controller(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """With two controllers, stop reaches only the selected device's controller."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    await setup_entry(hass, make_entry(OTHER_ID))
    for client in clients.values():
        client.get_realtime_state.return_value = local_state(active=(1,))

    await _stop(hass, _device_id(hass, OTHER_ID))

    clients[OTHER_HOST].stop_irrigation.assert_awaited_once_with()
    clients[BACKYARD_HOST].stop_irrigation.assert_not_awaited()


async def test_unknown_device_is_rejected(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """A device ID that does not exist is rejected."""
    await setup_entry(hass, make_entry(BACKYARD_ID))

    with pytest.raises(ServiceValidationError) as err:
        await _stop(hass, "missing")

    assert err.value.translation_key == "invalid_device"
    _assert_no_writes(*clients.values())


async def test_foreign_device_is_rejected(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """A device owned by another integration is rejected."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    other_entry = MockConfigEntry(domain="other")
    other_entry.add_to_hass(hass)
    foreign = dr.async_get(hass).async_get_or_create(
        config_entry_id=other_entry.entry_id, identifiers={("other", "1")}
    )

    with pytest.raises(ServiceValidationError) as err:
        await _stop(hass, foreign.id)

    assert err.value.translation_key == "invalid_device"
    _assert_no_writes(*clients.values())


async def test_actions_after_unload_are_rejected(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """Actions stay registered after the last unload but refuse an unloaded entry."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    device_id = _device_id(hass, BACKYARD_ID)
    assert await hass.config_entries.async_unload(entry.entry_id)

    assert hass.services.has_service(DOMAIN, "stop_irrigation")
    with pytest.raises(ServiceValidationError) as err:
        await _stop(hass, device_id)

    assert err.value.translation_key == "entry_not_loaded"
    _assert_no_writes(*clients.values())


async def test_local_not_configured_is_rejected(hass: HomeAssistant) -> None:
    """A cloud-only entry cannot be controlled."""
    await setup_entry(hass, make_entry(BACKYARD_ID, local=False))

    with pytest.raises(ServiceValidationError) as err:
        await _stop(hass, _device_id(hass, BACKYARD_ID))

    assert err.value.translation_key == "local_not_configured"
