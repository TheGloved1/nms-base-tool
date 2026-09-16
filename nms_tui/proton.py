"""Proton save autodetect — replaces utils/file_utils.get_default_save_directory() which is Windows-only."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

APPID = "275850"
SUB = Path("drive_c/users/steamuser/AppData/Roaming/HelloGames/NMS")

def _candidate_roots() -> list[Path]:
    h = Path.home()
    # Prefer explicit .local/share first (user's actual path), then .steam symlink
    roots = [
        h / ".local/share/Steam/steamapps/compatdata" / APPID / "pfx" / SUB,
        h / ".steam/steam/steamapps/compatdata" / APPID / "pfx" / SUB,
        h / ".var/app/com.valvesoftware.Steam/data/Steam/steamapps/compatdata" / APPID / "pfx" / SUB,
        h / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/compatdata" / APPID / "pfx" / SUB,
        h / "snap/steam/common/.local/share/Steam/steamapps/compatdata" / APPID / "pfx" / SUB,
        h / ".steam/steam/steamapps/common/No Man's Sky",  # native fallback (unlikely)
    ]
    # dedupe preserve order
    seen = set()
    out = []
    for p in roots:
        s = str(p)
        if s not in seen:
            seen.add(s)
            out.append(p)
    return out

def find_proton_save_dirs() -> list[Path]:
    """Return all st_* dirs that exist under known Proton roots."""
    found: list[Path] = []
    for root in _candidate_roots():
        if not root.exists():
            continue
        try:
            for name in os.listdir(root):
                if "st_" in name:
                    d = root / name
                    if d.is_dir():
                        found.append(d)
        except PermissionError:
            continue
    return found

def find_proton_save_dir(prefer: Optional[str | Path] = None) -> Optional[Path]:
    """Autodetect single best save dir. Env $NMS_SAVE_DIR wins, then prefer arg, then first with save*.hg."""
    # 1. env override
    env = os.getenv("NMS_SAVE_DIR")
    if env:
        p = Path(env).expanduser()
        if p.exists() and p.is_dir():
            return p
        # also allow file path -> parent
        if p.exists() and p.is_file():
            return p.parent
    if prefer:
        p = Path(prefer).expanduser()
        if p.exists():
            return p if p.is_dir() else p.parent
    dirs = find_proton_save_dirs()
    if not dirs:
        return None
    # prefer one containing save.hg/save2.hg
    for d in dirs:
        try:
            files = os.listdir(d)
            if any(f.startswith("save") and f.endswith(".hg") for f in files):
                return d
        except OSError:
            continue
    return dirs[0]

def list_save_files(save_dir: Path | str) -> list[Path]:
    """List save*.hg files in dir sorted by mtime desc."""
    p = Path(save_dir)
    if not p.exists() or not p.is_dir():
        return []
    try:
        files = [p / f for f in os.listdir(p) if f.startswith("save") and f.endswith(".hg")]
    except OSError:
        return []
    files.sort(key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True)
    return files
