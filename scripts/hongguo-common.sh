#!/bin/bash

# Shared constants and helpers for the Hongguo install/launch/remove scripts.
# Sourced, not executed.
#
# Hongguo runs 100% NATIVELY on Linux -- no Wine, no Proton. The Windows
# "setup.exe" is just an NSIS self-extracting archive: install-hongguo.sh unpacks
# it with 7z to obtain the app's Python backend + Java signer jar (discarding the
# bundled Windows python/ and jre/). Everything then runs on a native Python venv
# + the host JVM + a native browser. So there is NO Wine prefix; all state lives
# under HG_HOME.

# App home: extracted backend, the native Python venv, and runtime data.
HG_HOME="$HOME/.local/share/hongguo-native"
HG_BACKEND="$HG_HOME/backend"      # unpacked app code (server.py, sign/, frida/, ...)
HG_VENV="$HG_HOME/venv"            # native Python 3.11 venv

# Echo the backend directory (the one holding server.py / desktop_bootstrap.py)
# if the app has been extracted, else empty.
find_backend_dir() {
  [[ -f "$HG_BACKEND/server.py" ]] && printf '%s' "$HG_BACKEND"
}

install_hongguo_launcher() {
  local source_dir="$1" launcher_dir="$HG_HOME/launcher"
  install -Dm755 "$source_dir/launch-hongguo.sh" "$launcher_dir/launch-hongguo"
  install -Dm755 "$source_dir/upgrade-hongguo.sh" "$launcher_dir/upgrade-hongguo"
  install -Dm644 "$source_dir/hongguo-upgrade.py" "$launcher_dir/hongguo-upgrade.py"
  install -Dm644 "$source_dir/hongguo-common.sh" "$launcher_dir/hongguo-common.sh"
  install -Dm644 "$source_dir/hongguo-web/standalone_server.py" "$launcher_dir/hongguo-web/standalone_server.py"
  install -Dm644 "$source_dir/hongguo-web/index.html" "$launcher_dir/hongguo-web/index.html"
  mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
  ln -sf "$launcher_dir/launch-hongguo" "$HOME/.local/bin/launch-hongguo"
  ln -sf "$launcher_dir/upgrade-hongguo" "$HOME/.local/bin/upgrade-hongguo"
  python3 - "$source_dir/../applications/hongguo.desktop" \
    "$HOME/.local/share/applications/hongguo.desktop" "$HOME/.local/bin/launch-hongguo" <<'PY'
from pathlib import Path
import sys

source, destination, executable = sys.argv[1:]
quoted = ''.join('\\' + char if char in '\\"`$' else char for char in executable)
command = ('"' + quoted + '"').replace('\\', '\\\\')
entry = Path(source).read_text().replace('Exec=launch-hongguo', 'Exec=' + command)
Path(destination).write_text(entry)
PY
  update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
}
