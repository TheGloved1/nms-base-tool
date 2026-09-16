"""System file-manager save dialog — zenity/kdialog/yad → fallback InputScreen."""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

def _zenity_save(suggested: Path, title: str) -> str | None:
    if not shutil.which("zenity"):
        return None
    # zenity --file-selection --save --confirm-overwrite --title --filename
    cmd = [
        "zenity",
        "--file-selection",
        "--save",
        "--confirm-overwrite",
        f"--title={title}",
        f"--filename={str(suggested)}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None

def _kdialog_save(suggested: Path, title: str) -> str | None:
    if not shutil.which("kdialog"):
        return None
    cmd = ["kdialog", "--getsavefilename", str(suggested), title]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None

def _yad_save(suggested: Path, title: str) -> str | None:
    if not shutil.which("yad"):
        return None
    cmd = ["yad", "--file", "--save", "--confirm-overwrite", f"--title={title}", f"--filename={str(suggested)}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None

def ask_save_path_sync(suggested: Path, title: str = "Save file") -> str | None:
    """Try system dialogs synchronously; returns path string or None if cancelled/unavailable."""
    for fn in (_zenity_save, _kdialog_save, _yad_save):
        r = fn(suggested, title)
        if r is not None:
            return r
        # If dialog was attempted but cancelled, zenity returns 1 with empty stdout → we return None to signal cancel
        # Continue only if tool not present
    return None

def _zenity_open(title: str, start_dir: Path | None = None) -> str | None:
    if not shutil.which("zenity"):
        return None
    cmd = ["zenity", "--file-selection", f"--title={title}"]
    if start_dir:
        cmd.append(f"--filename={str(start_dir)}/")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None

def _kdialog_open(title: str, start_dir: Path | None = None) -> str | None:
    if not shutil.which("kdialog"):
        return None
    cmd = ["kdialog", "--getopenfilename", str(start_dir) if start_dir else "", title]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None

def _yad_open(title: str, start_dir: Path | None = None) -> str | None:
    if not shutil.which("yad"):
        return None
    cmd = ["yad", "--file", f"--title={title}"]
    if start_dir:
        cmd.append(f"--filename={str(start_dir)}/")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None

def ask_open_path_sync(title: str = "Open file", start_dir: Path | None = None) -> str | None:
    """Try system dialogs for open file; returns path or None if cancelled/unavailable."""
    for fn in (_zenity_open, _kdialog_open, _yad_open):
        r = fn(title, start_dir)
        if r is not None:
            return r
    return None

def has_system_dialog() -> bool:
    return any(shutil.which(x) for x in ("zenity", "kdialog", "yad"))

def reveal_in_file_manager(path: Path) -> bool:
    """Try to reveal file/dir in system file manager (xdg-open/dolphin/nautilus)."""
    target = path if path.is_dir() else path.parent
    for cmd in (["xdg-open", str(target)], ["gio", "open", str(target)], ["exo-open", str(target)]):
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
                return True
            except Exception:
                continue
    return False
