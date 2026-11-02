#!/usr/bin/env bash

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
HYPR_DIR="$CONFIG_DIR/hypr"
NOCTALIA_DIR="${NOCTALIA_CONFIG_HOME:-$CONFIG_DIR}/noctalia"
SKEL_HYPR=/etc/skel/.config/hypr
SKEL_NOCTALIA=/etc/skel/.config/noctalia/config.toml
NOCTALIA_SOURCE="$REPO_DIR/noctalia-v5/zz-shared.toml"
DRY_RUN=false
WITH_LAYOUT=false
WITH_THEMES=false

usage() {
    echo "Usage: ./install.sh [--profile hypr-v5] [--dry-run] [--with-layout] [--with-themes]"
}

for arg in "$@"; do
    case "$arg" in
        --dry-run|--dry) DRY_RUN=true ;;
        --with-layout) WITH_LAYOUT=true ;;
        --with-themes) WITH_THEMES=true ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

if (( EUID == 0 )); then
    echo "Run this as the desktop user, without sudo." >&2
    exit 1
fi

if ! pacman -Qq cachyos-hypr-noctalia >/dev/null 2>&1; then
    echo "Install the CachyOS profile first: sudo pacman -Syu --needed cachyos-hypr-noctalia" >&2
    exit 1
fi

shopt -s nullglob
HYPR_SOURCES=("$REPO_DIR"/hypr/config/my_*.lua)
if (( ${#HYPR_SOURCES[@]} == 0 )) || [[ ! -f "$REPO_DIR/hypr/config/my_desktop.lua" ]]; then
    echo "Missing Hyprland profile files under $REPO_DIR/hypr/config." >&2
    exit 1
fi
if [[ "$WITH_LAYOUT" == true && ! -f "$NOCTALIA_SOURCE" ]]; then
    echo "Missing Noctalia v5 profile: $NOCTALIA_SOURCE" >&2
    exit 1
fi

if [[ ! -f "$HYPR_DIR/hyprland.lua" ]]; then
    if [[ -e "$HYPR_DIR" ]]; then
        echo "$HYPR_DIR exists without hyprland.lua; inspect it before installing the CachyOS base." >&2
        exit 1
    fi
    if [[ ! -f "$SKEL_HYPR/hyprland.lua" ]]; then
        echo "CachyOS Hyprland base is missing from $SKEL_HYPR." >&2
        exit 1
    fi
    LOADER="$SKEL_HYPR/hyprland.lua"
else
    LOADER="$HYPR_DIR/hyprland.lua"
fi

if ! grep -Fq 'require("config.binds")' "$LOADER"; then
    echo "Unknown CachyOS Hyprland loader in $LOADER; no files changed." >&2
    exit 1
fi

for source in "${HYPR_SOURCES[@]}"; do
    luac -p "$source"
done
if [[ "$WITH_LAYOUT" == true ]]; then
    noctalia config validate "$NOCTALIA_SOURCE"
fi

backup_file() {
    local path="$1"
    local backup="${path}.bak.$(date +%Y%m%d-%H%M%S).$$"
    cp -a "$path" "$backup"
    echo "Backed up $path to $backup"
}

copy_if_changed() {
    local source="$1" destination="$2" temp
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
        backup_file "$destination"
    fi
    mv -f "$temp" "$destination"
    echo "Installed: $destination"
}

if [[ ! -f "$HYPR_DIR/hyprland.lua" ]]; then
    if [[ "$DRY_RUN" == true ]]; then
        echo "Would copy CachyOS Hyprland base: $SKEL_HYPR -> $HYPR_DIR"
    else
        mkdir -p "$CONFIG_DIR"
        cp -a "$SKEL_HYPR" "$HYPR_DIR"
        echo "Copied CachyOS Hyprland base to $HYPR_DIR"
    fi
fi

for source in "${HYPR_SOURCES[@]}"; do
    copy_if_changed "$source" "$HYPR_DIR/config/$(basename "$source")"
done

if ! grep -Fq 'require("config.my_desktop")' "$LOADER"; then
    if [[ "$DRY_RUN" == true ]]; then
        echo "Would add require(\"config.my_desktop\") to $HYPR_DIR/hyprland.lua"
    else
        loader="$HYPR_DIR/hyprland.lua"
        temp="$(mktemp "${loader}.tmp.XXXXXX")"
        cp -p "$loader" "$temp"
        printf '\nrequire("config.my_desktop")\n' >> "$temp"
        backup_file "$loader"
        mv -f "$temp" "$loader"
        echo "Added custom profile loader to $loader"
    fi
fi

if [[ ! -f "$NOCTALIA_DIR/config.toml" && -f "$SKEL_NOCTALIA" ]]; then
    copy_if_changed "$SKEL_NOCTALIA" "$NOCTALIA_DIR/config.toml"
fi
if [[ "$WITH_LAYOUT" == true ]]; then
    copy_if_changed "$NOCTALIA_SOURCE" "$NOCTALIA_DIR/zz-shared.toml"
fi

if [[ "$DRY_RUN" == true ]]; then
    echo "Dry run complete. No files changed."
else
    noctalia config validate "$NOCTALIA_DIR"
    echo "Profile staged. Log into Hyprland (UWSM) from SDDM to test it."
fi

if [[ "$WITH_THEMES" == true ]]; then
    if [[ "$DRY_RUN" == true ]]; then
        "$REPO_DIR/scripts/setup-omarchy-themes.sh" --dry-run
    else
        "$REPO_DIR/scripts/setup-omarchy-themes.sh"
    fi
fi
