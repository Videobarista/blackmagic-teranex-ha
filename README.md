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

Stage 1 — connection layer and diagnostic sensors. Controls for input
selection, output format, aspect ratio, proc amp and presets are in progress.

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

| Entity | Notes |
| --- | --- |
| Model | Reported model name |
| Software version | Firmware checksum, disabled by default |
| FPGA version | Disabled by default |
| Protocol version | Disabled by default |
| Friendly name | Disabled by default |
| IP address | Decoded from the device's 32-bit integer notation |

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

## Security

The protocol has no authentication or encryption. See [SECURITY.md](SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).
