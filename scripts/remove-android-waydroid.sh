#!/bin/bash

# Remove Waydroid: stop the session/container, optionally delete the downloaded
# Android images and app data, remove the package, and clean up the launcher,
# desktop entry, and auto-generated per-app shortcuts.

set -e

installed=true
if ! pacman -Q waydroid &>/dev/null; then
  installed=false
  echo "Waydroid is not installed (pacman -Q waydroid failed)."
  echo "Continuing to clean up any leftover files it may have left behind."
  echo
fi

# Stop the running session and the container service (best-effort).
waydroid session stop 2>/dev/null || true
sudo systemctl disable --now waydroid-container.service 2>/dev/null || true

# Large/irreversible cleanup: downloaded Android images and all app data.
# Separate confirm from package removal because this is the big, unrecoverable one.
echo
echo "The Android images and app data live in:"
echo "  /var/lib/waydroid        (downloaded system/vendor images, multi-GB)"
echo "  $HOME/.local/share/waydroid   (your Waydroid profile and app data)"
echo "Deleting these removes every installed Android app and its data. This cannot be undone."
read -r -p "Delete the downloaded Waydroid images and all app data? [y/N] " ans
[[ $ans == [Yy]* ]] && {
  sudo rm -rf /var/lib/waydroid
  rm -rf "$HOME/.local/share/waydroid"
}

# Remove the package itself (only if it was installed).
if $installed; then
  echo
  read -r -p "Remove the waydroid package (sudo pacman -Rns waydroid)? [y/N] " ans
  [[ $ans == [Yy]* ]] && { sudo pacman -Rns --noconfirm waydroid; }
fi

# Remove the installer's artifacts and any auto-generated per-app shortcuts.
rm -f "$HOME/.local/bin/launch-waydroid"
rm -f "$HOME/.local/bin/install-waydroid-apk"
rm -f "$HOME/.local/bin/install-waydroid-arm"
rm -f "$HOME/.local/share/applications/waydroid.desktop"
rm -f "$HOME"/.local/share/applications/waydroid.*.desktop
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "Done."
echo "Stopped the Waydroid session and container service (if they were running)."
echo "Removed launch-waydroid, install-waydroid-apk, and install-waydroid-arm from ~/.local/bin,"
echo "the desktop entry, and any"
echo "auto-generated Waydroid app shortcuts."
if $installed; then
  echo "If you confirmed the prompt, the waydroid package was removed."
else
  echo "The waydroid package was not installed, so nothing was uninstalled."
fi
echo "The downloaded images and app data in /var/lib/waydroid and ~/.local/share/waydroid"
echo "were deleted only if you confirmed that prompt; otherwise they are left intact."
