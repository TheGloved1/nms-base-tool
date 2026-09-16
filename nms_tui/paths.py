"""Freeze-aware paths for PyInstaller onefile + dev."""
from __future__ import annotations
import os
import sys
from pathlib import Path

def get_bundle_dir() -> Path:
    """Read-only bundle dir: source root when dev, _MEIPASS when frozen."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]

def get_project_root() -> Path:
    return get_bundle_dir()

def get_writable_data_dir() -> Path:
    # Allow override
    env = os.getenv("NMS_DATA_DIR")
    if env:
        p = Path(env).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p
    if getattr(sys, "frozen", False):
        # Bundled binary: prefer XDG data dir for persistence across temp _MEIPASS
        xdg = Path.home() / ".local" / "share" / "nms-proton-tui"
        try:
            xdg.mkdir(parents=True, exist_ok=True)
            # Test writable
            test = xdg / ".write_test"
            test.touch()
            test.unlink()
            return xdg
        except Exception:
            pass
        # Fallback to exe dir portable mode
        exe_dir = Path(sys.executable).parent
        try:
            test = exe_dir / ".write_test"
            test.touch()
            test.unlink()
            return exe_dir
        except Exception:
            pass
        return xdg
    return get_bundle_dir()

def get_backup_save_dir() -> Path:
    return get_writable_data_dir() / "backups" / "save files"

def get_output_dir() -> Path:
    return get_writable_data_dir() / "output"

def get_vendor_dir() -> Path:
    return get_bundle_dir() / "vendor" / "upstream"
