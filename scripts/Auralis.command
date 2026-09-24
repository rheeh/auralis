#!/bin/bash
# Finder can run this file directly or through a desktop symbolic link.
set -euo pipefail
SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SOURCE" ]]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  TARGET="$(readlink "$SOURCE")"
  if [[ "$TARGET" = /* ]]; then SOURCE="$TARGET"; else SOURCE="$DIR/$TARGET"; fi
done
ROOT_DIR="$(cd -P "$(dirname "$SOURCE")/.." && pwd)"
export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
if ! "$ROOT_DIR/SonicVale/.venv/bin/python" "$ROOT_DIR/scripts/start_local.py" "$@"; then
  echo "启动未完成，请查看上方原因。按回车关闭。"
  read -r _
  exit 1
fi
