"""Fixtures for unit tests of coordinators, connection and entities against real HA."""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import pytest


@pytest.fixture(autouse=True)
def mock_io() -> Generator[None]:
    """Let these tests mock cloud and local I/O themselves."""
    yield


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
