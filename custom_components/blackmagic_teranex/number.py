"""Proc amp controls for the Blackmagic Teranex integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TeranexConfigEntry
from .entity import TeranexEntity
from .protocol import BLOCK_PROC_AMP, TeranexClient

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class TeranexNumberDescription(NumberEntityDescription):
    """Describes a Teranex proc amp control."""

    field: str


# Ranges come from the Teranex Ethernet Protocol documentation.
NUMBERS: tuple[TeranexNumberDescription, ...] = (
    TeranexNumberDescription(
        key="proc_amp_gain",
        translation_key="proc_amp_gain",
        field="Gain",
        native_min_value=-60,
        native_max_value=60,
    ),
    TeranexNumberDescription(
        key="proc_amp_black",
        translation_key="proc_amp_black",
        field="Black",
        native_min_value=-30,
        native_max_value=30,
    ),
    TeranexNumberDescription(
        key="proc_amp_saturation",
        translation_key="proc_amp_saturation",
        field="Saturation",
        native_min_value=-60,
        native_max_value=60,
    ),
    TeranexNumberDescription(
        key="proc_amp_hue",
        translation_key="proc_amp_hue",
        field="Hue",
        native_min_value=-179,
        native_max_value=180,
    ),
    TeranexNumberDescription(
        key="proc_amp_ry",
        translation_key="proc_amp_ry",
        field="RY",
        native_min_value=-200,
        native_max_value=200,
        entity_registry_enabled_default=False,
    ),
    TeranexNumberDescription(
        key="proc_amp_by",
        translation_key="proc_amp_by",
        field="BY",
        native_min_value=-200,
        native_max_value=200,
        entity_registry_enabled_default=False,
    ),
    TeranexNumberDescription(
        key="proc_amp_sharp",
        translation_key="proc_amp_sharp",
        field="Sharp",
        native_min_value=-50,
        native_max_value=50,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeranexConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the proc amp controls."""
    client = entry.runtime_data
    async_add_entities(
        TeranexNumber(client, entry.entry_id, description) for description in NUMBERS
    )


class TeranexNumber(TeranexEntity, NumberEntity):
    """One proc amp parameter."""

    entity_description: TeranexNumberDescription
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        client: TeranexClient,
        entry_id: str,
        description: TeranexNumberDescription,
    ) -> None:
        """Initialise the number entity."""
        super().__init__(client, entry_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the value the device last reported."""
        raw = self._client.get(BLOCK_PROC_AMP, self.entity_description.field)
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            _LOGGER.debug(
                "Teranex reported a non-numeric %s: %r",
                self.entity_description.field,
                raw,
            )
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Send the new value and wait for the device to confirm it."""
        await self.async_send(
            BLOCK_PROC_AMP, {self.entity_description.field: str(int(value))}
        )
