"""Thin wrapper around upstream SaveEditor that injects Proton autodetect - freeze aware."""
from __future__ import annotations
import sys
from pathlib import Path

# Freeze-aware paths
try:
    from nms_tui.paths import get_writable_data_dir, get_vendor_dir, get_bundle_dir
    ROOT = get_writable_data_dir()
    BUNDLE = get_bundle_dir()
    VENDOR = get_vendor_dir()
except Exception:
    ROOT = Path(__file__).resolve().parent.parent
    VENDOR = ROOT / "vendor" / "upstream"
    BUNDLE = ROOT

if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from save_editor import SaveEditor  # type: ignore  # noqa: E402
try:
    from nms_tui.proton import find_proton_save_dir  # type: ignore
except ImportError:
    from proton import find_proton_save_dir  # type: ignore

__all__ = ["ProtonSaveEditor", "SaveEditor"]

class ProtonSaveEditor(SaveEditor):
    """SaveEditor that auto-detects Proton save dir on Linux."""

    def __init__(self, save_dir: str | Path | None = None):
        super().__init__()
        try:
            from nms_tui.paths import get_writable_data_dir as _gwd
            self.project_directory = _gwd()
        except Exception:
            self.project_directory = ROOT
        detected = find_proton_save_dir(prefer=save_dir)
        if detected:
            self.save_file_directory = str(detected)
        elif save_dir:
            self.save_file_directory = str(Path(save_dir).expanduser())

    def load_save_files(self, save_file_directory: str | None = None):
        if save_file_directory is None:
            save_file_directory = getattr(self, "save_file_directory", None)
            if save_file_directory is None:
                d = find_proton_save_dir()
                if d:
                    save_file_directory = str(d)
                    self.save_file_directory = save_file_directory
        return super().load_save_files(save_file_directory)

    def _get_ship_ownership(self) -> list[dict] | None:
        if not self.selected_save_file_dict:
            return None
        try:
            from utils.base_or_corvette_detection import find_key_recursively  # type: ignore
            res = list(find_key_recursively(self.selected_save_file_dict, "ShipOwnership"))
            if res:
                _, val = res[0]
                if isinstance(val, list):
                    return val
        except Exception:
            pass
        return None

    def get_base_display_name(self, base: dict, idx: int | None = None) -> str:
        try:
            btype = base.get("BaseType", {}).get("PersistentBaseTypes", "")
        except Exception:
            btype = ""
        name = (base.get("Name") or "").strip()
        if btype == "PlayerShipBase":
            ud = base.get("UserData")
            ships = self._get_ship_ownership()
            if isinstance(ud, int) and ships is not None and 0 <= ud < len(ships):
                ship_name = (ships[ud].get("Name") or "").strip()
                if ship_name:
                    return ship_name
            if name and name != "Default":
                return name
            if idx is not None:
                try:
                    n = self.get_numer_of_components_from_base(base)
                except Exception:
                    n = len(base.get("Objects", [])) if isinstance(base.get("Objects"), list) else 0
                return f"Corvette #{ud if isinstance(ud, int) else idx} ({n} objs)"
            return name or "Corvette"
        if btype == "FreighterBase" and not name:
            return "Freighter Base"
        if name:
            return name
        return f"Unnamed {idx}" if idx is not None else "Unnamed"

    def export_base_as_nmsbase(self, base: dict, out_path: str | Path) -> str:
        import json
        objs = base.get("Objects", [])
        if not isinstance(objs, list):
            objs = []
        p = Path(out_path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        if not objs:
            p.write_text("", encoding="utf-8")
            return str(p)
        if p.exists():
            try:
                from datetime import datetime
                import shutil
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                try:
                    from nms_tui.paths import get_writable_data_dir as _gwd2
                    backups = _gwd2() / "backups" / "nmsbase"
                except Exception:
                    backups = ROOT / "backups" / "nmsbase"
                backups.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, backups / f"{p.stem}_backup_{ts}{p.suffix}")
            except Exception:
                pass
        txt = ",\n" + ",\n".join(json.dumps(o, indent=2, ensure_ascii=False) for o in objs)
        p.write_text(txt, encoding="utf-8")
        return str(p)
