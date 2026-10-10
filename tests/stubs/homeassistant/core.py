"""Minimal Home Assistant core objects for integration tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .config_entries import ConfigEntries


@dataclass
class HomeAssistant:
    """Simple stand-in for the real Home Assistant instance."""

    data: dict[str, Any] = field(default_factory=dict)
    config_entries: ConfigEntries = field(default_factory=ConfigEntries)


type ServiceResponse = dict[str, Any] | None


class SupportsResponse(StrEnum):
    """Service response support levels."""

    NONE = "none"
    OPTIONAL = "optional"
    ONLY = "only"


class ServiceCall:
    """Placeholder service call."""


def callback[T: Callable[..., Any]](func: T) -> T:
    """Mark a function as safe to run in the event loop."""
    return func
