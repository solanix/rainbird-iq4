"""Constants for the Rain Bird IQ4 integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "rainbird_iq4"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_CONTROLLER_ID = "controller_id"
CONF_LOCAL_HOST = "local_host"
CONF_LOCAL_PASSWORD = "local_password"
PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SELECT, Platform.SENSOR]
UPDATE_INTERVAL = timedelta(minutes=5)
LOCAL_IDLE_UPDATE_INTERVAL = timedelta(seconds=30)
LOCAL_RUNNING_UPDATE_INTERVAL = timedelta(seconds=10)
LOCAL_SLOW_UPDATE_INTERVAL = timedelta(minutes=5)
LOCAL_FAILURE_BACKOFF_INTERVALS = (
    timedelta(seconds=30),
    timedelta(seconds=60),
    timedelta(seconds=120),
)
DISCOVERY_STALE_SECONDS = 900
