"""Minimal data-entry flow primitives for config-flow tests."""

from __future__ import annotations

from typing import cast


class FlowResult(dict):
    """A minimal flow result dict."""


class FlowManager:
    """Manage config-flow flows for tests."""

    def __init__(self, hass: object) -> None:
        self.hass = hass

    async def async_init(
        self,
        domain: str,
        *,
        context: dict[str, str],
        data: dict[str, str],
    ) -> dict[str, object]:
        """Initialize a flow using the configured integration entry points."""
        from custom_components.rainbird_iq4.config_flow import RainBirdIQ4ConfigFlow

        flow = RainBirdIQ4ConfigFlow()
        flow.hass = self.hass  # type: ignore[assignment]
        return cast(dict[str, object], await flow.async_step_user(data))
