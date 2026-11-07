#!/bin/bash

# Install a local standalone APK into the current user's Waydroid session.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install-waydroid-apk APK_PATH
       install-waydroid-apk --help

Validate and install one local standalone APK. Starts Android if needed,
without opening the full UI, then lists apps so you can confirm installation.
Run as your desktop user, without sudo. Split APK sets and XAPK/APKS bundles
are not supported. ARM translation is never installed automatically.
EOF
}

if [[ $# == 1 && ( "$1" == --help || "$1" == -h ) ]]; then
  usage
  exit 0
fi
if [[ $# != 1 || "$1" == --* ]]; then
  usage >&2
  exit 1
fi
if [[ ! -f "$1" || ! -r "$1" ]]; then
  echo "Error: APK must be a readable file: $1" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required to validate APK files." >&2
  exit 1
fi

apk_path=$(realpath -e -- "$1")
apk_abis=$(python3 - "$apk_path" <<'PY'
import sys
import zipfile

try:
    with zipfile.ZipFile(sys.argv[1]) as apk:
        manifest = apk.getinfo('AndroidManifest.xml')
        if manifest.is_dir() or manifest.file_size == 0:
            raise ValueError('AndroidManifest.xml is empty')
        corrupt = apk.testzip()
        if corrupt:
            raise ValueError(f'corrupt archive member: {corrupt}')
        abis = set()
        for name in apk.namelist():
            parts = name.split('/')
            if len(parts) == 3 and parts[0] == 'lib' and parts[2].endswith('.so'):
                abis.add(parts[1])
        print(','.join(sorted(abis)))
except (OSError, ValueError, KeyError, RuntimeError, EOFError, zipfile.BadZipFile) as error:
    print(f'Error: not a valid standalone APK: {error}', file=sys.stderr)
    sys.exit(1)
PY
)

script_dir=$(dirname "$(realpath "$0")")
launcher="$script_dir/launch-waydroid.sh"
if [[ ! -x "$launcher" ]]; then
  launcher="$script_dir/launch-waydroid"
fi
if [[ ! -x "$launcher" ]]; then
  echo "Error: launch-waydroid is missing beside this script. Re-run install-android-waydroid.sh." >&2
  exit 1
fi
"$launcher" --ensure-session

if [[ -n "$apk_abis" ]]; then
  echo "APK native ABIs: $apk_abis"
  android_abis=$(timeout --kill-after=1 10s waydroid prop get ro.product.cpu.abilist || true)
  if [[ -n "$android_abis" ]]; then
    echo "Android ABIs: $android_abis"
    compatible=false
    native_match=false
    IFS=, read -r -a abis <<< "$apk_abis"
    for abi in "${abis[@]}"; do
      if [[ ",$android_abis," == *",$abi,"* ]]; then
        compatible=true
        if [[ "$abi" != arm* ]]; then
          native_match=true
        fi
      fi
    done
    if [[ "$compatible" == false ]]; then
      echo "Error: no matching native ABI. ARM-only APKs on x86 Android require ARM translation." >&2
      echo "For Android 13, run install-waydroid-arm libndk (AMD) or install-waydroid-arm libhoudini (Intel)." >&2
      exit 1
    fi
    if [[ "$native_match" == false ]]; then
      primary_abi=$(timeout --kill-after=1 10s waydroid prop get ro.product.cpu.abi || true)
      if [[ "$primary_abi" == x86* ]]; then
        bridge=$(timeout --kill-after=1 10s waydroid prop get ro.dalvik.vm.native.bridge || true)
        if [[ -z "$bridge" || "$bridge" == 0 ]]; then
          echo "Error: Android advertises ARM ABIs but has no native bridge configured. Install ARM translation first." >&2
          exit 1
        fi
        echo "ARM native bridge: $bridge"
      elif [[ "$primary_abi" != arm* ]]; then
        echo "Error: could not verify native ARM support or an x86 translation bridge." >&2
        exit 1
      fi
    fi
  else
    echo "Error: could not determine Android ABIs; refusing to install an APK with native libraries." >&2
    exit 1
  fi
fi

# Some Waydroid failures are logged without a nonzero process exit status.
install_output=$(mktemp)
trap 'rm -f "$install_output"' EXIT
install_status=0
waydroid app install "$apk_path" >"$install_output" 2>&1 || install_status=$?
cat "$install_output" >&2
if (( install_status != 0 )) || grep -qiE '(^|[[:space:]])(ERROR:|Failure([[:space:]]|$)|Failed([[:space:]]|$)|INSTALL_FAILED_)' "$install_output"; then
  echo "Error: Waydroid could not install the APK. Review the output above." >&2
  exit 1
fi

echo "Install request completed. Confirm your app appears in the list below:"
waydroid app list
echo
echo 'Launch it from your app menu, or use: launch-waydroid --app PACKAGE_NAME'
