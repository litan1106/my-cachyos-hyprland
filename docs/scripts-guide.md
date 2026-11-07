# Scripts Guide

Reference for setup and maintenance utilities in [`scripts/`](../scripts/) — one-shot utilities for backing up dev-tool configs (Antigravity CLI, Claude Code, Zed), fixing an AMD GPU monitor-wake bug, setting up SMB/mDNS network discovery, installing/managing gaming platforms (Battle.net, Hearthstone Deck Tracker, Lutris, Hongguo), and setting up Rust (plus Bevy deps), Go, and Docker dev toolchains. The desktop profile installer uses `install-hypr-v5.sh`; run the other utilities directly when needed. See the [README](../README.md) for desktop installation.

## Table of Contents

1. [backup-antigravity.sh](#backup-antigravitysh)
2. [backup-claude.sh](#backup-claudesh)
3. [backup-zed.sh](#backup-zedsh)
4. [fix-monitor-wake.sh](#fix-monitor-wakesh)
5. [setup_smb_discovery.sh](#setup_smb_discoverysh)
6. [install-gaming-battlenet.sh](#install-gaming-battlenetsh)
7. [launch-battlenet.sh](#launch-battlenetsh)
8. [remove-gaming-battlenet.sh](#remove-gaming-battlenetsh)
9. [install-gaming-hdt.sh](#install-gaming-hdtsh)
10. [launch-hdt.sh](#launch-hdtsh)
11. [remove-gaming-hdt.sh](#remove-gaming-hdtsh)
12. [install-gaming-lutris.sh](#install-gaming-lutrissh)
13. [remove-gaming-lutris.sh](#remove-gaming-lutrissh)
14. [install-hongguo.sh](#install-hongguosh)
15. [launch-hongguo.sh](#launch-hongguosh)
16. [remove-hongguo.sh](#remove-hongguosh)
17. [install-gpu-lib32.sh](#install-gpu-lib32sh)
18. [setup-local-bin-path.sh](#setup-local-bin-pathsh)
19. [install-android-waydroid.sh](#install-android-waydroidsh)
20. [finish-waydroid-init.py](#finish-waydroid-initpy)
21. [launch-waydroid.sh](#launch-waydroidsh)
22. [install-waydroid-apk.sh](#install-waydroid-apksh)
23. [install-waydroid-arm.sh](#install-waydroid-armsh)
24. [remove-android-waydroid.sh](#remove-android-waydroidsh)
25. [fix-waydroid-firewall.sh](#fix-waydroid-firewallsh)
26. [install-rust.sh](#install-rustsh)
27. [install-bevy.sh](#install-bevysh)
28. [install-golang.sh](#install-golangsh)
29. [install-docker.sh](#install-dockersh)

---

## backup-antigravity.sh

**Purpose**: Backs up and restores **Antigravity CLI** (`agy`) configuration — settings, keybindings, status line, plugins, skills, MCP config, and hooks — via zip archive or a secret GitHub Gist. See also [`agy-artifact-custom-command-walkthrough.md`](agy-artifact-custom-command-walkthrough.md) for what the `plugins/` and `skills/` content actually contains.

**Usage**:
```bash
./backup-antigravity.sh                 # create zip backup (default)
./backup-antigravity.sh --zip   | -z    # create zip in ~/backups/antigravity/
./backup-antigravity.sh --gist  | -g    # upload to a secret GitHub Gist
./backup-antigravity.sh --both  | -b    # zip AND gist
./backup-antigravity.sh --restore | -r <zip>   # restore from a zip backup
./backup-antigravity.sh --diff    | -d <zip>   # diff a backup against current config
./backup-antigravity.sh --list    | -l  # list existing backups
./backup-antigravity.sh --help    | -h  # show help
```

**What gets backed up**: `settings.json`, `keybindings.json`, `statusline.sh`, `plugins/`, `mcp_config.json`, `hooks.json` (always checked), plus `skills/` (optional). Missing targets are silently skipped.

**Not backed up**: `brain/`, `cache/`, `log/`, `conversations/`, `builtin/`, `bin/`, `implicit/`, `knowledge/` — machine-specific, transient, or auto-restored on install.

**What it does**:
- `--zip` — collects existing targets, prints a summary (file/plugin counts), and zips them (relative paths) into `~/backups/antigravity/antigravity-backup-<timestamp>.zip`, excluding `.DS_Store`, dotfiles, `.log`, `__pycache__`, `node_modules`. Lists the 5 most recent backups if more than one exists.
- `--gist` — same collection, but flattens directory structure with `__` separators (e.g. `plugins__artifact-manager__plugin.json`) into a temp dir, then uploads via `gh gist create`. Requires `gh auth login` beforehand.
- `--restore <zip>` — previews the zip contents, asks `[y/N]` confirmation, takes a **pre-restore safety zip** (`antigravity-pre-restore-<timestamp>.zip`) of the current config, then extracts into `AGY_CONFIG_DIR` and re-applies `chmod +x` to any `.sh` files. Restore stops if the safety backup fails.
- `--diff <zip>` — extracts the backup to a temp dir and reports `MISSING` (in backup, not current), `CHANGED` (with a unified diff, first 20 lines), and `NEW` (in current, not backup) — no files are modified.
- `--list` — lists all `antigravity-*.zip` files in the backup dir, newest first.

**Prerequisites**: `bsdtar` from `libarchive` (for `--zip`/`--both`/`--restore`/`--diff`), `gh` CLI authenticated via `gh auth login` (for `--gist`/`--both`). Exits 1 if the Antigravity CLI config dir doesn't exist, or if there's nothing to back up.

**Environment variables**:
| Variable | Default | Purpose |
|---|---|---|
| `AGY_CONFIG_DIR` | `~/.gemini/antigravity-cli` | Source config directory |
| `BACKUP_DIR` | `~/backups/antigravity` | Where zips are written |

**Warnings**:
- `--restore` **overwrites** existing config files in place (after confirmation and an automatic safety backup).
- Gist backups flatten directory structure — restoring from a cloned Gist requires manually un-flattening `__`-separated filenames, or using `--restore` with a zip instead (recommended).

---

## backup-claude.sh

**Purpose**: Backs up and restores Claude Code configuration (`~/.claude`) — instructions, agents, skills, rules, hooks, MCP configs — via zip or GitHub Gist. Same design as `backup-antigravity.sh` and `backup-zed.sh` (see that section above for the shared zip/gist/restore/diff mechanics); this section covers only what's Claude-specific.

**Usage**:
```bash
./backup-claude.sh                    # create zip backup (default)
./backup-claude.sh --zip    | -z      # create zip in ~/backups/claude/
./backup-claude.sh --gist   | -g      # upload to a secret GitHub Gist
./backup-claude.sh --both   | -b      # zip AND gist
./backup-claude.sh --restore| -r <zip>   # restore from a zip backup
./backup-claude.sh --list   | -l      # list existing backups
./backup-claude.sh --help   | -h      # show help
```

**What gets backed up**: `CLAUDE.md`, `RTK.md`, `settings.json`, `keybindings.json`, `agents/`, `skills/`, `rules/`, `hooks/`, `mcp-configs/`. Missing targets are skipped.

**Not backed up**: `.credentials.json` (OAuth tokens/secrets), `projects/`, `sessions/` (conversation transcripts), `history.jsonl`, `cache/`, `telemetry/`, `plugins/` (marketplace cache), `downloads/`, `paste-cache/`, `file-history/`, `shell-snapshots/`, `session-env/`, and its own `backups/` output dir.

**What it does**: Identical flow to `backup-antigravity.sh` — `--zip` creates `~/backups/claude/claude-backup-<timestamp>.zip`; `--gist` flattens with `__` and uploads via `gh gist create`; `--restore <zip>` previews contents, asks `[y/N]`, takes a `claude-pre-restore-<timestamp>.zip` safety backup, then `unzip -o`'s over `CLAUDE_CONFIG_DIR`; `--list` shows existing backups newest-first. (No `--diff` mode is provided for this script, unlike `backup-antigravity.sh`.)

**Prerequisites**: `zip`, `unzip`, `gh` (authenticated) for the Gist path. Exits 1 if `~/.claude` doesn't exist.

**Environment variables**:
| Variable | Default | Purpose |
|---|---|---|
| `CLAUDE_CONFIG_DIR` | `~/.claude` | Source config directory |
| `BACKUP_DIR` | `~/backups/claude` | Where zips are written |

**Warnings**:
- `--restore` overwrites existing files in `~/.claude` after confirmation (safety backup is automatic).
- Restart Claude Code after a restore to pick up the new config.
- Never commit or share zip/Gist output without checking it doesn't include `.credentials.json` — it's excluded by design, but verify if you customize `BACKUP_TARGETS`.

---

## backup-zed.sh

**Purpose**: Backs up and restores Zed editor configuration (`~/.config/zed`) — settings, keymap, tasks, debug config, themes, extensions, snippets — via zip or GitHub Gist. Same shared design as `backup-antigravity.sh` (see above).

**Usage**:
```bash
./backup-zed.sh                    # create zip backup (default)
./backup-zed.sh --zip    | -z      # create zip in ~/backups/zed/
./backup-zed.sh --gist   | -g      # upload to a secret GitHub Gist
./backup-zed.sh --both   | -b      # zip AND gist
./backup-zed.sh --restore| -r <zip>   # restore from a zip backup
./backup-zed.sh --list   | -l      # list existing backups
./backup-zed.sh --help   | -h      # show help
```

**What gets backed up**: `settings.json`, `keymap.json`, `tasks.json`, `debug.json`, `themes/`, `extensions/`, `snippets/`.

**Not backed up**: `db/` (internal database), `copilot/` (auth tokens), `node/` (bundled runtime), `logs/`, `languages/` (downloaded LSP binaries), `*_server/` state dirs.

**What it does**: Same flow as `backup-antigravity.sh` — `--zip` creates `~/backups/zed/zed-backup-<timestamp>.zip`; `--gist` flattens with `__` and uploads via `gh gist create`; `--restore <zip>` previews, confirms `[y/N]`, takes a `zed-pre-restore-<timestamp>.zip` safety backup, then `unzip -o`'s over `ZED_CONFIG_DIR`; `--list` shows backups newest-first. No `--diff` mode.

**Prerequisites**: `zip`, `unzip`, `gh` (authenticated) for Gist. Exits 1 if `~/.config/zed` doesn't exist.

**Environment variables**:
| Variable | Default | Purpose |
|---|---|---|
| `ZED_CONFIG_DIR` | `~/.config/zed` (Linux) | Source config directory — override to `~/Library/Application Support/Zed` on macOS |
| `BACKUP_DIR` | `~/backups/zed` | Where zips are written |

**Warnings**:
- `--restore` overwrites existing files in `~/.config/zed` after confirmation (safety backup is automatic).
- Restart Zed after a restore to pick up the new config.

---

## fix-monitor-wake.sh

**Purpose**: Applies a workaround for a black-screen-on-wake issue observed on an AMD RX 9060 XT (RDNA 4 / navi48) over HDMI in a previous Wayland session, involving an `amdgpu` `REG_WAIT` timeout on `optc401_disable_crtc` during DPMS off/on. Test whether it is needed in Hyprland.

**Usage**:
```bash
sudo ./fix-monitor-wake.sh
```
(The script invokes `sudo` internally for the privileged steps, but you'll be prompted for your password regardless of how it's launched.)

**What it does** (runs with `set -e`, so it stops on the first failure):
1. Writes `/etc/modprobe.d/amdgpu.conf` with `options amdgpu psr=0 runpm=0` — disables Panel Self Refresh (`psr=0`, which causes the CRTC-disable hang on HDMI) and GPU runtime power management (`runpm=0`, which prevents the deep-idle state that triggers the timeout).
2. Rebuilds the initramfs with `sudo mkinitcpio -P` so the module parameters apply on next boot.
3. Verifies the parameters are picked up via `modprobe --showconfig` (falls back to grepping the conf file directly).
4. Prints a reminder to reboot, plus the commands to verify post-reboot (`cat /sys/module/amdgpu/parameters/psr` and `.../runpm`, both should read `0`).

**Prerequisites**: `sudo` access; `mkinitcpio`-based system (CachyOS/Arch); AMD `amdgpu` driver in use.

**Warnings**:
- **A reboot is required** — the fix does not take effect until the machine restarts.
- Disabling PSR and GPU runtime PM system-wide may slightly increase idle power draw — this is a deliberate tradeoff to avoid the wake hang, not a general-purpose tuning change.
- Overwrites `/etc/modprobe.d/amdgpu.conf` wholesale (uses a heredoc, not an append) — if you already have custom `amdgpu` module options in that file, back it up first.

---

## setup_smb_discovery.sh

**Purpose**: Configures a CachyOS/Arch machine to mimic Ubuntu's out-of-the-box SMB/network-discovery experience — Samba file sharing, mDNS (`.local` hostname resolution and Bonjour/AFP-style discovery for Apple devices), and WSDD (discovery for Windows 10/11 clients), plus matching firewall rules.

**Usage**:
```bash
sudo ./setup_smb_discovery.sh
```
Exits 1 immediately if not run as root.

**What it does**:
1. Installs `samba`, `avahi`, `nss-mdns`, `wsdd` via `pacman -S --needed --noconfirm`.
2. Edits `/etc/nsswitch.conf`, inserting `mdns_minimal [NOTFOUND=return]` before `resolve`/`dns` in the `hosts:` line (skipped if already present).
3. **Backs up** any existing `/etc/samba/smb.conf` to `/etc/samba/smb.conf.bak`, then writes a new Ubuntu-style `smb.conf` with `[global]`, `[homes]`, `[printers]`, and `[print$]` sections tuned for high-throughput streaming (large SMB2/3 read/write/trans sizes, `TCP_NODELAY`, `use sendfile`), multi-channel SMB3, and macOS/iPad compatibility (`vfs objects = catia fruit streams_xattr`, Apple metadata/AFP settings).
4. Writes `/etc/avahi/services/samba.service` to advertise the `_smb._tcp` service over mDNS.
5. Opens firewall ports via `ufw`: `139/tcp`, `445/tcp` (Samba), `mdns`, `3702/udp` + `5357/tcp` (WSDD), then `ufw reload`.
6. Enables and starts `smb.service`, `nmb.service`, `avahi-daemon.service`, `wsdd.service`, and `ufw.service`.
7. Prints a completion message and suggests running `testparm` to validate the new `smb.conf`.

**Prerequisites**: Root/`sudo`; `pacman`-based system; `ufw` installed (the script assumes it and does not check).

**Warnings**:
- **Overwrites `/etc/samba/smb.conf` and `/etc/avahi/services/samba.service` unconditionally** — the old `smb.conf` is preserved as `.bak`, but the Avahi service file is not backed up.
- Does not check whether `ufw` is installed/enabled before calling `ufw allow`/`ufw reload` — if you don't use `ufw`, adapt the firewall section to your setup (`firewalld`, `nftables`, etc.) before running.
- Sets `security = user` and `map to guest = bad user` — shares fall back to guest access for unrecognized users; review `[homes]`/`[printers]` permissions if this is a multi-user or untrusted-network machine.
- Runs `pacman -S --noconfirm`, so it will install/upgrade packages without prompting.

---

## install-gaming-battlenet.sh

**Purpose**: Installs Battle.net as a standalone Windows application via umu-launcher and GE-Proton, without Steam, Lutris, or Heroic. The script downloads the official Battle.net installer, sets up a Wine prefix at `~/Games/battlenet`, and installs a launch script to `~/.local/bin/launch-battlenet` with a desktop entry.

**Usage**:
```bash
./install-gaming-battlenet.sh
```

**What it does**:
1. Installs `umu-launcher` via `pacman` (it's in the `cachyos` sync repo).
2. Auto-detects the GPU vendor(s) via `lspci` and installs the matching lib32 graphics drivers through the shared [install-gpu-lib32.sh](#install-gpu-lib32sh) helper — `lib32-vulkan-radeon` (AMD), `lib32-vulkan-intel` (Intel), and/or `lib32-nvidia-utils` (NVIDIA), plus `lib32-mesa` always.
3. Checks for a partial/failed Battle.net installation at `~/Games/battlenet` and prompts to wipe it if detected (the installer is not idempotent and cannot resume).
4. Creates the Wine prefix directory if it doesn't exist.
5. Downloads the official Battle.net installer from Blizzard's server into `~/.cache/cachyos-gaming/Battle.net-Setup.exe`.
6. Launches the installer via `umu-run` in the background, which opens the Battle.net setup wizard (standard Windows installer; click through normally).
7. Installs the `launch-battlenet` script to `~/.local/bin/launch-battlenet` (requires `~/.local/bin` on `$PATH`).
8. Installs a desktop entry to `~/.local/share/applications/battlenet.desktop` and updates the desktop database.

**Prerequisites**: `sudo` access (packages install via `pacman` from the CachyOS/Arch sync repos — multilib must be enabled for the lib32 drivers, which is the CachyOS default); any AMD/Intel/NVIDIA GPU (the correct lib32 driver is auto-detected); `~/.local/bin` must be on `$PATH` for the launcher command to resolve — run [setup-local-bin-path.sh](#setup-local-bin-pathsh) once.

**Warnings**:
- The installer runs in the background and logs to `/tmp/battlenet-installer.log` — it does **not** block the script's completion. The script prints instructions for launching Battle.net after installation finishes (which may take several minutes).
- If a partial prefix is detected (directory exists but `Launcher.exe` is missing), the script will ask for confirmation to wipe it before proceeding. This is necessary because Battle.net's installer cannot resume from a partial state.
- GE-Proton is auto-fetched and cached by umu-launcher on first launch; no manual download is needed.
- Test Battle.net window handling in Hyprland and configure a window rule if needed.

---

## launch-battlenet.sh

**Purpose**: Launches the installed Battle.net client via umu-launcher and GE-Proton, with optional MangoHud performance overlay for in-game FPS monitoring and logging.

**Usage**:
```bash
launch-battlenet                 # standard launch
launch-battlenet --with-mangohud # launch with MangoHud overlay
launch-battlenet --help          # show help
```

**What it does**:
1. Verifies that Battle.net is installed at `~/Games/battlenet` (checks for `Launcher.exe`).
2. Sets up Wine/Proton environment variables (`WINEPREFIX`, `PROTONPATH=GE-Proton`, `GAMEID=umu-battlenet`, `PROTON_VERB=run`).
3. If `--with-mangohud` is passed, adds `MANGOHUD=1` to the environment to enable the MangoHud overlay.
4. Invokes `umu-run` with the Battle.net launcher executable.

**Prerequisites**: Battle.net must be installed via `install-gaming-battlenet.sh` first; `umu-launcher` must be installed; `~/.local/bin` must be on `$PATH`.

**Warnings**:
- MangoHud (when enabled) displays an FPS overlay and logs performance metrics to `~/mangohud/` as CSV files. Toggle it in-game with `Shift_L+F2`.
- The launcher script does not validate GE-Proton availability — umu-launcher will fetch it on first use if missing.

---

## remove-gaming-battlenet.sh

**Purpose**: Uninstalls Battle.net, its Wine prefix, all installed games, and associated desktop entries. Optionally removes umu-launcher and cached GE-Proton runtimes if they are not needed.

**Usage**:
```bash
./remove-gaming-battlenet.sh
```

**What it does**:
1. Kills any running processes tied to the Battle.net prefix (`~/Games/battlenet`).
2. Removes the Wine prefix directory at `~/Games/battlenet` (all installed games and Battle.net client).
3. Removes the launcher script at `~/.local/bin/launch-battlenet`.
4. Removes the desktop entry at `~/.local/share/applications/battlenet.desktop` and updates the desktop database.
5. Removes the cached installer at `~/.cache/cachyos-gaming/Battle.net-Setup.exe`.
6. Prompts whether to also remove `umu-launcher` (used only by Battle.net in this setup).
7. Prompts whether to also remove GE-Proton runtimes cached at `~/.local/share/Steam/compatibilitytools.d/GE-Proton*` and `~/.local/share/umu`.

**Prerequisites**: None; the script handles cases where Battle.net or its components are not fully installed.

**Warnings**:
- This script **permanently deletes** the Battle.net prefix and all installed games — there is no undo.
- Prompts are non-interactive `[y/N]` (default is No) for `umu-launcher` and GE-Proton removal; answer `y` or `Y` to proceed.

---

## install-gaming-hdt.sh

**Purpose**: Installs [Hearthstone Deck Tracker](https://hsdecktracker.net/) (HDT) **into the existing Battle.net Proton prefix** (`~/Games/battlenet`). HDT only tracks a Hearthstone install that lives in the same Wine prefix — that's how it reads the game's log files and overlays it — so this reuses the Battle.net prefix rather than creating a separate one. No Lutris and no extra wine prefix involved.

**Usage**:
```bash
./install-gaming-hdt.sh
```

**What it does**:
1. Verifies the Battle.net prefix exists (`Battle.net Launcher.exe` present); exits with guidance if not.
2. Warns (but continues) if Hearthstone isn't installed in the prefix yet — HDT can't track anything until it is.
3. Installs `winetricks`, `cabextract`, `unzip`, `curl` via `pacman` (`--needed`).
4. Installs **.NET Framework 4.8** into the prefix using GE-Proton's own `wine` build (auto-detected under `~/.local/share/Steam/compatibilitytools.d/GE-Proton*`). Idempotent — skips if `dotnet48` is already recorded in the prefix's `winetricks.log`.
5. Downloads the latest HDT portable zip from GitHub (`HearthSim/Hearthstone-Deck-Tracker`) into `~/.cache/cachyos-gaming/`.
6. Extracts it into the prefix at `~/Games/battlenet/drive_c/Hearthstone Deck Tracker/`.
7. Installs the `launch-hdt` script to `~/.local/bin/launch-hdt` and a desktop entry to `~/.local/share/applications/hdt.desktop`.

**Prerequisites**: Battle.net installed via [install-gaming-battlenet.sh](#install-gaming-battlenetsh) **and Hearthstone installed through it** (needs your Blizzard login — launch Battle.net with `launch-battlenet`); GE-Proton already fetched by umu (happens on first Battle.net launch); `sudo` access.

**Warnings**:
- The .NET 4.8 install takes several minutes and a few Wine dialogs may flash by — let it run unattended.
- HDT only tracks the Hearthstone that lives in this same prefix. Install HDT *after* Hearthstone, and start Hearthstone before HDT.

---

## launch-hdt.sh

**Purpose**: Launches Hearthstone Deck Tracker via umu-launcher and GE-Proton in the Battle.net prefix, so it can attach to the running Hearthstone.

**Usage**:
```bash
launch-hdt                 # standard launch
launch-hdt --with-mangohud # launch with MangoHud overlay
launch-hdt --help          # show help
```

**What it does**:
1. Verifies HDT is installed at `~/Games/battlenet/drive_c/Hearthstone Deck Tracker/`.
2. Sets the Wine/Proton environment (`WINEPREFIX`, `PROTONPATH=GE-Proton`, `GAMEID=umu-battlenet`, `PROTON_VERB=run`) — the same prefix/GAMEID as Battle.net.
3. Optionally adds `MANGOHUD=1` with `--with-mangohud`.
4. Invokes `umu-run` with the HDT executable.

**Prerequisites**: HDT installed via `install-gaming-hdt.sh`; `umu-launcher` installed; `~/.local/bin` on `$PATH`. Start Hearthstone (`launch-battlenet` → launch Hearthstone) first so HDT can detect it.

**Warnings**:
- If HDT can't find Hearthstone automatically, point it at the Hearthstone folder *inside the prefix* (e.g. `C:\Program Files (x86)\Hearthstone`).

---

## remove-gaming-hdt.sh

**Purpose**: Removes Hearthstone Deck Tracker — its files inside the Battle.net prefix, the launcher, and the desktop entry — while leaving the Battle.net prefix and its .NET runtime intact (both are shared with Battle.net/Hearthstone).

**Usage**:
```bash
./remove-gaming-hdt.sh
```

**What it does**:
1. Kills any running `Hearthstone Deck Tracker.exe` process.
2. Removes `~/Games/battlenet/drive_c/Hearthstone Deck Tracker/`.
3. Removes the launcher at `~/.local/bin/launch-hdt`.
4. Removes the desktop entry at `~/.local/share/applications/hdt.desktop` and updates the desktop database.
5. Removes the cached HDT zip(s) from `~/.cache/cachyos-gaming/`.

**Prerequisites**: None.

**Warnings**:
- Leaves the Battle.net prefix and the .NET runtime in place on purpose — they belong to Battle.net/Hearthstone. Use [remove-gaming-battlenet.sh](#remove-gaming-battlenetsh) to remove those.

---

## install-gaming-lutris.sh

**Purpose**: Installs Lutris gaming platform along with Wine and runtime dependencies (wine-staging, wine-mono, wine-gecko, winetricks), AMD lib32 graphics drivers, and umu-launcher. Also patches the Lutris shebang for machines where `python3` is managed by mise (a version manager), ensuring Lutris can import its Python modules correctly.

**Usage**:
```bash
./install-gaming-lutris.sh
```

**What it does**:
1. Installs Lutris and its dependencies via `pacman` (all in the CachyOS/Arch sync repos; `--needed` makes the already-installed `lutris` a no-op): `lutris`, `umu-launcher`, `wine-staging`, `wine-mono`, `wine-gecko`, `winetricks`, `python-protobuf`.
2. Auto-detects the GPU vendor(s) via `lspci` and installs the matching lib32 graphics drivers through the shared [install-gpu-lib32.sh](#install-gpu-lib32sh) helper — `lib32-vulkan-radeon` (AMD), `lib32-vulkan-intel` (Intel), and/or `lib32-nvidia-utils` (NVIDIA), plus `lib32-mesa` always.
3. **Detects mise-managed Python**: Checks if Lutris's shebang line points to `#!/usr/bin/env python3` and if `python3` resolves through a mise shim. If detected, patches the shebang in `/usr/bin/lutris` to `#!/bin/python3` (the system Python) instead, bypassing the mise shim so the lutris module can be imported.
4. Launches Lutris in the background, which begins auto-fetching DXVK and VKD3D runtimes (watch the status bar at the bottom of the Lutris window).
5. Prints instructions to add or install games once the runtimes finish downloading.

**Prerequisites**: `sudo` access (packages install via `pacman`; multilib must be enabled for the lib32 drivers — the CachyOS default); any AMD/Intel/NVIDIA GPU (the correct lib32 driver is auto-detected via the shared [install-gpu-lib32.sh](#install-gpu-lib32sh) helper).

**Environment variables**: None explicitly used, but the script detects the presence of `mise` in the `python3` path.

**Warnings**:
- The shebang patch only runs if `python3` is detected as mise-managed; on systems without mise, this step is skipped.
- Lutris auto-fetches runtimes in the background on first launch — the process runs in parallel with the script's completion, so you may need to wait for the status bar to show 100% before launching games.
- The script opens Lutris immediately after install; you can close it and re-open later if needed.

---

## remove-gaming-lutris.sh

**Purpose**: Uninstalls Lutris and all associated gaming dependencies (Wine, winetricks, umu-launcher) along with configuration and cache directories.

**Usage**:
```bash
./remove-gaming-lutris.sh
```

**What it does**:
1. Checks which of the following packages are installed and removes them via `sudo pacman -Rns --noconfirm`: `lutris`, `wine-staging`, `wine-mono`, `wine-gecko`, `winetricks`, `python-protobuf`, `umu-launcher`.
2. Removes Lutris configuration and cache directories: `~/.config/lutris`, `~/.local/share/lutris`, `~/.cache/lutris`.
3. Removes umu-launcher and Wine directories: `~/.local/share/umu`, `~/.cache/umu`, `~/.wine`, `~/.cache/wine`, `~/.cache/winetricks`.
4. Prints a confirmation message listing what was removed.

**Prerequisites**: `pacman` (Arch/CachyOS); `sudo` access.

**Warnings**:
- This script **permanently deletes** all Lutris configurations, game prefixes, installed games, and Wine caches — there is no undo.
- Runs `pacman -Rns --noconfirm`, so package removal is automatic without prompts.

---

## install-hongguo.sh

**Purpose**: Installs the Hongguo (红果短剧) desktop app **100% natively — no Wine, no Proton**. Hongguo ships only as a Windows installer, but it's just an NSIS self-extracting archive, so the script **unpacks it with `7z`** (no Wine) and keeps only the app's Python backend + Java signer jar (discarding the bundled Windows `python/` and `jre/`). It then installs the `launch-hongguo` script to `~/.local/bin/` with a desktop entry. Shared constants/helpers live in `hongguo-common.sh` (sourced, not run directly). The app's Edge/WebView2 UI crashes under Wine and is **not** used; instead [`launch-hongguo`](#launch-hongguosh) runs the backend on a native Python venv (with the signer on the host JVM) and opens the UI in a **native browser**. See the deep-dive under [launch-hongguo.sh](#launch-hongguosh) for the full investigation of how this app is structured and why none of it needs Wine.

**Usage**:
```bash
./install-hongguo.sh
# Use a newer build:
HONGGUO_INSTALLER_URL="https://.../hongguo-<ver>-windows-x86_64-setup.exe" ./install-hongguo.sh
```

**What it does**:
1. Installs `uv`, `7zip`, and `curl` via `pacman` (all in the `cachyos`/Arch sync repos — no AUR, no Wine). `uv` provisions the native Python venv; `7zip` unpacks the setup.exe; `curl` downloads it. A host JVM runs the API signer, so it installs `jre-openjdk` **only if there's no `java` on `$PATH`** already (most CachyOS boxes ship a JDK; the unversioned `jre-openjdk` would otherwise pull a newer JDK than needed). It also checks for a Chromium-class browser (used for the UI) and suggests installing one if none is found.
2. Downloads the installer (default: the pinned `v1.0.12` GitHub release, overridable with `$HONGGUO_INSTALLER_URL`) into `~/.cache/cachyos-windows/`, reusing a cached copy if present.
3. Unpacks `backend/*` from the NSIS installer with `7z` into a temp staging dir (no Wine), drops the bundled Windows `python/` and `jre/` (~330 MB → ~45 MB kept), and moves the result to `~/.local/share/hongguo-native/backend`.
4. Installs the `launch-hongguo` script to `~/.local/bin/` and a desktop entry to `~/.local/share/applications/hongguo.desktop`, then updates the desktop database.
5. Ensures `~/.local/bin` is on `$PATH` via [setup-local-bin-path.sh](#setup-local-bin-pathsh).

**Prerequisites**: `sudo` access (packages install via `pacman`); `~/.local/bin` on `$PATH` for the launcher command (set up automatically). No GPU drivers, multilib, or Wine needed — the UI runs in your existing native browser.

**Warnings**:
- The download URL is **pinned to a specific version** (unlike Battle.net's stable vendor URL). Override `$HONGGUO_INSTALLER_URL` for newer builds, or edit the default in the script. To update, delete the cached `~/.cache/cachyos-windows/hongguo-*-setup.exe` and re-run.
- Extraction expects a `backend/` tree inside the installer (checked for `server.py`). If a future build changes that layout, the script aborts with a hint to inspect `7z l <installer>`.
- The launcher opens the UI with `--class=hongguo`. Test its window handling in Hyprland and configure a window rule if needed.
- This is an unofficial, reverse-engineered FQNovel client — treat it as such. **Read the investigation deep-dive under [launch-hongguo.sh](#launch-hongguosh) to understand what's actually running.** The Android app via Waydroid ([install-android-waydroid.sh](#install-android-waydroidsh)) remains an alternative.

---

## launch-hongguo.sh

**Purpose**: Runs Hongguo **100% natively — no Wine, no Proton**. It runs the app's Python backend in a venv built from your **system Python** (with the API signer on the host JVM) and opens the UI in a native Linux browser — the app's own Edge/WebView2 shell (which crashes unfixably under Wine) is simply not used. Video is served as plain MP4, so H264 "just works" in the native browser.

**Usage**:
```bash
launch-hongguo                  # start backend, open UI in a native browser
launch-hongguo --browser CMD    # use a specific browser command
launch-hongguo --no-open        # start backend only; print the URL
launch-hongguo --reinstall-deps # rebuild the Python venv, then run
launch-hongguo --help           # show help
```

**What it does**:
1. Locates the extracted backend (`find_backend_dir` → `~/.local/share/hongguo-native/backend`); exits with guidance if missing. Requires a **host** JVM (`java` on `$PATH`) for the signer; points to `pacman -S jre-openjdk` if absent.
2. Provisions (once) a venv at `~/.local/share/hongguo-native/venv` from your **system Python** (`python3`; override with `$HONGGUO_PYTHON`) and installs the backend's deps into it with `uv` (falls back to `python3 -m venv` + `pip`). The app is pure Python and its deps ship binary wheels for current Pythons, so no separate runtime is downloaded. The venv is cached and reused; `--reinstall-deps` rebuilds it.
3. Generates a per-launch 64-hex session API key, installs `standalone_server.py` into the backend dir, and writes the web UI (`scripts/hongguo-web/index.html`) into the backend's `web/index.html` with that key baked in. Both are re-installed every launch, so they survive app updates/reinstalls. `standalone_server.py` also wires in **persistent caches** (see below) before importing the vendor `server`.
4. Creates the runtime data dirs under `~/.local/share/hongguo-native/` (`data/`, `data/stream-cache`, `hls/`).
5. Starts the `unidbg-sign.jar` signer on the **host JVM** on a free port and waits until it's listening.
6. Starts the backend with the venv's Python (`python -I standalone_server.py`) on a **stable port** (`8793` by default; override with `$HONGGUO_PORT`, falls back to a random free port only if it's taken), run **from the backend dir** so `import server` and its siblings (incl. `frida/offline_decrypt.py`, which `server.py` adds to `sys.path`) resolve to the real code — with `SIGN_SERVER` pointed at the host signer and `HONGGUO_SESSION_API_KEY` / `HONGGUO_CONTENT_CONFIG` (= the shipped `guest-config.json`) / data-dir env set (all plain Linux paths). Waits until `http://127.0.0.1:<port>/` answers. A stale backend from a crashed prior run is reaped first so the stable port is free. The stable port matters for caching: cover thumbnails load via a keyless `/img?url=…` proxy sent with a long `max-age`, but the browser keys its disk cache on the full URL (including the port) — a random port each launch would silently re-download every cover.
7. Opens `http://127.0.0.1:<port>/ui` in a native browser — a Chromium-class browser in **app mode** (chromeless window, dedicated profile, `--class=hongguo`) if one is found, else `$BROWSER`/`xdg-open`. In app mode the script waits on the browser window and tears down the backend + signer when it closes; otherwise it runs until `Ctrl-C`.

**Prerequisites**: Hongguo installed via `install-hongguo.sh`; a host `java` (any JDK — `jre-openjdk` is auto-installed only if none exists); `curl`, `uv`, and a `python3`; a browser (Chromium-class recommended); `~/.local/bin` on `$PATH`. No `umu-launcher`/Wine.

**Warnings**:
- The **first** run installs the backend's Python deps into a venv using your system Python (~1 min, one-time). Subsequent runs start in about a second.
- The first `/stream` request for an episode downloads + decrypts the whole clip server-side before it plays (then it's cached and instant); expect a short wait on first play.

**Persistent caches** (why re-opens are fast): stock Hongguo keeps its catalog cache (`safeguards._cache`) and HEIC→JPEG cover cache (`server._img_cache`) in **process memory**, so every app open started cold — the first click on each page hit the throttled FQNovel API (a few seconds) and every cover re-downloaded/re-decoded. `standalone_server.py` now backs both with disk stores under `~/.local/share/hongguo-native/data/cache/` (`catalog.sqlite` + `img/`), honouring the vendor's own TTLs (rank 30 min, episodes/stream URLs ~5–6 h, search 10 min). It monkeypatches `safeguards.cache_get/cache_set` before importing `server` (both `hongguo.py` and `server.py` use `import safeguards as SG`, so the swap is picked up at request time) and swaps `server._img_cache` for a disk-backed mapping after import — all best-effort, falling back to stock in-memory behaviour on any error. Combined with the stable port (so the browser caches covers too), a warm re-open serves pages from disk in ~1 ms instead of ~3.5 s. The cache lives under the data dir, so `remove-hongguo.sh` clears it; delete `data/cache/` by hand to force a cold refresh.

> **📓 Getting Hongguo working on Linux — the full investigation**
>
> The end state is Wine-free (install *and* run), but getting there meant first making it work under Proton, then peeling Wine away entirely. This app is **not** the simple "Tauri + WebView2" wrapper it looks like. It's a native **companion launcher** (`hongguo-desktop-companion.exe`, a Tauri 2 app) that starts a local **Python/FastAPI backend**, which forges ByteDance/FQNovel Android API signatures with a **Java signer** (`unidbg-sign.jar`, emulating `libmetasec_ml.so`), fetches the catalog, and serves **decrypted, seekable MP4** over HTTP; the UI is rendered by the bundled **Edge/WebView2 (Chromium 154)** runtime. It works on native Windows but broke in two independent places under Proton. Diagnosing it meant running each component by hand under the prefix and reading the companion's `startup-status.json` / `diagnostics/lifecycle.jsonl` under `AppData/Roaming/cn.guoban.desktop-companion/`, plus full Wine SEH traces (`WINEDEBUG=+seh,+module`).
>
> **Problem 1 — no window at all (SOLVED).** The companion exited ~instantly. Root cause: the **signer** died, so the backend couldn't authenticate. The bundled **Windows JRE under Wine** failed two ways: `Error: could not find java.dll` (the Java launcher can't resolve its runtime through the **non-ASCII install path** `红果免费短剧` under Wine), and — past that — `NullPointerException … sun.nio.ch.UnixDomainSockets.localAddress` when `Selector.open()` runs (JDK 17+ builds its NIO selector wakeup pipe over an **AF_UNIX** socket, and **Wine's `getsockname` returns null**). No JVM flag works around it.
>
>   **Fix:** run the signer on the **host (native Linux) JVM** — no AF_UNIX/Selector bug. It's just a localhost HTTP service, and Wine shares the host's `127.0.0.1`, so the Wine-side backend reaches it directly (verified Wine→host `POST /sign` → `200`).
>
> **Problem 2 — WebView2 crashes in Wine's COM, not the GPU (UNFIXABLE; bypassed).** With the signer fixed, the window opens but paints **white and dies in ~1s**. A full SEH trace shows the real cause: WebView2 (Edge/Chromium 154) dies during init with `EXCEPTION_ACCESS_VIOLATION (0xc0000005)` at a **fixed address inside Wine's `ole32.dll`** (`ole32+0x34d7d`) — a Wine COM bug, reproducible identically with GPU **and** accessibility (`PROTON_USE_XALIA=0`) disabled and with any flags. So it is **not** a GPU or H264 problem, and we can't fix Wine's `ole32` from the app side. The earlier software-rendering idea (`--disable-gpu --use-angle=swiftshader`) was a dead end on two counts: the crash isn't GPU, and this app doesn't read `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` anyway — it's a Tauri 2.11/wry build that sets its own browser args (confirmed: the env var name isn't in the binary; env passthrough and a Wine-registry `HKCU\Environment` override both reach the process but have no effect).
>
>   **Fix (step 1): drop the broken half.** The Windows app = (Python backend that works under Wine) + (Edge/WebView2 shell that crashes under Wine). We keep the backend and replace the shell with a **native Linux browser**. `launch-hongguo` runs `standalone_server.py` (the backend's own FastAPI `app`, started like the app's `desktop_bootstrap.py` does, minus the companion/handshake/in-Wine signer) on a fixed port and opens `/ui` — a small self-contained UI (`scripts/hongguo-web/index.html`) that calls the backend's documented endpoints (`/rank`, `/latest`, `/search`, `/episodes`, `/stream`). The backend auth runs in **ephemeral mode**: when `HONGGUO_SESSION_API_KEY` (a 64-hex string) is set, that is the *only* valid key, so the launcher picks one and bakes it into the served UI.
>
> **H264 video.** Because `/stream` serves a plain decrypted MP4 (H264) with HTTP Range support, a native browser's `<video>` plays it directly — no Media Foundation, no Wine codec path, no flags. This was the original "play H264 under Proton" goal, reached by not using WebView2 at all.
>
> **Fix (step 2): drop Wine entirely.** With the UI a native browser and the signer a host-JVM service, the only thing still under Wine was the Python backend — and *nothing in it is actually Windows-bound*. Its whole dependency closure (`requests`, `fastapi`, `uvicorn[standard]`, `pycryptodome`, `av`/PyAV, `pillow[-heif]`) ships as native Linux wheels; the 128 `.pyd` files in the bundle are just the stock CPython embeddable stdlib, which native Python already has; the optional reverse-engineering deps (`frida`, `redis`, `curl_cffi`) are import-guarded and unused when `SIGN_SERVER` is set; and it uses PyAV (bundled ffmpeg), not a shelled-out `ffmpeg.exe`. So the *same* backend code runs unchanged on a native venv built from the **system Python** (provisioned by `uv`; it also runs on the bundle's 3.11 if ever needed, via `$HONGGUO_PYTHON`). And since the setup.exe is just an NSIS archive, even the **install** needs no Wine — `7z x` unpacks the `backend/` tree directly (we keep ~45 MB of it, discarding the bundled Windows `python/`+`jre/`). End state: `install-hongguo` extracts with `7z`, `launch-hongguo` runs the backend on a native venv + host JVM + native browser — **no Wine, no Proton, no `umu-launcher`, no prefix anywhere.** That also removes the Proton cold-start that made an earlier Wine-hosted version of the UI feel sluggish (cached runs now reach ready in ~1s), and makes the recipe portable to macOS. (Aside: **Electron would be the wrong tool** — it only replaces the browser shell we already dropped, re-adding a bundled Chromium to do what the system browser does for free, while leaving the backend where it was. The win was porting the *backend* off Wine, not repackaging the UI.) Verified end-to-end on the 7z-extracted backend under native Python: `/rank` returns the real catalog, `/stream` serves seekable `video/mp4` (`HTTP 206`, `ftyp isom`).
>
> **Operational notes.**
> - The signer runs on your host `java` — any mainstream JDK works (tested on OpenJDK 21; an LTS is ideal for this `--add-opens`-heavy unidbg jar). `install-hongguo.sh` adds `jre-openjdk` only if no `java` is present.
> - The content config is the shipped `backend/guest-config.json` (a guest/"audit" FQNovel profile: `api5-normal-sinfonlinea.fqnovel.com`, no login). If a future build drops it, capture the real one by logging `HONGGUO_CONTENT_CONFIG`'s target.
> - The backend writes a small startup log to `~/.local/share/hongguo-native/standalone.log` — check it if the backend won't come up.
> - All state lives under `~/.local/share/hongguo-native/`: `backend/` (extracted app), `venv/` (built from the system Python, deps installed on first run, reused after — rebuild with `launch-hongguo --reinstall-deps`), and `data/`+`hls/` (runtime cache).
>
> **Alternative.** 红果短剧 is a ByteDance **Android-first** app; the Android version via **Waydroid** ([install-android-waydroid.sh](#install-android-waydroidsh)) is another route with a working media stack.

---

## remove-hongguo.sh

**Purpose**: Uninstalls Hongguo — the extracted backend, native Python venv, runtime data, launcher, desktop entry, browser profile, and cached installer. (Nothing here touches Wine/Proton; the native install uses none.)

**Usage**:
```bash
./remove-hongguo.sh
```

**What it does**:
1. Stops the backend (`standalone_server.py`) and host-JVM signer (`FqTrace`) if running.
2. Removes the app home `~/.local/share/hongguo-native/` (extracted backend + venv + data).
3. Removes the launcher `~/.local/bin/launch-hongguo` and the desktop entry `~/.local/share/applications/hongguo.desktop`, then updates the desktop database.
4. Removes the dedicated browser profile (`~/.local/share/hongguo-browser`) and cached `hongguo-*-setup.exe` installers from `~/.cache/cachyos-windows/`.

**Prerequisites**: None; handles partial/missing installs.

**Warnings**:
- **Permanently deletes** `~/.local/share/hongguo-native/` — no undo.
- Leaves the `uv` / `7zip` packages (and `jre-openjdk`, if the installer added it) in place — they're generally useful and shared; remove them manually if you want them gone.

---

## install-gpu-lib32.sh

**Purpose**: Detects the GPU vendor(s) via `lspci` and installs the matching 32-bit (lib32) graphics drivers needed for Wine/Proton gaming. Shared helper sourced by both gaming installers so the same scripts work on AMD, Intel, and NVIDIA machines — including multi-GPU setups (e.g. an Intel iGPU + NVIDIA dGPU laptop). Can also be run standalone.

**Usage**:
```bash
./install-gpu-lib32.sh        # standalone
# or, from another script:
source ./install-gpu-lib32.sh && install_gpu_lib32
```

**What it does**:
1. Installs `pciutils` if `lspci` is missing.
2. Always queues `lib32-mesa` (shared 32-bit OpenGL/Vulkan loader bits).
3. Adds `lib32-vulkan-radeon` if an AMD GPU is found, `lib32-vulkan-intel` for Intel, and `lib32-nvidia-utils` for NVIDIA (proprietary driver — swap for `lib32-vulkan-nouveau` on a nouveau-only setup).
4. Deduplicates the list and installs it with `sudo pacman -S --needed --noconfirm`.
5. If no AMD/Intel/NVIDIA GPU is identified (e.g. a VM), installs `lib32-mesa` only and prints a warning to install the vendor driver manually.

**Prerequisites**: `sudo` access; `[multilib]` enabled in `/etc/pacman.conf` (CachyOS default). The AMD matcher is anchored (`amd` / `advanced micro devices` / `ati technologies`) so it does not false-match the "ati" substring inside "VGA comp**ati**ble controller".

**Warnings**:
- Assumes the proprietary NVIDIA driver for NVIDIA GPUs; nouveau users should edit the script.

---

## setup-local-bin-path.sh

**Purpose**: Puts `~/.local/bin` on `PATH` through the systemd user environment for a graphical session. Without this, user-installed launchers such as `launch-battlenet` don't resolve by name, because CachyOS/Arch only add `/usr/local/bin` to `PATH` by default.

> `install-gaming-battlenet.sh` **sources and runs this automatically** (it's the only installer that puts a command in `~/.local/bin`), so you normally don't need to run it by hand. Run it standalone only to add the `--with-bashrc` fallback, or on a machine where you want `~/.local/bin` on PATH independent of the gaming scripts.

**Usage**:
```bash
./setup-local-bin-path.sh                # environment.d for the systemd user environment
./setup-local-bin-path.sh --with-bashrc  # also add a ~/.bashrc fallback for TTY/SSH sessions
```

**What it does**:
1. Ensures `~/.local/bin` exists.
2. Warns if `/usr/lib/systemd/user-environment-generators/30-systemd-environment-d-generator` is missing (meaning the session isn't systemd-managed and `environment.d` won't be honored).
3. Writes `~/.config/environment.d/10-local-bin.conf` with `PATH=${HOME}/.local/bin:${PATH}`. This is read by the systemd user manager and passed to processes that inherit its environment. Overwriting is idempotent — the file *is* the desired state.
4. With `--with-bashrc`, appends a duplicate-guarded `export PATH` to `~/.bashrc` for bare TTY / SSH shells, which don't inherit the graphical session environment.

**Prerequisites**: A systemd user session with the environment.d generator. `bash` for the optional `--with-bashrc` fallback.

**Warnings**:
- `environment.d` applies on the **next re-login** (the user manager reads it at session start). For the current terminal, run `export PATH="$HOME/.local/bin:$PATH"` once.
- Idempotent and safe to re-run, including on a second machine.

---

## install-android-waydroid.sh

**Purpose**: Installs Waydroid (Android via LXC) on CachyOS + Hyprland so Android apps run as native Wayland windows. This script is CachyOS-specific: the kernel ships `binder` built-in, so no DKMS/kernel module steps are needed — the blocker that stops Waydroid on other distros is already solved here.

**Usage**:
```bash
./install-android-waydroid.sh
```

**What it does**:
1. Installs `waydroid` via `sudo pacman -S --needed --noconfirm` (lives in the `extra` sync repo — no AUR).
2. Initializes Waydroid before starting the container service. For a new installation, prompts for the VANILLA or GAPPS image and downloads it via `sudo waydroid init -s <image>` (several GB). Initialization is skipped only when the configuration and system/vendor images are valid; an existing user directory alone is insufficient. Incomplete existing installations are reported without resetting them.
3. Enables and starts `waydroid-container.service` via `systemctl`.
4. Installs `launch-waydroid`, `install-waydroid-apk`, and `install-waydroid-arm` to `~/.local/bin/` (requires `~/.local/bin` on `$PATH`). Installing the ARM helper does not enable translation; run it explicitly when needed.
5. Installs the desktop entry to `~/.local/share/applications/waydroid.desktop` and updates the desktop database.
6. Ensures `~/.local/bin` is on `$PATH` by sourcing [setup-local-bin-path.sh](#setup-local-bin-pathsh) (idempotent).
7. Prints setup completion and platform-specific notes (GAPPS registration, AMD GPU troubleshooting).

**Prerequisites**: `sudo` access (packages and container service require root); `~/.local/bin` must be on `$PATH` for the launcher command to resolve — this script sets it up automatically via `setup-local-bin-path.sh`, but a re-login is required for the current session to see it.

**Notes on system images**:
- **VANILLA** (default): Google-free LineageOS. No registration needed. Recommended.
- **GAPPS** (opt-in): Includes Google Play Services and Play Store. Requires a one-time device registration at `https://www.google.com/android/uncertified` after the first boot (see Warnings below) or Play will refuse to run.

**Notes on ARM apps**:
- Check the Android image architecture and the APK's native library ABIs before considering ARM translation. For Android 13 on x86_64, [install-waydroid-arm.sh](#install-waydroid-armsh) installs the matching libndk or libhoudini package from a pinned revision of [waydroid_script](https://github.com/casualsnek/waydroid_script). Translation is an explicit step and does not guarantee app compatibility.

**Warnings**:
- **The CachyOS kernel has `binder` built in** — no `modprobe` step or binder DKMS is needed or present. Do not add it.
- The first boot can take a moment while the LXC container initializes and the Android system starts.
- **GAPPS device registration required** (if chosen): After the first boot, read the GSF / Android ID and register it at `https://www.google.com/android/uncertified`. Until you do, Google Play will refuse to run. The registration command is printed when the script finishes; re-run it from a Waydroid session shell.
- Test Waydroid window handling in Hyprland and configure window rules if needed.

---

## finish-waydroid-init.py

**Purpose**: Finish a default x86_64 Android 13 initialization after the system image downloaded successfully but the vendor download was interrupted or too slow.

Stop the running initializer with **Ctrl+C** before using this utility. Supply a complete vendor ZIP downloaded from an official SourceForge mirror:

```bash
sudo python3 scripts/finish-waydroid-init.py ~/Downloads/lineage-20.0-20261022-MAINLINE-waydroid_x86_64-vendor.zip
./scripts/install-android-waydroid.sh
```

The utility checks the archive against the current official OTA size and SHA-256, verifies that the system image is current, and refuses a running initializer, an existing rootfs/vendor image, or unexpected configuration. It installs the vendor image, backs up `waydroid.cfg`, updates only the vendor timestamp, and invokes normal initialization with the existing GAPPS/VANILLA choice. Equal image timestamps make Waydroid skip downloading completed images. Official OTA URLs are retained. If the archive or existing system image is stale, recovery stops before making changes.

After successful initialization, rerun the base installer to enable the container and refresh desktop helpers. Then configure ARM translation and test the APK. This recovery utility does not reset an initialized Android system.

---

## launch-waydroid.sh

**Purpose**: Launches Android apps via Waydroid, or opens the full Android UI.

**Usage**:
```bash
launch-waydroid                # open the full Android UI (default)
launch-waydroid --app <package>  # launch a specific Android app by package name
launch-waydroid --ensure-session # wait for Android to boot without opening the UI
launch-waydroid --help         # show help
```

**What it does**:
1. Checks that `waydroid` is installed; exits with an error if not.
2. Ensures the session is running, handling running and frozen sessions, and waits for Android to boot for up to 120 seconds by default. Set `WAYDROID_START_TIMEOUT` to change the timeout.
3. With `--ensure-session`, exits after the session is ready. With `--app <package>`, launches that app via `waydroid app launch <package>`.
4. With no arguments, opens the full Android UI via `waydroid show-full-ui`.

**Prerequisites**: Waydroid must be installed via `install-android-waydroid.sh` first; `~/.local/bin` must be on `$PATH` for the command to resolve.

**Warnings**:
- The first session can take a moment to boot the LXC container. Subsequent launches are faster.
- Auto-generated per-app shortcuts appear in your app menu once you install Android apps via the full UI or Play Store.
- Multi-window apps can carry an app-id like `waydroid.<package>`. Inspect the window in Hyprland before configuring any matching rule.

---

## install-waydroid-apk.sh

**Purpose**: Installs one local standalone APK into Waydroid. The base installer places it at `~/.local/bin/install-waydroid-apk`.

```bash
install-waydroid-apk APK_PATH
install-waydroid-apk --help
```

The helper validates the APK as a ZIP containing `AndroidManifest.xml` and checks native library ABIs under `lib/`. It runs the sibling `launch-waydroid --ensure-session` and refuses installation when Android reports no matching ABI or its ABI list is unavailable. For ARM libraries on x86 Android it also checks that a native bridge is configured. It then runs `waydroid app install` as the desktop user, exposes failures, and lists installed apps. It accepts only one standalone APK; APKS, XAPK, and split APK sets are unsupported. It does not download APKs or install translation automatically.

For example, the Hongguo APK downloaded from the [publisher's site](https://hongguoduanju.com/) on 2026-11-05 is version **7.4.3.32**, package `com.phoenix.read`, SHA-256 `ca3de95c35dac2630e8ffe38ec8875e269472ae3b2ac25643db42c54841d90f1`. Its manifest requires **API 21 (Android 5.0)** and targets API 35; targeting Android 15 does not make Android 15 the minimum. Android 13 supplies API 33 and meets the minimum. This APK contains **ARM64-only** native libraries, so the AMD x86_64 machine needs translation first:

```bash
install-waydroid-arm libndk
install-waydroid-apk ~/Downloads/hongguo.apk
waydroid app list
launch-waydroid --app com.phoenix.read
```

For other APKs, choose the package ID from the app list. Installation and bridge properties are prerequisites; they do not prove Hongguo playback, audio, scrolling, relaunch, or updates. Those require a live session and remain unverified until tested. The APK also declares camera and step-counter features, which may be unavailable in Waydroid. These declarations affect Play Store filtering and are not enforced when sideloading ([Android documentation](https://developer.android.com/guide/topics/manifest/uses-feature-element)). The [unofficial native Hongguo client](#install-hongguosh) remains an alternative. If Android connectivity is diagnosed as a firewall issue, see [fix-waydroid-firewall.sh](#fix-waydroid-firewallsh).

---

## install-waydroid-arm.sh

**Purpose**: Explicitly install an Android 13 ARM translation package on an x86_64 Waydroid host.

```bash
install-waydroid-arm libndk              # AMD
install-waydroid-arm libhoudini          # Intel
install-waydroid-arm --remove libndk     # undo libndk, even if Android cannot boot
```

The helper checks for Android API 33, reuses an already configured bridge, and refuses to replace a conflicting bridge. It requires an explicit `mount_overlays=True` in `/var/lib/waydroid/waydroid.cfg`; direct image modifications are unsupported because the pinned upstream removal path does not mount those images reliably. It installs `git`, `lzip`, and `uv`, checks out upstream revision `48dbfaf34a6ddbe78688c530f9ba1c26522aafb2` under `~/.cache/cachyos-waydroid/`, and creates a temporary Python environment. It invokes the upstream tool with `--android-version 13`, which selects a different translation archive from Android 11. Unknown or modified cached checkouts are rejected.

Setup stops the Android session and restarts its container, so close Android apps first. After installation it waits for Android to boot and checks API 33, the selected bridge, and the advertised `arm64-v8a` ABI. Failed checks report the removal command. Removal does not require a successful Android boot. Neither path wipes app data or changes the Android image flavor; a working bridge still needs app-specific playback testing.

When invoking directly from the repository, use `./scripts/install-waydroid-arm.sh libndk`. After updating these scripts, rerun the base installer to refresh installed helpers.

---

## remove-android-waydroid.sh

**Purpose**: Uninstalls Waydroid, stops the Android container, and optionally deletes downloaded images and app data. Leaves cleanup decisions to the user (large/irreversible steps require confirmation).

**Usage**:
```bash
./remove-android-waydroid.sh
```

**What it does**:
1. Checks if the `waydroid` package is installed; continues (with a note) if it isn't, to clean up any leftover files.
2. Stops the running Waydroid session via `waydroid session stop` (best-effort; ignores errors if already stopped).
3. Disables and stops the `waydroid-container.service` via `systemctl` (best-effort; ignores errors if not running).
4. **Prompts before deleting images and app data** (large, irreversible step): offers to delete `/var/lib/waydroid` (downloaded system/vendor images, multi-GB) and `~/.local/share/waydroid` (your Waydroid profile and all installed app data). If confirmed, deletes both.
5. **Prompts whether to remove the package** (only if it was installed): confirms and runs `sudo pacman -Rns --noconfirm waydroid` if answered yes.
6. Removes `launch-waydroid`, `install-waydroid-apk`, and `install-waydroid-arm` from `~/.local/bin/`. Local APK files are kept. This does not uninstall an ARM bridge or delete the cached upstream checkout; remove a bridge explicitly before removing Waydroid if you are retaining the Android images.
7. Removes the desktop entry at `~/.local/share/applications/waydroid.desktop`.
8. Removes any auto-generated per-app shortcuts at `~/.local/share/applications/waydroid.*.desktop` and updates the desktop database.
9. Prints a summary of what was removed or skipped.

**Prerequisites**: None; the script handles cases where Waydroid or its components are not fully installed.

**Warnings**:
- This script **permanently deletes** the Waydroid images (downloaded Android system) and all app data (every installed app and its settings/files) — there is no undo. The delete step requires explicit confirmation.
- Prompts are non-interactive `[y/N]` (default is No); answer `y` or `Y` to proceed with deletions.
- Leaving `/var/lib/waydroid` and `~/.local/share/waydroid` intact preserves your images and app data — you can reinstall Waydroid later and resume (though this is rare; most users delete everything).

---

## fix-waydroid-firewall.sh

**Purpose**: Fixes the common "Waydroid boots but Android has no internet" problem on this machine, where the host firewall drops the container's forwarded traffic. Waydroid's container service builds a NAT bridge on the `waydroid0` interface (subnet `192.168.240.0/24`) and runs its own dnsmasq on the host for the Android side's DNS/DHCP; if the firewall blocks forwarding or DNS/DHCP from that interface, Android has no connectivity.

**Usage**:
```bash
./fix-waydroid-firewall.sh            # apply the fix
./fix-waydroid-firewall.sh --revert   # undo the firewall rules it added
./fix-waydroid-firewall.sh --help     # show help
```

**What it does**:
1. **Auto-detects the active firewall backend**: `ufw` (what this machine uses — `firewalld` isn't installed) or `firewalld`. If neither is active it just ensures IP forwarding and says there's nothing to open.
2. **Persists IP forwarding** by writing `net.ipv4.ip_forward=1` to `/etc/sysctl.d/99-waydroid-forward.conf` and applying it immediately. (The container service sets this at runtime too; persisting it makes it independent of the service.)
3. **ufw path**: adds a targeted `ufw route allow in on waydroid0` forwarding rule (safer than flipping `DEFAULT_FORWARD_POLICY` to `ACCEPT`, which this machine has set to `DROP` and which would otherwise permit *all* forwarding — ufw's built-in `RELATED,ESTABLISHED` rule handles the return traffic), plus interface-scoped `allow in on waydroid0` rules for DNS (53/udp, 53/tcp) and DHCP (67/udp), then `ufw reload`.
4. **firewalld path**: `firewall-cmd --zone=trusted --add-interface=waydroid0 --permanent` + `--reload`.
5. **Restarts `waydroid-container.service`** (if running) so it re-establishes its network under the new rules; if it isn't running, says the rules apply next time you launch.
6. `--revert` removes the rules it added and deletes the sysctl drop-in.

**Prerequisites**: `sudo` access. The `waydroid0` interface does **not** need to exist yet — the rules reference it by name and apply once the container network comes up. Run this after [install-android-waydroid.sh](#install-android-waydroidsh), only if you actually see no internet inside Android.

**Warnings**:
- This machine uses **ufw**, so the firewalld commands in generic Waydroid guides (the KDE/default path) do **not** apply here — the script picks the ufw path automatically. Don't run the firewalld `firewall-cmd` commands by hand on this box.
- The rules are **idempotent** — re-running is safe (ufw skips rules it already has).
- Rules persist across reboots; use `--revert` to cleanly remove them (the [remover](#remove-android-waydroidsh) does not touch firewall rules).

---

## install-rust.sh

**Purpose**: Installs Rust + Cargo via `rustup` (from the sync repos, not the `curl | sh` installer) and puts `~/.cargo/bin` on `$PATH`.

**Usage**:
```bash
./install-rust.sh
```

**What it does**:
1. Installs `rustup` via `sudo pacman -S --needed --noconfirm`.
2. Sets the default toolchain to `stable` and updates it (an existing `~/.rustup` is reused, not re-downloaded). The default profile includes `rustc`, `cargo`, `rustfmt`, and `clippy`.
3. Writes `~/.config/environment.d/20-cargo-bin.conf` so `cargo install`ed tools in `~/.cargo/bin` are on `$PATH` in the systemd user environment.
4. Prints the installed versions and a quick start.

**Prerequisites**: `sudo` access.

**Warnings**:
- The pacman `rustup` package **conflicts with `rust`** — if the distro `rust` package is installed, pacman will offer to replace it. That's intended.
- `rustc`/`cargo` are proxies in `/usr/bin`, so they work immediately; only `~/.cargo/bin` needs a re-login to appear on `$PATH`.
- To uninstall: `sudo pacman -Rns rustup && rm -rf ~/.rustup ~/.cargo ~/.config/environment.d/20-cargo-bin.conf`.

---

## install-bevy.sh

**Purpose**: Installs the native libraries [Bevy](https://bevy.org) needs to build and run on CachyOS + Hyprland (Wayland, AMD/Vulkan). Rust itself comes from [install-rust.sh](#install-rustsh).

**Usage**:
```bash
./install-rust.sh   # first, if Rust isn't installed
./install-bevy.sh
```

**What it does**:
1. Exits with a pointer to `install-rust.sh` if `cargo` isn't found.
2. Installs `pkgconf`, `clang`, and Bevy's Linux deps (`alsa-lib`, `systemd-libs` for libudev, `libxkbcommon`, `wayland`, `libx11`/`libxcursor`/`libxrandr`/`libxi`, `vulkan-icd-loader`) via `sudo pacman -S --needed --noconfirm`.
3. Warns if no Vulkan ICD is installed, then prints the Bevy quick start, the recommended `[profile.dev]` settings, and an optional per-project mold linker config.

**Prerequisites**: `sudo` access; Rust ([install-rust.sh](#install-rustsh)); a Vulkan driver for your GPU (`vulkan-radeon` on this machine).

**Warnings**:
- Most of these libraries are shared with the desktop, so there's no clean uninstall — `sudo pacman -Rns pkgconf clang` removes the build tools, and pacman refuses anything still in use.

---

## install-golang.sh

**Purpose**: Installs Go and the standard dev tools (`gopls`, `delve`, `golangci-lint`) from the sync repos and puts `~/go/bin` on `$PATH`.

**Usage**:
```bash
./install-golang.sh
```

**What it does**:
1. Installs `go`, `gopls` (language server), `delve` (`dlv` debugger), and `golangci-lint` via `sudo pacman -S --needed --noconfirm`.
2. Writes `~/.config/environment.d/30-go-bin.conf` so `go install`ed tools in `~/go/bin` are on `$PATH` in the systemd user environment.
3. Prints the installed versions, `GOPATH`, and a quick-start / common-commands cheat sheet.

**Prerequisites**: `sudo` access.

**Warnings**:
- `GOPATH` stays at its default `~/go`; an existing module cache in `~/go/pkg/mod` is reused.
- `go` itself is in `/usr/bin` and works immediately; only `~/go/bin` needs a re-login to appear on `$PATH`.
- To uninstall: `sudo pacman -Rns go gopls delve golangci-lint && rm -rf ~/go ~/.cache/go-build ~/.config/environment.d/30-go-bin.conf`.

---

## install-docker.sh

**Purpose**: Installs Docker Engine with the Compose and Buildx plugins, and lets the current user run `docker` without `sudo`.

**Usage**:
```bash
./install-docker.sh
```

**What it does**:
1. Installs `docker`, `docker-compose`, and `docker-buildx` via `sudo pacman -S --needed --noconfirm` (used as `docker compose` / `docker buildx`).
2. Writes `/etc/docker/daemon.json` with container log rotation (3 × 10 MB) — **only if the file doesn't already exist**.
3. Enables `docker.socket`, so the daemon starts on the first `docker` command rather than at boot.
4. Adds `$USER` to the `docker` group (skipped if already a member).
5. Prints versions, a `hello-world` smoke test, and the firewall / boot-start notes below.

**Prerequisites**: `sudo` access.

**Warnings**:
- **Re-login** (or `newgrp docker`) before `docker` works without `sudo`.
- The `docker` group is **root-equivalent** — that's the trade-off for sudo-less docker.
- **ufw does not filter Docker-published ports.** `-p 8080:80` is reachable from the LAN even if ufw would block it. Bind dev services to localhost: `-p 127.0.0.1:8080:80` (Compose: `ports: ["127.0.0.1:8080:80"]`).
- Docker's FORWARD rules sit ahead of ufw's, so container internet and the [Waydroid ufw rules](#fix-waydroid-firewallsh) coexist.
- Containers with `--restart` policies only come back after reboot if you also `sudo systemctl enable docker.service`.
- To uninstall: `sudo systemctl disable --now docker.socket docker.service`, `sudo pacman -Rns docker docker-compose docker-buildx`, `sudo rm -rf /var/lib/docker /var/lib/containerd /etc/docker`, `sudo gpasswd -d $USER docker`.
