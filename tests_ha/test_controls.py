"""Tests for the station picker and duration entities against real Home Assistant."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import voluptuous as vol
import yaml
from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pyrainbird_iq4.cloud.models import Station

from custom_components.rainbird_iq4.const import DOMAIN
from tests.common import MockUser, mock_restore_cache, mock_restore_cache_with_extra_data

from .conftest import (
    CLOUD_DATA,
    OTHER_ID,
    BACKYARD_ID,
    BACKYARD_STATION_ID,
    cloud_data,
    make_entry,
    setup_entry,
)

SELECT = "select.controller_200001_start_station"
NUMBER = "number.controller_200001_start_duration"


async def test_select_lists_only_enabled_stations(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """Disabled and unknown-state stations are never offered, and selecting sends nothing."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    state = hass.states.get(SELECT)
    assert state is not None
    assert state.attributes["options"] == ["Station 001"]
    assert state.state == STATE_UNKNOWN

    await hass.services.async_call(
        "select",
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: SELECT, ATTR_OPTION: "Station 001"},
        blocking=True,
    )

    state = hass.states.get(SELECT)
    assert state is not None
    assert state.state == "Station 001"
    assert state.attributes["station_id"] == BACKYARD_STATION_ID
    assert state.attributes["terminal"] == 1
    for client in clients.values():
        client.start_station.assert_not_awaited()


async def test_select_disambiguates_duplicate_names(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Duplicate cloud names get a terminal suffix so each option is unique."""
    monkeypatch.setitem(
        CLOUD_DATA,
        OTHER_ID,
        cloud_data(
            OTHER_ID,
            [
                Station(1, OTHER_ID, "Lawn", 2, True),
                Station(2, OTHER_ID, "Lawn", 1, True),
                Station(3, OTHER_ID, "Beds", 3, True),
            ],
        ),
    )
    await setup_entry(hass, make_entry(OTHER_ID))

    state = hass.states.get(f"select.controller_{OTHER_ID}_start_station")
    assert state is not None
    assert state.attributes["options"] == [
        "Lawn (terminal 1)",
        "Lawn (terminal 2)",
        "Beds",
    ]


@pytest.mark.parametrize(
    ("station_id", "expected_state", "expected_station_id"),
    [
        pytest.param(BACKYARD_STATION_ID, "Station 001", BACKYARD_STATION_ID, id="enabled"),
        pytest.param(30000008, STATE_UNKNOWN, None, id="now-disabled"),
    ],
)
async def test_select_restores_by_station_id(
    hass: HomeAssistant,
    station_id: int,
    expected_state: str,
    expected_station_id: int | None,
) -> None:
    """A restored choice is kept only while that station is still enabled."""
    mock_restore_cache(hass, [State(SELECT, "renamed", {"station_id": station_id})])

    await setup_entry(hass, make_entry(BACKYARD_ID))

    state = hass.states.get(SELECT)
    assert state is not None
    assert state.state == expected_state
    assert state.attributes["station_id"] == expected_station_id


async def test_duration_defaults_sets_and_restores(hass: HomeAssistant) -> None:
    """Duration starts at 5 minutes, accepts 1-30, and restores a saved value."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(NUMBER, "12"),
                {
                    "native_value": 12,
                    "native_min_value": 1,
                    "native_max_value": 30,
                    "native_step": 1,
                    "native_unit_of_measurement": "min",
                },
            )
        ],
    )
    await setup_entry(hass, make_entry(BACKYARD_ID))
    state = hass.states.get(NUMBER)
    assert state is not None
    assert state.state == "12"
    assert state.attributes["min"] == 1
    assert state.attributes["max"] == 30

    await hass.services.async_call(
        "number", SERVICE_SET_VALUE, {ATTR_ENTITY_ID: NUMBER, ATTR_VALUE: 7}, blocking=True
    )

    state = hass.states.get(NUMBER)
    assert state is not None
    assert state.state == "7"


async def test_duration_default(hass: HomeAssistant) -> None:
    """Without saved state the duration is 5 minutes."""
    await setup_entry(hass, make_entry(BACKYARD_ID))

    state = hass.states.get(NUMBER)
    assert state is not None
    assert state.state == "5"


async def test_controls_absent_without_local(hass: HomeAssistant) -> None:
    """A cloud-only entry has nothing to control, so no picker or duration exists."""
    await setup_entry(hass, make_entry(BACKYARD_ID, local=False))

    assert hass.states.get(SELECT) is None
    assert hass.states.get(NUMBER) is None


async def test_selection_drives_start_action(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """The script pattern used by the dashboard starts the selected station for the set time."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    await hass.services.async_call(
        "select",
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: SELECT, ATTR_OPTION: "Station 001"},
        blocking=True,
    )
    await hass.services.async_call(
        "number", SERVICE_SET_VALUE, {ATTR_ENTITY_ID: NUMBER, ATTR_VALUE: 3}, blocking=True
    )
    select_state = hass.states.get(SELECT)
    number_state = hass.states.get(NUMBER)
    assert select_state is not None
    assert number_state is not None
    entity_entry = er.async_get(hass).async_get(SELECT)
    assert entity_entry is not None
    device_id = entity_entry.device_id

    await hass.services.async_call(
        DOMAIN,
        "start_station",
        {
            "device_id": device_id,
            "station_id": select_state.attributes["station_id"],
            "duration_minutes": float(number_state.state),
        },
        blocking=True,
        return_response=True,
    )

    clients[f"host-{BACKYARD_ID}"].start_station.assert_awaited_once_with(1, 3)


async def _setup_example_script(hass: HomeAssistant) -> None:
    """Load examples/script.yaml with this test's entity and device IDs substituted."""
    entity_entry = er.async_get(hass).async_get(SELECT)
    assert entity_entry is not None
    text = (
        (Path(__file__).parents[1] / "examples" / "script.yaml")
        .read_text()
        .replace("select.backyard_start_station", SELECT)
        .replace("number.backyard_start_duration", NUMBER)
        .replace("REPLACE_WITH_DEVICE_ID", str(entity_entry.device_id))
    )
    assert await async_setup_component(hass, "script", {"script": yaml.safe_load(text)})


async def _select_station(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        "select",
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: SELECT, ATTR_OPTION: "Station 001"},
        blocking=True,
    )


async def test_example_script_starts_selected_station(
    hass: HomeAssistant, hass_admin_user: MockUser, clients: dict[str, MagicMock]
) -> None:
    """The shipped example script starts the picked station for the set duration."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    await _select_station(hass)
    await _setup_example_script(hass)

    await hass.services.async_call(
        "script",
        "rainbird_backyard_start_selected",
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )

    clients[f"host-{BACKYARD_ID}"].start_station.assert_awaited_once_with(1, 5)


async def test_example_script_keeps_admin_check(
    hass: HomeAssistant, hass_read_only_user: MockUser, clients: dict[str, MagicMock]
) -> None:
    """A non-admin running the script is still refused by start_station."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    await _select_station(hass)
    await _setup_example_script(hass)

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "script",
            "rainbird_backyard_start_selected",
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )

    clients[f"host-{BACKYARD_ID}"].start_station.assert_not_awaited()


async def test_example_script_requires_selection(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """Without a selected station the call is rejected visibly and nothing is sent."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    await _setup_example_script(hass)

    with pytest.raises(vol.Invalid, match="station_id"):
        await hass.services.async_call("script", "rainbird_backyard_start_selected", blocking=True)

    clients[f"host-{BACKYARD_ID}"].start_station.assert_not_awaited()
