#!/bin/bash
set -e
script_dir="$(dirname "$(realpath "$0")")"
source "$script_dir/hongguo-common.sh"
exec python3 "$script_dir/hongguo-upgrade.py" --home "$HG_HOME" --scripts-dir "$script_dir" "$@"
