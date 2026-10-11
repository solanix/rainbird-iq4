"""Serialized local controller access and the irrigation control safety boundary.

Every local read and write for one controller goes through one RainBirdIQ4LocalConnection,
so polling can never interleave with a start or stop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pyrainbird_iq4.local import (
    LocalIrrigationState,
    RainBirdIQ4LocalClient,
)

from .const import (
    CONF_CONTROLLER_ID,
    CONF_LOCAL_HOST,
    CONF_LOCAL_PASSWORD,
    LOCAL_TRANSIENT_RETRY_DELAY,
)
from .models import RainBirdIQ4Data

_LOGGER = logging.getLogger(__name__)


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
        """Run one realtime snapshot exclusively, retrying a transient failure once."""
        async with self._operation_lock:
            return await self._async_read_snapshot(lambda client: client.get_realtime_state())

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
        """Run one slow snapshot exclusively, retrying a transient failure once."""
        async with self._operation_lock:
            return await self._async_read_snapshot(lambda client: client.get_slow_state())

    async def _async_read_snapshot(
        self, read: Callable[[RainBirdIQ4LocalClient], Awaitable[LocalIrrigationState]]
    ) -> LocalIrrigationState:
        """Read once more on the same client before treating a transport failure as real.

        Failures are isolated (another client briefly holds the controller), so a short
        retry usually succeeds; the client is reset only when the retry fails too.
        """
        client = await self.async_get_client()
        try:
            state = await read(client)
        except Exception as err:
            failure = type(err).__name__
        else:
            if not state.transport_failure:
                return state
            failure = "partial"
        _LOGGER.debug(
            "Local IQ4 transient failure for controller %s (%s); retrying in %s seconds",
            self._entry.data[CONF_CONTROLLER_ID],
            failure,
            int(LOCAL_TRANSIENT_RETRY_DELAY.total_seconds()),
        )
        await asyncio.sleep(LOCAL_TRANSIENT_RETRY_DELAY.total_seconds())
        try:
            state = await read(client)
        except Exception:
            await self.async_reset(client)
            raise
        if state.transport_failure:
            await self.async_reset(client)
        return state
