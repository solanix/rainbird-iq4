"""The Rain Bird IQ4 custom integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from . import cache
from .connection import RainBirdIQ4LocalConnection
from .const import DOMAIN, PLATFORMS
from .coordinator import (
    RainBirdIQ4Coordinator,
    RainBirdIQ4LocalCoordinator,
    RainBirdIQ4LocalSlowCoordinator,
)
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class RainBirdIQ4RuntimeData:
    """Independently refreshed cloud and optional local coordinators."""

    cloud: RainBirdIQ4Coordinator
    local: RainBirdIQ4LocalCoordinator | None
    local_slow: RainBirdIQ4LocalSlowCoordinator | None


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register control actions once, independent of config entry lifecycle."""
    async_setup_services(hass)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration after local options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Rain Bird IQ4 from a config entry."""
    cloud_coordinator = RainBirdIQ4Coordinator(hass, entry)
    try:
        await cloud_coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        # Local stop must not depend on the cloud (ADR-002).
        if not cloud_coordinator.local_configured or not (
            await cloud_coordinator.async_use_saved_data()
        ):
            raise
    local_coordinator = None
    local_slow_coordinator = None
    if cloud_coordinator.local_configured:
        connection = RainBirdIQ4LocalConnection(hass, entry)
        local_coordinator = RainBirdIQ4LocalCoordinator(hass, entry, connection)
        local_slow_coordinator = RainBirdIQ4LocalSlowCoordinator(hass, entry, connection)
        await local_coordinator.async_refresh()
        await local_slow_coordinator.async_refresh()
    entry.runtime_data = RainBirdIQ4RuntimeData(
        cloud_coordinator, local_coordinator, local_slow_coordinator
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the saved cloud snapshot with the entry."""
    await Store(hass, cache.STORAGE_VERSION, cache.storage_key(entry.entry_id)).async_remove()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry.runtime_data = None
    return bool(unload_ok)
