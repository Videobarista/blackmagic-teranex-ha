"""Tests for setting up and tearing down the Blackmagic Teranex integration."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blackmagic_teranex.const import (
    CONF_SW_VERSION,
    CONF_VIDEO_MODES,
    DOMAIN,
    SERVICE_SAVE_PRESET,
)
from custom_components.blackmagic_teranex.protocol import (
    TeranexCommandError,
    TeranexConnectionError,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import FakeClient


def _entity_id(hass: HomeAssistant, domain: str, entry: MockConfigEntry, key: str) -> str:
    """Look an entity up by its unique ID, independent of its display name."""
    entity_id = er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id is not None
    return entity_id


def _device(hass: HomeAssistant, entry: MockConfigEntry) -> dr.DeviceEntry:
    """Return the single device the config entry owns."""
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 1
    return devices[0]


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_while_unit_is_off(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_client: type[FakeClient]
) -> None:
    """A switched-off unit sets up fine and shows as disconnected."""
    fake_client.online = False
    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED

    connection = hass.states.get(_entity_id(hass, "binary_sensor", config_entry, "connection"))
    assert connection is not None
    assert connection.state == STATE_OFF

    model = hass.states.get(_entity_id(hass, "sensor", config_entry, "model_name"))
    assert model is not None
    assert model.state == STATE_UNAVAILABLE

    device = _device(hass, config_entry)
    assert device.name == "Studio Teranex"
    assert device.model == "Teranex 2D"
    assert device.sw_version == "0x74e4b2e"


async def test_setup_while_unit_is_on(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_client: type[FakeClient]
) -> None:
    """A reachable unit shows its live state."""
    await _setup(hass, config_entry)

    connection = hass.states.get(_entity_id(hass, "binary_sensor", config_entry, "connection"))
    assert connection is not None
    assert connection.state == STATE_ON

    model = hass.states.get(_entity_id(hass, "sensor", config_entry, "model_name"))
    assert model is not None
    assert model.state == "Teranex 2D"

    video_input = hass.states.get(_entity_id(hass, "select", config_entry, "video_source"))
    assert video_input is not None
    assert video_input.state == "SDI1"
    assert "SDI1" in video_input.attributes["options"]


async def test_new_firmware_is_remembered(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_client: type[FakeClient]
) -> None:
    """A changed identity is stored in the entry and device, without a reload."""
    await _setup(hass, config_entry)
    client = fake_client.instances[0]

    client.state["TERANEX DEVICE"]["Software Version"] = "0x80000ab"
    client.notify()
    await hass.async_block_till_done()

    assert config_entry.data[CONF_SW_VERSION] == "0x80000ab"
    device = _device(hass, config_entry)
    assert device.sw_version == "0x80000ab"
    assert len(fake_client.instances) == 1
    assert config_entry.state is ConfigEntryState.LOADED


async def test_changing_options_reloads(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_client: type[FakeClient]
) -> None:
    """New output formats take effect through a reload."""
    await _setup(hass, config_entry)

    hass.config_entries.async_update_entry(config_entry, options={CONF_VIDEO_MODES: ["1080p25"]})
    await hass.async_block_till_done()

    assert len(fake_client.instances) == 2
    assert fake_client.instances[0].closed
    assert config_entry.state is ConfigEntryState.LOADED


async def test_unload_closes_connection(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_client: type[FakeClient]
) -> None:
    """Unloading closes the connection to the unit."""
    await _setup(hass, config_entry)

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert fake_client.instances[0].closed


async def test_save_preset_action(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_client: type[FakeClient]
) -> None:
    """The save_preset action reaches the unit through the Preset entity."""
    await _setup(hass, config_entry)
    preset = _entity_id(hass, "select", config_entry, "preset")

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SAVE_PRESET,
        {"entity_id": preset, "preset": 3},
        blocking=True,
    )

    assert fake_client.instances[0].sent == [("PRESET", {"Save": "3"})]


async def test_save_preset_on_other_select_does_nothing(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_client: type[FakeClient]
) -> None:
    """Targeting a different Teranex select sends nothing to the unit."""
    await _setup(hass, config_entry)
    video_input = _entity_id(hass, "select", config_entry, "video_source")

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SAVE_PRESET,
        {"entity_id": video_input, "preset": 3},
        blocking=True,
    )

    assert fake_client.instances[0].sent == []


@pytest.mark.parametrize(
    "error",
    [
        TeranexConnectionError("connection dropped"),
        TeranexCommandError("NACK"),
    ],
)
async def test_failed_command_raises(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    fake_client: type[FakeClient],
    error: Exception,
) -> None:
    """A dropped connection or a rejected value surfaces as an error."""
    await _setup(hass, config_entry)
    fake_client.instances[0].send_error = error
    gain = _entity_id(hass, "number", config_entry, "proc_amp_gain")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": gain, "value": 10}, blocking=True
        )


async def test_number_scaling(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_client: type[FakeClient]
) -> None:
    """Audio level is sent in tenths of a decibel."""
    await _setup(hass, config_entry)
    level = er.async_get(hass).async_get_entity_id(
        "number", DOMAIN, f"{config_entry.entry_id}_audio_input_level"
    )
    assert level is not None

    await hass.services.async_call(
        "number", "set_value", {"entity_id": level, "value": -3}, blocking=True
    )

    assert fake_client.instances[0].sent == [("AUDIO", {"AudioInLevel0": "-30"})]


async def test_aspect_ranges_follow_output_format(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_client: type[FakeClient]
) -> None:
    """Aspect ranges use the output size the unit reports."""
    await _setup(hass, config_entry)

    size_x = hass.states.get(_entity_id(hass, "number", config_entry, "aspect_size_x"))
    assert size_x is not None
    assert size_x.attributes["min"] == -3840
    assert size_x.attributes["max"] == 3840

    trim_y = hass.states.get(_entity_id(hass, "number", config_entry, "aspect_trim_y"))
    assert trim_y is not None
    assert trim_y.attributes["max"] == 1080

    pos_y = hass.states.get(_entity_id(hass, "number", config_entry, "aspect_position_y"))
    assert pos_y is not None
    assert float(pos_y.state) == -12


async def test_aspect_ranges_fall_back_to_hd(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_client: type[FakeClient]
) -> None:
    """Without a reported output size the ranges assume an HD output."""
    fake_client.online = False
    await _setup(hass, config_entry)
    client = fake_client.instances[0]
    client.connected = True
    client.notify()
    await hass.async_block_till_done()

    size_y = hass.states.get(_entity_id(hass, "number", config_entry, "aspect_size_y"))
    assert size_y is not None
    assert size_y.attributes["min"] == -1080
    assert size_y.attributes["max"] == 1080


async def test_aspect_value_is_sent(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_client: type[FakeClient]
) -> None:
    """Setting an aspect value sends the left field, which a 2D acts on."""
    await _setup(hass, config_entry)
    size_y = _entity_id(hass, "number", config_entry, "aspect_size_y")

    await hass.services.async_call(
        "number", "set_value", {"entity_id": size_y, "value": -67}, blocking=True
    )

    assert fake_client.instances[0].sent == [
        ("VARIABLE ASPECT RATIO", {"Variable Aspect Ratio size Y left": "-67"})
    ]


async def test_zoom_crop_switch(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_client: type[FakeClient]
) -> None:
    """Zoom/crop is a switch that sends true or false."""
    await _setup(hass, config_entry)
    zoom = _entity_id(hass, "switch", config_entry, "aspect_zoom_crop")
    state = hass.states.get(zoom)
    assert state is not None
    assert state.state == "off"

    await hass.services.async_call("switch", "turn_on", {"entity_id": zoom}, blocking=True)

    assert fake_client.instances[0].sent == [
        ("VARIABLE ASPECT RATIO", {"Variable Aspect Ratio zoom/crop": "true"})
    ]


async def test_number_modes(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_client: type[FakeClient]
) -> None:
    """Precise values are typed in; proc amp controls stay sliders."""
    await _setup(hass, config_entry)

    delay = hass.states.get(_entity_id(hass, "number", config_entry, "audio_delay"))
    assert delay is not None
    assert delay.attributes["mode"] == "box"
    assert delay.attributes["min"] == -28
    assert delay.attributes["max"] == 1000

    gain = hass.states.get(_entity_id(hass, "number", config_entry, "proc_amp_gain"))
    assert gain is not None
    assert gain.attributes["mode"] == "slider"
