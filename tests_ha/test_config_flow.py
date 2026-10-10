"""Tests for the Rain Bird IQ4 config, reauth and options flows against real Home Assistant."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pyrainbird_iq4.cloud.models import ConnectionStatus, Controller
from pyrainbird_iq4.exceptions import (
    RainBirdIQ4ConnectionError,
    RainBirdIQ4CredentialsError,
    RainBirdIQ4WAFChallengeError,
)

from custom_components.rainbird_iq4.const import (
    CONF_CONTROLLER_ID,
    CONF_LOCAL_HOST,
    CONF_LOCAL_PASSWORD,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.rainbird_iq4.coordinator import RainBirdIQ4Coordinator

from .conftest import OTHER_ID, BACKYARD_ID, controller, make_entry, setup_entry

# Captured before the autouse mock replaces it, to exercise the real auth path.
REAL_CLOUD_UPDATE = RainBirdIQ4Coordinator._async_update_data

CREDENTIALS = {CONF_USERNAME: "user", CONF_PASSWORD: "secret"}


@pytest.fixture
def account() -> dict[str, Any]:
    """Controllers the mocked IQ4 account exposes."""
    return {"controllers": [controller(BACKYARD_ID)]}


@pytest.fixture
def mock_authenticate(account: dict[str, Any]) -> Generator[AsyncMock]:
    """Mock IQ4 authentication and discovery underneath the real validate_input."""

    def make_client(*_: Any, **__: Any) -> MagicMock:
        client = MagicMock()
        client.get_controllers = AsyncMock(side_effect=lambda: account["controllers"])
        client.get_connection_statuses = AsyncMock(
            side_effect=lambda ids: [
                ConnectionStatus(item, True, "2026-10-10T00:00:00Z") for item in ids
            ]
        )
        return client

    with (
        patch(
            "custom_components.rainbird_iq4.config_flow.authenticate",
            AsyncMock(return_value="token"),
        ) as authenticate,
        patch(
            "custom_components.rainbird_iq4.config_flow.RainBirdIQ4CloudClient",
            side_effect=make_client,
        ),
    ):
        yield authenticate


@pytest.mark.usefixtures("mock_authenticate")
async def test_user_flow_single_controller(hass: HomeAssistant) -> None:
    """One discovered controller creates an entry keyed by controller ID."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Controller {BACKYARD_ID} (Site)"
    assert result["data"] == CREDENTIALS | {CONF_CONTROLLER_ID: BACKYARD_ID}
    assert result["result"].unique_id == str(BACKYARD_ID)


@pytest.mark.usefixtures("mock_authenticate")
async def test_user_flow_selects_among_controllers(
    hass: HomeAssistant, account: dict[str, Any]
) -> None:
    """Several controllers lead to a selection step."""
    account["controllers"] = [controller(BACKYARD_ID), controller(OTHER_ID)]
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select_controller"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONTROLLER_ID: OTHER_ID}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CONTROLLER_ID] == OTHER_ID


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        pytest.param(RainBirdIQ4CredentialsError("bad"), "invalid_auth", id="credentials"),
        pytest.param(RainBirdIQ4WAFChallengeError("waf"), "cannot_connect", id="waf"),
        pytest.param(RainBirdIQ4ConnectionError("down"), "cannot_connect", id="connection"),
        pytest.param(RuntimeError("boom"), "unknown", id="unexpected"),
    ],
)
async def test_user_flow_errors_recover(
    hass: HomeAssistant, mock_authenticate: AsyncMock, error: Exception, expected: str
) -> None:
    """Errors are shown on the form and the user can retry successfully."""
    mock_authenticate.side_effect = error
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}

    mock_authenticate.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_authenticate")
async def test_user_flow_no_controllers(hass: HomeAssistant, account: dict[str, Any]) -> None:
    """An account without controllers aborts."""
    account["controllers"] = []
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_controllers"


@pytest.mark.usefixtures("mock_authenticate")
async def test_user_flow_rejects_duplicate_controller(hass: HomeAssistant) -> None:
    """A controller that is already configured cannot be added twice."""
    make_entry(BACKYARD_ID).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("mock_authenticate")
async def test_reauth_updates_password_and_reloads(hass: HomeAssistant) -> None:
    """Reauthentication stores the new password and reloads the entry."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["username"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-secret"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-secret"
    assert entry.data[CONF_USERNAME] == "user"
    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize(
    ("error", "controllers", "expected"),
    [
        pytest.param(RainBirdIQ4CredentialsError("bad"), None, "invalid_auth", id="credentials"),
        pytest.param(RainBirdIQ4ConnectionError("down"), None, "cannot_connect", id="connection"),
        pytest.param(RuntimeError("boom"), None, "unknown", id="unexpected"),
        pytest.param(None, [], "controller_not_found", id="controller-gone"),
    ],
)
async def test_reauth_errors_recover(
    hass: HomeAssistant,
    mock_authenticate: AsyncMock,
    account: dict[str, Any],
    error: Exception | None,
    controllers: list[Controller] | None,
    expected: str,
) -> None:
    """Reauth errors are shown, the password is unchanged, and a retry succeeds."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))
    mock_authenticate.side_effect = error
    if controllers is not None:
        account["controllers"] = controllers

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    assert entry.data[CONF_PASSWORD] == "secret"

    mock_authenticate.side_effect = None
    account["controllers"] = [controller(BACKYARD_ID)]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-secret"}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-secret"


async def test_rejected_credentials_start_reauth(hass: HomeAssistant) -> None:
    """IQ4 rejecting the stored password during polling prompts reauthentication."""
    entry = await setup_entry(hass, make_entry(BACKYARD_ID))

    with (
        patch.object(RainBirdIQ4Coordinator, "_async_update_data", REAL_CLOUD_UPDATE),
        patch(
            "custom_components.rainbird_iq4.coordinator.authenticate",
            AsyncMock(side_effect=RainBirdIQ4CredentialsError("rejected")),
        ),
    ):
        await entry.runtime_data.cloud.async_refresh()
        await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
    assert flows[0]["context"]["entry_id"] == entry.entry_id


@pytest.mark.parametrize(
    ("current", "user_input", "expected"),
    [
        pytest.param(
            {},
            {CONF_LOCAL_HOST: " 10.0.0.2 ", CONF_LOCAL_PASSWORD: "pin"},
            {CONF_LOCAL_HOST: "10.0.0.2", CONF_LOCAL_PASSWORD: "pin"},
            id="enable",
        ),
        pytest.param(
            {CONF_LOCAL_HOST: "10.0.0.2", CONF_LOCAL_PASSWORD: "pin"},
            {CONF_LOCAL_HOST: "10.0.0.3"},
            {CONF_LOCAL_HOST: "10.0.0.3", CONF_LOCAL_PASSWORD: "pin"},
            id="change-host-keeps-pin",
        ),
        pytest.param(
            {CONF_LOCAL_HOST: "10.0.0.2", CONF_LOCAL_PASSWORD: "pin"},
            {CONF_LOCAL_HOST: ""},
            {},
            id="disable",
        ),
    ],
)
async def test_options_flow(
    hass: HomeAssistant,
    current: dict[str, str],
    user_input: dict[str, str],
    expected: dict[str, str],
) -> None:
    """Local options can be enabled, changed without retyping the PIN, and disabled."""
    entry = make_entry(BACKYARD_ID, local=False)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options=current)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == expected


async def test_options_flow_requires_pin_for_new_host(hass: HomeAssistant) -> None:
    """A host without any PIN is rejected."""
    entry = make_entry(BACKYARD_ID, local=False)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOCAL_HOST: "10.0.0.2"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "local_credentials_required"}
