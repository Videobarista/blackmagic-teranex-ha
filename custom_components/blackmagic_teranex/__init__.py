"""The Blackmagic Teranex integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DEFAULT_PORT
from .protocol import TeranexClient, TeranexConnectionError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]

type TeranexConfigEntry = ConfigEntry[TeranexClient]


async def async_setup_entry(hass: HomeAssistant, entry: TeranexConfigEntry) -> bool:
    """Set up Blackmagic Teranex from a config entry."""
    client = TeranexClient(
        entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT)
    )

    try:
        await client.async_start()
    except TeranexConnectionError as err:
        await client.async_close()
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = client
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TeranexConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_close()
    return unloaded


async def _async_options_updated(
    hass: HomeAssistant, entry: TeranexConfigEntry
) -> None:
    """Reload the entry so changed output formats take effect."""
    await hass.config_entries.async_reload(entry.entry_id)
