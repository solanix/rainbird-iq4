"""Minimal service registration helpers."""

from __future__ import annotations

from typing import Any


def async_register_admin_service(*args: Any, **kwargs: Any) -> None:
    """Accept admin service registrations without a service registry."""
