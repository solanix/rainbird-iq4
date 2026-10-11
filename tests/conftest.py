"""Test fixtures for the Rain Bird IQ4 custom integration."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant


@pytest.fixture(autouse=True)
def no_local_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry transient local failures immediately so tests do not sleep."""
    monkeypatch.setattr(
        "custom_components.rainbird_iq4.connection.LOCAL_TRANSIENT_RETRY_DELAY", timedelta(0)
    )


@pytest.fixture
def hass() -> HomeAssistant:
    """Provide a minimal Home Assistant instance for config-flow tests."""
    return HomeAssistant()  # type: ignore[call-arg]
