"""Minimal Home Assistant exceptions for the custom integration tests."""

from __future__ import annotations


class HomeAssistantError(Exception):
    """Base Home Assistant error."""


class ConfigEntryAuthFailed(HomeAssistantError):
    """Raised when the config entry credentials are invalid."""
