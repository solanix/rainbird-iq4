"""Minimal Home Assistant constants used by the Rain Bird IQ4 custom integration."""

from __future__ import annotations

from enum import StrEnum

ATTR_DEVICE_ID = "device_id"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"


class Platform(StrEnum):
    """Platform enum used by custom integrations."""

    BINARY_SENSOR = "binary_sensor"
    NUMBER = "number"
    SELECT = "select"
    SENSOR = "sensor"


class UnitOfTime(StrEnum):
    """Time units used by sensor entities."""

    SECONDS = "s"
    MINUTES = "min"
    DAYS = "d"


class EntityCategory(StrEnum):
    """Entity categories."""

    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"
