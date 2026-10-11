"""Coordinator for the Rain Bird IQ4 integration."""

from __future__ import annotations

import asyncio
import logging
from asyncio import gather
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
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
)

from . import saved_data
from .connection import RainBirdIQ4LocalConnection
from .const import (
    CLOUD_UPDATE_INTERVAL,
    CONF_CONTROLLER_ID,
    CONF_LOCAL_HOST,
    CONF_LOCAL_PASSWORD,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    LOCAL_FAILURE_BACKOFF_INTERVALS,
    LOCAL_IDLE_UPDATE_INTERVAL,
    LOCAL_RUNNING_UPDATE_INTERVAL,
    LOCAL_SLOW_UPDATE_INTERVAL,
)
from .models import RainBirdIQ4Data, build_effective_programs, is_stale

_LOGGER = logging.getLogger(__name__)


AUTH_BACKOFF_INITIAL_SECONDS = 5 * 60
AUTH_BACKOFF_MAX_SECONDS = 60 * 60


class RainBirdIQ4CloudCoordinator(DataUpdateCoordinator[RainBirdIQ4Data]):
    """Coordinate refreshes for the selected controller."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.controller_id = entry.data[CONF_CONTROLLER_ID]
        self._client: RainBirdIQ4CloudClient | None = None
        self._session = async_get_clientsession(hass)
        self._auth_retry_at: float = 0.0
        self._auth_failure_count: int = 0
        self._store: Store[dict[str, Any]] = Store(
            hass, saved_data.STORAGE_VERSION, saved_data.storage_key(entry.entry_id)
        )
        self._saved: dict[str, Any] | None = None
        self.saved_data_since: str | None = None
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.controller_id}",
            update_interval=CLOUD_UPDATE_INTERVAL,
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
                translation_domain=DOMAIN,
                translation_key="auth_backoff",
                translation_placeholders={"seconds": str(int(remaining))},
            )

        try:
            token = await authenticate(
                self.entry.data[CONF_USERNAME],
                self.entry.data[CONF_PASSWORD],
            )
        except RainBirdIQ4CredentialsError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except (
            RainBirdIQ4WAFChallengeError,
            RainBirdIQ4AuthenticationError,
            RainBirdIQ4ConnectionError,
        ) as err:
            delay = self._record_auth_backoff()
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="auth_unavailable",
                translation_placeholders={"error": type(err).__name__, "seconds": str(delay)},
            ) from err

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
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="controller_missing",
                translation_placeholders={"controller_id": str(self.controller_id)},
            )

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
            stale=is_stale(connection_status),
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
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="token_rejected") from err

    async def _async_update_data(self) -> RainBirdIQ4Data:
        """Refresh cloud configuration without touching local realtime state."""
        try:
            data = await self._async_fetch_cloud()
        except RainBirdIQ4Error as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cloud_update_failed",
                translation_placeholders={"error": type(err).__name__},
            ) from err
        self.saved_data_since = None
        await self._async_save(data)
        return data

    async def _async_save(self, data: RainBirdIQ4Data) -> None:
        """Persist the snapshot when it changed; a failed write never fails the refresh."""
        serialized = saved_data.serialize(data)
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
            data = saved_data.deserialize(stored["data"])
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Ignoring unreadable IQ4 cloud snapshot: %s", type(err).__name__)
            return False
        self.data = data
        self.saved_data_since = stored["saved_at"]
        self._saved = stored["data"]
        _LOGGER.warning(
            "IQ4 cloud unavailable for controller %s; using station data saved at %s. "
            "Starts are blocked until the cloud recovers; stop remains available",
            self.controller_id,
            self.saved_data_since,
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
        except Exception as err:
            interval = self._record_local_failure()
            _LOGGER.debug(
                "Local IQ4 poll failed for controller %s: %s; session reset; "
                "next retry in %s seconds",
                self.controller_id,
                type(err).__name__,
                int(interval.total_seconds()),
            )
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="local_update_failed",
                translation_placeholders={"error": type(err).__name__},
            ) from err
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
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="local_slow_update_failed",
                translation_placeholders={"error": type(err).__name__},
            ) from err
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
