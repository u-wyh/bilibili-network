#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}/bilibili-network"
python="$data_dir/linux-app-venv/bin/python"

if [[ ! -x "$python" ]]; then
    if ! python3 -m venv --without-pip "$data_dir/linux-app-venv"; then
        printf '%s\n' '需要 Python 3.10+ 和 venv。Ubuntu 可安装 python3-venv。' >&2
        exit 1
    fi
fi

if ! "$python" -c 'import imageio_ffmpeg, keyring, yt_dlp, PySide6.QtWebEngineWidgets' 2>/dev/null; then
    if "$python" -m pip --version >/dev/null 2>&1; then
        "$python" -m pip install -r "$app_dir/app/requirements.txt"
    elif [[ -f "$app_dir/bootstrap/pip.whl" ]]; then
        PYTHONPATH="$app_dir/bootstrap/pip.whl" "$python" -m pip install -r "$app_dir/app/requirements.txt"
    else
        "$python" -m ensurepip
        "$python" -m pip install -r "$app_dir/app/requirements.txt"
    fi
fi

exec "$python" -B "$app_dir/app/main.py" "$@"
