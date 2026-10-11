"""Config flow for the Rain Bird IQ4 custom integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pyrainbird_iq4.cloud.auth import authenticate
from pyrainbird_iq4.cloud.client import RainBirdIQ4CloudClient
from pyrainbird_iq4.exceptions import (
    RainBirdIQ4AuthenticationError,
    RainBirdIQ4ConnectionError,
    RainBirdIQ4CredentialsError,
    RainBirdIQ4WAFChallengeError,
)

from .const import CONF_CONTROLLER_ID, CONF_LOCAL_HOST, CONF_LOCAL_PASSWORD, DOMAIN
from .coordinator import _is_stale

_LOGGER = logging.getLogger(__name__)


def _controller_status_label(controller: Any, status: Any | None) -> str:
    """Create a friendly label for selection UI."""
    if status is not None:
        if status.is_connected:
            return f"{controller.name} (connected)"
        if _is_stale(status):
            return f"{controller.name} (disconnected, stale status)"
        if status.timestamp:
            return f"{controller.name} (disconnected)"
        return f"{controller.name} (disconnected)"
    return f"{controller.name} (disconnected)"


def _preferred_controller_order(controllers: list[Any], statuses: dict[int, Any]) -> list[Any]:
    """Prefer connected controllers and place them first in selection lists."""
    return sorted(
        controllers,
        key=lambda controller: (
            0 if statuses.get(controller.id) and statuses[controller.id].is_connected else 1,
            controller.name.lower(),
            controller.id,
        ),
    )


async def validate_input(
    hass: HomeAssistant, username: str, password: str
) -> tuple[list[Any], dict[int, Any]]:
    """Validate user credentials and return discovered controllers."""
    token = await authenticate(username, password)
    client = RainBirdIQ4CloudClient(token, session=async_get_clientsession(hass))
    controllers = await client.get_controllers()
    status_response = await client.get_connection_statuses(
        [controller.id for controller in controllers]
    )
    statuses = {item.controller_id: item for item in status_response}
    return controllers, statuses


class RainBirdIQ4ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Rain Bird IQ4."""

    VERSION = 1

    def __init__(self) -> None:
        self._username: str | None = None
        self._password: str | None = None
        self._controllers: list[Any] = []
        self._statuses: dict[int, Any] = {}

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> RainBirdIQ4OptionsFlow:
        """Return the optional local-controller configuration flow."""
        return RainBirdIQ4OptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the initial credentials form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            try:
                controllers, statuses = await validate_input(
                    self.hass, self._username, self._password
                )
            except RainBirdIQ4CredentialsError:
                errors["base"] = "invalid_auth"
            except (
                RainBirdIQ4WAFChallengeError,
                RainBirdIQ4AuthenticationError,
                RainBirdIQ4ConnectionError,
            ):
                errors["base"] = "cannot_connect"
            except Exception:  # pragma: no cover - HA requires a defensive fallback
                _LOGGER.exception("Unexpected exception while connecting to Rain Bird IQ4")
                errors["base"] = "unknown"

            if not errors:
                self._controllers = _preferred_controller_order(controllers, statuses)
                self._statuses = statuses
                if not self._controllers:
                    return self.async_abort(reason="no_controllers")
                if len(self._controllers) == 1:
                    return await self._async_create_entry_for_controller(self._controllers[0])
                return await self.async_step_select_controller()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_controller(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick which controller to use."""
        errors: dict[str, str] = {}

        if user_input is not None:
            controller_id = user_input[CONF_CONTROLLER_ID]
            controller = next(
                (item for item in self._controllers if item.id == controller_id),
                None,
            )
            if controller is None:
                errors["base"] = "unknown"
            else:
                return await self._async_create_entry_for_controller(controller)

        choices = {
            controller.id: _controller_status_label(controller, self._statuses.get(controller.id))
            for controller in self._controllers
        }
        default_controller_id = self._controllers[0].id
        return self.async_show_form(
            step_id="select_controller",
            data_schema=vol.Schema(
                {vol.Required(CONF_CONTROLLER_ID, default=default_controller_id): vol.In(choices)}
            ),
            errors=errors,
        )

    async def _async_validate_account(
        self, username: str, password: str, controller_id: int
    ) -> dict[str, str]:
        """Return form errors unless the credentials reach the configured controller."""
        try:
            controllers, _ = await validate_input(self.hass, username, password)
        except RainBirdIQ4CredentialsError:
            return {"base": "invalid_auth"}
        except (
            RainBirdIQ4WAFChallengeError,
            RainBirdIQ4AuthenticationError,
            RainBirdIQ4ConnectionError,
        ):
            return {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected exception while validating Rain Bird IQ4 account")
            return {"base": "unknown"}
        if not any(item.id == controller_id for item in controllers):
            return {"base": "controller_not_found"}
        return {}

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the IQ4 cloud account used for this controller."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_validate_account(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                entry.data[CONF_CONTROLLER_ID],
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_USERNAME): str,
                        vol.Required(CONF_PASSWORD): selector.TextSelector(
                            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                        ),
                    }
                ),
                {CONF_USERNAME: entry.data[CONF_USERNAME]},
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after IQ4 rejects the stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new IQ4 password and confirm it still reaches this controller."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_validate_account(
                entry.data[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                entry.data[CONF_CONTROLLER_ID],
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    )
                }
            ),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )

    async def _async_create_entry_for_controller(self, controller: Any) -> ConfigFlowResult:
        """Create the config entry for the selected controller."""
        await self.async_set_unique_id(str(controller.id))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"{controller.name} ({controller.site_name or 'IQ4'})",
            data={
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_CONTROLLER_ID: controller.id,
            },
        )


class RainBirdIQ4OptionsFlow(config_entries.OptionsFlow):
    """Configure optional local read-only polling."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure the controller LAN address and controller-local PIN."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input.get(CONF_LOCAL_HOST, "").strip()
            if not host:
                return self.async_create_entry(title="", data={})
            password = user_input.get(CONF_LOCAL_PASSWORD) or self._config_entry.options.get(
                CONF_LOCAL_PASSWORD, ""
            )
            if password:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_LOCAL_HOST: host,
                        CONF_LOCAL_PASSWORD: password,
                    },
                )
            errors["base"] = "local_credentials_required"
        current = self._config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_LOCAL_HOST,
                        default=current.get(CONF_LOCAL_HOST, ""),
                    ): str,
                    vol.Optional(CONF_LOCAL_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        )
                    ),
                }
            ),
            errors=errors,
        )
