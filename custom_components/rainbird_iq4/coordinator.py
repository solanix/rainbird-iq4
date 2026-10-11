"""Coordinator for the Rain Bird IQ4 integration."""

from __future__ import annotations

import asyncio
import logging
from asyncio import gather
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyrainbird.exceptions import (  # type: ignore[import-untyped]
    RainbirdApiException,
    RainbirdConnectionError,
)
from pyrainbird_iq4.cloud.auth import authenticate
from pyrainbird_iq4.cloud.client import RainBirdIQ4CloudClient
from pyrainbird_iq4.exceptions import (
    RainBirdIQ4AuthenticationError,
    RainBirdIQ4ConnectionError,
    RainBirdIQ4CredentialsError,
    RainBirdIQ4Error,
    RainBirdIQ4WAFChallengeError,
)
from pyrainbird_iq4.local import (
    LocalIrrigationState,
    LocalRunState,
    RainBirdIQ4LocalClient,
)

from . import cache
from .const import (
    CONF_CONTROLLER_ID,
    CONF_LOCAL_HOST,
    CONF_LOCAL_PASSWORD,
    CONF_PASSWORD,
    CONF_USERNAME,
    DISCOVERY_STALE_SECONDS,
    DOMAIN,
    LOCAL_FAILURE_BACKOFF_INTERVALS,
    LOCAL_IDLE_UPDATE_INTERVAL,
    LOCAL_RUNNING_UPDATE_INTERVAL,
    LOCAL_SLOW_UPDATE_INTERVAL,
    UPDATE_INTERVAL,
)
from .models import RainBirdIQ4Data

_LOGGER = logging.getLogger(__name__)


def _observed_scheduled_program_number(name: str) -> int | None:
    """Map only scheduled program labels confirmed by local protocol evidence."""
    normalized = name.strip().casefold()
    return {"a": 1, "program a": 1, "b": 2, "program b": 2}.get(normalized)


