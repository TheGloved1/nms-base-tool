#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable, Footer, Header, Input, Static, TextArea
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual import on

# Ensure vendor on path before importing editor - freeze aware
try:
    from nms_tui.paths import get_bundle_dir, get_writable_data_dir, get_vendor_dir
    ROOT = get_writable_data_dir()
    BUNDLE = get_bundle_dir()
    VENDOR = get_vendor_dir()
except Exception:
    ROOT = Path(__file__).resolve().parent.parent
    VENDOR = ROOT / "vendor" / "upstream"
    BUNDLE = ROOT
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from nms_tui.proton import find_proton_save_dir, list_save_files  # noqa: E402
from nms_tui.editor import ProtonSaveEditor  # noqa: E402
from nms_tui.clipboard import copy_text, try_paste  # noqa: E402
from nms_tui.file_dialog import ask_open_path_sync, ask_save_path_sync, has_system_dialog, reveal_in_file_manager  # noqa: E402


# For safe filename like upstream save_editor.py:309
def safe_name(name: str) -> str:
    s = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    s = s.replace(" ", "_")
    return s or "unnamed_base"


BACKUP_SAVE_DIR = ROOT / "backups" / "save files"


class ConfirmScreen(ModalScreen[bool]):
    def __init__(self, message: str, ok_label="OK", cancel_label="Cancel"):
        super().__init__()
        self.message = message
        self.ok_label = ok_label
        self.cancel_label = cancel_label

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(self.message, id="confirm-msg"),
            Horizontal(
                Button(self.ok_label, variant="primary", id="confirm-ok"),
                Button(self.cancel_label, variant="default", id="confirm-cancel"),
                id="confirm-btns",
            ),
            id="confirm-dialog",
        )

    @on(Button.Pressed, "#confirm-ok")
    def ok(self):
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-cancel")
    def cancel(self):
        self.dismiss(False)


class InputScreen(ModalScreen[str | None]):
    def __init__(self, prompt: str, placeholder: str = "", initial: str = ""):
        super().__init__()
        self.prompt = prompt
        self.placeholder = placeholder
        self.initial = initial

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(self.prompt, id="input-prompt"),
            Input(placeholder=self.placeholder, value=self.initial, id="input-field"),
            Horizontal(
                Button("OK", variant="primary", id="input-ok"),
                Button("Cancel", id="input-cancel"),
                id="input-btns",
            ),
            id="input-dialog",
        )

    def on_mount(self):
        self.query_one("#input-field", Input).focus()

    @on(Button.Pressed, "#input-ok")
    def ok(self):
        v = self.query_one("#input-field", Input).value.strip()
        self.dismiss(v if v else None)

    @on(Button.Pressed, "#input-cancel")
    def cancel(self):
        self.dismiss(None)

    @on(Input.Submitted)
    def submit(self, e: Input.Submitted):
        if e.input.id == "input-field":
            v = e.value.strip()
            self.dismiss(v if v else None)


class JsonViewScreen(ModalScreen[None]):
    def __init__(self, title: str, json_text: str):
        super().__init__()
        self.title_text = title
        self.json_text = json_text

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(self.title_text, id="json-title"),
            TextArea(self.json_text, read_only=True, language="json", id="json-area"),
            Horizontal(
                Button("Copy", variant="primary", id="json-copy"),
                Button("Close", id="json-close"),
                id="json-btns",
            ),
            id="json-dialog",
        )

    @on(Button.Pressed, "#json-copy")
    def do_copy(self):
        ok, backend = copy_text(self.json_text)
        self.notify(
            f"Copied via {backend}" if ok else f"Clipboard failed: {backend}",
            severity="information" if ok else "warning",
        )

    @on(Button.Pressed, "#json-close")
    def close(self):
        self.dismiss(None)


class RestoreScreen(ModalScreen[Path | None]):
    """Pick a backup .hg to restore over the live save file."""

    def __init__(self, save_name: str, backups: list[Path]):
        super().__init__()
        self.save_name = save_name
        self.backups = backups
        self.selected: Path | None = backups[0] if backups else None

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(f"Restore '{self.save_name}' — pick a backup to overwrite the live save:", id="restore-title"),
            Static(
                "Backups are in backups/save files/. The current live file will be backed up again before restore. Close NMS first!",
                id="restore-hint",
            ),
            DataTable(id="restore-table", cursor_type="row"),
            Horizontal(
                Button("Restore", variant="error", id="restore-do"),
                Button("Reveal in file manager", id="restore-reveal"),
                Button("Cancel", id="restore-cancel"),
                id="restore-btns",
            ),
            id="restore-dialog",
        )

    def on_mount(self):
        table = self.query_one("#restore-table", DataTable)
        table.add_columns("Backup file", "Size", "Modified")
        for p in self.backups:
            try:
                sz = p.stat().st_size
                szs = f"{sz / 1024 / 1024:.2f} MB" if sz > 1024 * 1024 else f"{sz / 1024:.0f} KB"
                mt = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            except OSError:
                szs, mt = "?", "?"
            table.add_row(p.name, szs, mt, key=str(p))
        if self.backups:
            table.move_cursor(row=0)
            self.selected = self.backups[0]

    @on(DataTable.RowSelected, "#restore-table")
    def _selected(self, e: DataTable.RowSelected):
        if e.row_key.value:
            self.selected = Path(e.row_key.value)

    @on(Button.Pressed, "#restore-do")
    def _do(self):
        self.dismiss(self.selected)

    @on(Button.Pressed, "#restore-cancel")
    def _cancel(self):
        self.dismiss(None)

    @on(Button.Pressed, "#restore-reveal")
    def _reveal(self):
        # Reveal the backups folder, don't dismiss
        try:
            reveal_in_file_manager(BACKUP_SAVE_DIR)
            self.notify(f"Opened {BACKUP_SAVE_DIR}", timeout=3)
        except Exception:
            pass


