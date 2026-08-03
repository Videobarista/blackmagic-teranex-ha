"""Config flow for the Blackmagic Teranex integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import DEFAULT_NAME, DEFAULT_PORT, DOMAIN
from .protocol import TeranexClient, TeranexConnectionError

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


class TeranexConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the user-initiated config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the host and verify we can talk to it."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            client = TeranexClient(host, port)
            try:
                await client.async_connect_once()
            except TeranexConnectionError:
                errors["base"] = "cannot_connect"
            else:
                title = (
                    client.get("NETWORK CONFIG", "Friendly name")
                    or client.model
                    or DEFAULT_NAME
                )
                return self.async_create_entry(
                    title=title, data={CONF_HOST: host, CONF_PORT: port}
                )
            finally:
                await client.async_close()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
