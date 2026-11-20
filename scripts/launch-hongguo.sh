#!/bin/bash

# Launch Hongguo -- 100% NATIVE, no Wine, no Proton.
# Usage: launch-hongguo [--browser CMD] [--no-open] [--reinstall-deps]
#
# Hongguo (红果短剧) is an unofficial FQNovel desktop client. On Windows it's a
# Tauri shell: a native companion starts a local FastAPI backend and renders the
# UI in bundled Edge/WebView2, streaming video from the backend. The backend
# forges the ByteDance/FQNovel Android API signatures with a Java "signer"
# (unidbg-sign.jar, emulating libmetasec_ml.so), fetches the catalog, and -- the
# key part -- serves *decrypted, seekable MP4* over HTTP.
#
# None of that is actually Windows-bound:
#   * The backend is plain Python; its whole dependency set (requests, fastapi,
#     uvicorn, pycryptodome, av/PyAV, pillow[-heif]) ships as native Linux wheels.
#   * The signer is a Java jar -> runs on the host JVM.
#   * The UI is just HTML/JS -> runs in any native browser.
#   * The crashing piece (Edge/WebView2, which dies in Wine's ole32 COM) is simply
#     not used -- a native browser replaces it, and plain MP4 means H264 "just
#     works" with no codec fight.
#
# So install-hongguo.sh unpacks the setup.exe with 7z (no Wine) and this launcher
# runs the SAME backend on a native Python venv, with the signer on the host JVM,
# and opens the UI in a native browser. See docs/scripts-guide.md for the full
# investigation of how we got here.

set -e

script_dir="$(dirname "$(realpath "$0")")"
source "$script_dir/hongguo-common.sh"

browser_cmd=""
do_open=1
reinstall_deps=0
for ((i=1; i<=$#; i++)); do
  arg="${!i}"
  case "$arg" in
    --browser) ((i++)); browser_cmd="${!i}" ;;
    --no-open) do_open=0 ;;
    --reinstall-deps) reinstall_deps=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: launch-hongguo [--browser CMD] [--no-open] [--reinstall-deps]

Runs the Hongguo backend natively (no Wine) and opens its UI in a native browser.

Options:
  --browser CMD      Browser command to use (default: first Chromium-class
                     browser found, opened in app mode; else xdg-open / $BROWSER).
  --no-open          Start the backend but don't open a browser; print the URL.
  --reinstall-deps   Rebuild the native Python venv from scratch, then run.
EOF
      exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; echo "Try: launch-hongguo --help" >&2; exit 1 ;;
  esac
done

mkdir -p "$HG_HOME"
exec 9>"$HG_HOME/.maintenance.lock"
if ! flock --shared --nonblock 9; then
  echo "Hongguo is being upgraded. Try launching it again when the upgrade finishes." >&2
  exit 1
fi

# --- Locate the extracted backend ----------------------------------------------
backend_dir="$(find_backend_dir)"
if [[ -z $backend_dir ]]; then
  echo "Hongguo is not installed (no backend at $HG_BACKEND)." >&2
  echo "Run install-hongguo.sh first." >&2
  exit 1
fi
signer_jar="$backend_dir/sign/unidbg-sign.jar"
content_config="$backend_dir/guest-config.json"
if [[ ! -f $signer_jar || ! -f $content_config ]]; then
  echo "The Hongguo backend looks incomplete (missing signer jar or guest-config)." >&2
  echo "Try re-running install-hongguo.sh." >&2
  exit 1
fi

host_java="$(command -v java || true)"
if [[ -z $host_java ]]; then
  echo "A host Java runtime is required for the Hongguo signer, but 'java' was" >&2
  echo "not found. Install one with:  sudo pacman -S --needed jre-openjdk" >&2
  exit 1
fi

