#!/bin/bash

# Install the Hongguo (红果短剧) desktop app -- 100% NATIVE, no Wine/Proton.
#
# Hongguo ships only as a Windows installer, but it's just an NSIS self-extracting
# archive, and nothing in the app that matters is actually Windows-bound (see
# docs/scripts-guide.md for the full investigation). So instead of running the
# setup.exe under Wine, we UNPACK it with 7z and keep only the app's Python
# backend + Java signer jar (discarding the bundled Windows python/ and jre/).
# launch-hongguo then runs that backend on a native Python venv, with the signer
# on the host JVM, and opens the UI in a native browser.
#
# The installer is a versioned NSIS build (hongguo-<ver>-windows-x86_64-setup.exe),
# not a stable vendor URL, so the download link is pinned below and overridable
# with $HONGGUO_INSTALLER_URL.

set -e

# Resolve this script's own dir so the shared helpers are found no matter
# where the script is invoked from.
script_dir="$(dirname "$(realpath "$0")")"
source "$script_dir/setup-local-bin-path.sh"
source "$script_dir/hongguo-common.sh"

if [[ $# -eq 1 && $1 == --launcher-only ]]; then
  if [[ ! -f "$HG_BACKEND/server.py" ]]; then
    echo "Hongguo is not installed. Run this script without --launcher-only first." >&2
    exit 1
  fi
  exec 9>"$HG_HOME/.maintenance.lock"
  if ! flock --exclusive --nonblock 9; then
    echo "Close Hongguo and wait for any upgrade to finish before refreshing its launcher." >&2
    exit 1
  fi
  install_hongguo_launcher "$script_dir"
  setup_local_bin_path
  echo "Hongguo launcher refreshed. Open your app launcher and search for Hongguo."
  exit 0
elif [[ $# -gt 0 ]]; then
  echo "Usage: install-hongguo.sh [--launcher-only]"
  echo "  --launcher-only  Refresh the installed launcher and desktop entry without reinstalling the backend."
  [[ $# -eq 1 && ( $1 == --help || $1 == -h ) ]] && exit 0
  exit 1
fi

# Pinned installer. Override with HONGGUO_INSTALLER_URL=... to use a newer build.
INSTALLER_URL="${HONGGUO_INSTALLER_URL:-https://github.com/waligoraamodio288-rgb/hongguo-desktop-releases/releases/download/v1.0.12/hongguo-1.0.12-windows-x86_64-setup.exe}"

echo "Installing Hongguo..."

# All deps are in the cachyos/Arch sync repos -- no AUR helper, no Wine/Proton.
#   uv    : provisions the native Python venv for launch-hongguo.
#   7zip  : unpacks the NSIS setup.exe without Wine.
#   curl  : downloads the installer and health-checks the backend.
sudo pacman -S --needed --noconfirm uv 7zip curl

# The API signer (unidbg-sign.jar) needs a host JVM. Only install one if there
# isn't already a `java` on PATH -- most CachyOS boxes ship a JDK, and the
# unversioned `jre-openjdk` would otherwise pull a newer JDK (currently 27)
# needlessly. Any mainstream JDK (an LTS like 17/21 is ideal) works.
if ! command -v java >/dev/null 2>&1; then
  echo "No 'java' found; installing a JRE for the signer..."
  sudo pacman -S --needed --noconfirm jre-openjdk
fi

# --- Download the installer -----------------------------------------------------
cache_dir="$HOME/.cache/cachyos-windows"
mkdir -p "$cache_dir"
installer="$cache_dir/$(basename "$INSTALLER_URL")"

if [[ -f $installer ]]; then
  echo "Using cached installer: $installer"
else
  echo
  echo "Downloading Hongguo installer..."
  echo "  $INSTALLER_URL"
  curl --fail --location --retry 3 "$INSTALLER_URL" --output "$installer"
fi

# --- Unpack the backend with 7z (no Wine) --------------------------------------
# Extract only backend/* into a staging dir, drop the bundled Windows python/ and
# jre/ (we use a native venv + the host JVM), then move it into place. ~330MB
# extracts down to ~45MB kept.
echo
echo "Unpacking the app backend..."
staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
7z x -y -o"$staging" "$installer" 'backend/*' >/dev/null
if [[ ! -f "$staging/backend/server.py" ]]; then
  echo "Extraction did not produce the expected backend (no server.py)." >&2
  echo "The installer layout may have changed; check: 7z l '$installer'" >&2
  exit 1
fi
rm -rf "$staging/backend/python" "$staging/backend/jre"

mkdir -p "$HG_HOME"
rm -rf "$HG_BACKEND"
mv "$staging/backend" "$HG_BACKEND"
echo "Backend installed to $HG_BACKEND ($(du -sh "$HG_BACKEND" | cut -f1))."

# --- Install the launcher (with its helpers) + desktop entry --------------------
# launch-hongguo sources hongguo-common.sh and copies hongguo-web/* from its OWN
# directory at runtime, so it can't live alone in ~/.local/bin. Install the whole
# set into a lib dir under $HG_HOME, then symlink the launcher onto PATH -- it
# resolves its real directory via `realpath "$0"`, so the symlink still finds the
# helpers beside the target.
install_hongguo_launcher "$script_dir"

# Make sure ~/.local/bin is on PATH so the `launch-hongguo` command resolves
# (CachyOS doesn't add it by default). The app-menu entry works regardless via
# its absolute Exec above; this is for running the command by name.
setup_local_bin_path

# The UI opens in a native browser; app mode needs a Chromium-class one.
if ! command -v chromium >/dev/null 2>&1 \
   && ! command -v brave >/dev/null 2>&1 \
   && ! command -v google-chrome-stable >/dev/null 2>&1 \
   && ! command -v microsoft-edge-stable >/dev/null 2>&1; then
  echo
  echo "Tip: install a Chromium-class browser for the best experience, e.g.:"
  echo "  sudo pacman -S --needed chromium"
  echo "(Without one, launch-hongguo falls back to your default browser.)"
fi

cat <<EOF

Hongguo is installed (natively — no Wine). Find it in your app launcher, or run:

  launch-hongguo

The first launch installs the backend's Python deps into a venv using your
system Python (one-time); later runs start in about a second. The UI opens in a
native browser (the Windows WebView2 UI is not used). To update later:

  upgrade-hongguo --check
  upgrade-hongguo

Close Hongguo before upgrading. Use upgrade-hongguo --rollback to restore the
previous backend if needed; your data and Python environment are preserved.

(Re-login once so the app launcher and new terminals see ~/.local/bin.)

EOF
