"""Serve the bundled Lovelace card and load it on every dashboard."""

from __future__ import annotations

import hashlib
from pathlib import Path

from homeassistant.core import HomeAssistant

CARD_PATH = Path(__file__).parent / "frontend" / "rainbird-iq4-card.js"
CARD_URL = "/rainbird_iq4/rainbird-iq4-card.js"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


async def async_register_card(hass: HomeAssistant) -> None:
    """Register the card once; a content hash in the URL busts browser caches."""
    # Imported here so the stub test suite needs no frontend or http stand-ins.
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    digest = await hass.async_add_executor_job(_digest, CARD_PATH)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=True)]
    )
    add_extra_js_url(hass, f"{CARD_URL}?v={digest}")
