#!/usr/bin/env bash
set -euo pipefail

repo="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
output="${1:?Usage: build.sh OUTPUT_DIRECTORY PIP_WHEEL}"
pip_wheel="${2:?Provide a pip wheel from PyPI}"
mkdir -p -- "$output"
output="$(cd -- "$output" && pwd)"
archive="$output/bilibili-cache-linux-x64.tar.gz"
if [[ -e "$archive" ]]; then
    printf 'Archive already exists: %s\n' "$archive" >&2
    exit 1
fi

stage="$(mktemp -d)"
trap 'rm -r -- "$stage"' EXIT
bundle="$stage/Bilibili-Download"
mkdir -p -- "$bundle/app" "$bundle/bootstrap"
cp -- "$repo/Bilibili-Download.sh" "$repo/download-bilibili.sh" "$bundle/"
cp -- "$repo/packaging/portable-readme.txt" "$bundle/README.txt"
cp -- "$pip_wheel" "$bundle/bootstrap/pip.whl"
for file in main.py platform_support.py account_session.py bilibili.py cache_library.py cache_worker.py style.qss requirements.txt; do
    cp -- "$repo/app/$file" "$bundle/app/"
done
tar -czf "$archive" -C "$stage" Bilibili-Download
printf '%s\n' "$archive"
