"""Tests for Rain Bird IQ4 config-entry setup."""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry

from custom_components.rainbird_iq4 import (
    _async_update_listener,
    async_setup_entry,
)
from custom_components.rainbird_iq4.const import (
    CONF_CONTROLLER_ID,
    CONF_LOCAL_HOST,
    CONF_LOCAL_PASSWORD,
    CONF_PASSWORD,
    CONF_USERNAME,
)


def _entry(*, local: bool) -> ConfigEntry:
    entry = type(
        "Entry",
        (),
        {
            "entry_id": "backyard",
            "data": {
                CONF_USERNAME: "cloud-user",
                CONF_PASSWORD: "cloud-secret",
                CONF_CONTROLLER_ID: 200001,
            },
            "options": (
                {
                    CONF_LOCAL_HOST: "controller.local",
                    CONF_LOCAL_PASSWORD: "local-secret",
                }
                if local
                else {}
            ),
            "runtime_data": None,
            "add_update_listener": lambda self, listener: listener,
            "async_on_unload": lambda self, callback: None,
        },
    )()
    return cast(ConfigEntry, entry)


async def test_old_cloud_only_entry_does_not_create_local_coordinator(hass) -> None:
    """An entry predating local options remains a working cloud-only entry."""
    entry = _entry(local=False)
    cloud = MagicMock(local_configured=False)
    cloud.async_config_entry_first_refresh = AsyncMock()

    with (
        patch(
            "custom_components.rainbird_iq4.RainBirdIQ4Coordinator",
            return_value=cloud,
        ),
        patch("custom_components.rainbird_iq4.RainBirdIQ4LocalCoordinator") as local_class,
    ):
        assert await async_setup_entry(hass, entry) is True

    assert entry.runtime_data.cloud is cloud
    assert entry.runtime_data.local is None
    local_class.assert_not_called()


async def test_local_options_create_coordinator_and_reload_entry(hass) -> None:
    """Persisted local options create local polling after an entry reload."""
    entry = _entry(local=True)
    cloud = MagicMock(local_configured=True)
    cloud.async_config_entry_first_refresh = AsyncMock()
    local = MagicMock()
    local.async_refresh = AsyncMock()
    slow = MagicMock()
    slow.async_refresh = AsyncMock()
    connection = MagicMock()
    hass.config_entries.async_reload = AsyncMock()

    with (
        patch(
            "custom_components.rainbird_iq4.RainBirdIQ4Coordinator",
            return_value=cloud,
        ),
        patch(
            "custom_components.rainbird_iq4.RainBirdIQ4LocalConnection",
            return_value=connection,
        ),
        patch(
            "custom_components.rainbird_iq4.RainBirdIQ4LocalCoordinator",
            return_value=local,
        ) as local_class,
        patch(
            "custom_components.rainbird_iq4.RainBirdIQ4LocalSlowCoordinator",
            return_value=slow,
        ) as slow_class,
    ):
        assert await async_setup_entry(hass, entry) is True
        await _async_update_listener(hass, entry)

    local_class.assert_called_once_with(hass, entry, connection)
    slow_class.assert_called_once_with(hass, entry, connection)
    local.async_refresh.assert_awaited_once_with()
    slow.async_refresh.assert_awaited_once_with()
    assert entry.runtime_data.local is local
    assert entry.runtime_data.local_slow is slow
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
