"""Test fixtures for the Rain Bird IQ4 custom integration."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant


@pytest.fixture
def hass() -> HomeAssistant:
    """Provide a minimal Home Assistant instance for config-flow tests."""
    return HomeAssistant()  # type: ignore[call-arg]
