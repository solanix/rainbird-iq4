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
CLOUD_UPDATE_INTERVAL = timedelta(minutes=5)
LOCAL_IDLE_UPDATE_INTERVAL = timedelta(seconds=30)
LOCAL_RUNNING_UPDATE_INTERVAL = timedelta(seconds=10)
LOCAL_SLOW_UPDATE_INTERVAL = timedelta(minutes=5)
LOCAL_FAILURE_BACKOFF_INTERVALS = (
    timedelta(seconds=30),
    timedelta(seconds=60),
    timedelta(seconds=120),
)
# Another IQ4 client (the Rain Bird app via the cloud) sometimes holds the controller's
# local port; a refused or timed-out read usually clears within seconds.
LOCAL_TRANSIENT_RETRY_DELAY = timedelta(seconds=2)
# Most outages last under ~30 s, some ~2 min (2026-10-13 soak). Keep the last good
# values available this long (their age still shows, and start re-reads everything)
# instead of flapping to unavailable.
LOCAL_REALTIME_GRACE = timedelta(seconds=90)
LOCAL_SLOW_GRACE = timedelta(minutes=15)
DISCOVERY_STALE_SECONDS = 900
