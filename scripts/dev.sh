#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/SonicVale"
FRONTEND_DIR="$ROOT_DIR/sonicvale-front"
export AURALIS_CONFIG_DIR="${AURALIS_CONFIG_DIR:-$ROOT_DIR/.local-data}"
mkdir -p "$AURALIS_CONFIG_DIR"

PYTHON_BIN="${AURALIS_PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 python3.12; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "Auralis 需要 Python 3.12。请先安装 python@3.12，或通过 AURALIS_PYTHON 指定解释器。" >&2
  exit 1
fi

if [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  VENV_MINOR="$($BACKEND_DIR/.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [[ "$VENV_MINOR" != "3.12" ]]; then
    rm -rf "$BACKEND_DIR/.venv"
  fi
fi

if [[ ! -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv"
fi

"$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  npm --prefix "$FRONTEND_DIR" install --registry=https://registry.npmmirror.com
fi

if [[ ! -x "$FRONTEND_DIR/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron" \
   && ! -x "$FRONTEND_DIR/node_modules/electron/dist/electron" \
   && ! -x "$FRONTEND_DIR/node_modules/electron/dist/electron.exe" ]]; then
  npm --prefix "$FRONTEND_DIR" rebuild electron --registry=https://registry.npmmirror.com
fi

cleanup() {
  jobs -p | xargs -r kill
}
trap cleanup EXIT

(
  cd "$BACKEND_DIR"
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8200
) &

(
  cd "$FRONTEND_DIR"
  npm run dev -- --host 127.0.0.1
) &

wait
