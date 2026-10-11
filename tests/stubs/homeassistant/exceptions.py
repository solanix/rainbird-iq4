"""Minimal Home Assistant exceptions for the custom integration tests."""

from __future__ import annotations

from typing import Any


class HomeAssistantError(Exception):
    """Base Home Assistant error carrying optional translation details."""

    def __init__(
        self,
        *args: Any,
        translation_domain: str | None = None,
        translation_key: str | None = None,
        translation_placeholders: dict[str, str] | None = None,
    ) -> None:
        super().__init__(*args or ((translation_key,) if translation_key else ()))
        self.translation_domain = translation_domain
        self.translation_key = translation_key
        self.translation_placeholders = translation_placeholders


class ConfigEntryAuthFailed(HomeAssistantError):
    """Raised when the config entry credentials are invalid."""


class ServiceValidationError(HomeAssistantError):
    """Raised when a service call is invalid."""


class ConfigEntryNotReady(HomeAssistantError):
    """Raised when a config entry is not ready yet."""
