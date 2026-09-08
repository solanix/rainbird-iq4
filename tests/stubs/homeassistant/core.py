"""Minimal Home Assistant core objects for integration tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config_entries import ConfigEntries


@dataclass
class HomeAssistant:
    """Simple stand-in for the real Home Assistant instance."""

    data: dict[str, Any] = field(default_factory=dict)
    config_entries: ConfigEntries = field(default_factory=ConfigEntries)
