# Brand images

Home Assistant 2026.3 and later reads brand images from this folder. Drop the
files in here and they appear in the interface, taking priority over the
brands CDN. Nothing needs to be configured.

Supported filenames:

- `icon.png` / `dark_icon.png` — square, 256x256 px
- `logo.png` / `dark_logo.png` — landscape, shortest side 128-256 px
- `icon@2x.png` / `dark_icon@2x.png` — square, 512x512 px
- `logo@2x.png` / `dark_logo@2x.png` — landscape, shortest side 256-512 px

All files must be PNG, trimmed to the subject with no surrounding empty space,
and preferably transparent and losslessly compressed.

No images are shipped with this repository. The Blackmagic Design and Teranex
marks belong to Blackmagic Design; anyone using this integration is free to
place their own files here.
