# Noctalia v5 overlay

`zz-shared.toml` is an optional overlay loaded after CachyOS's `config.toml`. It
provides a top status bar with a CachyOS system-menu icon and active window on
the left, workspaces in the center, and status icons plus the clock/date on the
right. Left-click the CachyOS icon for the session menu or right-click it for
the app launcher. The clock opens the Control Center notifications view.
Noctalia's native Dock shows pinned and running apps, running dots,
magnification, and an Apps button. It stays visible at the bottom with compact,
edge-aligned spacing and reserves space for windows. The overlay includes a grid
launcher and the Kanagawa dark theme. Install it with
`./install.sh --with-layout`; the default installer keeps the CachyOS layout.
The Dock groups windows by app. Hold a pinned icon briefly, then drag it to
reorder it. The native Dock does not provide a separate files/minimized-windows
section on Hyprland. Noctalia's built-in active-window label shows the window
title; its stock widgets do not display each application's File/Edit/View menus.
A later run without the flag leaves an existing overlay in place. Move
`~/.config/noctalia/zz-shared.toml` aside to return to the CachyOS layout.

Set per-user choices in Noctalia Settings (Super+Z), such as Dock pins,
wallpapers, widgets, and an avatar. Keep Dock pins in a local overlay such as
`~/.config/noctalia/zzz-local.toml` so the shared profile remains portable.
The launcher and session menu use Noctalia v5's built-in UI.

Display-specific UI scale belongs in a local overlay. On the LG ultrawide,
`./scripts/setup-lg-ultrawide.sh` sets it in `~/.config/noctalia/zzzz-lg-ultrawide.toml`;
the shared installer does not run that script. Preview it with `--dry-run`.

Export the resulting settings with `noctalia config export`, review them for
private values, and keep machine-specific values outside this shared file. Use
`noctalia config validate` after edits. GUI changes are stored separately and
can override values in `zz-shared.toml`.

For twelve selectable Omarchy palettes with color previews, install the separate
[Omarchy theme picker](omarchy-themes/README.md) with `./install.sh --with-themes`.
