# Omarchy themes for Noctalia

`./install.sh --with-themes` installs twelve version 2 custom palettes in
`~/.config/noctalia/palettes/` and a local Noctalia plugin in
`~/.local/share/noctalia/plugins/omarchy-themes/`. It can be combined with
`--with-layout`, but the picker works with either Noctalia layout.

Open the picker with:

```bash
noctalia msg panel-toggle my-cachyos-hyprland/omarchy-themes:picker
```

The plugin also provides a Control Center shortcut and a command for scripts:

```bash
noctalia msg plugin my-cachyos-hyprland/omarchy-themes:apply all set "Tokyo Night"
```

The palette files map Omarchy's foreground, background, accent, named colors,
and ANSI terminal colors to Noctalia's roles. Light themes set Noctalia's light
mode; the other themes set dark mode. This uses Noctalia's existing app templates
from the CachyOS profile. Existing wallpapers are kept. The generated previews
show sample UI colors, not a wallpaper or an exact desktop screenshot.

The eleven bundled Omarchy themes come from the
[Omarchy theme tree](https://github.com/omacom/omarchy/tree/bda3aaf6955404712dbd46541e6c8a75a2b16b7c/themes)
(MIT license). Solarized comes from
[Gazler's Omarchy Solarized theme](https://github.com/Gazler/omarchy-solarized-theme/tree/236840f05449f1becfafd1f5995c2c5c9c79ca70).
To regenerate palettes and previews after deliberately changing the pinned
source revisions in `scripts/generate-omarchy-themes.py`, install Pillow and run:

```bash
python scripts/generate-omarchy-themes.py
```
