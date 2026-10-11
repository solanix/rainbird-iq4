"""Tests for the Rain Bird IQ4 coordinator."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyrainbird.exceptions import (
    RainbirdApiException,
    RainbirdAuthException,
    RainbirdConnectionError,
)
from pyrainbird_iq4.cloud.models import ConnectionStatus, Controller, Station, StationRuntime
from pyrainbird_iq4.exceptions import (
    RainBirdIQ4AuthenticationError,
    RainBirdIQ4ConnectionError,
    RainBirdIQ4WAFChallengeError,
)
from pyrainbird_iq4.local import (
    LocalCurrentQueue,
    LocalIrrigationState,
    LocalQueueState,
)

from custom_components.rainbird_iq4.const import (
    CONF_CONTROLLER_ID,
    CONF_LOCAL_HOST,
    CONF_LOCAL_PASSWORD,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from custom_components.rainbird_iq4.coordinator import (
    IrrigationControlAmbiguousError,
    IrrigationControlError,
    RainBirdIQ4Coordinator,
    RainBirdIQ4Data,
    RainBirdIQ4LocalConnection,
    RainBirdIQ4LocalCoordinator,
    RainBirdIQ4LocalSlowCoordinator,
)


@pytest.fixture
def controller() -> Controller:
    return Controller(
        id=1001,
        name="Controller One",
        type=1,
        site_id=55,
        site_name="Site One",
        station_count=3,
        programs_used_count=2,
        mac_address="AA:AA",
        version="5.0",
        is_mqtt=True,
        latitude=0.0,
        longitude=0.0,
        rain_delay=12,
        simultaneous_stations=1,
        is_shutdown=False,
        satellite_enabled=True,
    )


async def test_coordinator_refresh(hass, controller):
    """Coordinator refresh gathers controller and program metadata."""
    entry = type(
        "Entry",
        (),
        {
            "data": {
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
                CONF_CONTROLLER_ID: controller.id,
            },
            "entry_id": "abc",
        },
    )()
    coordinator = RainBirdIQ4Coordinator(hass, entry)

    authenticate = AsyncMock(return_value="token")
    with (
        patch(
            "custom_components.rainbird_iq4.coordinator.authenticate",
            authenticate,
        ),
        patch("custom_components.rainbird_iq4.coordinator.RainBirdIQ4CloudClient") as mock_client,
    ):
        client = mock_client.return_value
        client.get_controllers = AsyncMock(return_value=[controller])
        client.get_connection_statuses = AsyncMock(
            return_value=[ConnectionStatus(controller.id, True, "2024-01-01T00:00:00Z")]
        )
        client.get_stations = AsyncMock(
            return_value=[
                Station(1, controller.id, "Front Lawn", 1),
                Station(2, controller.id, "Back Lawn", 2),
            ]
        )
        client.get_programs = AsyncMock(return_value=[])
        client.get_scheduled_start_times = AsyncMock(return_value=[])
        client.get_station_runtimes = AsyncMock(
            return_value=[StationRuntime(1, ()), StationRuntime(2, ())]
        )

        data = await coordinator._async_update_data()
        second_data = await coordinator._async_update_data()

    assert authenticate.await_count == 1
    mock_client.assert_called_once_with("token", session=coordinator._session)
    assert data.controller.id == controller.id
    assert second_data.controller.id == controller.id
    assert data.connected is True
    assert len(data.stations) == 2


def _configure_client(client: Any, controller: Controller) -> None:
    client.get_controllers = AsyncMock(return_value=[controller])
    client.get_connection_statuses = AsyncMock(
        return_value=[ConnectionStatus(controller.id, True, "2024-01-01T00:00:00Z")]
    )
    client.get_stations = AsyncMock(return_value=[Station(1, controller.id, "Front Lawn", 1)])
    client.get_programs = AsyncMock(return_value=[])
    client.get_scheduled_start_times = AsyncMock(return_value=[])
    client.get_station_runtimes = AsyncMock(return_value=[StationRuntime(1, ())])


def _local_state(*, active: tuple[int, ...] = ()) -> LocalIrrigationState:
    return LocalIrrigationState(
        irrigation_enabled=True,
        active_terminals=active,
        available_terminals=(1, 2, 3),
        rain_sensor_active=False,
        rain_delay_days=0,
        queue=LocalQueueState(
            current=LocalCurrentQueue(0, False, None, None, None, 0),
            zones=(),
        ),
    )


def _poll_interval_seconds(
    coordinator: RainBirdIQ4LocalCoordinator | RainBirdIQ4LocalSlowCoordinator,
) -> int:
    """Return the configured local interval with a non-optional test assertion."""
    interval = coordinator.update_interval
    assert interval is not None
    return int(interval.total_seconds())


async def test_expired_api_token_reauthenticates_once(hass, controller) -> None:
    """An API authentication response replaces the cached token once."""
    entry = type(
        "Entry",
        (),
        {
            "data": {
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
                CONF_CONTROLLER_ID: controller.id,
            },
            "entry_id": "abc",
        },
    )()
    coordinator = RainBirdIQ4Coordinator(hass, entry)
    authenticate = AsyncMock(side_effect=["old-token", "new-token"])
    expired_client = type("Client", (), {})()
    expired_client.get_controllers = AsyncMock(
        side_effect=RainBirdIQ4AuthenticationError("HTTP 401")
    )
    refreshed_client = type("Client", (), {})()
    _configure_client(refreshed_client, controller)

    with (
        patch(
            "custom_components.rainbird_iq4.coordinator.authenticate",
            authenticate,
        ),
        patch(
            "custom_components.rainbird_iq4.coordinator.RainBirdIQ4CloudClient",
            side_effect=[expired_client, refreshed_client],
        ) as client_class,
    ):
        data = await coordinator._async_update_data()
        second_data = await coordinator._async_update_data()

    assert data.controller.id == controller.id
    assert second_data.controller.id == controller.id
    assert authenticate.await_count == 2
    assert client_class.call_count == 2


async def test_transient_api_failure_keeps_cached_authentication(hass, controller) -> None:
    """A transport failure retries polling later without a new login."""
    entry = type(
        "Entry",
        (),
        {
            "data": {
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
                CONF_CONTROLLER_ID: controller.id,
            },
            "entry_id": "abc",
        },
    )()
    coordinator = RainBirdIQ4Coordinator(hass, entry)
    authenticate = AsyncMock(return_value="token")
    client = type("Client", (), {})()
    _configure_client(client, controller)
    client.get_controllers = AsyncMock(
        side_effect=[
            RainBirdIQ4ConnectionError("IQ4 connection failed: TimeoutError"),
            [controller],
        ]
    )

    with (
        patch(
            "custom_components.rainbird_iq4.coordinator.authenticate",
            authenticate,
        ),
        patch(
            "custom_components.rainbird_iq4.coordinator.RainBirdIQ4CloudClient",
            return_value=client,
        ) as client_class,
    ):
        with pytest.raises(UpdateFailed) as err:
            await coordinator._async_update_data()
        assert err.value.translation_key == "cloud_update_failed"
        assert err.value.translation_placeholders == {"error": "RainBirdIQ4ConnectionError"}
        data = await coordinator._async_update_data()

    assert data.controller.id == controller.id
    assert authenticate.await_count == 1
    assert client_class.call_count == 1


async def test_waf_challenge_enters_authentication_backoff(hass, controller) -> None:
    """A WAF challenge does not cause authentication on every refresh."""
    entry = type(
        "Entry",
        (),
        {
            "data": {
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
                CONF_CONTROLLER_ID: controller.id,
            },
            "entry_id": "abc",
        },
    )()
    coordinator = RainBirdIQ4Coordinator(hass, entry)
    authenticate = AsyncMock(
        side_effect=RainBirdIQ4WAFChallengeError("IQ4 login was blocked by an AWS WAF challenge")
    )

    with (
        patch(
            "custom_components.rainbird_iq4.coordinator.authenticate",
            authenticate,
        ),
        patch(
            "custom_components.rainbird_iq4.coordinator.monotonic",
            return_value=100.0,
        ),
    ):
        with pytest.raises(UpdateFailed) as first:
            await coordinator._async_update_data()
        with pytest.raises(UpdateFailed) as second:
            await coordinator._async_update_data()

    assert first.value.translation_key == "auth_unavailable"
    assert first.value.translation_placeholders == {
        "error": "RainBirdIQ4WAFChallengeError",
        "seconds": "300",
    }
    assert second.value.translation_key == "auth_backoff"

    assert authenticate.await_count == 1


async def test_local_failure_keeps_cloud_snapshot_available(hass, controller) -> None:
    """A local timeout does not discard freshly fetched cloud schedules."""
    entry = type(
        "Entry",
        (),
        {
            "data": {
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
                CONF_CONTROLLER_ID: controller.id,
            },
            "options": {
                CONF_LOCAL_HOST: "192.0.2.10",
                CONF_LOCAL_PASSWORD: "pin",
            },
            "entry_id": "abc",
        },
    )()
    cloud_coordinator = RainBirdIQ4Coordinator(hass, entry)
    local_coordinator = RainBirdIQ4LocalCoordinator(hass, entry)
    local_client = type(
        "Local",
        (),
        {"get_realtime_state": AsyncMock(side_effect=[_local_state(), TimeoutError])},
    )()

    with (
        patch(
            "custom_components.rainbird_iq4.coordinator.authenticate",
            AsyncMock(return_value="token"),
        ),
        patch("custom_components.rainbird_iq4.coordinator.RainBirdIQ4CloudClient") as cloud,
        patch(
            "custom_components.rainbird_iq4.coordinator.RainBirdIQ4LocalClient.connect",
            AsyncMock(return_value=local_client),
        ),
    ):
        _configure_client(cloud.return_value, controller)
        await cloud_coordinator.async_refresh()
        await local_coordinator.async_refresh()
        first_local = local_coordinator.data
        await local_coordinator.async_refresh()

    assert cloud_coordinator.data.controller.id == controller.id
    assert cloud_coordinator.data.stations[0].name == "Front Lawn"
    assert local_coordinator.data is first_local
    assert local_coordinator.last_update_success is False
    assert cloud_coordinator.last_update_success is True


async def test_cloud_failure_keeps_local_snapshot_available(hass, controller) -> None:
    """A cloud timeout marks metadata stale without erasing local realtime state."""
    entry = type(
        "Entry",
        (),
        {
            "data": {
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
                CONF_CONTROLLER_ID: controller.id,
            },
            "options": {
                CONF_LOCAL_HOST: "192.0.2.10",
                CONF_LOCAL_PASSWORD: "pin",
            },
            "entry_id": "abc",
        },
    )()
    cloud_coordinator = RainBirdIQ4Coordinator(hass, entry)
    local_coordinator = RainBirdIQ4LocalCoordinator(hass, entry)
    cloud = type("Client", (), {})()
    _configure_client(cloud, controller)
    cloud.get_controllers = AsyncMock(
        side_effect=[[controller], RainBirdIQ4ConnectionError("timeout")]
    )
    local = type("Local", (), {"get_realtime_state": AsyncMock(return_value=_local_state())})()
    authenticate = AsyncMock(return_value="token")

    with (
        patch(
            "custom_components.rainbird_iq4.coordinator.authenticate",
            authenticate,
        ),
        patch(
            "custom_components.rainbird_iq4.coordinator.RainBirdIQ4CloudClient",
            return_value=cloud,
        ),
        patch(
            "custom_components.rainbird_iq4.coordinator.RainBirdIQ4LocalClient.connect",
            AsyncMock(return_value=local),
        ),
    ):
        await cloud_coordinator.async_refresh()
        await local_coordinator.async_refresh()
        first_cloud = cloud_coordinator.data
        await cloud_coordinator.async_refresh()

    assert cloud_coordinator.data is first_cloud
    assert cloud_coordinator.last_update_success is False
    assert local_coordinator.data.state.value == "idle"
    assert local_coordinator.last_update_success is True
    assert authenticate.await_count == 1


async def test_local_polling_does_not_refresh_cloud_or_authenticate(hass, controller) -> None:
    """Repeated realtime polling is independent from cloud calls and login."""
    entry = type(
        "Entry",
        (),
        {
            "data": {
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
                CONF_CONTROLLER_ID: controller.id,
            },
            "options": {
                CONF_LOCAL_HOST: "192.0.2.10",
                CONF_LOCAL_PASSWORD: "pin",
            },
            "entry_id": "abc",
        },
    )()
    cloud_coordinator = RainBirdIQ4Coordinator(hass, entry)
    local_coordinator = RainBirdIQ4LocalCoordinator(hass, entry)
    authenticate = AsyncMock(return_value="token")
    local_client = type(
        "Local",
        (),
        {"get_realtime_state": AsyncMock(return_value=_local_state())},
    )()

    with (
        patch(
            "custom_components.rainbird_iq4.coordinator.authenticate",
            authenticate,
        ),
        patch("custom_components.rainbird_iq4.coordinator.RainBirdIQ4CloudClient") as cloud,
        patch(
            "custom_components.rainbird_iq4.coordinator.RainBirdIQ4LocalClient.connect",
            AsyncMock(return_value=local_client),
        ),
    ):
        _configure_client(cloud.return_value, controller)
        await cloud_coordinator._async_update_data()
        for _ in range(3):
            await local_coordinator._async_update_data()

    assert authenticate.await_count == 1
    assert cloud.return_value.get_controllers.await_count == 1
    assert local_client.get_realtime_state.await_count == 3
    assert cloud_coordinator.update_interval is not None
    assert local_coordinator.update_interval is not None
    assert cloud_coordinator.update_interval.total_seconds() == 300
    assert local_coordinator.update_interval.total_seconds() == 30


async def test_local_adaptive_polling_backoff_and_recovery(
    hass, controller, caplog: pytest.LogCaptureFixture
) -> None:
    """Local cadence follows idle, running, bounded backoff, and recovery."""
    entry = type(
        "Entry",
        (),
        {
            "data": {CONF_CONTROLLER_ID: controller.id},
            "options": {
                CONF_LOCAL_HOST: "controller.local",
                CONF_LOCAL_PASSWORD: "local-secret",
            },
            "entry_id": "abc",
        },
    )()
    coordinator = RainBirdIQ4LocalCoordinator(hass, entry)
    idle = _local_state()
    running = _local_state(active=(2,))
    initial_client = type(
        "Local",
        (),
        {
            "get_realtime_state": AsyncMock(
                side_effect=[
                    idle,
                    running,
                    RainbirdApiException("payload local-secret"),
                ]
            )
        },
    )()
    second_client = type(
        "Local",
        (),
        {
            "get_realtime_state": AsyncMock(
                side_effect=RainbirdConnectionError("reset local-secret")
            )
        },
    )()
    third_client = type(
        "Local",
        (),
        {"get_realtime_state": AsyncMock(side_effect=RainbirdApiException("decode local-secret"))},
    )()
    recovered_client = type(
        "Local",
        (),
        {"get_realtime_state": AsyncMock(return_value=idle)},
    )()
    connect = AsyncMock(side_effect=[initial_client, second_client, third_client, recovered_client])
    caplog.set_level(logging.DEBUG)

    with patch(
        "custom_components.rainbird_iq4.coordinator.RainBirdIQ4LocalClient.connect",
        connect,
    ):
        await coordinator.async_refresh()
        assert _poll_interval_seconds(coordinator) == 30
        assert coordinator.consecutive_failures == 0

        await coordinator.async_refresh()
        assert _poll_interval_seconds(coordinator) == 10
        assert coordinator.data is running

        await coordinator.async_refresh()
        assert _poll_interval_seconds(coordinator) == 30
        assert coordinator.consecutive_failures == 1
        assert coordinator.last_update_success is False
        assert coordinator.data is running
        assert connect.await_count == 1

        await coordinator.async_refresh()
        assert _poll_interval_seconds(coordinator) == 60
        assert coordinator.consecutive_failures == 2
        assert connect.await_count == 2

        await coordinator.async_refresh()
        assert _poll_interval_seconds(coordinator) == 120
        assert coordinator.consecutive_failures == 3
        assert connect.await_count == 3

        await coordinator.async_refresh()

    assert _poll_interval_seconds(coordinator) == 30
    assert coordinator.consecutive_failures == 0
    assert coordinator.last_update_success is True
    assert coordinator.data is idle
    assert connect.await_count == 4
    assert "poll succeeded" in caplog.text
    assert "poll failed" in caplog.text
    assert "session reset" in caplog.text
    assert "next retry" in caplog.text
    assert "local-secret" not in caplog.text


async def test_slow_partial_failure_preserves_values_and_realtime_state(hass, controller) -> None:
    """A slow field failure retains its value without affecting realtime data."""
    entry = type(
        "Entry",
        (),
        {
            "data": {CONF_CONTROLLER_ID: controller.id},
            "options": {
                CONF_LOCAL_HOST: "controller.local",
                CONF_LOCAL_PASSWORD: "local-secret",
            },
            "entry_id": "abc",
        },
    )()
    realtime_state = _local_state(active=(2,))
    slow_state = LocalIrrigationState(True, (), (1, 2, 3), False, 2)
    partial_slow_state = LocalIrrigationState(
        True,
        (),
        (1, 2, 3),
        False,
        None,
        failed_commands=frozenset({"rain_delay"}),
        transport_failure=True,
    )
    client = type(
        "Local",
        (),
        {
            "get_realtime_state": AsyncMock(return_value=realtime_state),
            "get_slow_state": AsyncMock(side_effect=[slow_state, partial_slow_state]),
        },
    )()
    connection = type(
        "Connection",
        (),
        {
            "async_get_realtime_state": AsyncMock(return_value=realtime_state),
            "async_get_slow_state": AsyncMock(side_effect=[slow_state, partial_slow_state]),
        },
    )()
    realtime = RainBirdIQ4LocalCoordinator(hass, entry, connection)
    slow = RainBirdIQ4LocalSlowCoordinator(hass, entry, connection)

    await realtime.async_refresh()
    await slow.async_refresh()
    await slow.async_refresh()

    assert realtime.data is realtime_state
    assert realtime.last_update_success is True
    assert slow.data.rain_delay_days == 2
    assert slow.data.failed_commands == frozenset({"rain_delay"})
    assert slow.last_update_success is True
    assert _poll_interval_seconds(realtime) == 10
    assert _poll_interval_seconds(slow) == 30
    assert connection.async_get_realtime_state.await_count == 1
    assert connection.async_get_slow_state.await_count == 2


async def test_slow_failure_retries_with_backoff_then_recovers(hass, controller) -> None:
    """A failed slow poll retries at 30/60/120 seconds, then returns to five minutes."""
    entry = type(
        "Entry",
        (),
        {
            "data": {CONF_CONTROLLER_ID: controller.id},
            "options": {CONF_LOCAL_HOST: "controller.local", CONF_LOCAL_PASSWORD: "pin"},
            "entry_id": "abc",
        },
    )()
    connection = type(
        "Connection",
        (),
        {
            "async_get_slow_state": AsyncMock(
                side_effect=[
                    RainbirdConnectionError(),
                    RainbirdConnectionError(),
                    RainbirdConnectionError(),
                    RainbirdConnectionError(),
                    LocalIrrigationState(True, (), (1, 2, 3), False, 0),
                ]
            ),
        },
    )()
    slow = RainBirdIQ4LocalSlowCoordinator(hass, entry, connection)

    intervals = []
    for _ in range(5):
        await slow.async_refresh()
        intervals.append(_poll_interval_seconds(slow))

    assert intervals == [30, 60, 120, 120, 300]
    assert slow.last_update_success is True


async def test_slow_partial_failure_retries_soon_then_relaxes(hass, controller) -> None:
    """A single failed slow command retries within 30 seconds; a clean poll restores 5 minutes."""
    entry = type(
        "Entry",
        (),
        {
            "data": {CONF_CONTROLLER_ID: controller.id},
            "options": {CONF_LOCAL_HOST: "controller.local", CONF_LOCAL_PASSWORD: "pin"},
            "entry_id": "abc",
        },
    )()
    partial = LocalIrrigationState(
        True, (), (1, 2, 3), False, None, failed_commands=frozenset({"rain_delay"})
    )
    connection = type(
        "Connection",
        (),
        {
            "async_get_slow_state": AsyncMock(
                side_effect=[partial, partial, LocalIrrigationState(True, (), (1, 2, 3), False, 0)]
            ),
        },
    )()
    slow = RainBirdIQ4LocalSlowCoordinator(hass, entry, connection)

    intervals = []
    for _ in range(3):
        await slow.async_refresh()
        intervals.append(_poll_interval_seconds(slow))

    assert intervals == [30, 60, 300]
    assert slow.data.rain_delay_days == 0


async def test_overlapping_local_coordinator_refreshes_are_serialized(hass, controller) -> None:
    """Only one complete local refresh may use the controller at a time."""
    entry = type(
        "Entry",
        (),
        {
            "data": {CONF_CONTROLLER_ID: controller.id},
            "options": {
                CONF_LOCAL_HOST: "controller.local",
                CONF_LOCAL_PASSWORD: "local-secret",
            },
            "entry_id": "abc",
        },
    )()
    coordinator = RainBirdIQ4LocalCoordinator(hass, entry)
    active_calls = 0
    maximum_active_calls = 0
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def get_realtime_state(_self: object) -> LocalIrrigationState:
        nonlocal active_calls, maximum_active_calls
        active_calls += 1
        maximum_active_calls = max(maximum_active_calls, active_calls)
        if not first_started.is_set():
            first_started.set()
            await release_first.wait()
        active_calls -= 1
        return _local_state()

    local_client = type("Local", (), {"get_realtime_state": get_realtime_state})()
    connect = AsyncMock(return_value=local_client)
    with patch(
        "custom_components.rainbird_iq4.coordinator.RainBirdIQ4LocalClient.connect",
        connect,
    ):
        first = asyncio.create_task(coordinator._async_update_data())
        await first_started.wait()
        second = asyncio.create_task(coordinator._async_update_data())
        await asyncio.sleep(0)
        assert maximum_active_calls == 1
        release_first.set()
        await asyncio.gather(first, second)

    assert maximum_active_calls == 1
    assert connect.await_count == 1


async def test_connection_reset_reconnects_once_on_next_poll(hass, controller) -> None:
    """A reset retains state and creates one fresh client on the next interval."""
    entry = type(
        "Entry",
        (),
        {
            "data": {CONF_CONTROLLER_ID: controller.id},
            "options": {
                CONF_LOCAL_HOST: "controller.local",
                CONF_LOCAL_PASSWORD: "local-secret",
            },
            "entry_id": "abc",
        },
    )()
    coordinator = RainBirdIQ4LocalCoordinator(hass, entry)
    first_state = _local_state()
    recovered_state = _local_state(active=(2,))
    first_client = type(
        "Local",
        (),
        {
            "get_realtime_state": AsyncMock(
                side_effect=[first_state, RainbirdConnectionError("connection reset")]
            )
        },
    )()
    recovered_client = type(
        "Local",
        (),
        {"get_realtime_state": AsyncMock(return_value=recovered_state)},
    )()
    connect = AsyncMock(side_effect=[first_client, recovered_client])

    with patch(
        "custom_components.rainbird_iq4.coordinator.RainBirdIQ4LocalClient.connect",
        connect,
    ):
        await coordinator.async_refresh()
        await coordinator.async_refresh()
        assert coordinator.data is first_state
        assert coordinator.last_update_success is False
        assert connect.await_count == 1
        await coordinator.async_refresh()

    assert coordinator.data is recovered_state
    assert coordinator.last_update_success is True
    assert connect.await_count == 2


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(
            RainbirdAuthException("rejected local-secret"),
            id="local-authentication-failure",
        ),
        pytest.param(
            RainbirdConnectionError("controller.local refused local-secret"),
            id="local-host-unavailable",
        ),
    ],
)
async def test_local_connection_failures_are_sanitized(
    hass, controller, failure: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    """Local failures expose only their type and never configuration secrets."""
    entry = type(
        "Entry",
        (),
        {
            "data": {
                CONF_USERNAME: "cloud-user",
                CONF_PASSWORD: "cloud-secret",
                CONF_CONTROLLER_ID: controller.id,
            },
            "options": {
                CONF_LOCAL_HOST: "controller.local",
                CONF_LOCAL_PASSWORD: "local-secret",
            },
            "entry_id": "abc",
        },
    )()
    coordinator = RainBirdIQ4LocalCoordinator(hass, entry)

    with (
        patch(
            "custom_components.rainbird_iq4.coordinator.RainBirdIQ4LocalClient.connect",
            AsyncMock(side_effect=failure),
        ),
        pytest.raises(UpdateFailed) as raised,
    ):
        await coordinator._async_update_data()

    output = f"{raised.value} {raised.value.translation_placeholders}\n{caplog.text}"
    assert type(failure).__name__ in output
    assert "local-secret" not in output
    assert "cloud-secret" not in output


def _control_cloud_data(controller: Controller, *, enabled: bool | None = True) -> RainBirdIQ4Data:
    """Build a minimal cloud catalog for internal control-boundary tests."""
    return RainBirdIQ4Data(
        controller=controller,
        connected=True,
        connection_status=None,
        stale=False,
        stations=[Station(30000001, controller.id, "Station 001", 1, enabled)],
        programs=[],
        scheduled_programs=[],
        runtime_assignments=[],
        effective_programs=[],
    )


def _control_entry(controller: Controller) -> Any:
    return type(
        "Entry",
        (),
        {
            "data": {CONF_CONTROLLER_ID: controller.id},
            "options": {CONF_LOCAL_HOST: "controller.local", CONF_LOCAL_PASSWORD: "pin"},
        },
    )()


def _control_client(
    *,
    realtime: LocalIrrigationState | Exception | None = None,
    slow: LocalIrrigationState | None = None,
    start: Exception | None = None,
    stop: Exception | None = None,
    active_verified: bool = True,
    idle_verified: bool = True,
) -> Any:
    """Build a local client double whose write methods record every attempt."""
    return type(
        "Client",
        (),
        {
            "get_realtime_state": AsyncMock(
                side_effect=realtime if isinstance(realtime, Exception) else None,
                return_value=realtime or _local_state(),
            ),
            "get_slow_state": AsyncMock(return_value=slow or _local_state()),
            "start_station": AsyncMock(side_effect=start),
            "stop_irrigation": AsyncMock(side_effect=stop),
            "wait_for_station_active": AsyncMock(return_value=active_verified),
            "wait_for_idle": AsyncMock(return_value=idle_verified),
        },
    )()


def _slow_state(**overrides: Any) -> LocalIrrigationState:
    values: dict[str, Any] = {
        "irrigation_enabled": True,
        "active_terminals": (),
        "available_terminals": (1, 2, 3),
        "rain_sensor_active": False,
        "rain_delay_days": 0,
    }
    values.update(overrides)
    return LocalIrrigationState(**values)


async def _start(
    connection: RainBirdIQ4LocalConnection,
    controller: Controller,
    *,
    station_id: int = 30000001,
    duration: Any = 1,
    enabled: bool | None = True,
    telemetry: LocalIrrigationState | None = None,
    updated_at: datetime | None = None,
) -> Any:
    return await connection.async_start_station(
        station_id,
        duration,
        _control_cloud_data(controller, enabled=enabled),
        telemetry or _local_state(),
        updated_at or datetime.now(UTC),
    )


async def test_safe_start_resolves_station_id_and_verifies_state(hass, controller) -> None:
    """A fresh idle start resolves stable cloud ID and verifies the active terminal."""
    connection = RainBirdIQ4LocalConnection(hass, _control_entry(controller))
    client = _control_client()
    connection._client = client

    result = await _start(connection, controller)

    client.get_slow_state.assert_awaited_once_with()
    client.start_station.assert_awaited_once_with(1, 1)
    client.wait_for_station_active.assert_awaited_once_with(1)
    assert result.acknowledged is True
    assert result.verified is True
    assert result.station_id == 30000001
    assert result.terminal == 1


@pytest.mark.parametrize(
    ("kwargs", "error_code"),
    [
        pytest.param({"duration": 0}, "invalid_duration", id="duration-zero"),
        pytest.param({"duration": 31}, "invalid_duration", id="duration-too-long"),
        pytest.param({"duration": True}, "invalid_duration", id="duration-bool"),
        pytest.param({"duration": 1.5}, "invalid_duration", id="duration-float"),
        pytest.param({"station_id": 99}, "station_not_found", id="cross-controller"),
        pytest.param({"enabled": False}, "station_not_enabled", id="disabled"),
        pytest.param({"enabled": None}, "station_not_enabled", id="enabled-unknown"),
        pytest.param({"telemetry": _local_state(active=(2,))}, "controller_not_idle", id="busy"),
        pytest.param(
            {"updated_at": datetime(2020, 1, 1, tzinfo=UTC)}, "telemetry_stale", id="stale"
        ),
        pytest.param(
            {
                "telemetry": _slow_state(
                    failed_commands=frozenset({"active_terminals"}),
                    queue=_local_state().queue,
                )
            },
            "telemetry_incomplete",
            id="incomplete",
        ),
    ],
)
async def test_safe_start_rejects_invalid_preconditions(
    hass, controller, kwargs: dict[str, Any], error_code: str
) -> None:
    """Unsafe starts fail before the controller is contacted."""
    connection = RainBirdIQ4LocalConnection(hass, _control_entry(controller))
    client = _control_client()
    connection._client = client

    with pytest.raises(IrrigationControlError, match=error_code):
        await _start(connection, controller, **kwargs)

    client.get_realtime_state.assert_not_awaited()
    client.start_station.assert_not_awaited()


@pytest.mark.parametrize(
    ("realtime", "slow", "error_code"),
    [
        pytest.param(
            _local_state(active=(3,)), None, "controller_not_idle", id="started-meanwhile"
        ),
        pytest.param(None, _slow_state(rain_sensor_active=True), "rain_sensor_active", id="rain"),
        pytest.param(None, _slow_state(rain_delay_days=2), "rain_delay_active", id="rain-delay"),
        pytest.param(
            None, _slow_state(rain_sensor_active=None), "rain_state_unknown", id="rain-unknown"
        ),
        pytest.param(
            None, _slow_state(rain_delay_days=None), "rain_state_unknown", id="delay-unknown"
        ),
        pytest.param(
            None, _slow_state(available_terminals=(2, 3)), "terminal_unavailable", id="terminal"
        ),
        pytest.param(
            None,
            _slow_state(available_terminals=None),
            "terminal_unavailable",
            id="terminal-unknown",
        ),
        pytest.param(
            None, _slow_state(irrigation_enabled=False), "irrigation_disabled", id="global-off"
        ),
    ],
)
async def test_safe_start_rejects_fresh_controller_state(
    hass,
    controller,
    realtime: LocalIrrigationState | None,
    slow: LocalIrrigationState | None,
    error_code: str,
) -> None:
    """The in-lock fresh reads block starts the coordinator snapshot could not see."""
    connection = RainBirdIQ4LocalConnection(hass, _control_entry(controller))
    client = _control_client(realtime=realtime, slow=slow)
    connection._client = client

    with pytest.raises(IrrigationControlError, match=error_code):
        await _start(connection, controller)

    client.start_station.assert_not_awaited()


async def test_safe_start_refresh_failure_sends_nothing(hass, controller) -> None:
    """A failed preflight read resets the client and never writes."""
    connection = RainBirdIQ4LocalConnection(hass, _control_entry(controller))
    client = _control_client(realtime=RainbirdConnectionError())
    connection._client = client

    with pytest.raises(IrrigationControlError, match="telemetry_refresh_failed"):
        await _start(connection, controller)

    client.start_station.assert_not_awaited()
    assert connection._client is None


async def test_safe_start_timeout_is_ambiguous_and_not_retried(hass, controller) -> None:
    """A write timeout resets the client and is never retried automatically."""
    connection = RainBirdIQ4LocalConnection(hass, _control_entry(controller))
    client = _control_client(start=TimeoutError())
    connection._client = client

    with pytest.raises(IrrigationControlAmbiguousError, match="write_outcome_ambiguous"):
        await _start(connection, controller)

    assert client.start_station.await_count == 1
    client.wait_for_station_active.assert_not_awaited()
    assert connection._client is None


async def test_safe_start_unconfirmed_is_not_repeated(hass, controller) -> None:
    """An acknowledged start without observed watering is reported, not retried."""
    connection = RainBirdIQ4LocalConnection(hass, _control_entry(controller))
    client = _control_client(active_verified=False)
    connection._client = client

    result = await _start(connection, controller)

    assert client.start_station.await_count == 1
    assert result.acknowledged is True
    assert result.verified is False


async def test_control_connect_failure_means_not_sent(hass, controller) -> None:
    """A failed local connection is a definite non-delivery, not an ambiguous write."""
    connection = RainBirdIQ4LocalConnection(hass, _control_entry(controller))

    with (
        patch(
            "custom_components.rainbird_iq4.coordinator.RainBirdIQ4LocalClient.connect",
            AsyncMock(side_effect=RainbirdConnectionError()),
        ),
        pytest.raises(IrrigationControlError, match="controller_unreachable") as err,
    ):
        await connection.async_stop_irrigation()

    assert not isinstance(err.value, IrrigationControlAmbiguousError)


async def test_stop_running_verifies_idle_without_cloud(hass, controller) -> None:
    """Stop needs no cloud data and verifies the resulting idle state."""
    connection = RainBirdIQ4LocalConnection(hass, _control_entry(controller))
    client = _control_client(realtime=_local_state(active=(1,)))
    connection._client = client

    result = await connection.async_stop_irrigation()

    client.stop_irrigation.assert_awaited_once_with()
    client.wait_for_idle.assert_awaited_once_with()
    assert result.no_op is False
    assert result.acknowledged is True
    assert result.verified is True


async def test_stop_verified_idle_is_safe_no_op(hass, controller) -> None:
    """A complete idle snapshot means stop sends nothing."""
    connection = RainBirdIQ4LocalConnection(hass, _control_entry(controller))
    client = _control_client()
    connection._client = client

    result = await connection.async_stop_irrigation()

    client.stop_irrigation.assert_not_awaited()
    assert result.no_op is True
    assert result.acknowledged is False
    assert result.verified is True


async def test_stop_sends_when_state_is_unknown(hass, controller) -> None:
    """A failed pre-stop read cannot prove idle, so stop is still sent once."""
    connection = RainBirdIQ4LocalConnection(hass, _control_entry(controller))
    client = _control_client(realtime=RainbirdConnectionError())
    connection._client = client

    with patch(
        "custom_components.rainbird_iq4.coordinator.RainBirdIQ4LocalClient.connect",
        AsyncMock(return_value=client),
    ):
        result = await connection.async_stop_irrigation()

    client.stop_irrigation.assert_awaited_once_with()
    assert result.acknowledged is True


async def test_stop_timeout_is_ambiguous_and_not_retried(hass, controller) -> None:
    """A stop write timeout is reported as ambiguous after exactly one attempt."""
    connection = RainBirdIQ4LocalConnection(hass, _control_entry(controller))
    client = _control_client(realtime=_local_state(active=(1,)), stop=TimeoutError())
    connection._client = client

    with pytest.raises(IrrigationControlAmbiguousError, match="write_outcome_ambiguous"):
        await connection.async_stop_irrigation()

    assert client.stop_irrigation.await_count == 1
    client.wait_for_idle.assert_not_awaited()


async def test_stop_unconfirmed_is_not_repeated(hass, controller) -> None:
    """An acknowledged stop without observed idle is reported, not retried."""
    connection = RainBirdIQ4LocalConnection(hass, _control_entry(controller))
    client = _control_client(realtime=_local_state(active=(1,)), idle_verified=False)
    connection._client = client

    result = await connection.async_stop_irrigation()

    assert client.stop_irrigation.await_count == 1
    assert result.acknowledged is True
    assert result.verified is False
