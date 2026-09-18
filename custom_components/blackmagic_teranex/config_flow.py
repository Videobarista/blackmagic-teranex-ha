"""Config flow for the Blackmagic Teranex integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_VIDEO_MODES,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_VIDEO_MODES,
    DOMAIN,
)
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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TeranexOptionsFlow:
        """Return the options flow."""
        return TeranexOptionsFlow()

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


class TeranexOptionsFlow(OptionsFlow):
    """Let the user narrow the list of output formats."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the output format list as comma separated values."""
        if user_input is not None:
            modes = [
                mode.strip()
                for mode in user_input[CONF_VIDEO_MODES].split(",")
                if mode.strip()
            ]
            return self.async_create_entry(data={CONF_VIDEO_MODES: modes})

        current = self.config_entry.options.get(
            CONF_VIDEO_MODES, list(DEFAULT_VIDEO_MODES)
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_VIDEO_MODES, default=", ".join(current)
                ): str
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