def _is_stale(connection_status: Any | None, *, now: datetime | None = None) -> bool:
    """Return whether a controller is stale based on the connection timestamp."""
    if connection_status is None:
        return True
    if not connection_status.timestamp:
        return True
    try:
        timestamp = datetime.fromisoformat(connection_status.timestamp.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return ((now or datetime.now(UTC)) - timestamp).total_seconds() > DISCOVERY_STALE_SECONDS


def build_effective_programs(
    programs: Iterable[Any],
    scheduled_programs: Iterable[Any],
) -> list[dict[str, Any]]:
    """Build effective programs while respecting MQTT-derived schedules."""
    direct = list(programs)
    if direct:
        return [
            {
                "source": "direct",
                "id": program.id,
                "name": program.name,
                "short_name": program.short_name,
                "protocol_program_number": program.number,
            }
            for program in direct
        ]

    effective: list[dict[str, Any]] = []
    for item in scheduled_programs:
        if getattr(item, "program_name", None):
            effective.append(
                {
                    "source": "scheduled",
                    "id": item.program_id,
                    "name": item.program_name,
                    "protocol_program_number": _observed_scheduled_program_number(
                        item.program_name
                    ),
                    "scheduled_times": [
                        {
                            "time_of_day": start.time_of_day.isoformat(),
                            "start_time_index": start.start_time_index,
                        }
                        for start in item.scheduled_times
                    ],
                }
            )
    return effective


AUTH_BACKOFF_INITIAL_SECONDS = 5 * 60
AUTH_BACKOFF_MAX_SECONDS = 60 * 60


class RainBirdIQ4Coordinator(DataUpdateCoordinator[RainBirdIQ4Data]):
    """Coordinate refreshes for the selected controller."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.controller_id = entry.data[CONF_CONTROLLER_ID]
        self._client: RainBirdIQ4CloudClient | None = None
        self._session = async_get_clientsession(hass)
        self._auth_retry_at: float = 0.0
        self._auth_failure_count: int = 0
        self._store: Store[dict[str, Any]] = Store(
            hass, cache.STORAGE_VERSION, cache.storage_key(entry.entry_id)
        )
        self._saved: dict[str, Any] | None = None
        self.cached_since: str | None = None
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.controller_id}",
            update_interval=UPDATE_INTERVAL,
        )

    def _record_auth_backoff(self) -> int:
        """Record an authentication transport failure and return its delay."""
        delay: int = min(
            AUTH_BACKOFF_INITIAL_SECONDS * 2**self._auth_failure_count,
            AUTH_BACKOFF_MAX_SECONDS,
        )
        self._auth_failure_count += 1
        self._auth_retry_at = monotonic() + delay
        return delay

    async def _async_get_client(self) -> RainBirdIQ4CloudClient:
        """Return the cached API client, authenticating only when required."""
        if self._client is not None:
            return self._client

        if (remaining := self._auth_retry_at - monotonic()) > 0:
            raise UpdateFailed(
                "IQ4 authentication is temporarily backed off; "
                f"retry available in {int(remaining)} seconds"
            )

        try:
            token = await authenticate(
                self.entry.data[CONF_USERNAME],
                self.entry.data[CONF_PASSWORD],
            )
        except RainBirdIQ4CredentialsError as err:
            raise ConfigEntryAuthFailed from err
        except (
            RainBirdIQ4WAFChallengeError,
            RainBirdIQ4AuthenticationError,
            RainBirdIQ4ConnectionError,
        ) as err:
            delay = self._record_auth_backoff()
            raise UpdateFailed(f"{err}; authentication retry delayed by {delay} seconds") from err

        self._auth_failure_count = 0
        self._auth_retry_at = 0.0
        self._client = RainBirdIQ4CloudClient(token, session=self._session)
        return self._client

    async def _async_fetch_data(self, client: RainBirdIQ4CloudClient) -> RainBirdIQ4Data:
        """Fetch one complete controller snapshot with an authenticated client."""
        controllers = await client.get_controllers()
        controller = next(
            (item for item in controllers if item.id == self.controller_id),
            None,
        )
        if controller is None:
            raise UpdateFailed(f"Controller {self.controller_id} is no longer available")

        connection_statuses = await client.get_connection_statuses([self.controller_id])
        connection_status = connection_statuses[0] if connection_statuses else None
        stations, programs, scheduled_programs, station_runtimes = await gather(
            client.get_stations(self.controller_id),
            client.get_programs(self.controller_id),
            client.get_scheduled_start_times(self.controller_id),
            client.get_station_runtimes(self.controller_id),
        )

        return RainBirdIQ4Data(
            controller=controller,
            connected=bool(connection_status and connection_status.is_connected),
            connection_status=connection_status,
            stale=_is_stale(connection_status),
            stations=stations,
            programs=programs,
            scheduled_programs=scheduled_programs,
            runtime_assignments=station_runtimes,
            effective_programs=build_effective_programs(programs, scheduled_programs),
        )

    @property
    def local_configured(self) -> bool:
        """Return whether both optional local connection fields are configured."""
        options = getattr(self.entry, "options", {})
        return bool(options.get(CONF_LOCAL_HOST) and options.get(CONF_LOCAL_PASSWORD))

    async def _async_fetch_cloud(self) -> RainBirdIQ4Data:
        """Fetch cloud data, refreshing authentication once after an API 401."""
        client = await self._async_get_client()
        try:
            return await self._async_fetch_data(client)
        except RainBirdIQ4AuthenticationError:
            self._client = None

        client = await self._async_get_client()
        try:
            return await self._async_fetch_data(client)
        except RainBirdIQ4AuthenticationError as err:
            self._client = None
            raise UpdateFailed("IQ4 API rejected a newly refreshed access token") from err

    async def _async_update_data(self) -> RainBirdIQ4Data:
        """Refresh cloud configuration without touching local realtime state."""
        try:
            data = await self._async_fetch_cloud()
        except (RainBirdIQ4ConnectionError, RainBirdIQ4Error, UpdateFailed) as err:
            raise UpdateFailed(str(err)) from err
        self.cached_since = None
        await self._async_save(data)
        return data

    async def _async_save(self, data: RainBirdIQ4Data) -> None:
        """Persist the snapshot when it changed; a failed write never fails the refresh."""
        serialized = cache.serialize(data)
        if serialized == self._saved:
            return
        try:
            await self._store.async_save(
                {"saved_at": datetime.now(UTC).isoformat(), "data": serialized}
            )
        except OSError as err:
            _LOGGER.warning("Could not save IQ4 cloud snapshot: %s", err)
            return
        self._saved = serialized

    async def async_use_saved_data(self) -> bool:
        """Load the last saved snapshot after a failed first refresh.

        Cloud entities stay unavailable and starts stay blocked because
        last_update_success remains false; local entities and stop can work.
        """
        stored = await self._store.async_load()
        if stored is None:
            return False
        try:
            data = cache.deserialize(stored["data"])
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Ignoring unreadable IQ4 cloud snapshot: %s", type(err).__name__)
            return False
        self.data = data
        self.cached_since = stored["saved_at"]
        self._saved = stored["data"]
        _LOGGER.warning(
            "IQ4 cloud unavailable for controller %s; using station data saved at %s. "
            "Starts are blocked until the cloud recovers; stop remains available",
            self.controller_id,
            self.cached_since,
        )
        return True


class RainBirdIQ4LocalCoordinator(DataUpdateCoordinator[LocalIrrigationState]):
    """Poll local realtime state independently from IQ4 cloud data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        connection: RainBirdIQ4LocalConnection | None = None,
    ) -> None:
        self.entry = entry
        self.controller_id = entry.data[CONF_CONTROLLER_ID]
        self._session = async_get_clientsession(hass)
        self._connection = connection or RainBirdIQ4LocalConnection(hass, entry)
        self._refresh_lock = asyncio.Lock()
        self.consecutive_failures = 0
        self.last_successful_update: datetime | None = None
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.controller_id}_local",
            update_interval=LOCAL_IDLE_UPDATE_INTERVAL,
        )

    @property
    def connection(self) -> RainBirdIQ4LocalConnection:
        """Return the serialized local connection shared with control actions."""
        return self._connection

    async def _async_update_data(self) -> LocalIrrigationState:
        """Fetch one local snapshot without invoking any cloud operation."""
        async with self._refresh_lock:
            return await self._async_fetch_local()

    async def _async_fetch_local(self) -> LocalIrrigationState:
        """Fetch a partial realtime snapshot without touching slow local data."""
        try:
            state = await self._connection.async_get_realtime_state()
        except (RainbirdApiException, RainbirdConnectionError) as err:
            interval = self._record_local_failure()
            _LOGGER.debug(
                "Local IQ4 poll failed for controller %s: %s",
                self.controller_id,
                type(err).__name__,
            )
            _LOGGER.debug("Local IQ4 session reset for controller %s", self.controller_id)
            _LOGGER.debug(
                "Local IQ4 next retry for controller %s in %s seconds",
                self.controller_id,
                int(interval.total_seconds()),
            )
            raise UpdateFailed(f"Local IQ4 realtime update failed: {type(err).__name__}") from err
        except Exception as err:
            interval = self._record_local_failure()
            _LOGGER.debug(
                "Local IQ4 poll failed for controller %s: %s",
                self.controller_id,
                type(err).__name__,
            )
            _LOGGER.debug("Local IQ4 session reset for controller %s", self.controller_id)
            _LOGGER.debug(
                "Local IQ4 next retry for controller %s in %s seconds",
                self.controller_id,
                int(interval.total_seconds()),
            )
            raise UpdateFailed(f"Local IQ4 realtime update failed: {type(err).__name__}") from err
        if state.transport_failure:
            interval = self._record_local_failure()
            _LOGGER.debug(
                "Local IQ4 realtime poll partial for controller %s; session reset; "
                "next retry in %s seconds",
                self.controller_id,
                int(interval.total_seconds()),
            )
        else:
            self.consecutive_failures = 0
            interval = (
                LOCAL_RUNNING_UPDATE_INTERVAL
                if state.state is LocalRunState.RUNNING
                else LOCAL_IDLE_UPDATE_INTERVAL
            )
            self.update_interval = interval
            _LOGGER.debug(
                "Local IQ4 poll succeeded for controller %s; next poll in %s seconds",
                self.controller_id,
                int(interval.total_seconds()),
            )
        self.last_successful_update = datetime.now(UTC)
        return state

    def _record_local_failure(self) -> timedelta:
        """Advance bounded local backoff and update the polling interval."""
        self.consecutive_failures += 1
        index = min(
            self.consecutive_failures - 1,
            len(LOCAL_FAILURE_BACKOFF_INTERVALS) - 1,
        )
        interval = LOCAL_FAILURE_BACKOFF_INTERVALS[index]
        self.update_interval = interval
        return interval


