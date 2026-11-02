#!/usr/bin/env bash

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$REPO_DIR/noctalia-v5/omarchy-themes"
CONFIG_DIR="${NOCTALIA_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}}/noctalia"
DATA_DIR="${NOCTALIA_DATA_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}}/noctalia"
PALETTE_DIR="$CONFIG_DIR/palettes"
PLUGIN_DIR="$DATA_DIR/plugins/omarchy-themes"
PLUGIN_ID=my-cachyos-hyprland/omarchy-themes
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --dry-run|--dry) DRY_RUN=true ;;
        --help|-h)
            echo "Usage: ./scripts/setup-omarchy-themes.sh [--dry-run]"
            exit 0
            ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

if (( EUID == 0 )); then
    echo "Run this as the desktop user, without sudo." >&2
    exit 1
fi

if ! command -v noctalia >/dev/null 2>&1; then
    echo "Noctalia v5 is required." >&2
    exit 1
fi

shopt -s nullglob
PALETTES=("$SOURCE_DIR"/palettes/*.json)
PREVIEWS=("$SOURCE_DIR"/plugin/previews/*.png)
PLUGIN_FILES=("$SOURCE_DIR"/plugin/*.luau "$SOURCE_DIR"/plugin/plugin.toml "$SOURCE_DIR"/plugin/LICENSE)
if (( ${#PALETTES[@]} != 12 || ${#PREVIEWS[@]} != 12 )); then
    echo "Expected twelve palettes and twelve previews in $SOURCE_DIR." >&2
    exit 1
fi

noctalia plugins lint "$SOURCE_DIR/plugin"
for palette in "${PALETTES[@]}"; do
    noctalia theme --theme-json "$palette" -o /dev/null
done

copy_if_changed() {
    local source="$1" destination="$2" backup temp
    if [[ -e "$destination" ]] && cmp -s "$source" "$destination"; then
        echo "Unchanged: $destination"
        return
    fi
    if [[ "$DRY_RUN" == true ]]; then
        echo "Would install: $destination"
        return
    fi
    mkdir -p "$(dirname "$destination")"
    temp="$(mktemp "${destination}.tmp.XXXXXX")"
    cp -p "$source" "$temp"
    if [[ -e "$destination" || -L "$destination" ]]; then
        backup="${destination}.bak.$(date +%Y%m%d-%H%M%S).$$"
        cp -a "$destination" "$backup"
        echo "Backed up $destination to $backup"
    fi
    mv -f "$temp" "$destination"
    echo "Installed: $destination"
}

for source in "${PALETTES[@]}"; do
    copy_if_changed "$source" "$PALETTE_DIR/$(basename "$source")"
done
for source in "${PLUGIN_FILES[@]}"; do
    copy_if_changed "$source" "$PLUGIN_DIR/$(basename "$source")"
done
for source in "${PREVIEWS[@]}"; do
    copy_if_changed "$source" "$PLUGIN_DIR/previews/$(basename "$source")"
done

if [[ "$DRY_RUN" == true ]]; then
    echo "Dry run complete. No files changed."
elif noctalia msg status >/dev/null 2>&1; then
    noctalia msg config-reload >/dev/null
    noctalia msg plugins enable "$PLUGIN_ID"
    echo "Open the picker: noctalia msg panel-toggle $PLUGIN_ID:picker"
else
    echo "Files installed. In a Noctalia session, enable the picker with: noctalia msg plugins enable $PLUGIN_ID"
fi
