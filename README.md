# Blackmagic Teranex for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Validate](https://github.com/Videobarista/blackmagic-teranex-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/Videobarista/blackmagic-teranex-ha/actions/workflows/validate.yml)
[![CodeQL](https://github.com/Videobarista/blackmagic-teranex-ha/actions/workflows/codeql.yml/badge.svg)](https://github.com/Videobarista/blackmagic-teranex-ha/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/Videobarista/blackmagic-teranex-ha?include_prereleases)](https://github.com/Videobarista/blackmagic-teranex-ha/releases)

Home Assistant custom integration for Blackmagic Design Teranex video
processors, using the Teranex Ethernet Protocol on TCP port 9800.

Developed against a **Teranex 2D**.

## Status

Stable, running against a Teranex 2D.

## Why local push

The Teranex sends a full state dump on connect and then pushes every change,
whoever made it — front panel, Teranex Setup, or another controller. The
integration holds one persistent connection and never polls, so Home Assistant
stays in sync even when the unit is driven by other software at the same time.

Two consequences of that design, both deliberate:

- A command's ACK means "understood", not "applied". The integration never
  writes optimistically; entity state changes only when the device reports it.
- Status updates carry only the fields that changed, so they are merged into
  the known state rather than replacing a whole block.

## Installation

HACS → Custom repositories → add this repository URL → category
**Integration** → install → restart Home Assistant → Settings → Devices &
services → Add integration → *Blackmagic Teranex*.

Enter the IP address of the unit. Port 9800 is the default.

## Entities

Around ninety entities. The ones you are least likely to need are disabled by
default; enable them from the device page.

Entity names are prefixed by function — `Proc amp`, `Video adjust`, `Audio`,
`Noise reduction`, `Timecode`, `Captions` — because Home Assistant sorts a
device page alphabetically. Set-and-forget settings sit under Configuration
rather than Controls, so what is left in Controls is what you touch during a
show.

### Video

| Entity | Type |
| --- | --- |
| Video input, Audio source | select |
| Output format, Output aspect ratio, Output analogue | select |
| Proc amp gain, black level, saturation, hue, sharpness, R-Y, B-Y | number |
| Proc amp red, green and blue trim | number |
| Video adjust luma and chroma clipping | number |
| Video adjust fill luma, Cb and Cr | number |
| Video input auto detection, wide SD source | switch |

### Noise reduction

| Entity | Type |
| --- | --- |
| Noise reduction | switch |
| Noise reduction bias | number |
| Split screen, Red overlay | switch |

### Test pattern

| Entity | Type |
| --- | --- |
| Test pattern | select |
| Test pattern on signal loss | select |

### Audio

| Entity | Type |
| --- | --- |
| Audio output 1 to 16 | select |
| Audio input level | number |
| Audio delay | number |

### Timecode and captions

| Entity | Type |
| --- | --- |
| Timecode mode, start source, drop frame | select |
| Timecode start value, jam sync value | text |
| Timecode input and output line | number |
| Captions insert | switch |
| Captions input and output line | number |
| AFD insert, AFD output line | select, number |

### Status and diagnostics

| Entity | Type |
| --- | --- |
| Input signal, Genlock locked, Timecode, Closed captions | binary sensor |
| Still frame, Optical module | binary sensor |
| Input format, Input pixel format | sensor |
| Model, Software version, FPGA version, Protocol version, Friendly name, IP address | sensor |
| Preset | select |

## Saving presets

Recalling a preset is a normal select. Saving is the action
`blackmagic_teranex.save_preset`, deliberately not a button: it overwrites
every setting in that preset slot and cannot be undone.

```yaml
action: blackmagic_teranex.save_preset
target:
  entity_id: select.teranex_2d_preset
data:
  preset: 3
```

The device never reports which preset is active, so the Preset entity shows
the last preset recalled from Home Assistant and goes back to unknown when
anyone recalls one from the front panel.

## Test tone

Not implemented. The protocol documents the test tone for the Teranex AV only.
A 2D reports the field and accepts the command, but ignores it and reports
`None` straight back, so an entity for it would only ever look broken.

## Audio routing

Output channel 1 is `AudioOut0` in the protocol, so the entity named *Audio
output 1* writes `AudioOut0`. Sources are the 16 embedded inputs, the 8 Dolby
decoded channels, and the built-in test tones. Only the first two output
channels are enabled by default; enable the rest from the device page.

Input level is shown in decibels. The device stores it in tenths of a decibel,
which the integration converts in both directions.

## Output formats

The Teranex cannot list the formats it supports, so the integration ships a
default set for the 2D. Trim it to what you actually use through the
integration options, writing each format exactly as the device reports it
(`1080p24`, not `1080p23.98`). The format currently active on the device is
always offered, whatever the list says.

If the device answers a setting with NACK, Home Assistant shows an error and
the entity does not move. That usually means your model spells the value
differently; turn on debug logging to see what it actually sends.

## Power state

The Teranex has no power on, standby or Wake-on-LAN command, so there is no
power entity. A unit that is off or unplugged simply shows as unavailable,
and the integration keeps retrying with a backoff.

`Panel lock` and `Remote lock` can be written over the protocol but are never
reported back by the device, so they are not exposed as entities.

## Notes on field names

Field names are read exactly as the device reports them, which is not always
what the manual documents. On the tested unit the key is `Output sdi mode`
(lower case) and the SDI input reports as `SDI1`. Keys that a model does not
support are simply absent, and the integration treats absent as unknown rather
than failing.

## Troubleshooting

Add this to `configuration.yaml` to see the protocol traffic:

```yaml
logger:
  logs:
    custom_components.blackmagic_teranex: debug
```

Unreachable devices log at debug level on purpose — a switched-off processor is
a normal condition in a rack, not an error worth filling your log with.

## Brand images

Home Assistant 2026.3 and later reads icons and logos from
`custom_components/blackmagic_teranex/brand/`. That folder is empty here: the
Blackmagic Design and Teranex marks are not mine to redistribute. Drop your own
`icon.png` (256x256) and `logo.png` in there and they show up in the interface.

## Security

The protocol has no authentication or encryption. See [SECURITY.md](SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).
