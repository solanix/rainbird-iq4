"""Minimal config entry primitives used by the integration tests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from .data_entry_flow import FlowResult

ConfigFlowResult = FlowResult


@dataclass
class ConfigEntry:
    """Minimal config entry."""

    entry_id: str
    data: dict[str, Any] = field(default_factory=dict)
    title: str = ""
    unique_id: str | None = None
    runtime_data: Any = None
    options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = "entry-1"

    def add_update_listener(self, listener: Any) -> Any:
        return listener

    def async_on_unload(self, _callback: Any) -> None:
        return None


class FlowManager:
    """Manage config flows for the simulated Home Assistant environment."""

    def __init__(self, hass: Any) -> None:
        self.hass = hass

    async def async_init(
        self,
        domain: str,
        *,
        context: dict[str, Any],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Start a config flow for the given domain."""
        from custom_components.rainbird_iq4.config_flow import RainBirdIQ4ConfigFlow

        flow = RainBirdIQ4ConfigFlow()
        flow.hass = self.hass
        return cast(dict[str, Any], await flow.async_step_user(data))


class ConfigEntries:
    """Minimal config-entry manager."""

    def __init__(self) -> None:
        self.flow = FlowManager(self)

    async def async_forward_entry_setups(
        self, entry: ConfigEntry, platforms: Sequence[Any]
    ) -> bool:
        """Simulate forwarding platform setups."""
        return True

    async def async_unload_platforms(self, entry: ConfigEntry, platforms: Sequence[Any]) -> bool:
        """Simulate unloading platform setups."""
        return True


class ConfigFlow:
    """Simple config-flow base class."""

    VERSION = 1
    domain: str | None = None
    hass: Any

    def __init_subclass__(cls, *, domain: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.domain = domain

    async def async_set_unique_id(self, unique_id: str) -> None:
        """Set the unique ID for the config flow."""
        self._unique_id = unique_id

    def _abort_if_unique_id_configured(self) -> None:
        """Abort if the unique ID is already configured."""
        return None

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: Any,
        errors: dict[str, str] | None = None,
    ) -> FlowResult:
        """Return a minimal form payload for tests."""
        return FlowResult(type="form", step_id=step_id, errors=errors or {})

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> FlowResult:
        """Return a minimal create-entry payload for tests."""
        return FlowResult(type="create_entry", title=title, data=data)

    def async_abort(self, *, reason: str) -> FlowResult:
        """Return a minimal abort payload for tests."""
        return FlowResult(type="abort", reason=reason)


class OptionsFlow(ConfigFlow):
    """Minimal options-flow base class."""