class IrrigationControlError(Exception):
    """A safe local irrigation control precondition failed."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class IrrigationControlAmbiguousError(IrrigationControlError):
    """A write may have reached the controller but could not be confirmed."""


@dataclass(frozen=True, slots=True)
class IrrigationControlResult:
    """Separate protocol acknowledgement from observed post-write state."""

    action: str
    acknowledged: bool
    verified: bool
    station_id: int | None = None
    terminal: int | None = None
    no_op: bool = False


def _check_realtime_idle(state: LocalIrrigationState) -> None:
    """Reject a start unless complete realtime data proves the controller idle."""
    if state.failed_commands & {"active_terminals", "current_queue_page_0"}:
        raise IrrigationControlError("telemetry_incomplete")
    if not state.confirms_idle:
        raise IrrigationControlError("controller_not_idle")


def _check_start_safety(state: LocalIrrigationState, terminal: int) -> None:
    """Reject a start unless fresh slow data proves it is permitted; unknown blocks."""
    if state.irrigation_enabled is not True:
        raise IrrigationControlError("irrigation_disabled")
    if state.available_terminals is None or terminal not in state.available_terminals:
        raise IrrigationControlError("terminal_unavailable")
    if state.rain_sensor_active is None or state.rain_delay_days is None:
        raise IrrigationControlError("rain_state_unknown")
    if state.rain_sensor_active:
        raise IrrigationControlError("rain_sensor_active")
    if state.rain_delay_days != 0:
        raise IrrigationControlError("rain_delay_active")


class RainBirdIQ4LocalConnection:
    """Share one serialized local client across realtime and slow polling."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry
        self._session = async_get_clientsession(hass)
        self._client: RainBirdIQ4LocalClient | None = None
        self._lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()

    async def async_get_client(self) -> RainBirdIQ4LocalClient:
        """Return the shared client, connecting once when needed."""
        async with self._lock:
            if self._client is None:
                self._client = await RainBirdIQ4LocalClient.connect(
                    self._session,
                    self._entry.options[CONF_LOCAL_HOST],
                    self._entry.options[CONF_LOCAL_PASSWORD],
                    controller_id=self._entry.data[CONF_CONTROLLER_ID],
                )
            return self._client

    async def async_reset(self, client: RainBirdIQ4LocalClient | None = None) -> None:
        """Discard a failed client without closing HA's shared HTTP session."""
        async with self._lock:
            if client is None or self._client is client:
                if self._client is not None:
                    _LOGGER.debug(
                        "Local IQ4 client controller=%s status=discarded",
                        self._entry.data[CONF_CONTROLLER_ID],
                    )
                self._client = None

    async def async_get_realtime_state(self) -> LocalIrrigationState:
        """Run one realtime snapshot exclusively and reset failed transports."""
        async with self._operation_lock:
            client = await self.async_get_client()
            try:
                state = await client.get_realtime_state()
            except Exception:
                await self.async_reset(client)
                raise
            if state.transport_failure:
                await self.async_reset(client)
            return state

    async def _async_get_control_client(self) -> RainBirdIQ4LocalClient:
        """Connect for a control operation; failure here means nothing was sent."""
        try:
            return await self.async_get_client()
        except Exception as err:
            raise IrrigationControlError("controller_unreachable") from err

    async def async_start_station(
        self,
        station_id: int,
        duration_minutes: int,
        cloud_data: RainBirdIQ4Data | None,
        telemetry: LocalIrrigationState | None,
        telemetry_updated_at: datetime | None,
    ) -> IrrigationControlResult:
        """Start an enabled station only from fresh, confirmed-idle telemetry."""
        if (
            not isinstance(duration_minutes, int)
            or isinstance(duration_minutes, bool)
            or not 1 <= duration_minutes <= 30
        ):
            raise IrrigationControlError("invalid_duration")
        if cloud_data is None:
            raise IrrigationControlError("cloud_data_unavailable")
        station = next((item for item in cloud_data.stations if item.id == station_id), None)
        if station is None:
            raise IrrigationControlError("station_not_found")
        if station.is_enabled is not True:
            raise IrrigationControlError("station_not_enabled")
        if telemetry is None or telemetry_updated_at is None:
            raise IrrigationControlError("telemetry_unavailable")
        if datetime.now(UTC) - telemetry_updated_at > timedelta(seconds=60):
            raise IrrigationControlError("telemetry_stale")
        _check_realtime_idle(telemetry)
        async with self._operation_lock:
            client = await self._async_get_control_client()
            try:
                current = await client.get_realtime_state()
                safety = await client.get_slow_state()
            except Exception as err:
                await self.async_reset(client)
                raise IrrigationControlError("telemetry_refresh_failed") from err
            _check_realtime_idle(current)
            _check_start_safety(safety, station.terminal)
            try:
                await client.start_station(station.terminal, duration_minutes)
            except Exception as err:
                await self.async_reset(client)
                _LOGGER.warning(
                    "IQ4 local control controller=%s action=start_station station_id=%s "
                    "terminal=%s status=ambiguous exception=%s",
                    self._entry.data[CONF_CONTROLLER_ID],
                    station.id,
                    station.terminal,
                    type(err).__name__,
                )
                raise IrrigationControlAmbiguousError("write_outcome_ambiguous") from err
            try:
                verified = await client.wait_for_station_active(station.terminal)
            except Exception as err:
                await self.async_reset(client)
                _LOGGER.debug(
                    "IQ4 local control controller=%s action=start_station "
                    "status=acknowledged verification=failed exception=%s",
                    self._entry.data[CONF_CONTROLLER_ID],
                    type(err).__name__,
                )
                verified = False

        return IrrigationControlResult(
            action="start_station",
            acknowledged=True,
            verified=verified,
            station_id=station.id,
            terminal=station.terminal,
        )

    async def async_stop_irrigation(self) -> IrrigationControlResult:
        """Stop once without requiring cloud data or fresh coordinator telemetry."""
        async with self._operation_lock:
            client = await self._async_get_control_client()
            try:
                current: LocalIrrigationState | None = await client.get_realtime_state()
            except Exception:
                await self.async_reset(client)
                client = await self._async_get_control_client()
                current = None
            if current is not None and current.confirms_idle:
                return IrrigationControlResult(
                    "stop_irrigation", acknowledged=False, verified=True, no_op=True
                )
            try:
                await client.stop_irrigation()
            except Exception as err:
                await self.async_reset(client)
                _LOGGER.warning(
                    "IQ4 local control controller=%s action=stop_irrigation "
                    "status=ambiguous exception=%s",
                    self._entry.data[CONF_CONTROLLER_ID],
                    type(err).__name__,
                )
                raise IrrigationControlAmbiguousError("write_outcome_ambiguous") from err
            try:
                verified = await client.wait_for_idle()
            except Exception as err:
                await self.async_reset(client)
                _LOGGER.debug(
                    "IQ4 local control controller=%s action=stop_irrigation "
                    "status=acknowledged verification=failed exception=%s",
                    self._entry.data[CONF_CONTROLLER_ID],
                    type(err).__name__,
                )
                verified = False
        return IrrigationControlResult(
            "stop_irrigation",
            acknowledged=True,
            verified=verified,
        )

    async def async_get_slow_state(self) -> LocalIrrigationState:
        """Run one slow snapshot exclusively and reset failed transports."""
        async with self._operation_lock:
            client = await self.async_get_client()
            try:
                state = await client.get_slow_state()
            except Exception:
                await self.async_reset(client)
                raise
            if state.transport_failure:
                await self.async_reset(client)
            return state


