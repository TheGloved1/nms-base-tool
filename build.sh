#!/usr/bin/env bash
# Legacy Python/GTK single-binary build (pre-Tauri implementation).
# PyInstaller work/dist dirs moved to py-build/py-dist so the Tauri+SvelteKit
# web build can own build/ (frontendDist ../build per https://tauri.app/start/frontend/sveltekit/).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating venv..."
  python -m venv "$VENV"
fi
echo "Installing deps..."
"$VENV/bin/pip" install -q -e "$DIR"
"$VENV/bin/pip" show PyGObject >/dev/null 2>&1 || "$VENV/bin/pip" install -q PyGObject
"$VENV/bin/pip" show pyinstaller >/dev/null 2>&1 || "$VENV/bin/pip" install -q pyinstaller
echo "Building single binary (GTK)..."
cd "$DIR"
"$VENV/bin/pyinstaller" nms-proton-gtk.spec --noconfirm --clean --workpath "$DIR/py-build" --distpath "$DIR/py-dist"
echo "Build done: $DIR/py-dist/nms-proton-gtk"
ls -lh "$DIR/py-dist/nms-proton-gtk"
echo "Test headless decompress..."
"$DIR/py-dist/nms-proton-gtk" --test 2>&1 | tail -n 20
