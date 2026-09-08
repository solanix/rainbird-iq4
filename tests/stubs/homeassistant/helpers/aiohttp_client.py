"""Minimal shared HTTP session helper."""

from typing import Any


def async_get_clientsession(_hass: Any) -> Any:
    """Return a stable shared-session placeholder."""
    return object()
