# CachyOS Hyprland + Noctalia v5

This repository adds portable shortcuts to the maintained [CachyOS Hyprland + Noctalia setup](https://github.com/CachyOS/cachyos-hypr-noctalia). CachyOS supplies Hyprland and its Lua base configuration; this repository adds an Omarchy-inspired shortcut layer and an optional Noctalia layout.

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

Use the standalone backup script for Linux-to-Linux snapshots of the Default
profile and all registered user profiles:

```bash
# Source machine: create a timestamped archive in ~/backups/vscode/
./scripts/backup-vscode.sh
./scripts/backup-vscode.sh --list

# Copy the printed archive path to the other machine, for example with scp.
# Destination machine: inspect changes, then close VS Code and pause Settings Sync.
./scripts/backup-vscode.sh --diff ~/vscode-backup-TIMESTAMP.zip
./scripts/backup-vscode.sh --restore ~/vscode-backup-TIMESTAMP.zip
```

Requires Python 3 and the `code` CLI. Includes settings, keybindings, user tasks,
snippets, profile names/icons and inheritance for those resources, plus extension
IDs and versions. Restore registers profiles and reinstalls extensions from the
Marketplace, which requires network access. Unavailable versions, private/VSIX
extensions, and extension installation failures are reported; configuration stays
restored, and the command exits with a failure status. Extension enablement and
prerelease-channel preferences are not transferred.

MCP configuration, authentication, history, workspace state, extension binaries,
and machine-specific profile associations are excluded. Project `.vscode/` files
stay with their repositories. Legacy inline MCP servers in `settings.json` block
backup and restore; migrate those servers to `mcp.json` in VS Code first. Other
settings are copied as written, so review absolute
paths and any credentials you have put in settings before transferring an archive.

Restore previews its writes and asks for confirmation. Before changing an existing
configuration, it must successfully create a `vscode-pre-restore-*.zip` safety
snapshot. Profiles are matched by name; existing extra files, extensions, and local
MCP configuration are retained. The safety archive can be restored with the same
command to recover overwritten configuration; restore does not delete added files,
profiles, or extensions. `--diff` exits 0 for no differences, 1 for differences, and
2 for errors. Config and snippet symlinks are rejected rather than followed.

Environment overrides: `VSCODE_CONFIG_DIR` is the **data root** containing `User/`
(default `$XDG_CONFIG_HOME/Code`, falling back to `~/.config/Code`), `VSCODE_EXTENSIONS_DIR` defaults to
`~/.vscode/extensions`, `CODE_BIN` defaults to `code`, and `BACKUP_DIR` defaults to
`~/backups/vscode`. Use `--help` for all commands. Keep backups outside this Git
repository. If a custom `code` wrapper overrides profile or directory arguments,
set `CODE_BIN` to the direct launcher (on Arch/CachyOS, `/usr/share/code/bin/code`).

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

The picker shows color previews for Catppuccin, Catppuccin Latte, Everforest, Flexoki Light, Gruvbox, Kanagawa, Matte Black, Nord, Ristretto, Rose Pine, Solarized, and Tokyo Night. Selecting a card applies its palette and light or dark mode through Noctalia; CachyOS's enabled Noctalia templates then update supported apps. Wallpapers stay as the user chose them. The picker can also be added as an **Omarchy themes** shortcut in Noctalia's Control Center. To select from a terminal, run `noctalia msg plugin my-cachyos-hyprland/omarchy-themes:apply all set "Catppuccin Latte"`.

The palettes are ports of Omarchy's color files, including the separate Solarized theme. The previews show those colors in a sample UI; they are not Omarchy wallpaper screenshots. The setup script backs up changed files and leaves unrelated palettes and plugins alone. See [noctalia-v5/omarchy-themes/README.md](noctalia-v5/omarchy-themes/README.md) for sources and regeneration details.

The default installer keeps the CachyOS appearance. To install the optional macOS-style arrangement with a CachyOS system-menu icon and active window on the left, workspaces in the center, status icons and clock on the right, and Noctalia's always-visible native Dock at the bottom:

```bash
./install.sh --with-layout --dry-run
./install.sh --with-layout
```

The flag installs `~/.config/noctalia/zz-shared.toml`. Later runs without the flag leave it in place; move that file aside to return to the CachyOS layout. See [noctalia-v5/README.md](noctalia-v5/README.md) for details.

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
