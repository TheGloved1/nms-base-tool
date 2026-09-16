"""Clipboard helper — wl-copy -> xclip -> xsel -> pyperclip -> file fallback."""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

def copy_text(text: str) -> tuple[bool, str]:
    """Try to copy text to clipboard. Returns (ok, backend_name_or_msg)."""
    # wl-copy (Wayland)
    if shutil.which("wl-copy"):
        try:
            subprocess.run(["wl-copy"], input=text, text=True, check=True, timeout=5)
            return True, "wl-copy"
        except Exception as e:
            pass
    # xclip
    if shutil.which("xclip"):
        try:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, check=True, timeout=5)
            return True, "xclip"
        except Exception:
            pass
    # xsel
    if shutil.which("xsel"):
        try:
            subprocess.run(["xsel", "--clipboard", "--input"], input=text, text=True, check=True, timeout=5)
            return True, "xsel"
        except Exception:
            pass
    # pyperclip fallback
    try:
        import pyperclip  # type: ignore
        pyperclip.copy(text)
        return True, "pyperclip"
    except Exception:
        pass
    return False, "no clipboard tool (install wl-clipboard or xclip)"

def try_paste() -> str | None:
    """Try to paste from clipboard (best effort)."""
    if shutil.which("wl-paste"):
        try:
            r = subprocess.run(["wl-paste"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout:
                return r.stdout
        except Exception:
            pass
    if shutil.which("xclip"):
        try:
            r = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout:
                return r.stdout
        except Exception:
            pass
    try:
        import pyperclip  # type: ignore
        return pyperclip.paste()
    except Exception:
        return None
