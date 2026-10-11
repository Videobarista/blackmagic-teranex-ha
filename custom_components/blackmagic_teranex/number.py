"""Numeric controls for the Blackmagic Teranex integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TeranexConfigEntry
from .entity import TeranexEntity
from .protocol import (
    BLOCK_ANCILLARY,
    BLOCK_AUDIO,
    BLOCK_NOISE_REDUCTION,
    BLOCK_PROC_AMP,
    BLOCK_VARIABLE_ASPECT,
    BLOCK_VIDEO_ADJUST,
    TeranexClient,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class TeranexNumberDescription(NumberEntityDescription):
    """Describes a Teranex numeric control."""

    block: str
    field: str
    # The device stores some values scaled, such as audio gain in tenths of a
    # decibel. Everything the user sees is divided by this.
    scale: int = 1
    # Some ranges depend on the current output format. When set, the range
    # is plus and minus this share of the output width or height, which the
    # unit reports in the same block. The fallback covers an HD output.
    span_field: str | None = None
    span_fallback: int = 0
    span_share: float = 1.0


# Ranges come from the Teranex Ethernet Protocol documentation.
NUMBERS: tuple[TeranexNumberDescription, ...] = (
    # Proc amp
    TeranexNumberDescription(
        key="proc_amp_gain",
        translation_key="proc_amp_gain",
        block=BLOCK_PROC_AMP,
        field="Gain",
        native_min_value=-60,
        native_max_value=60,
    ),
    TeranexNumberDescription(
        key="proc_amp_black",
        translation_key="proc_amp_black",
        block=BLOCK_PROC_AMP,
        field="Black",
        native_min_value=-30,
        native_max_value=30,
    ),
    TeranexNumberDescription(
        key="proc_amp_saturation",
        translation_key="proc_amp_saturation",
        block=BLOCK_PROC_AMP,
        field="Saturation",
        native_min_value=-60,
        native_max_value=60,
    ),
    TeranexNumberDescription(
        key="proc_amp_hue",
        translation_key="proc_amp_hue",
        block=BLOCK_PROC_AMP,
        field="Hue",
        native_min_value=-179,
        native_max_value=180,
    ),
    TeranexNumberDescription(
        key="proc_amp_ry",
        translation_key="proc_amp_ry",
        block=BLOCK_PROC_AMP,
        field="RY",
        native_min_value=-200,
        native_max_value=200,
        entity_registry_enabled_default=False,
    ),
    TeranexNumberDescription(
        key="proc_amp_by",
        translation_key="proc_amp_by",
        block=BLOCK_PROC_AMP,
        field="BY",
        native_min_value=-200,
        native_max_value=200,
        entity_registry_enabled_default=False,
    ),
    TeranexNumberDescription(
        key="proc_amp_sharp",
        translation_key="proc_amp_sharp",
        block=BLOCK_PROC_AMP,
        field="Sharp",
        native_min_value=-50,
        native_max_value=50,
    ),
    # Video adjust: RGB trim
    TeranexNumberDescription(
        key="adjust_red",
        translation_key="adjust_red",
        block=BLOCK_VIDEO_ADJUST,
        field="Red",
        native_min_value=-200,
        native_max_value=200,
    ),
    TeranexNumberDescription(
        key="adjust_green",
        translation_key="adjust_green",
        block=BLOCK_VIDEO_ADJUST,
        field="Green",
        native_min_value=-200,
        native_max_value=200,
    ),
    TeranexNumberDescription(
        key="adjust_blue",
        translation_key="adjust_blue",
        block=BLOCK_VIDEO_ADJUST,
        field="Blue",
        native_min_value=-200,
        native_max_value=200,
    ),
    # Video adjust: clipping levels, in 10-bit code values
    TeranexNumberDescription(
        key="luma_low",
        translation_key="luma_low",
        block=BLOCK_VIDEO_ADJUST,
        field="Luma low",
        native_min_value=4,
        native_max_value=1018,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    TeranexNumberDescription(
        key="luma_high",
        translation_key="luma_high",
        block=BLOCK_VIDEO_ADJUST,
        field="Luma high",
        native_min_value=5,
        native_max_value=1019,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    TeranexNumberDescription(
        key="chroma_low",
        translation_key="chroma_low",
        block=BLOCK_VIDEO_ADJUST,
        field="Chroma low",
        native_min_value=4,
        native_max_value=1018,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    TeranexNumberDescription(
        key="chroma_high",
        translation_key="chroma_high",
        block=BLOCK_VIDEO_ADJUST,
        field="Chroma high",
        native_min_value=5,
        native_max_value=1019,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    # Video adjust: letterbox and pillarbox fill colour
    TeranexNumberDescription(
        key="aspect_fill_luma",
        translation_key="aspect_fill_luma",
        block=BLOCK_VIDEO_ADJUST,
        field="Aspect fill luma",
        native_min_value=64,
        native_max_value=940,
        mode=NumberMode.BOX,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.CONFIG,
    ),
    TeranexNumberDescription(
        key="aspect_fill_cb",
        translation_key="aspect_fill_cb",
        block=BLOCK_VIDEO_ADJUST,
        field="Aspect fill Cb",
        native_min_value=64,
        native_max_value=960,
        mode=NumberMode.BOX,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.CONFIG,
    ),
    TeranexNumberDescription(
        key="aspect_fill_cr",
        translation_key="aspect_fill_cr",
        block=BLOCK_VIDEO_ADJUST,
        field="Aspect fill Cr",
        native_min_value=64,
        native_max_value=960,
        mode=NumberMode.BOX,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.CONFIG,
    ),
    # Noise reduction strength
    TeranexNumberDescription(
        key="noise_reduction_bias",
        translation_key="noise_reduction_bias",
        block=BLOCK_NOISE_REDUCTION,
        field="Bias",
        native_min_value=-3,
        native_max_value=3,
    ),
    # Audio. The device stores gain in tenths of a decibel.
    TeranexNumberDescription(
        key="audio_input_level",
        translation_key="audio_input_level",
        block=BLOCK_AUDIO,
        field="AudioInLevel0",
        native_min_value=-32,
        native_max_value=16,
        native_step=0.1,
        native_unit_of_measurement="dB",
        scale=10,
    ),
    TeranexNumberDescription(
        key="audio_delay",
        translation_key="audio_delay",
        block=BLOCK_AUDIO,
        field="AudioUserDelay0",
        native_min_value=-28,
        native_max_value=1000,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        mode=NumberMode.BOX,
    ),
    # Ancillary data line numbers. 0 means automatic.
    TeranexNumberDescription(
        key="timecode_input_line",
        translation_key="timecode_input_line",
        block=BLOCK_ANCILLARY,
        field="Timecode input line",
        native_min_value=0,
        native_max_value=25,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    TeranexNumberDescription(
        key="timecode_output_line",
        translation_key="timecode_output_line",
        block=BLOCK_ANCILLARY,
        field="Timecode output line",
        native_min_value=0,
        native_max_value=25,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    TeranexNumberDescription(
        key="cc_input_line",
        translation_key="cc_input_line",
        block=BLOCK_ANCILLARY,
        field="CC input line",
        native_min_value=20,
        native_max_value=22,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    TeranexNumberDescription(
        key="cc_output_line",
        translation_key="cc_output_line",
        block=BLOCK_ANCILLARY,
        field="CC output line",
        native_min_value=20,
        native_max_value=22,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    TeranexNumberDescription(
        key="afd_output_line",
        translation_key="afd_output_line",
        block=BLOCK_ANCILLARY,
        field="AFD output line",
        native_min_value=0,
        native_max_value=25,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    # Variable aspect ratio, the ADJ menu on the front panel. Horizontal
    # values are in pixels and vertical values in lines of the current output
    # format; only the "left" fields act on a Teranex 2D.
    TeranexNumberDescription(
        key="aspect_size_x",
        translation_key="aspect_size_x",
        block=BLOCK_VARIABLE_ASPECT,
        field="Variable Aspect Ratio size X left",
        mode=NumberMode.BOX,
        span_field="Variable Aspect Ratio last output width",
        span_fallback=1920,
    ),
    TeranexNumberDescription(
        key="aspect_size_y",
        translation_key="aspect_size_y",
        block=BLOCK_VARIABLE_ASPECT,
        field="Variable Aspect Ratio size Y left",
        mode=NumberMode.BOX,
        span_field="Variable Aspect Ratio last output height",
        span_fallback=1080,
    ),
    TeranexNumberDescription(
        key="aspect_position_x",
        translation_key="aspect_position_x",
        block=BLOCK_VARIABLE_ASPECT,
        field="Variable Aspect Ratio pos X left",
        mode=NumberMode.BOX,
        span_field="Variable Aspect Ratio last output width",
        span_fallback=1920,
    ),
    TeranexNumberDescription(
        key="aspect_position_y",
        translation_key="aspect_position_y",
        block=BLOCK_VARIABLE_ASPECT,
        field="Variable Aspect Ratio pos Y left",
        mode=NumberMode.BOX,
        span_field="Variable Aspect Ratio last output height",
        span_fallback=1080,
    ),
    TeranexNumberDescription(
        key="aspect_trim_x",
        translation_key="aspect_trim_x",
        block=BLOCK_VARIABLE_ASPECT,
        field="Variable Aspect Ratio trim X left",
        mode=NumberMode.BOX,
        span_field="Variable Aspect Ratio last output width",
        span_fallback=1920,
        span_share=0.5,
    ),
    TeranexNumberDescription(
        key="aspect_trim_y",
        translation_key="aspect_trim_y",
        block=BLOCK_VARIABLE_ASPECT,
        field="Variable Aspect Ratio trim Y left",
        mode=NumberMode.BOX,
        span_field="Variable Aspect Ratio last output height",
        span_fallback=1080,
        span_share=0.5,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeranexConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the numeric controls."""
    client = entry.runtime_data
    async_add_entities(
        TeranexNumber(client, entry.entry_id, description) for description in NUMBERS
    )


