"""Tests for Rain Bird IQ4 diagnostics against real Home Assistant."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from syrupy.assertion import SnapshotAssertion

from tests.components.diagnostics import get_diagnostics_for_config_entry
from tests.typing import ClientSessionGenerator

from .conftest import BACKYARD_ID, make_entry, setup_entry


@pytest.mark.freeze_time("2026-10-10T02:00:00+00:00")
async def test_diagnostics_are_redacted(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    snapshot: SnapshotAssertion,
) -> None:
    """Diagnostics include coordinator health and data with credentials and location redacted."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diagnostics == snapshot
    assert "pin" not in str(diagnostics)
    assert "secret" not in str(diagnostics)
    assert f"host-{BACKYARD_ID}" not in str(diagnostics)
