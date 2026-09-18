"""Constants for the Blackmagic Teranex integration."""

from __future__ import annotations

DOMAIN = "blackmagic_teranex"
DEFAULT_PORT = 9800
DEFAULT_NAME = "Teranex"

MANUFACTURER = "Blackmagic Design"

CONF_VIDEO_MODES = "video_modes"

# Output formats offered by default. The device cannot enumerate its own
# format list, so this is a sensible starting set for a Teranex 2D; it can be
# replaced per config entry through the options flow. Whatever the device
# currently reports is always added to the list at runtime.
DEFAULT_VIDEO_MODES: tuple[str, ...] = (
    "625i50",
    "525i5994",
    "720p50",
    "720p5994",
    "720p60",
    "1080i50",
    "1080i5994",
    "1080i60",
    "1080p23976",
    "1080p24",
    "1080p25",
    "1080p2997",
    "1080p30",
    "1080p50",
    "1080p5994",
    "1080p60",
    "1080PsF23976",
    "1080PsF24",
    "1080PsF25",
    "1080PsF2997",
    "1080PsF30",
)

# Documented values for the Teranex 2D. The unit under test reports "SDI1"
# where the manual says "SDI", which is exactly why the current value is
# always merged into the option list.
VIDEO_SOURCES: tuple[str, ...] = ("SDI", "HDMI", "Composite", "Component")
AUDIO_SOURCES: tuple[str, ...] = ("Embedded", "AES", "RCA", "DB25")
ASPECT_RATIOS: tuple[str, ...] = (
    "Anamorphic",
    "Letterbox",
    "CentreCut",
    "14x9",
    "Smart",
)
ANALOG_OUTPUTS: tuple[str, ...] = ("Composite", "Component")

SERVICE_SAVE_PRESET = "save_preset"
ATTR_PRESET = "preset"