class TeranexNumber(TeranexEntity, NumberEntity):
    """One numeric parameter on the device."""

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
    def native_min_value(self) -> float:
        """Return the lower bound, following the output format where needed."""
        if self.entity_description.span_field is None:
            return super().native_min_value
        return -self._span()

    @property
    def native_max_value(self) -> float:
        """Return the upper bound, following the output format where needed."""
        if self.entity_description.span_field is None:
            return super().native_max_value
        return self._span()

    def _span(self) -> float:
        """Return the allowed distance from zero for an output-format range."""
        description = self.entity_description
        size = float(description.span_fallback)
        if description.span_field is not None:
            raw = self._client.get(description.block, description.span_field)
            try:
                reported = float(raw) if raw is not None else 0.0
            except ValueError:
                _LOGGER.debug("Teranex reported a non-numeric %s: %r", description.span_field, raw)
                reported = 0.0
            if reported > 0:
                size = reported
        return round(size * description.span_share)

    @property
    def native_value(self) -> float | None:
        """Return the value the device last reported."""
        raw = self._client.get(
            self.entity_description.block, self.entity_description.field
        )
        if raw is None:
            return None
        try:
            value = float(raw)
        except ValueError:
            _LOGGER.debug(
                "Teranex reported a non-numeric %s: %r",
                self.entity_description.field,
                raw,
            )
            return None
        return value / self.entity_description.scale

    async def async_set_native_value(self, value: float) -> None:
        """Send the new value and wait for the device to confirm it."""
        scaled = round(value * self.entity_description.scale)
        await self.async_send(
            self.entity_description.block,
            {self.entity_description.field: str(scaled)},
        )
