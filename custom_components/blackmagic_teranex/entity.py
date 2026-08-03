"""Shared entity base for the Blackmagic Teranex integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER
from .protocol import BLOCK_DEVICE, BLOCK_NETWORK, TeranexClient


class TeranexEntity(Entity):
    """Base entity wired to the push client."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, client: TeranexClient, entry_id: str, key: str) -> None:
        """Initialise the entity."""
        self._client = client
        self._attr_unique_id = f"{entry_id}_{key}"
        self._entry_id = entry_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            manufacturer=MANUFACTURER,
            model=self._client.model or "Teranex",
            name=self._client.get(BLOCK_NETWORK, "Friendly name"),
            sw_version=self._client.get(BLOCK_DEVICE, "Software Version"),
            configuration_url=f"http://{self._client.host}",
        )

    @property
    def available(self) -> bool:
        """Return whether the connection is up."""
        return self._client.connected

    async def async_added_to_hass(self) -> None:
        """Subscribe to push updates."""
        self.async_on_remove(
            self._client.add_listener(self.async_write_ha_state)
        )
