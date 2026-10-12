"""Tests that control actions and local polling share one serialized connection."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pyrainbird_iq4.local import LocalIrrigationState

from custom_components.rainbird_iq4.const import DOMAIN

from .conftest import BACKYARD_ID, BACKYARD_STATION_ID, local_state, make_entry, setup_entry


def _device_id(hass: HomeAssistant) -> str:
    return next(
        device.id
        for device in dr.async_get(hass).devices
        if (DOMAIN, str(BACKYARD_ID)) in device.identifiers
    )


async def test_start_waits_for_in_flight_poll(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """A start issued mid-poll waits for the poll, then runs its own reads and one write."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    client = clients[f"host-{BACKYARD_ID}"]
    calls: list[str] = []
    poll_started = asyncio.Event()
    release_poll = asyncio.Event()

    async def realtime() -> LocalIrrigationState:
        calls.append("realtime")
        if not release_poll.is_set():
            poll_started.set()
            await release_poll.wait()
        return local_state()

    async def slow() -> LocalIrrigationState:
        calls.append("slow")
        return local_state()

    async def start(*_: Any) -> None:
        calls.append("start")

    client.get_realtime_state.side_effect = realtime
    client.get_slow_state.side_effect = slow
    client.start_station.side_effect = start

    poll = hass.async_create_task(entry.runtime_data.local.async_refresh())
    await asyncio.wait_for(poll_started.wait(), 1)
    action = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "start_station",
            {
                "device_id": _device_id(hass),
                "station_id": BACKYARD_STATION_ID,
                "duration_minutes": 1,
            },
            blocking=True,
        )
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert calls == ["realtime"]
    client.start_station.assert_not_awaited()

    release_poll.set()
    await asyncio.wait_for(asyncio.gather(poll, action), 5)

    assert calls[:4] == ["realtime", "realtime", "slow", "start"]
    assert client.start_station.await_count == 1


async def test_concurrent_start_and_stop_are_serialized(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """A stop sent while a start is writing runs after it, never interleaved."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    client = clients[f"host-{BACKYARD_ID}"]
    calls: list[str] = []
    start_writing = asyncio.Event()
    release_start = asyncio.Event()
    running = False

    async def realtime() -> LocalIrrigationState:
        calls.append("realtime")
        return local_state(active=(1,)) if running else local_state()

    async def start(*_: Any) -> None:
        nonlocal running
        calls.append("start")
        start_writing.set()
        await release_start.wait()
        running = True

    async def stop() -> None:
        nonlocal running
        calls.append("stop")
        running = False

    client.get_realtime_state.side_effect = realtime
    client.start_station.side_effect = start
    client.stop_irrigation.side_effect = stop
    device_id = _device_id(hass)

    start_task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "start_station",
            {"device_id": device_id, "station_id": BACKYARD_STATION_ID, "duration_minutes": 1},
            blocking=True,
        )
    )
    await asyncio.wait_for(start_writing.wait(), 1)
    stop_task = hass.async_create_task(
        hass.services.async_call(DOMAIN, "stop_irrigation", {"device_id": device_id}, blocking=True)
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert "stop" not in calls

    release_start.set()
    await asyncio.wait_for(asyncio.gather(start_task, stop_task), 5)

    assert calls.index("start") < calls.index("stop")
    assert client.start_station.await_count == 1
    assert client.stop_irrigation.await_count == 1


async def test_reload_waits_for_in_flight_start(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """A reload mid-start lets the write finish before the new entry touches the controller."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    client = clients[f"host-{BACKYARD_ID}"]
    calls: list[str] = []
    start_writing = asyncio.Event()
    release_start = asyncio.Event()

    async def realtime() -> LocalIrrigationState:
        calls.append("realtime")
        return local_state()

    async def slow() -> LocalIrrigationState:
        calls.append("slow")
        return local_state()

    async def start(*_: Any) -> None:
        calls.append("start")
        start_writing.set()
        await release_start.wait()

    async def verify(*_: Any) -> bool:
        calls.append("verify")
        return True

    client.get_realtime_state.side_effect = realtime
    client.get_slow_state.side_effect = slow
    client.start_station.side_effect = start
    client.wait_for_station_active.side_effect = verify

    start_task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "start_station",
            {
                "device_id": _device_id(hass),
                "station_id": BACKYARD_STATION_ID,
                "duration_minutes": 1,
            },
            blocking=True,
            return_response=True,
        )
    )
    await asyncio.wait_for(start_writing.wait(), 1)
    reload_task = hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
    for _ in range(20):
        await asyncio.sleep(0)

    # The new entry's first polls must not interleave with the write in flight.
    assert calls[calls.index("start") + 1 :] == []
    assert not reload_task.done()

    release_start.set()
    response = await asyncio.wait_for(start_task, 5)
    assert await asyncio.wait_for(reload_task, 5)
    await hass.async_block_till_done()

    assert response is not None
    assert response["verified"] is True
    assert calls[calls.index("start") + 1] == "verify"
    assert "realtime" in calls[calls.index("verify") + 1 :]
    assert client.start_station.await_count == 1


async def test_action_queued_behind_unload_sends_nothing(
    hass: HomeAssistant, clients: dict[str, MagicMock]
) -> None:
    """A stop that arrives while unload waits for a start is refused, never sent later."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    client = clients[f"host-{BACKYARD_ID}"]
    start_writing = asyncio.Event()
    release_start = asyncio.Event()

    async def start(*_: Any) -> None:
        start_writing.set()
        await release_start.wait()

    client.start_station.side_effect = start
    device_id = _device_id(hass)

    start_task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "start_station",
            {"device_id": device_id, "station_id": BACKYARD_STATION_ID, "duration_minutes": 1},
            blocking=True,
        )
    )
    await asyncio.wait_for(start_writing.wait(), 1)
    unload_task = hass.async_create_task(hass.config_entries.async_unload(entry.entry_id))
    for _ in range(20):
        await asyncio.sleep(0)
    stop_task = hass.async_create_task(
        hass.services.async_call(DOMAIN, "stop_irrigation", {"device_id": device_id}, blocking=True)
    )
    for _ in range(20):
        await asyncio.sleep(0)

    release_start.set()
    await asyncio.wait_for(start_task, 5)
    assert await asyncio.wait_for(unload_task, 5)
    with pytest.raises(HomeAssistantError) as err:
        await asyncio.wait_for(stop_task, 5)

    assert err.value.translation_key == "entry_not_loaded"
    assert client.start_station.await_count == 1
    client.stop_irrigation.assert_not_awaited()