# --- Provision / reuse the native Python venv ----------------------------------
# Uses the SYSTEM Python (whatever `python3` is) -- the app is pure Python and
# forward-compatible, and all its deps ship binary wheels for current Pythons, so
# there's no need to download a separate runtime. Arch's system Python is
# "externally managed", so we always install into a dedicated venv, never /usr.
# Cached; the first run only downloads the dependencies.
#
# Override the interpreter with HONGGUO_PYTHON=/path/to/pythonX.Y (e.g. point at a
# python3.11 if a future Python ever lacks a wheel for one of the deps).
mkdir -p "$HG_HOME"
py="${HONGGUO_PYTHON:-$(command -v python3)}"

# The exact third-party closure of server.py's imports. Optional deps
# (frida/redis/curl_cffi) are guarded in the code and skipped; pillow + pillow-heif
# render HEIC cover thumbnails in /ui.
venv_deps=(requests fastapi "uvicorn[standard]" pycryptodome av pillow pillow-heif python-dotenv pyyaml)

(( reinstall_deps )) && rm -rf "$HG_VENV"

if [[ ! -x "$HG_VENV/bin/python" ]]; then
  echo "Setting up the Python environment (first run only -- installs the backend's"
  echo "dependencies into a venv using $("$py" --version 2>&1))..."
  if command -v uv >/dev/null 2>&1; then
    uv venv --python "$py" "$HG_VENV"
    uv pip install --python "$HG_VENV/bin/python" --quiet "${venv_deps[@]}"
  else
    "$py" -m venv "$HG_VENV"
    "$HG_VENV/bin/python" -m pip install --quiet --upgrade pip
    "$HG_VENV/bin/python" -m pip install --quiet "${venv_deps[@]}"
  fi
  touch "$HG_VENV/.deps-ok"
elif [[ ! -f "$HG_VENV/.deps-ok" ]]; then
  # venv exists but deps never finished installing -- redo them.
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$HG_VENV/bin/python" --quiet "${venv_deps[@]}"
  else
    "$HG_VENV/bin/python" -m pip install --quiet "${venv_deps[@]}"
  fi
  touch "$HG_VENV/.deps-ok"
fi

# --- Install our standalone entry point + web UI into the backend --------------
# Redone every launch so they survive app updates/reinstalls. standalone_server.py
# sits beside server.py so `import server` resolves; the UI has the per-launch
# session key baked in and is served by the backend's own /ui.
api_key="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
install -Dm644 "$script_dir/hongguo-web/standalone_server.py" "$backend_dir/standalone_server.py"
mkdir -p "$backend_dir/web"
sed "s|__HG_API_KEY__|$api_key|g" "$script_dir/hongguo-web/index.html" > "$backend_dir/web/index.html"

# --- Runtime data dirs ---------------------------------------------------------
data_dir="$HG_HOME/data"
hls_dir="$HG_HOME/hls"
mkdir -p "$hls_dir" "$data_dir/stream-cache"

