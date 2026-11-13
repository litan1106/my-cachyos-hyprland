# CachyOS Hyprland + Noctalia v5

This repository adds portable shortcuts to the maintained [CachyOS Hyprland + Noctalia setup](https://github.com/CachyOS/cachyos-hypr-noctalia). CachyOS supplies Hyprland and its Lua base configuration; this repository adds an Omarchy-inspired shortcut layer and an optional Noctalia layout.

See the [documentation index](docs/README.md) for desktop customization, scripts,
editor setup, GPU workflows, and historical records.

## Fresh install or another account

Select Hyprland during CachyOS installation, or install the profile first. Clone this repository and run the installer as the desktop user:

```bash
sudo pacman -Syu --needed cachyos-hypr-noctalia
git clone https://github.com/litan1106/my-cachyos-hyprland.git
cd my-cachyos-hyprland
./install.sh --dry-run
./install.sh
```

The installer copies CachyOS's `/etc/skel/.config/hypr` base only when the account has no Hyprland configuration. It appends `require("config.my_desktop")` to the CachyOS loader and installs `hypr/config/my_*.lua`. The default Noctalia layout remains in use. Changed files receive timestamped `.bak` copies; identical files are left alone. The installer checks for the expected CachyOS Lua loader and stops if its structure has changed.

Log out and select **Hyprland (UWSM)** in the display manager. In that session, check the configuration and shell:

```bash
hyprctl configerrors
noctalia config validate
noctalia msg status
```

Test the launcher, dock, session menu, lock screen, hardware keys, notifications, and your usual applications.

## Transfer VS Code configuration

Create a Linux-to-Linux configuration snapshot with `./scripts/backup-vscode.sh`.
On the destination machine, preview it before restoring:

```bash
./scripts/backup-vscode.sh --diff ~/vscode-backup-TIMESTAMP.zip
# Close VS Code and pause Settings Sync before restoring.
./scripts/backup-vscode.sh --restore ~/vscode-backup-TIMESTAMP.zip
```

See the [VS Code backup reference](docs/scripts-guide.md#backup-vscodesh) for
profiles, extension transfer, exclusions, prerequisites, and recovery behavior.

## Customize the setup

### Shortcuts

Edit `hypr/config/my_desktop.lua` in this repository. It loads after CachyOS's `~/.config/hypr/config/binds.lua`, so it can replace default bindings. Reapply and check the active config:

```bash
./apply.sh --dry-run
./apply.sh
hyprctl configerrors
hyprctl binds
```

Super is the Windows/Command key. The full custom list is in `my_desktop.lua`; other CachyOS defaults remain available.

| Shortcut | Action |
| --- | --- |
| Super+Escape | Session menu |
| Super+Alt+Space | Control Center |
| Super+W / Super+T | Close window / toggle floating |
| Super+Tab / Super+Shift+Tab | Next / previous workspace |
| Super+Ctrl+Tab | Previous workspace on this monitor |
| Super+1–4 / Super+Shift+1–4 | Focus / move window to workspace |
| Super+Alt+F | Maximize window |
| Super+Ctrl+L | Lock screen |
| Super+Shift+Return / Super+Shift+F | Browser / file manager |
| Super+Ctrl+T or Super+Shift+T | System monitor |
| Super+Ctrl+V / Super+Ctrl+E | Clipboard / emoji launcher |
| Super+Ctrl+W | Wallpaper picker |
| Super+Comma / Super+Shift+Comma | Notifications / clear active notifications |
| Super+Ctrl+I / Super+Ctrl+N | Toggle caffeine / night light |
| Super+Ctrl+Comma / Super+Shift+Space | Toggle Do Not Disturb / bar |
| Super+Shift+M | Restore a window hidden by the yellow title-bar button (with Hyprbars) |
| Super+Print / Alt+Print | Capture window / full screen |

### Displays, input, and Noctalia

Configure each machine's displays in `~/.config/hypr/config/monitors.lua` and monitor assignments in `variables.lua`; configure keyboard and pointer input in `inputs.lua`. These machine-specific files are not deployed by this repository. Use `hyprctl monitors` to inspect connected outputs.

For the LG ultrawide profile, run the optional setup script on the machine with that display:

```bash
./scripts/setup-lg-ultrawide.sh --dry-run
./scripts/setup-lg-ultrawide.sh
```

It matches the LG monitor by model, sets its Hyprland scale to 1.25, and puts the Noctalia UI scale in a local `zzzz-lg-ultrawide.toml` overlay. The shared installer does not run this script.

Open Noctalia settings with Super+Z to choose apps, wallpaper, and other local preferences. Noctalia v5 reads TOML from `~/.config/noctalia/`; GUI-managed `~/.local/state/noctalia/settings.toml` can override shared TOML. Run `noctalia config export` to inspect effective choices and `noctalia config validate` after edits. Review any export for private values before sharing it.

### Omarchy theme picker

Install the optional theme picker and twelve Omarchy palettes independently of the layout:

```bash
./install.sh --with-themes --dry-run
./install.sh --with-themes
noctalia msg panel-toggle my-cachyos-hyprland/omarchy-themes:picker
```

The picker applies twelve Omarchy palettes through Noctalia's app templates.
See the [theme-picker reference](noctalia-v5/omarchy-themes/README.md) for available
palettes, terminal commands, source revisions, and regeneration details.

### Optional layout and title bars

For the optional macOS-style top bar and always-visible native Dock, run:

```bash
./install.sh --with-layout --dry-run
./install.sh --with-layout
```

See the [layout reference](noctalia-v5/README.md) for Dock behavior, local
preferences, overlay precedence, and returning to the CachyOS layout.

The profile sets Hyprland window opacity to 1. The provided Foot config also uses an opaque background; installed terminals with their own transparency setting must use an opacity of 1.

For Mac-style title bars and left-side window buttons, install Hyprland's optional Hyprbars plugin as the desktop user:

```bash
sudo pacman -S --needed hyprpm
hyprpm update
hyprpm add https://github.com/hyprwm/hyprland-plugins
hyprpm enable hyprbars
./apply.sh --with-layout
hyprctl reload
hyprctl configerrors
```

The custom title bar is configured in `hypr/config/my_desktop.lua` and activates only when Hyprbars is loaded. The profile reloads enabled `hyprpm` plugins at the next Hyprland start. Red closes the window, green toggles maximize, and yellow hides it in Hyprland's `special:minimized` workspace. Super+Shift+M restores a hidden window; use this one window at a time. This is a workspace-based approximation of minimize; the native Dock on Hyprland does not restore it like a macOS dock. If a floating app opens with its bar under the top panel, hold Super and left-drag anywhere inside the window to move it down. JDownloader 2 does not draw its own close or maximize controls without Hyprbars, so this setup keeps the plugin. GNOME apps keep their built-in header bars to avoid two stacked bars. For GTK apps, set the controls on the left with `gsettings set org.gnome.desktop.wm.preferences button-layout 'close,minimize,maximize:'`. The installer leaves existing GTK files untouched; merge the button rules from this repository's `gtk-3.0/` and `gtk-4.0/` files into local GTK CSS if desired. Other apps that draw their own title bar may need a Hyprbars `no_bar` rule or an app-specific setting. Run `hyprpm update` after a Hyprland upgrade so Hyprbars matches the new version.

## Share and update

Give another user the repository link and the fresh install instructions above. The shared profile contains no fixed username, monitor ID, avatar, or wallpaper directory. Each user chooses their own displays, input devices, apps, and Noctalia preferences. Applications used by optional shortcuts must be installed separately.

After pulling or editing this repository, run `./apply.sh --dry-run` followed by `./apply.sh`. If you installed the optional layout or theme picker, repeat `--with-layout` or `--with-themes` on both commands to update those files too. The deployer backs up changed files. The previous `--profile hypr-v5` form is also accepted.

After a `cachyos-hypr-noctalia` package update, review its [release notes](https://github.com/CachyOS/cachyos-hypr-noctalia/releases) and compare `/etc/skel/.config/hypr/` with your `~/.config/hypr/`. Merge relevant changes to CachyOS's base modules and loader, retaining `require("config.my_desktop")`, `config/my_desktop.lua`, and your monitor/input choices. Compare `/etc/skel/.config/noctalia/config.toml` with your `~/.config/noctalia/config.toml` and merge any new CachyOS defaults you want. Package updates do not update copies in your home directory. Keep `zz-shared.toml`, local overlays, and Noctalia's GUI-managed state separate from the base. Then reapply this repository and run `hyprctl reload`, `hyprctl configerrors`, and `noctalia config validate`. Address any Noctalia migration warnings in the named TOML file; its compatibility migrations are temporary.

## Files

- `hypr/config/my_*.lua`: behavior layered after the CachyOS defaults.
- `noctalia-v5/zz-shared.toml`: optional Noctalia v5 layout and appearance.
- `noctalia-v5/omarchy-themes/`: optional Omarchy palettes and Noctalia theme picker.
- `install.sh`, `apply.sh`, and `scripts/install-hypr-v5.sh`: profile validation, backup, and deployment.
- [docs/scripts-guide.md](docs/scripts-guide.md): other setup and maintenance scripts.

## References

- [CachyOS Hyprland + Noctalia configuration](https://github.com/CachyOS/cachyos-hypr-noctalia)
- [CachyOS Hyprland post-install guide](https://wiki.cachyos.org/configuration/desktop_environments/hyprland/)
- [Noctalia v5 configuration and validation](https://docs.noctalia.dev/noctalia/configuration/)
- [Noctalia v5 Hyprland integration](https://docs.noctalia.dev/noctalia/compositor-settings/hyprland/)
