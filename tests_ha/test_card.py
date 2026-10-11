"""Tests that the integration ships its Lovelace card against real Home Assistant."""

from __future__ import annotations

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.core import HomeAssistant

from custom_components.rainbird_iq4.card import CARD_PATH, CARD_URL
from tests.typing import ClientSessionGenerator

from .conftest import BACKYARD_ID, make_entry, setup_entry


async def test_card_is_served_and_loaded_on_dashboards(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """Setup serves the bundled card and adds it to every dashboard with a versioned URL."""
    await setup_entry(hass, make_entry(BACKYARD_ID))

    urls = [url for url in hass.data[DATA_EXTRA_MODULE_URL].urls if url.startswith(CARD_URL)]
    assert len(urls) == 1
    assert urls[0].startswith(f"{CARD_URL}?v=")

    client = await hass_client()
    response = await client.get(urls[0])
    assert response.status == 200
    assert await response.text() == CARD_PATH.read_text()