# --- Pick ports ----------------------------------------------------------------
# The backend uses a STABLE port so the browser can cache cover thumbnails across
# launches: covers load via a keyless /img?url=... proxy sent with a long
# max-age, but the browser keys its cache on the full URL (incl. port) -- a random
# port each launch would silently defeat that and re-download every cover. The
# signer port is internal (backend -> signer only) so a random free one is fine.
# Override the backend port with HONGGUO_PORT if 8793 clashes with something.
free_port() { python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'; }
port_free() { ! ss -ltn 2>/dev/null | grep -q ":$1 "; }
signer_port="$(free_port)"
# Reclaim the stable port from a crashed prior run, then fall back to a random
# port only if something else is holding it.
pkill -f 'standalone_server.py' 2>/dev/null || true
backend_port="${HONGGUO_PORT:-8793}"
if ! port_free "$backend_port"; then
  echo "Port $backend_port is busy; using a random port (cover cache won't persist this run)." >&2
  backend_port="$(free_port)"
fi

# --- Start the host-JVM signer -------------------------------------------------
pkill -f 'com.hongguo.sign.FqTrace' 2>/dev/null || true
signer_log="$(mktemp -t hongguo-signer.XXXXXX.log)"
(
  cd "$backend_dir/sign"
  exec "$host_java" -Djava.net.preferIPv4Stack=true \
    --add-opens java.base/java.lang=ALL-UNNAMED -Xmx512m \
    -cp "$signer_jar" com.hongguo.sign.FqTrace serve "$signer_port"
) >"$signer_log" 2>&1 &
signer_pid=$!

backend_pid=""
cleanup() {
  [[ -n $backend_pid ]] && kill "$backend_pid" 2>/dev/null || true
  kill "$signer_pid" 2>/dev/null || true
  pkill -f 'com.hongguo.sign.FqTrace' 2>/dev/null || true
  pkill -f 'standalone_server.py' 2>/dev/null || true
  rm -f "$signer_log"
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 120); do
  kill -0 "$signer_pid" 2>/dev/null || { echo "The Hongguo signer exited at startup:" >&2; cat "$signer_log" >&2; exit 1; }
  ss -ltn 2>/dev/null | grep -q ":$signer_port " && break
  sleep 0.25
done
echo "Hongguo signer ready on 127.0.0.1:$signer_port (host JVM)."

# --- Start the backend (native Python) -----------------------------------------
# Run from the backend dir so `import server` and its siblings (incl.
# frida/offline_decrypt.py added to sys.path by server.py) resolve to the real
# code. Everything is plain Linux paths -- no C:\ conversion.
backend_log="$(mktemp -t hongguo-backend.XXXXXX.log)"
standalone_log="$HG_HOME/standalone.log"
(
  cd "$backend_dir"
  exec env \
    PORT="$backend_port" \
    SIGN_SERVER="http://127.0.0.1:$signer_port" \
    HONGGUO_SESSION_API_KEY="$api_key" \
    HONGGUO_BACKEND_DATA_DIR="$data_dir" \
    HONGGUO_CONTENT_CONFIG="$content_config" \
    HONGGUO_HLS_WORK_DIR="$hls_dir" \
    HONGGUO_STANDALONE_LOG="$standalone_log" \
    "$HG_VENV/bin/python" -I standalone_server.py
) >"$backend_log" 2>&1 &
backend_pid=$!

url="http://127.0.0.1:$backend_port/ui"
up=0
for _ in $(seq 1 240); do
  kill -0 "$backend_pid" 2>/dev/null || { echo "The Hongguo backend exited at startup:" >&2; tail -20 "$backend_log" >&2
    echo "(standalone log: $standalone_log)" >&2; exit 1; }
  curl -s -o /dev/null -m 2 "http://127.0.0.1:$backend_port/" && { up=1; break; }
  sleep 0.5
done
if (( ! up )); then
  echo "Timed out waiting for the Hongguo backend on $backend_port." >&2
  tail -20 "$backend_log" >&2; exit 1
fi
echo "Hongguo backend ready (native Python): $url"

# --- Open a native browser -----------------------------------------------------
open_browser() {
  if [[ -n $browser_cmd ]]; then "$browser_cmd" "$url" & return; fi
  local b
  for b in chromium brave google-chrome-stable google-chrome chrome microsoft-edge-stable microsoft-edge vivaldi-stable vivaldi; do
    if command -v "$b" >/dev/null 2>&1; then
      # App mode: chromeless, dedicated window; waits so closing it stops the backend.
      "$b" --app="$url" --class=hongguo --user-data-dir="$HOME/.local/share/hongguo-browser" >/dev/null 2>&1
      return 0
    fi
  done
  # Fallback: default browser in a normal tab; we can't track its lifetime.
  ( "${BROWSER:-xdg-open}" "$url" >/dev/null 2>&1 || true ) &
  return 1
}

if (( do_open )); then
  if open_browser; then
    :   # App-mode browser returned -> window was closed -> cleanup via trap.
  else
    echo "Opened in your default browser. Press Ctrl-C here to stop Hongguo."
    wait "$backend_pid"
  fi
else
  echo "Backend running. Open: $url"
  echo "Press Ctrl-C to stop."
  wait "$backend_pid"
fi
