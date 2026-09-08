"""Minimal sensor entity for integration architecture tests."""

from enum import StrEnum

from homeassistant.helpers.entity import Entity


class SensorDeviceClass(StrEnum):
    """Sensor device classes used by the integration."""

    DURATION = "duration"


class SensorEntity(Entity):
    """Generic sensor entity."""
