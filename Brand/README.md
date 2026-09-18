# Brand

This folder is here so users can drop in their own icons for the integration.

No logos are included, because the Blackmagic Design and Teranex marks are
their owner's property and are not mine to redistribute.

If you want an icon in the Home Assistant interface, place your own files here:

- `icon.png` — 256x256 px, square, transparent background
- `logo.png` — up to 256 px high, any width

Home Assistant itself pulls icons from the
[home-assistant/brands](https://github.com/home-assistant/brands) repository,
so files in this folder are for your own use and for anyone forking this
project. The HACS validation workflow skips the brands check for that reason.
