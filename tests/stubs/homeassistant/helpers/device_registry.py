"""Minimal device registry support."""

from __future__ import annotations

from typing import Any


class DeviceInfo(dict):
    """Minimal device info dict."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


def async_get(hass: Any) -> Any:
    """Return no device registry in stub tests."""
    raise NotImplementedError