class NMSApp(App):
    CSS = """
    #left { width: 36; min-width: 32; background: $surface; padding: 1; }
    #right { width: 1fr; background: $panel; padding: 1; }
    #confirm-dialog, #input-dialog { width: 70; height: auto; background: $panel; border: thick $primary; padding: 1 2; }
    #json-dialog { width: 78; height: 85%; background: $panel; border: thick $primary; padding: 1 2; }
    #restore-dialog { width: 80; height: auto; max-height: 85%; background: $panel; border: thick $primary; padding: 1 2; }
    #confirm-btns, #input-btns, #json-btns, #restore-btns { align: center middle; height: 3; }
    #confirm-msg { width: 100%; text-align: center; padding: 1; }
    #input-prompt { padding: 1 0; }
    #json-area { height: 1fr; }
    #json-title, #restore-title { text-style: bold; padding-bottom: 1; }
    #restore-hint { color: $warning; padding-bottom: 1; }
    #restore-table { height: 12; }
    #action-row { height: auto; }
    DataTable { height: 1fr; }
    Button { margin: 0 1; }
    #status { height: 3; background: $surface; padding: 0 1; }
    #type-row { height: 3; align: center middle; }
    """
    TITLE = "NMS Proton TUI — Base → Base Builder"
    SUB_TITLE = "Proton/Linux (compatdata 275850)"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("e", "export_base", "Export JSON"),
        ("E", "export_nmsbase", "Export NMSBASE"),
        ("v", "view_json", "View JSON"),
        ("i", "import_base", "Import"),
        ("r", "recompress", "Recompress"),
        ("c", "filter_corvettes", "Corvettes"),
        ("p", "filter_planetary", "Planetary"),
        ("b", "filter_both", "Both"),
        ("ctrl+b", "backup_save", "Backup Save"),
        ("ctrl+r", "restore_save", "Restore Save"),
        ("?", "help", "Help"),
    ]

    def __init__(self, save_dir: str | Path | None = None):
        super().__init__()
        self.save_dir: Path | None = (
            Path(save_dir).expanduser() if save_dir else find_proton_save_dir()
        )
        self.editor = ProtonSaveEditor(save_dir=self.save_dir)
        self.save_files: list[Path] = []
        self.selected_save: Path | None = None
        self.selected_base_type: str | None = None  # None = Both
        self.all_bases: list[dict] = []
        self.filtered: list[tuple[int, dict]] = []  # (global_index, base)
        self.selected_base_global_index: int | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left"):
                yield Static("Save dir:", id="save-dir-label")
                yield Static(
                    str(self.save_dir) if self.save_dir else "[no dir found]",
                    id="save-dir-value",
                )
                yield Static("Saves:", id="saves-label")
                yield DataTable(id="saves-table", cursor_type="row")
                with Horizontal(id="type-row"):
                    yield Button("Corvettes", id="btn-corvettes", variant="default")
                    yield Button("Planetary", id="btn-planetary", variant="default")
                    yield Button("Both", id="btn-both", variant="primary")
                yield Static("", id="counts")
                with Horizontal():
                    yield Button("Load", variant="primary", id="btn-load")
                    yield Button("Change dir", id="btn-chdir")
                with Horizontal():
                    yield Button("Backup", variant="default", id="btn-backup")
                    yield Button("Restore…", variant="default", id="btn-restore")
                yield Static("", id="save-status")
            with Vertical(id="right"):
                yield Static(
                    "Bases — pick one to Export → Base Builder", id="bases-title"
                )
                yield DataTable(id="bases-table", cursor_type="row")
                with Horizontal(id="action-row"):
                    yield Button("Export [e]", variant="success", id="btn-export")
                    yield Button("NMSBASE [E]", variant="primary", id="btn-export-nmsbase")
                    yield Button("View [v]", id="btn-view")
                    yield Button("Import [i]", variant="warning", id="btn-import")
                    yield Button("Recompress [r]", variant="error", id="btn-recompress")
                yield Static("", id="action-status")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self):
        self.query_one("#saves-table", DataTable).add_columns(
            "Save", "Size", "Modified"
        )
        self.query_one("#bases-table", DataTable).add_columns(
            "Idx", "Name", "Type", "Objects", "Owner UID"
        )
        self.refresh_saves()
        self.update_status("Ready. Autodetected Proton dir. Select save → Load.")

    def refresh_saves(self):
        table = self.query_one("#saves-table", DataTable)
        table.clear()
        self.save_files = []
        if not self.save_dir or not self.save_dir.exists():
            self.query_one("#save-dir-value", Static).update(
                f"[red]Not found: {self.save_dir} — set $NMS_SAVE_DIR[/]"
            )
            return
        self.query_one("#save-dir-value", Static).update(str(self.save_dir))
        files = list_save_files(self.save_dir)
        self.save_files = files
        for p in files:
            try:
                sz = p.stat().st_size
                mt = datetime.fromtimestamp(p.stat().st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                )
                szs = (
                    f"{sz / 1024 / 1024:.2f} MB"
                    if sz > 1024 * 1024
                    else f"{sz / 1024:.0f} KB"
                )
            except OSError:
                szs, mt = "?", "?"
            table.add_row(p.name, szs, mt, key=str(p))
        if files:
            table.move_cursor(row=0)
            self.selected_save = files[0]
        self.query_one("#save-status", Static).update(f"{len(files)} save(s)")

    def update_status(self, msg: str):
        self.query_one("#status", Static).update(msg)
        self.notify(msg, timeout=3)

    @on(DataTable.RowSelected, "#saves-table")
    def saves_selected(self, e: DataTable.RowSelected):
        k = e.row_key.value
        if k:
            self.selected_save = Path(k)
            self.update_status(f"Selected save: {Path(k).name} — press Load")

    @on(Button.Pressed, "#btn-load")
    def do_load(self):
        if not self.selected_save:
            if self.save_files:
                self.selected_save = self.save_files[0]
            else:
                self.notify("No save selected", severity="error")
                return
        self.load_save(str(self.selected_save.name))

    @on(Button.Pressed, "#btn-chdir")
    def do_chdir(self):
        async def _ask(inp: str | None):
            if not inp:
                return
            p = Path(inp).expanduser()
            if p.is_file():
                p = p.parent
            if not p.exists() or not p.is_dir():
                self.notify(f"Not a directory: {p}", severity="error")
                return
            self.save_dir = p
            self.editor.save_file_directory = str(p)
            self.editor.selected_save_file_dict = None
            self.all_bases = []
            self.filtered = []
            self.query_one("#bases-table", DataTable).clear()
            self.refresh_saves()
            self.update_status(f"Save dir changed to {p}")

        self.app.push_screen(
            InputScreen(
                "Enter save directory (or $NMS_SAVE_DIR):",
                placeholder=str(self.save_dir or ""),
                initial=str(self.save_dir or ""),
            ),
            _ask,
        )

    def load_save(self, save_name: str):
        self.update_status(f"Decompressing {save_name}… (lz4 + mapping)")
        self.query_one("#save-status", Static).update("Decompressing…")
        try:
            # Mimic SaveEditor workflow: load_save_files -> select -> decompress -> load_bases
            self.editor.load_save_files(str(self.save_dir))
            self.editor.select_save_file(save_name)
            self.editor.decompress_save_file(save_name, apply_key_mapping=True)
            self.editor.load_bases()
            self.all_bases = self.editor.all_bases
            # Default to Both
            self.selected_base_type = None
            self.query_one("#btn-both", Button).variant = "primary"
            self.query_one("#btn-corvettes", Button).variant = "default"
            self.query_one("#btn-planetary", Button).variant = "default"
            self.refresh_bases()
            self.update_status(
                f"Loaded {save_name}: {len(self.all_bases)} bases ✓  Backups in backups/"
            )
            self.query_one("#save-status", Static).update(
                f"Loaded {save_name} • {len(self.all_bases)} bases"
            )
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.notify(f"Load failed: {e}", severity="error", timeout=8)
            self.query_one("#save-status", Static).update(f"[red]Load failed: {e}[/]")
            self.update_status(f"Error: {e}")

    # filter sets for better UX: upstream has ExternalPlanetBase but saves use HomePlanetBase
    PLANETARY_TYPES = {"HomePlanetBase", "ExternalPlanetBase"}

    def refresh_bases(self):
        table = self.query_one("#bases-table", DataTable)
        table.clear()
        self.filtered = []
        if not self.all_bases:
            self.query_one("#counts", Static).update("No bases")
            return
        # filter
        for idx, base in enumerate(self.all_bases):
            try:
                t = (
                    base.get("BaseType", {}).get("PersistentBaseTypes", "Unknown")
                    if isinstance(base.get("BaseType"), dict)
                    else "Unknown"
                )
            except Exception:
                t = "Unknown"
            if self.selected_base_type:
                if self.selected_base_type == "PLANETARY":
                    if t not in self.PLANETARY_TYPES:
                        continue
                elif t != self.selected_base_type:
                    continue
            # Use display name (corvettes: ShipOwnership[UserData].Name)
            try:
                name = self.editor.get_base_display_name(base, idx)
            except Exception:
                name = base.get("Name") or f"Unnamed {idx}"
            # Also keep raw for tooltip/debug
            raw_name = (base.get("Name") or "").strip()
            # objects count
            try:
                n = self.editor.get_numer_of_components_from_base(base)
            except Exception:
                n = (
                    len(base.get("Objects", []))
                    if isinstance(base.get("Objects"), list)
                    else 0
                )
            owner = ""
            try:
                owner = (base.get("Owner", {}) or {}).get("UID", "")[:10]
            except Exception:
                pass
            self.filtered.append((idx, base))
            # Show display name; if corvette, suffix raw "Default" for clarity
            shown = name[:40]
            if t == "PlayerShipBase" and raw_name == "Default" and name != "Default":
                shown = f"{name[:32]}"
            table.add_row(str(idx), shown, t, str(n), owner, key=str(idx))
        # counts line like upstream save_editor.py:149-151 but with all actual types
        try:
            from collections import Counter

            cnt = Counter(
                b.get("BaseType", {}).get("PersistentBaseTypes", "Unknown")
                for b in self.all_bases
            )
            total_c = cnt.get("PlayerShipBase", 0)
            total_p = cnt.get("HomePlanetBase", 0) + cnt.get("ExternalPlanetBase", 0)
            total_f = cnt.get("FreighterBase", 0)
            total_s = cnt.get("PlayerSpaceBase", 0)
        except Exception:
            total_c = total_p = total_f = total_s = 0
        try:
            total_objs = (
                self.editor.get_number_of_components_for_all_bases_in_save_file()
                if self.all_bases
                else 0
            )
        except Exception:
            total_objs = sum(
                len(b.get("Objects", [])) if isinstance(b.get("Objects"), list) else 0
                for b in self.all_bases
            )
        self.query_one("#counts", Static).update(
            f"Showing {len(self.filtered)}/{len(self.all_bases)} — Ship:{total_c} Planet:{total_p} Freighter:{total_f} Space:{total_s} — Total objs: {total_objs}"
        )
        if self.filtered:
            table.move_cursor(row=0)
            self.selected_base_global_index = self.filtered[0][0]
        else:
            self.selected_base_global_index = None
        self.query_one("#bases-title", Static).update(
            f"Bases — {len(self.filtered)} shown (filter: {self.selected_base_type or 'Both'}) — select row, then [e]/[v]/[i]"
        )

    @on(DataTable.RowSelected, "#bases-table")
    def bases_selected(self, e: DataTable.RowSelected):
        if e.row_key and e.row_key.value is not None:
            try:
                self.selected_base_global_index = int(e.row_key.value)
            except Exception:
                pass
            self.query_one("#action-status", Static).update(
                f"Selected base idx {self.selected_base_global_index}"
            )

    @on(Button.Pressed, "#btn-corvettes")
    def filter_corvettes(self):
        self.selected_base_type = "PlayerShipBase"
        self.query_one("#btn-corvettes", Button).variant = "primary"
        self.query_one("#btn-planetary", Button).variant = "default"
        self.query_one("#btn-both", Button).variant = "default"
        self.refresh_bases()

    @on(Button.Pressed, "#btn-planetary")
    def filter_planetary(self):
        self.selected_base_type = "PLANETARY"
        self.query_one("#btn-corvettes", Button).variant = "default"
        self.query_one("#btn-planetary", Button).variant = "primary"
        self.query_one("#btn-both", Button).variant = "default"
        self.refresh_bases()

    @on(Button.Pressed, "#btn-both")
    def filter_both(self):
        self.selected_base_type = None
        self.query_one("#btn-corvettes", Button).variant = "default"
        self.query_one("#btn-planetary", Button).variant = "default"
        self.query_one("#btn-both", Button).variant = "primary"
        self.refresh_bases()

    # Actions
    def action_filter_corvettes(self):
        self.filter_corvettes()

    def action_filter_planetary(self):
        self.filter_planetary()

    def action_filter_both(self):
        self.filter_both()

    def action_export_base(self):
        self.do_export()

    def action_export_nmsbase(self):
        self.do_export_nmsbase()

    def action_view_json(self):
        self.do_view()

    def action_import_base(self):
        self.do_import()

    def action_recompress(self):
        self.do_recompress()

    def action_help(self):
        self.push_screen(
            ConfirmScreen(
                "Keys: [Enter] Load save • [c] Corvettes [p] Planetary [b] Both\n"
                "Actions: [e] Export JSON to output/bases + clipboard (Base Builder → Import from NMS)\n"
                "         [E] Export NMSBASE (objects-only .nmsbase for NomNom/NMSSE paste after ^BASE_FLAG)\n"
                "         [v] View JSON  [i] Import edited JSON (paste file path or clipboard)\n"
                "         [r] Recompress .hg (backup + atomic write) • [ctrl+b] Backup • [ctrl+r] Restore\n"
                "Workflow: Load save → pick base → Export → edit in Base Builder → Export to NMS → Import → Recompress",
                ok_label="Close",
                cancel_label="Close",
            )
        )

    # --- Backup / Restore for saves ---
    @on(Button.Pressed, "#btn-backup")
    def _backup_btn(self):
        self.do_backup_save()

    @on(Button.Pressed, "#btn-restore")
    def _restore_btn(self):
        self.do_restore_save()

    def action_backup_save(self):
        self.do_backup_save()

    def action_restore_save(self):
        self.do_restore_save()

    def do_backup_save(self):
        """Manual backup of saves to backups/save files/. Backs up all save*.hg + shows result.

        Nothing on disk is overwritten until Recompress — injecting is in-memory only.
        So if you injected the wrong base, just reload (Load) or restore, don't Recompress.
        """
        if not self.save_dir or not Path(self.save_dir).exists():
            self.notify("No save directory — set $NMS_SAVE_DIR or Change dir", severity="error")
            return
        # Backup all save*.hg files in the Proton save dir, not just selected one
        try:
            candidates = list(Path(self.save_dir).glob("save*.hg"))
        except Exception:
            candidates = []
        if not candidates and self.selected_save and Path(self.selected_save).exists():
            candidates = [Path(self.selected_save)]
        if not candidates:
            self.notify(f"No save*.hg found in {self.save_dir}", severity="error")
            return
        # Also include accountdata.hg optionally? Keep to save*.hg only for now
        BACKUP_SAVE_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ok = 0
        last_dst: Path | None = None
        errs = []
        for src in sorted(candidates):
            if not src.is_file():
                continue
            # Don't backup our own backups if user ever copied them into save_dir
            low = src.name.lower()
            if "backup" in low or "before_recompress" in low or "pre_restore" in low:
                continue
            # Verify it's a real save (at least 18 bytes per save_extractor)
            try:
                if src.stat().st_size < 18:
                    continue
            except Exception:
                continue
            stem = src.stem  # save, save2, etc.
            dst = BACKUP_SAVE_DIR / f"{stem}_manual_backup_{ts}.hg"
            # If multiple stems share same ts, avoid collision by suffix
            if dst.exists():
                dst = BACKUP_SAVE_DIR / f"{stem}_manual_backup_{ts}_{ok}.hg"
            try:
                shutil.copy2(src, dst)
                # Fix mtime to backup creation time, not original save's mtime
                # copy2 preserves original mtime, which makes "Modified at" look like original save
                try:
                    os.utime(dst, None)
                except Exception:
                    pass
                # Verify copy size matches
                if dst.stat().st_size != src.stat().st_size:
                    errs.append(f"{src.name}: size mismatch")
                else:
                    ok += 1
                    last_dst = dst
            except Exception as e:
                errs.append(f"{src.name}: {e}")
        if ok == 0:
            msg = f"Backup failed: {', '.join(errs) if errs else 'unknown error'}"
            self.notify(msg, severity="error", timeout=8)
            self.query_one("#action-status", Static).update(msg)
            return
        msg = f"Backed up {ok} file(s) to {BACKUP_SAVE_DIR} (e.g. {last_dst.name} {last_dst.stat().st_size/1024:.0f} KB)"
        if errs:
            msg += f" — {len(errs)} error(s): {', '.join(errs)}"
        self.query_one("#save-status", Static).update(f"Backed up {ok} save(s) ✓")
        self.query_one("#action-status", Static).update(msg)
        self.notify(msg, timeout=8)
        # Update subtitlle hint about inject vs recompress safety
        self.update_status("Backup done — inject is memory-only until Recompress. Wrong inject? Just Load again.")
        try:
            if last_dst:
                reveal_in_file_manager(last_dst)
        except Exception:
            pass

    def do_restore_save(self):
        """List backups for the selected save and restore chosen one over live file."""
        if not self.selected_save:
            if self.save_files:
                self.selected_save = self.save_files[0]
            else:
                self.notify("No save selected to restore over", severity="error")
                return
        save_name = Path(self.selected_save).name
        stem = Path(save_name).stem
        BACKUP_SAVE_DIR.mkdir(parents=True, exist_ok=True)
        # List backups whose filename contains the stem and ends with .hg
        try:
            all_backups = sorted(
                [p for p in BACKUP_SAVE_DIR.glob("*.hg") if stem in p.stem],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception:
            all_backups = []
        # Fallback: show all .hg backups if none match stem
        if not all_backups:
            try:
                all_backups = sorted(
                    list(BACKUP_SAVE_DIR.glob("*.hg")),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
            except Exception:
                all_backups = []
        if not all_backups:
            self.notify(f"No backups found in {BACKUP_SAVE_DIR}", severity="warning", timeout=6)
            try:
                reveal_in_file_manager(BACKUP_SAVE_DIR)
            except Exception:
                pass
            return

        async def _chosen(backup_path: Path | None):
            if not backup_path:
                return
            target = Path(self.save_dir) / save_name if self.save_dir else Path(self.selected_save)
            # Ensure target dir exists
            # Backup current live file first (pre-restore)
            try:
                if target.exists():
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    pre = BACKUP_SAVE_DIR / f"{stem}_pre_restore_{ts}.hg"
                    shutil.copy2(target, pre)
                    try:
                        os.utime(pre, None)
                    except Exception:
                        pass
            except Exception:
                pass
            # Confirm overwrite
            async def _confirm_restore(ok: bool | None):
                if not ok:
                    return
                try:
                    shutil.copy2(backup_path, target)
                    self.notify(f"Restored '{save_name}' from {backup_path.name} ✓", timeout=6)
                    self.query_one("#save-status", Static).update(f"Restored {save_name}")
                    self.query_one("#action-status", Static).update(f"Restored {save_name} ← {backup_path.name}")
                    # Clear editor state so user must reload
                    try:
                        self.editor.selected_save_file_dict = None
                        self.all_bases = []
                        self.filtered = []
                        self.query_one("#bases-table", DataTable).clear()
                    except Exception:
                        pass
                    self.refresh_saves()
                    # Auto-select restored file
                    for p in self.save_files:
                        if p.name == save_name:
                            self.selected_save = p
                            break
                except Exception as e:
                    self.notify(f"Restore failed: {e}", severity="error", timeout=8)

            self.push_screen(
                ConfirmScreen(
                    f"Restore '{save_name}'?\n\nBackup: {backup_path.name}\n  Size: {backup_path.stat().st_size / 1024:.0f} KB\n  Modified: {datetime.fromtimestamp(backup_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}\nTarget: {target}\n\nCurrent live file will be backed up as {stem}_pre_restore_*.hg first.\nClose NMS before restoring!",
                    ok_label="Restore",
                    cancel_label="Cancel",
                ),
                _confirm_restore,  # type: ignore[arg-type]
            )

        self.push_screen(RestoreScreen(save_name, all_backups), _chosen)  # type: ignore[arg-type]

    @on(Button.Pressed, "#btn-export")
    def do_export(self):
        if self.selected_base_global_index is None:
            self.notify("Select a base first", severity="warning")
            return
        idx = self.selected_base_global_index
        base = self.all_bases[idx] if 0 <= idx < len(self.all_bases) else None
        if not base:
            self.notify("Invalid selection", severity="error")
            return
        # Display name for file/UI (corvettes: ShipOwnership name); raw name is "Default"
        try:
            disp = self.editor.get_base_display_name(base, idx)
        except Exception:
            disp = base.get("Name") or f"base_{idx}"
        # Use display name for filename, not raw "Default"
        safe = safe_name(disp) or safe_name(base.get("Name") or f"base_{idx}")
        # Select in editor: avoid name collision for "Default" duplicates -> set by index directly
        self.editor.selected_base = base
        self.editor.selected_base_index = idx
        # Also try select_base for upstream bookkeeping but ignore failure
        try:
            raw = base.get("Name") or ""
            if raw and raw != "Default":
                self.editor.select_base(raw)
                # restore correct index if duplicate collision
                self.editor.selected_base = base
                self.editor.selected_base_index = idx
        except Exception:
            pass
        name = disp
        out_dir = ROOT / "output" / "bases"
        out_dir.mkdir(parents=True, exist_ok=True)
        # also try Documents target
        docs_bases = Path.home() / "Documents" / "No Mans Sky Base Builder" / "bases"
        out_path = out_dir / f"{safe}.json"
        try:
            saved = self.editor.save_selected_base_to_json(str(out_path))
        except Exception:
            # fallback manual
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(base, f, indent=2, ensure_ascii=False)
            saved = str(out_path)
        # also copy to docs if exists
        if docs_bases.exists() and docs_bases.is_dir():
            try:
                shutil.copy2(out_path, docs_bases / f"{safe}.json")
            except Exception:
                pass
        # clipboard
        try:
            txt = json.dumps(base, indent=2, ensure_ascii=False)
            ok, backend = copy_text(txt)
            clip_msg = (
                f"copied via {backend}"
                if ok
                else f"clipboard failed ({backend}) — file saved instead"
            )
        except Exception as e:
            clip_msg = f"clip fail: {e}"
        msg = f"Exported '{name}' → {saved} | {clip_msg}\n→ Paste in Base Builder: Import base from NMS"
        self.query_one("#action-status", Static).update(msg)
        self.notify(msg, timeout=6)
        # No auto preview — use View [v] button if you want to inspect JSON

    @on(Button.Pressed, "#btn-export-nmsbase")
    async def do_export_nmsbase(self):
        if self.selected_base_global_index is None:
            self.notify("Select a base first", severity="warning")
            return
        idx = self.selected_base_global_index
        base = self.all_bases[idx] if 0 <= idx < len(self.all_bases) else None
        if not base:
            self.notify("Invalid selection", severity="error")
            return
        try:
            disp = self.editor.get_base_display_name(base, idx)
        except Exception:
            disp = base.get("Name") or f"base_{idx}"
        safe = safe_name(disp) or safe_name(base.get("Name") or f"base_{idx}")
        suggested = ROOT / "output" / "nmsbase" / f"{safe}.nmsbase"
        suggested.parent.mkdir(parents=True, exist_ok=True)

        # Try system file manager dialog (zenity/kdialog/yad) in thread
        chosen: str | None = None
        if has_system_dialog():
            try:
                import asyncio

                chosen = await asyncio.to_thread(
                    ask_save_path_sync, suggested, f"Export '{disp}' as NMSBASE"
                )
                # zenity returns None on cancel → fallback to suggested
                if chosen is not None and not chosen.strip():
                    chosen = None
            except Exception:
                chosen = None

        if chosen:
            # User picked via system dialog
            out_path = Path(chosen)
            # Ensure .nmsbase suffix
            if not out_path.suffix:
                out_path = out_path.with_suffix(".nmsbase")
            try:
                saved = self.editor.export_base_as_nmsbase(base, out_path)
            except Exception as e:
                self.notify(f"NMSBASE export failed: {e}", severity="error", timeout=8)
                return
            # Also try to save a copy to default output for history
            try:
                copy_dest = suggested
                if Path(saved).resolve() != copy_dest.resolve():
                    self.editor.export_base_as_nmsbase(base, copy_dest)
            except Exception:
                pass
            # Clipboard (objects snippet)
            try:
                import json as _j

                objs = base.get("Objects", [])
                txt = ",\n" + ",\n".join(_j.dumps(o, indent=2, ensure_ascii=False) for o in objs) if objs else ""
                ok, backend = copy_text(txt)
                clip_msg = f"copied via {backend}" if ok else f"clipboard failed ({backend})"
            except Exception as e:
                clip_msg = f"clip fail: {e}"
            msg = f"NMSBASE exported '{disp}' → {saved} | {clip_msg} — paste after ^BASE_FLAG"
            self.query_one("#action-status", Static).update(msg)
            self.notify(msg, timeout=6)
            # Offer to reveal in file manager — no auto preview (use View [v] to inspect)
            try:
                reveal_in_file_manager(Path(saved))
            except Exception:
                pass
            return

        # Fallback: Textual InputScreen asking for path
        async def _ask_input(inp: str | None):
            if inp is None:
                return
            inp = inp.strip().strip('"').strip("'")
            if not inp:
                # User cleared → use suggested
                out = suggested
            else:
                out = Path(inp).expanduser()
                if out.is_dir():
                    out = out / f"{safe}.nmsbase"
                if not out.suffix:
                    out = out.with_suffix(".nmsbase")
            try:
                saved2 = self.editor.export_base_as_nmsbase(base, out)
            except Exception as e:
                self.notify(f"NMSBASE export failed: {e}", severity="error", timeout=8)
                return
            try:
                import json as _j

                objs = base.get("Objects", [])
                txt2 = ",\n" + ",\n".join(_j.dumps(o, indent=2, ensure_ascii=False) for o in objs) if objs else ""
                ok2, backend2 = copy_text(txt2)
                clip_msg2 = f"copied via {backend2}" if ok2 else f"clipboard failed ({backend2})"
            except Exception as e:
                clip_msg2 = f"clip fail: {e}"
            msg2 = f"NMSBASE exported '{disp}' → {saved2} | {clip_msg2} — paste after ^BASE_FLAG"
            self.query_one("#action-status", Static).update(msg2)
            self.notify(msg2, timeout=6)
            try:
                reveal_in_file_manager(Path(saved2))
            except Exception:
                pass
            # No auto preview — use View [v] for inspection

        self.push_screen(
            InputScreen(
                f"Export '{disp}' as NMSBASE:\nEnter file path (system dialog unavailable/cancelled).\nDefault: {suggested}\nWill copy Objects snippet (leading ',') for NomNom/NMSSE paste after ^BASE_FLAG:",
                placeholder=str(suggested),
                initial=str(suggested),
            ),
            _ask_input,
        )

    @on(Button.Pressed, "#btn-view")
    def do_view(self):
        if self.selected_base_global_index is None:
            self.notify("Select a base first", severity="warning")
            return
        idx = self.selected_base_global_index
        base = self.all_bases[idx]
        txt = json.dumps(base, indent=2, ensure_ascii=False)
        try:
            disp = self.editor.get_base_display_name(base, idx)
        except Exception:
            disp = base.get("Name", "Unnamed")
        self.push_screen(
            JsonViewScreen(
                f"{disp} — idx {idx} • {len(txt)} chars",
                txt,
            )
        )

    @on(Button.Pressed, "#btn-import")
    async def do_import(self):
        if not self.editor.selected_save_file_dict:
            self.notify("Load a save first", severity="warning")
            return
        if self.selected_base_global_index is None:
            self.notify(
                "Select target base to replace first (its slot will be overwritten)",
                severity="warning",
            )
            return
        idx = self.selected_base_global_index
        try:
            target_name = self.editor.get_base_display_name(self.all_bases[idx], idx)
        except Exception:
            target_name = self.all_bases[idx].get("Name") or f"idx {idx}"

        async def _ask(path_or_json: str | None):
            if not path_or_json:
                return
            p = Path(path_or_json.strip().strip('"').strip("'")).expanduser()
            data = None

            def _parse_text(txt: str):
                """Parse JSON handling .nmsbase leading comma and Objects-only arrays."""
                t = txt.strip()
                # Handle .nmsbase format: leading comma before first object
                # e.g. ",\n{...},\n{...}"
                if t.startswith(","):
                    t = t.lstrip(",").strip()
                    # If now starts with '{', it's comma-separated objects without outer []
                    if t.startswith("{"):
                        # Wrap to make valid JSON array for parsing
                        t = "[" + t + "]" if not t.startswith("[") else t
                    # If already "[" after stripping, keep as is
                return json.loads(t)

            # Try file path first
            if p.exists() and p.is_file():
                try:
                    raw = p.read_text(encoding="utf-8", errors="ignore")
                    # Use helper to support .nmsbase and Objects-only files
                    try:
                        data = _parse_text(raw)
                    except json.JSONDecodeError:
                        # Fallback to strict utf-8-sig load
                        raw2 = p.read_text(encoding="utf-8-sig", errors="ignore")
                        data = _parse_text(raw2)
                except Exception as e:
                    self.notify(f"Failed to load {p}: {e}", severity="error")
                    return
            else:
                # Try as raw JSON (clipboard paste) — if user pasted JSON directly
                txt = path_or_json.strip()
                # also try wl-paste fallback if input empty-ish
                if len(txt) < 10:
                    pasted = try_paste()
                    if pasted:
                        txt = pasted
                try:
                    data = _parse_text(txt)
                except Exception:
                    # Try clipboard as file content
                    pasted = try_paste()
                    if pasted:
                        try:
                            data = _parse_text(pasted)
                        except Exception as e2:
                            self.notify(
                                f"Not valid JSON (tried clipboard too): {e2}",
                                severity="error",
                            )
                            return
                    else:
                        self.notify(
                            "Not a file and not valid JSON. Paste file path or JSON.",
                            severity="error",
                        )
                        return

            # Normalize: handle Objects-only imports (list of objects with ObjectID)
            # Your snippet: [ {ObjectID:..., Position:...}, ... ] is such a case
            target_base = self.all_bases[idx] if 0 <= idx < len(self.all_bases) else {}
            if isinstance(data, list):
                if not data:
                    self.notify("JSON list is empty", severity="error")
                    return
                first = data[0] if isinstance(data[0], dict) else None
                if first is not None and "ObjectID" in first:
                    # Objects-only array — inject into target base
                    new_base = dict(target_base)
                    new_base["Objects"] = data
                    # Keep original base metadata (Name, BaseType, etc.) unless caller wants to override
                    # Update timestamp to now
                    try:
                        new_base["LastUpdateTimestamp"] = int(datetime.now().timestamp())
                    except Exception:
                        pass
                    self.notify(
                        f"Objects-only import: {len(data)} objects will replace '{target_name}'",
                        severity="information",
                    )
                    data = new_base
                elif first is not None and "Objects" in first:
                    # List of bases (e.g., export of multiple) — take first base
                    self.notify(
                        "JSON was a list of bases — using first element", severity="warning"
                    )
                    data = data[0]
                else:
                    # Generic list — take first
                    self.notify(
                        "JSON was a list — using first element", severity="warning"
                    )
                    data = data[0]

            if not isinstance(data, dict):
                self.notify(
                    "JSON must be a base object (dict) or Objects array", severity="error"
                )
                return
            # If dict has ObjectID but no Objects, it's a single object wrapped incorrectly — wrap to Objects
            if "ObjectID" in data and "Objects" not in data:
                # Single object dict passed as base — convert to base with one object
                new_base = dict(target_base)
                new_base["Objects"] = [data]
                data = new_base
                self.notify("Single object import — wrapped to Objects", severity="information")
            if "Objects" not in data:
                self.notify(
                    "Base JSON missing 'Objects' key — not a valid base", severity="error"
                )
                return
            # Ensure editor has selected_base_index pointing to target slot
            try:
                # Re-select target by name then override with new data
                try:
                    self.editor.select_base(target_name)
                except Exception:
                    pass
                self.editor.selected_base = data
                self.editor.selected_base_index = idx
                # Keep all_bases in sync before inject validates
            except Exception as e:
                self.notify(f"Setup failed: {e}", severity="error")
                return

            # Confirm
            async def _confirm(result: bool | None) -> None:
                if not result:
                    return
                try:
                    self.editor.inject_selected_base_into_save_file()
                    # refresh local all_bases from editor
                    self.all_bases = self.editor.all_bases
                    self.refresh_bases()
                    self.query_one("#action-status", Static).update(
                        f"Injected into slot {idx} ('{target_name}') — backup in backups/bases/ — now Recompress [r] to write .hg"
                    )
                    self.notify(
                        f"Injected replacement for '{target_name}' (idx {idx}). Backed up original. Now Recompress.",
                        timeout=6,
                    )
                except Exception as e:
                    import traceback

                    traceback.print_exc()
                    self.notify(f"Inject failed: {e}", severity="error", timeout=8)

            self.push_screen(
                ConfirmScreen(
                    f"Inject edited JSON into slot {idx} ?\nTarget: '{target_name}'\nOriginal will be backed up to backups/bases/",
                    ok_label="Inject",
                    cancel_label="Cancel",
                ),
                _confirm,  # type: ignore[arg-type]
            )

        # Try system file manager (open) first — pick file via zenity/kdialog
        # User's Objects snippet is large (your example 100+ objects) — file pick is easier than paste
        if has_system_dialog():
            try:
                import asyncio

                start = Path.home() / "Documents"
                bba = Path.home() / "Documents" / "No Mans Sky Base Builder" / "bases"
                nmsbase_out = ROOT / "output" / "nmsbase"
                if bba.exists():
                    start = bba
                elif nmsbase_out.exists():
                    start = nmsbase_out
                chosen_open = await asyncio.to_thread(
                    ask_open_path_sync, f"Import for '{target_name}' — pick JSON/NMSBASE/Objects", start
                )
                if chosen_open:
                    await _ask(chosen_open)
                    return
            except Exception:
                pass

        self.push_screen(
            InputScreen(
                f"Import for slot {idx} ('{target_name}'):\nEnter file path to edited JSON (from Base Builder → Export to NMS), or paste JSON directly.\n"
                f"Objects-only arrays like your snippet [{'{...}, {...}'}] are supported — they will replace this base's Objects.\n"
                f"NMSBASE leading ',' also supported. Or pick file via system dialog (if zenity available):",
                placeholder="/home/gloves/Documents/No Mans Sky Base Builder/bases/MyBase.json  or  paste JSON",
                initial="",
            ),
            _ask,
        )

    @on(Button.Pressed, "#btn-recompress")
    def do_recompress(self):
        if not self.editor.selected_save_file_dict:
            self.notify("No save loaded to recompress", severity="warning")
            return
        if not self.editor.selected_save_file:
            self.notify("No save file selected", severity="warning")
            return
        orig_name = self.editor.selected_save_file
        orig_path = Path(self.editor.save_file_directory) / orig_name
        default_out = ROOT / "output" / orig_name
        default_out.parent.mkdir(parents=True, exist_ok=True)
        msg = f"Recompress '{orig_name}'?\nOriginal: {orig_path}\n• Yes = overwrite live save (backs up to backups/save files/*_before_recompress_*.hg + atomic .tmp)\n• No = write to {default_out}\n\nClose NMS before overwriting!"

        async def _confirm(result: bool | None) -> None:
            overwrite = bool(result)
            out = str(orig_path) if overwrite else str(default_out)
            # extra confirm for overwrite
            if overwrite:

                async def _confirm2(result2: bool | None) -> None:
                    if not result2:
                        return
                    await self._run_recompress(out)

                self.push_screen(
                    ConfirmScreen(
                        f"OVERWRITE LIVE SAVE?\n{orig_path}\nBackup will be made. Ensure NMS is CLOSED.",
                        ok_label="OVERWRITE",
                        cancel_label="Cancel",
                    ),
                    _confirm2,  # type: ignore[arg-type]
                )
            else:
                await self._run_recompress(out)

        # Use custom screen with two options: Overwrite vs New file vs Cancel
        # Simplify: InputScreen for path, but provide quick choose
        self.push_screen(
            ConfirmScreen(
                msg, ok_label="Overwrite LIVE", cancel_label="Write to output/"
            ),
            _confirm,  # type: ignore[arg-type]
        )

    async def _run_recompress(self, out_path: str):
        self.update_status(f"Recompressing → {out_path} … (reverse-map + lz4)")
        try:
            # Run in thread to avoid blocking UI (recompress does network-ish mapping fetch)
            import asyncio

            def _work():
                return self.editor.recompress_save_file(out_path, mapping_file=None)

            await asyncio.to_thread(_work)
            self.query_one("#action-status", Static).update(
                f"[green]Wrote {out_path}[/] — backup in backups/save files/"
            )
            self.notify(f"Recompressed to {out_path} ✓", timeout=6)
            self.update_status(f"Done → {out_path}")
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.notify(f"Recompress failed: {e}", severity="error", timeout=8)
            self.update_status(f"Recompress error: {e}")


def main():
    import argparse

    p = argparse.ArgumentParser(description="NMS Proton TUI — Base → Base Builder App")
    p.add_argument("--save-dir", help="Override save directory (else autodetect)")
    p.add_argument("--save-file", help="Save file name to auto-load (e.g. save.hg)")
    args = p.parse_args()
    app = NMSApp(save_dir=args.save_dir)
    # optionally auto-load if --save-file given handled after mount? Could pre-set
    if args.save_file and args.save_dir:
        # will load after mount via call_later
        def _late():
            app.call_after_refresh(lambda: app.load_save(args.save_file))

        # not ideal, just pass
        pass
    app.run()


if __name__ == "__main__":
    main()
