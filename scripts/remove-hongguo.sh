#!/bin/bash

# Remove Hongguo: the extracted backend, native Python venv, runtime data,
# launcher, desktop entry, browser profile, and cached installer.
# (Nothing here touches Wine/Proton -- the native install uses none.)

set -e

# Resolve this script's own dir so the shared helper is found no matter where the
# script is invoked from.
script_dir="$(dirname "$(realpath "$0")")"
source "$script_dir/hongguo-common.sh"

# Stop the backend + host-JVM signer if they're running.
pkill -f 'standalone_server.py' 2>/dev/null || true
pkill -f 'com.hongguo.sign.FqTrace' 2>/dev/null || true
sleep 1

# App home: extracted backend + native venv + data.
rm -rf "$HG_HOME"
# Launcher + desktop entry.
rm -f "$HOME/.local/bin/launch-hongguo"
rm -f "$HOME/.local/bin/upgrade-hongguo"
rm -f "$HOME/.local/share/applications/hongguo.desktop"
# Dedicated browser profile used by launch-hongguo's app-mode window.
rm -rf "$HOME/.local/share/hongguo-browser"
# Cached installer archive.
rm -f "$HOME/.cache/cachyos-windows/"hongguo-*-setup.exe
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "Hongguo has been removed."
