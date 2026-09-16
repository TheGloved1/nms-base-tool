#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
# Prefer single binary if built (PyInstaller output moved to py-dist/ so the
# Tauri+SvelteKit web build can own build/ — see build.sh)
BIN="$DIR/py-dist/nms-proton-gtk"
if [ -x "$BIN" ]; then
  exec "$BIN" "$@"
fi
# Fallback to venv GTK
VENV="$DIR/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating venv..."
  python -m venv "$VENV"
  "$VENV/bin/pip" install -e "$DIR"
fi
exec "$VENV/bin/python" -m nms_gtk.app "$@"
