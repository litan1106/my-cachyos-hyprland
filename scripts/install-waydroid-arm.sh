#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install-waydroid-arm [--remove] libndk|libhoudini
       install-waydroid-arm --help

Install or remove an ARM translation bridge for Waydroid Android 13 on x86_64.
Run as your desktop user. Removing a bridge does not require Android to boot.
EOF
}
if [[ $# == 1 && ( $1 == --help || $1 == -h ) ]]; then usage; exit 0; fi
action=install
if [[ ${1-} == --remove ]]; then action=remove; shift; fi
if [[ $# != 1 || ( $1 != libndk && $1 != libhoudini ) ]]; then usage >&2; exit 1; fi
translator=$1
bridge=libndk_translation.so
[[ $translator == libhoudini ]] && bridge=libhoudini.so
rollback="install-waydroid-arm --remove $translator"
commit=48dbfaf34a6ddbe78688c530f9ba1c26522aafb2
repo=https://github.com/casualsnek/waydroid_script.git
cache="$HOME/.cache/cachyos-waydroid"
checkout="$cache/waydroid_script-$commit"

if [[ $(uname -m) != x86_64 ]]; then echo 'Error: an x86_64 host is required.' >&2; exit 1; fi
if [[ $action == install ]]; then
  script_dir=$(dirname "$(realpath "$0")")
  launcher="$script_dir/launch-waydroid.sh"
  [[ -x $launcher ]] || launcher="$script_dir/launch-waydroid"
  if [[ ! -x $launcher ]]; then echo 'Error: launch-waydroid is missing beside this script.' >&2; exit 1; fi
  "$launcher" --ensure-session
  sdk=$(timeout --kill-after=1 10s waydroid prop get ro.build.version.sdk || true)
  if [[ $sdk != 33 ]]; then echo "Error: Android 13 (SDK 33) is required; detected: ${sdk:-unknown}." >&2; exit 1; fi
  current=$(timeout --kill-after=1 10s waydroid prop get ro.dalvik.vm.native.bridge || true)
  abis=$(timeout --kill-after=1 10s waydroid prop get ro.product.cpu.abilist || true)
  if [[ -z $abis ]]; then echo 'Error: unable to determine Android ABIs.' >&2; exit 1; fi
  if [[ $current == "$bridge" && ,$abis, == *,arm64-v8a,* ]]; then echo "$translator is already configured with arm64-v8a."; exit 0; fi
  if [[ -n $current && $current != 0 && $current != "$bridge" ]]; then echo "Error: conflicting native bridge: $current" >&2; exit 1; fi
fi

if ! python3 - /var/lib/waydroid/waydroid.cfg <<'PYCONFIG'
import configparser
import sys

config = configparser.ConfigParser()
try:
    with open(sys.argv[1]) as f:
        config.read_file(f)
    if not config.has_section('waydroid') or not config.getboolean('waydroid', 'mount_overlays', fallback=False):
        raise ValueError('overlay mode is disabled or configuration is missing')
except (OSError, configparser.Error, ValueError) as error:
    print(f'Error: Waydroid overlay configuration is unsupported or unreadable: {error}', file=sys.stderr)
    sys.exit(1)
PYCONFIG
then
  exit 1
fi

sudo pacman -S --needed git lzip uv
mkdir -p -- "$cache"
if [[ -e $checkout || -L $checkout ]]; then
  if [[ ! -d $checkout/.git ]] || [[ $(git -C "$checkout" remote get-url origin) != "$repo" ]] ||
     [[ $(git -C "$checkout" rev-parse HEAD) != "$commit" ]] || [[ -n $(git -C "$checkout" status --porcelain --untracked-files=all) ]]; then
    echo "Error: refusing to overwrite or use an unknown or modified checkout: $checkout" >&2
    exit 1
  fi
else
  git clone --no-checkout "$repo" "$checkout"
  git -C "$checkout" checkout --detach "$commit"
fi
venv=$(mktemp -d "$cache/arm-venv.XXXXXXXX")
trap 'rm -rf -- "$venv"' EXIT
uv venv "$venv"
uv pip install --python "$venv/bin/python" -r "$checkout/requirements.txt"
waydroid session stop || true
if ! (cd "$checkout" && sudo env PYTHONDONTWRITEBYTECODE=1 "$venv/bin/python" main.py --android-version 13 "$action" "$translator"); then
  echo "Error: upstream $action failed. To remove the selected bridge, run: $rollback" >&2
  exit 1
fi
if ! sudo systemctl restart waydroid-container.service; then
  echo "Error: container restart failed. To remove the selected bridge, run: $rollback" >&2
  exit 1
fi
if [[ $action == install ]]; then
  if ! "$launcher" --ensure-session; then
    echo "Error: Android did not become ready. To remove the selected bridge, run: $rollback" >&2
    exit 1
  fi
  sdk=$(timeout --kill-after=1 10s waydroid prop get ro.build.version.sdk || true)
  current=$(timeout --kill-after=1 10s waydroid prop get ro.dalvik.vm.native.bridge || true)
  abis=$(timeout --kill-after=1 10s waydroid prop get ro.product.cpu.abilist || true)
  if [[ $sdk != 33 || $current != "$bridge" || ,$abis, != *,arm64-v8a,* ]]; then
    echo "Error: bridge verification failed. To remove the selected bridge, run: $rollback" >&2
    exit 1
  fi
fi
echo "$translator $action completed."
