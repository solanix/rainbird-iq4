"""Tests for sensor presentation against real Home Assistant."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import BACKYARD_ID, make_entry, setup_entry


async def test_remaining_runtime_shows_whole_seconds(hass: HomeAssistant) -> None:
    """Remaining runtime displays as whole seconds and reads 0 while idle."""
    await setup_entry(hass, make_entry(BACKYARD_ID))
    entity_id = "sensor.controller_200001_remaining_runtime"

    entry = er.async_get(hass).async_get(entity_id)
    state = hass.states.get(entity_id)

    assert entry is not None
    assert entry.options["sensor"]["suggested_display_precision"] == 0
    assert state is not None
    assert state.state == "0"
