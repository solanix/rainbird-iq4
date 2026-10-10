"""Admin-only irrigation control actions for Rain Bird IQ4."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NoReturn

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service import async_register_admin_service

from .const import CONF_CONTROLLER_ID, DOMAIN
from .coordinator import (
    IrrigationControlAmbiguousError,
    IrrigationControlError,
    IrrigationControlResult,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from . import RainBirdIQ4RuntimeData

_LOGGER = logging.getLogger(__name__)

ATTR_STATION_ID = "station_id"
ATTR_DURATION_MINUTES = "duration_minutes"
SERVICE_START_STATION = "start_station"
SERVICE_STOP_IRRIGATION = "stop_irrigation"

# Rejections caused by the caller's request rather than controller or cloud state.
_INPUT_ERRORS = frozenset({"invalid_duration", "station_not_found", "station_not_enabled"})


def _strict_int(value: Any) -> int:
    """Accept whole numbers only; bools and fractional values are never coerced."""
    if isinstance(value, bool):
        raise vol.Invalid("expected an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise vol.Invalid("expected an integer")


START_STATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_STATION_ID): vol.All(_strict_int, vol.Range(min=1)),
        vol.Required(ATTR_DURATION_MINUTES): vol.All(_strict_int, vol.Range(min=1, max=30)),
    }
)
STOP_IRRIGATION_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.string})


def _async_get_runtime(hass: HomeAssistant, device_id: str) -> RainBirdIQ4RuntimeData:
    """Resolve a device to the loaded config entry that owns its controller."""
    device = dr.async_get(hass).async_get(device_id)
    entry: ConfigEntry | None = None
    if device is not None:
        entry = next(
            (
                candidate
                for entry_id in device.config_entries
                if (candidate := hass.config_entries.async_get_entry(entry_id)) is not None
                and candidate.domain == DOMAIN
                and (DOMAIN, str(candidate.data[CONF_CONTROLLER_ID])) in device.identifiers
            ),
            None,
        )
    if entry is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_device",
            translation_placeholders={"device_id": device_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"title": entry.title},
        )
    runtime: RainBirdIQ4RuntimeData = entry.runtime_data
    if runtime.local is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="local_not_configured",
            translation_placeholders={"title": entry.title},
        )
    return runtime


def _raise_control_error(err: IrrigationControlError) -> NoReturn:
    """Translate a control-boundary failure into an HA-native error."""
    if isinstance(err, IrrigationControlAmbiguousError):
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="write_outcome_ambiguous"
        ) from err
    error_type = ServiceValidationError if err.code in _INPUT_ERRORS else HomeAssistantError
    raise error_type(translation_domain=DOMAIN, translation_key=err.code) from err


def _response(result: IrrigationControlResult) -> ServiceResponse:
    """Report acknowledgement and observed state separately."""
    if result.acknowledged and not result.verified:
        _LOGGER.warning(
            "IQ4 %s was acknowledged but not confirmed by controller state; "
            "check the controller before retrying",
            result.action,
        )
    return {
        "acknowledged": result.acknowledged,
        "verified": result.verified,
        "no_op": result.no_op,
        "station_id": result.station_id,
        "terminal": result.terminal,
    }


async def _async_start_station(call: ServiceCall) -> ServiceResponse:
    """Start one enabled station on the selected controller."""
    runtime = _async_get_runtime(call.hass, call.data[ATTR_DEVICE_ID])
    local = runtime.local
    assert local is not None
    cloud = runtime.cloud
    try:
        result = await local.connection.async_start_station(
            call.data[ATTR_STATION_ID],
            call.data[ATTR_DURATION_MINUTES],
            cloud.data if cloud.last_update_success else None,
            local.data if local.last_update_success else None,
            local.last_successful_update,
        )
    except IrrigationControlAmbiguousError as err:
        await local.async_request_refresh()
        _raise_control_error(err)
    except IrrigationControlError as err:
        _raise_control_error(err)
    await local.async_request_refresh()
    return _response(result)


async def _async_stop_irrigation(call: ServiceCall) -> ServiceResponse:
    """Stop irrigation on the selected controller without depending on cloud state."""
    runtime = _async_get_runtime(call.hass, call.data[ATTR_DEVICE_ID])
    local = runtime.local
    assert local is not None
    try:
        result = await local.connection.async_stop_irrigation()
    except IrrigationControlAmbiguousError as err:
        await local.async_request_refresh()
        _raise_control_error(err)
    except IrrigationControlError as err:
        _raise_control_error(err)
    await local.async_request_refresh()
    return _response(result)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's admin-only control actions once."""
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_START_STATION,
        _async_start_station,
        schema=START_STATION_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_STOP_IRRIGATION,
        _async_stop_irrigation,
        schema=STOP_IRRIGATION_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
