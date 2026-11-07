#!/bin/bash

# Launch Android apps via Waydroid, or show the full Android UI.
# Usage: launch-waydroid [--app <package> | --ensure-session]

set -e

app_package=""
ensure_session=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      if [[ $# -lt 2 || -z "$2" || "$2" == --* ]]; then
        echo "Error: --app requires a package name" >&2
        exit 1
      fi
      app_package="$2"
      shift 2
      ;;
    --ensure-session)
      ensure_session=true
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: launch-waydroid [--app <package> | --ensure-session]

Launch Android apps via Waydroid. If no app is specified, opens the full
Android UI.

Options:
  --app <package>   Launch a specific Android app by package name
  --ensure-session  Wait for Android to be ready without opening the UI
  -h, --help        Show this help message
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Try: launch-waydroid --help" >&2
      exit 1
      ;;
  esac
done

if [[ "$ensure_session" == true && -n "$app_package" ]]; then
  echo "Error: --ensure-session cannot be combined with --app" >&2
  exit 1
fi

timeout=${WAYDROID_START_TIMEOUT-120}
if [[ ! "$timeout" =~ ^[0-9]+$ || "$timeout" =~ ^0+$ || ${#timeout} -gt 9 ]]; then
  echo "Error: WAYDROID_START_TIMEOUT must be a positive integer" >&2
  exit 1
fi
timeout=$((10#$timeout))

# Pre-flight: check if waydroid is installed
if ! command -v waydroid >/dev/null 2>&1; then
  echo "Waydroid is not installed. Run install-android-waydroid.sh first." >&2
  exit 1
fi

SECONDS=0
probe() {
  local remaining=$((timeout - SECONDS))
  ((remaining > 0)) || return 1
  command timeout --kill-after=1 "${remaining}s" waydroid "$@" 2>/dev/null
}

status=$(probe status || true)
start_pid=""
start_log=""
cleanup() {
  if [[ -n "$start_log" ]]; then
    rm -f -- "$start_log"
  fi
}
show_start_log() {
  if [[ -n "$start_log" ]]; then
    tail -c 8192 -- "$start_log" >&2
  fi
}
trap cleanup EXIT
if ((SECONDS < timeout)) && ! grep -qiE '^Session:[[:space:]]*RUNNING' <<< "$status"; then
  start_log=$(mktemp)
  waydroid session start </dev/null >"$start_log" 2>&1 &
  start_pid=$!
fi

while ((SECONDS < timeout)); do
  status=$(probe status || true)
  if grep -qiE '^Session:[[:space:]]*RUNNING' <<< "$status" &&
     grep -qiE '^Container:[[:space:]]*(RUNNING|FROZEN)' <<< "$status" &&
     [[ "$(probe prop get sys.boot_completed || true)" == "1" ]]; then
    if [[ "$ensure_session" == true ]]; then
      exit 0
    fi
    cleanup
    if [[ -n "$app_package" ]]; then
      exec waydroid app launch "$app_package"
    fi
    exec waydroid show-full-ui
  fi

  if [[ -n "$start_pid" ]] && ! kill -0 "$start_pid" 2>/dev/null; then
    if ! wait "$start_pid"; then
      show_start_log
      echo "Error: Waydroid session failed to start" >&2
      exit 1
    fi
    start_pid=""
  fi
  if ((SECONDS < timeout)); then
    sleep 1
  fi
done

show_start_log
echo "Error: timed out waiting for Waydroid to be ready after ${timeout} seconds" >&2
exit 1