class RainBirdIQ4LocalSlowCoordinator(DataUpdateCoordinator[LocalIrrigationState]):
    """Poll low-frequency local configuration and rain values independently."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        connection: RainBirdIQ4LocalConnection,
    ) -> None:
        self.entry = entry
        self.controller_id = entry.data[CONF_CONTROLLER_ID]
        self._connection = connection
        self.last_successful_update: datetime | None = None
        self.consecutive_failures = 0
        self._retries = 0
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.controller_id}_local_slow",
            update_interval=LOCAL_SLOW_UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> LocalIrrigationState:
        """Fetch slow fields, retaining prior values for failed commands."""
        try:
            state = await self._connection.async_get_slow_state()
        except Exception as err:
            self.consecutive_failures += 1
            self._schedule_retry()
            raise UpdateFailed(f"Local IQ4 slow update failed: {type(err).__name__}") from err
        # A failed command makes its entity unavailable, so retry it soon too.
        if state.failed_commands:
            self._schedule_retry()
        else:
            self._retries = 0
            self.update_interval = LOCAL_SLOW_UPDATE_INTERVAL
        previous = getattr(self, "data", None)
        if previous is not None:
            state = LocalIrrigationState(
                irrigation_enabled=(
                    previous.irrigation_enabled
                    if "irrigation_enabled" in state.failed_commands
                    else state.irrigation_enabled
                ),
                active_terminals=(),
                available_terminals=(
                    previous.available_terminals
                    if "available_terminals" in state.failed_commands
                    else state.available_terminals
                ),
                rain_sensor_active=(
                    previous.rain_sensor_active
                    if "rain_sensor" in state.failed_commands
                    else state.rain_sensor_active
                ),
                rain_delay_days=(
                    previous.rain_delay_days
                    if "rain_delay" in state.failed_commands
                    else state.rain_delay_days
                ),
                failed_commands=state.failed_commands,
                transport_failure=state.transport_failure,
            )
        self.consecutive_failures = len(state.failed_commands)
        self.last_successful_update = datetime.now(UTC)
        return state

    def _schedule_retry(self) -> None:
        """Retry sooner than the slow interval after any failure, with bounded backoff."""
        self._retries += 1
        self.update_interval = LOCAL_FAILURE_BACKOFF_INTERVALS[
            min(self._retries, len(LOCAL_FAILURE_BACKOFF_INTERVALS)) - 1
        ]
