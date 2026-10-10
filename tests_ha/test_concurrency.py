"""Tests that control actions and local polling share one serialized connection."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
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
