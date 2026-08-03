# Blackmagic Teranex for Home Assistant

Home Assistant custom integration for Blackmagic Design Teranex video
processors, using the Teranex Ethernet Protocol on TCP port 9800.

Developed and tested against a **Teranex 2D**.

## Status

Stage 1 — connection layer and diagnostic sensors. Controls (input/output
format, aspect ratio, proc amp, presets) are in progress.

## Why local push

The Teranex sends a full state dump on connect and then pushes every change,
whoever made it — front panel, Teranex Setup, or another controller. The
integration holds one persistent connection and never polls, so Home Assistant
stays in sync even when the unit is driven by other software at the same time.

## Installation

HACS → Custom repositories → add this repository URL → category **Integration**
→ install → restart Home Assistant → Settings → Devices & services → Add
integration → *Blackmagic Teranex*.

Enter the IP address of the unit. Port 9800 is the default.

## Entities (stage 1)

| Entity | Notes |
| --- | --- |
| Model | Reported model name |
| Software version | Firmware checksum |
| FPGA version | Disabled by default |
| Protocol version | Disabled by default |
| Friendly name | Disabled by default |
| IP address | Decoded from the device's 32-bit integer notation |

## Notes

Field names are read exactly as the device reports them, which is not always
what the manual documents. On the tested unit the key is `Output sdi mode`
(lower case) and the SDI input reports as `SDI1`.

## License

MIT
