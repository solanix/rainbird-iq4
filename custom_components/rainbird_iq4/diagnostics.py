"""Diagnostics support for Rain Bird IQ4."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_LOCAL_HOST, CONF_LOCAL_PASSWORD, CONF_PASSWORD, CONF_USERNAME

TO_REDACT = {
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_LOCAL_HOST,
    CONF_LOCAL_PASSWORD,
    "mac_address",
    "latitude",
    "longitude",
    "site_name",
}


def _jsonable(value: Any) -> Any:
    """Convert library dataclasses and protocol values to JSON-safe structures."""
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted(_jsonable(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    return value


def _coordinator(coordinator: DataUpdateCoordinator[Any] | None) -> dict[str, Any] | None:
    """Summarize one coordinator's health and latest data."""
    if coordinator is None:
        return None
    return {
        "last_update_success": coordinator.last_update_success,
        "update_interval_seconds": _jsonable(coordinator.update_interval),
        "last_successful_update": _jsonable(getattr(coordinator, "last_successful_update", None)),
        "consecutive_failures": getattr(coordinator, "consecutive_failures", None),
        "data": _jsonable(coordinator.data),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for one controller entry."""
    runtime = entry.runtime_data
    cloud = _coordinator(runtime.cloud)
    if cloud is not None and runtime.cloud.data is not None:
        # IQ4's raw isLocked flag means enabled when true; show the derived value too.
        for station, raw in zip(
            cloud["data"]["stations"], runtime.cloud.data.stations, strict=True
        ):
            station["is_enabled"] = raw.is_enabled
    local = _coordinator(runtime.local)
    if local is not None and runtime.local.data is not None:
        local["derived_state"] = runtime.local.data.state.value
    return async_redact_data(
        {
            "entry": {
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "cloud": cloud,
            "local_realtime": local,
            "local_slow": _coordinator(runtime.local_slow),
        },
        TO_REDACT,
    )
