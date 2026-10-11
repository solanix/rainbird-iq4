"""Minimal binary sensor entity for integration architecture tests."""

from enum import StrEnum

from homeassistant.helpers.entity import Entity


class BinarySensorDeviceClass(StrEnum):
    """Binary sensor device classes used by the integration."""

    CONNECTIVITY = "connectivity"
    MOISTURE = "moisture"


class BinarySensorEntity(Entity):
    """Generic binary sensor entity."""
