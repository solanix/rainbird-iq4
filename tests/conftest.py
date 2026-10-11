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


@pytest.fixture(autouse=True)
def no_local_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail immediately unless a test opts into the grace period with `local_grace`."""
    monkeypatch.setattr(
        "custom_components.rainbird_iq4.coordinator.LOCAL_REALTIME_GRACE", timedelta(0)
    )
    monkeypatch.setattr("custom_components.rainbird_iq4.coordinator.LOCAL_SLOW_GRACE", timedelta(0))


@pytest.fixture
def local_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the production grace periods."""
    from custom_components.rainbird_iq4 import const  # noqa: PLC0415

    monkeypatch.setattr(
        "custom_components.rainbird_iq4.coordinator.LOCAL_REALTIME_GRACE",
        const.LOCAL_REALTIME_GRACE,
    )
    monkeypatch.setattr(
        "custom_components.rainbird_iq4.coordinator.LOCAL_SLOW_GRACE", const.LOCAL_SLOW_GRACE
    )


@pytest.fixture
def hass() -> HomeAssistant:
    """Provide a minimal Home Assistant instance for config-flow tests."""
    return HomeAssistant()  # type: ignore[call-arg]
