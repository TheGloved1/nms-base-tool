#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import sys
import shutil
import threading
from pathlib import Path
from datetime import datetime

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, Gdk, GLib

# Ensure vendor on path
from nms_tui.paths import get_writable_data_dir, get_bundle_dir
ROOT_WRITABLE = get_writable_data_dir()
BUNDLE = get_bundle_dir()
VENDOR = BUNDLE / "vendor" / "upstream"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from nms_tui.proton import find_proton_save_dir, list_save_files
from nms_tui.editor import ProtonSaveEditor

from nms_tui.clipboard import copy_text as cli_copy_text

# --- Freeze-aware cache patch for key_mapper (writable location when bundled) ---
try:
    import key_mapper as _km
    from nms_tui.paths import get_writable_data_dir as _gwdd
    _writable_cache = _gwdd() / ".nms_mapping_cache" / "mapping.json"
    def _patched_get_cache_path():
        _writable_cache.parent.mkdir(parents=True, exist_ok=True)
        return _writable_cache
    _km.get_cache_path = _patched_get_cache_path
    # Also patch file_utils settings to be writable
    try:
        from vendor.upstream.utils import file_utils as _fu
        # Override SETTINGS_DIR to writable
        _fu.SETTINGS_DIR = _gwdd() / "settings"
        _fu.FILE_SETTINGS_PATH = _fu.SETTINGS_DIR / "file_settings.json"
    except Exception:
        pass
    try:
        import utils.file_utils as _fu2
        _fu2.SETTINGS_DIR = _gwdd() / "settings"
        _fu2.FILE_SETTINGS_PATH = _fu2.SETTINGS_DIR / "file_settings.json"
    except Exception:
        pass
except Exception:
    pass

def safe_name(name: str) -> str:
    s = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    s = s.replace(" ", "_")
    return s or "unnamed_base"

BACKUP_SAVE_DIR = ROOT_WRITABLE / "backups" / "save files"

def get_clipboard_text_gtk():
    display = Gdk.Display.get_default()
    if not display:
        return None
    clipboard = display.get_clipboard()
    # async, but we try sync via cli helper as fallback
    from nms_tui.clipboard import try_paste
    return try_paste()

def set_clipboard_gtk(text: str):
    try:
        display = Gdk.Display.get_default()
        if display:
            clipboard = display.get_clipboard()
            # For GTK4, clipboard.set takes Gdk.ContentProvider
            from gi.repository import Gdk as Gdk2
            clipboard.set_content(Gdk2.ContentProvider.new_for_value(text))
            return True
    except Exception:
        pass
    # fallback to cli helper
    ok, _ = cli_copy_text(text)
    return ok

class JsonDialog(Adw.Window):
    def __init__(self, parent, title: str, text: str):
        super().__init__(transient_for=parent, modal=True)
        self.set_title(title)
        self.set_default_size(800, 600)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(12); box.set_margin_bottom(12); box.set_margin_start(12); box.set_margin_end(12)
        self.set_content(box)
        lbl = Gtk.Label(label=title)
        lbl.set_xalign(0)
        lbl.add_css_class("title-4")
        box.append(lbl)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        textview = Gtk.TextView()
        textview.set_editable(False)
        textview.set_monospace(True)
        textview.set_wrap_mode(Gtk.WrapMode.NONE)
        buf = textview.get_buffer()
        buf.set_text(text)
        scrolled.set_child(textview)
        box.append(scrolled)
        self._text = text
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_halign(Gtk.Align.CENTER)
        copy_btn = Gtk.Button(label="Copy")
        copy_btn.add_css_class("suggested-action")
        copy_btn.connect("clicked", self.on_copy)
        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda *_: self.close())
        btn_box.append(copy_btn)
        btn_box.append(close_btn)
        box.append(btn_box)
    def on_copy(self, _btn):
        set_clipboard_gtk(self._text)
        # toast via parent?
        self.close()

class RestoreDialog(Adw.Window):
    def __init__(self, parent, save_name: str, backups: list[Path], on_restore):
        super().__init__(transient_for=parent, modal=True)
        self.set_title(f"Restore {save_name}")
        self.set_default_size(700, 400)
        self.backups = backups
        self.on_restore = on_restore
        self.selected = backups[0] if backups else None
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(12); box.set_margin_bottom(12); box.set_margin_start(12); box.set_margin_end(12)
        self.set_content(box)
        lbl = Gtk.Label(label=f"Restore '{save_name}' — pick a backup to overwrite the live save:")
        lbl.set_xalign(0)
        lbl.add_css_class("title-4")
        box.append(lbl)
        hint = Gtk.Label(label="Backups are in backups/save files/. Current live file will be backed up again before restore. Close NMS first!")
        hint.set_xalign(0)
        hint.add_css_class("dim-label")
        hint.set_wrap(True)
        box.append(hint)
        # TreeView
        self.store = Gtk.ListStore(str, str, str, str)  # name, size, modified, path
        for p in backups:
            try:
                sz = p.stat().st_size
                szs = f"{sz/1024/1024:.2f} MB" if sz > 1024*1024 else f"{sz/1024:.0f} KB"
                mt = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            except OSError:
                szs, mt = "?", "?"
            self.store.append([p.name, szs, mt, str(p)])
        tree = Gtk.TreeView(model=self.store)
        for i, title in enumerate(["Backup file", "Size", "Modified"]):
            rend = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, rend, text=i)
            col.set_sort_column_id(i)
            tree.append_column(col)
        # hide path column
        sel = tree.get_selection()
        sel.set_mode(Gtk.SelectionMode.SINGLE)
        sel.connect("changed", self.on_sel_changed)
        # select first
        if backups:
            sel.select_path(Gtk.TreePath.new_from_string("0"))
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_child(tree)
        box.append(scrolled)
        self.tree_sel = sel
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_halign(Gtk.Align.CENTER)
        restore_btn = Gtk.Button(label="Restore")
        restore_btn.add_css_class("destructive-action")
        restore_btn.connect("clicked", self.on_restore_clicked)
        reveal_btn = Gtk.Button(label="Reveal in file manager")
        reveal_btn.connect("clicked", self.on_reveal)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda *_: self.close())
        btn_box.append(restore_btn)
        btn_box.append(reveal_btn)
        btn_box.append(cancel_btn)
        box.append(btn_box)
    def on_sel_changed(self, sel):
        model, itr = sel.get_selected()
        if itr:
            path = model[itr][3]
            self.selected = Path(path)
    def on_restore_clicked(self, _btn):
        if self.selected:
            self.on_restore(self.selected)
        self.close()
    def on_reveal(self, _btn):
        from nms_tui.file_dialog import reveal_in_file_manager
        try:
            reveal_in_file_manager(BACKUP_SAVE_DIR)
        except Exception:
            pass

class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, save_dir: Path | None = None):
        super().__init__(application=app)
        self.app = app
        self.save_dir: Path | None = save_dir or find_proton_save_dir()
        self.editor = ProtonSaveEditor(save_dir=self.save_dir)
        # For freeze-aware, ensure project_directory points to writable
        try:
            self.editor.project_directory = ROOT_WRITABLE
        except Exception:
            pass
        self.save_files: list[Path] = []
        self.selected_save: Path | None = None
        self.selected_base_type: str | None = None  # None = Both, PlayerShipBase, PLANETARY
        self.PLANETARY_TYPES = {"HomePlanetBase", "ExternalPlanetBase"}
        self.all_bases: list[dict] = []
        self.filtered: list[tuple[int, dict]] = []
        self.selected_base_idx: int | None = None

        self.set_title("NMS Proton — Base → Base Builder")
        self.set_default_size(1200, 700)

        # HeaderBar
        header = Adw.HeaderBar()
        # Use set_title_widget for Adw
        title = Adw.WindowTitle(title="NMS Proton — Base → Base Builder", subtitle="Proton/Linux (compatdata 275850)")
        header.set_title_widget(title)
        # Add help button
        help_btn = Gtk.Button(icon_name="help-about-symbolic")
        help_btn.set_tooltip_text("Help")
        help_btn.connect("clicked", self.on_help)
        header.pack_end(help_btn)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(content)
        content.append(header)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        content.append(paned)

        # Left panel
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.set_size_request(340, -1)
        left.set_margin_top(8); left.set_margin_bottom(8); left.set_margin_start(8); left.set_margin_end(8)
        paned.set_start_child(left)
        paned.set_resize_start_child(False)
        paned.set_shrink_start_child(False)

        # Save dir
        dir_lbl = Gtk.Label(label="Save dir:")
        dir_lbl.set_xalign(0)
        dir_lbl.add_css_class("heading")
        left.append(dir_lbl)
        self.dir_value = Gtk.Label(label=str(self.save_dir) if self.save_dir else "[no dir found]")
        self.dir_value.set_xalign(0)
        self.dir_value.set_wrap(True)
        self.dir_value.add_css_class("dim-label")
        self.dir_value.set_selectable(True)
        left.append(self.dir_value)
        left.append(Gtk.Separator())

        saves_lbl = Gtk.Label(label="Saves:")
        saves_lbl.set_xalign(0)
        saves_lbl.add_css_class("heading")
        left.append(saves_lbl)

        # Saves TreeView
        self.saves_store = Gtk.ListStore(str, str, str, str)  # name, size, modified, path
        self.saves_tree = Gtk.TreeView(model=self.saves_store)
        for i, title in enumerate(["Save", "Size", "Modified"]):
            rend = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, rend, text=i)
            col.set_sort_column_id(i)
            self.saves_tree.append_column(col)
        self.saves_tree.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self.saves_tree.get_selection().connect("changed", self.on_saves_selected)
        self.saves_tree.connect("row-activated", lambda tv, path, col: self.do_load())
        scrolled_saves = Gtk.ScrolledWindow()
        scrolled_saves.set_min_content_height(120)
        scrolled_saves.set_vexpand(False)
        scrolled_saves.set_child(self.saves_tree)
        left.append(scrolled_saves)

        # Filter buttons
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        filter_box.set_halign(Gtk.Align.CENTER)
        self.btn_corvettes = Gtk.ToggleButton(label="Corvettes")
        self.btn_planetary = Gtk.ToggleButton(label="Planetary")
        self.btn_both = Gtk.ToggleButton(label="Both")
        self.btn_both.set_active(True)
        # Group them
        self.btn_corvettes.set_group(self.btn_both)
        self.btn_planetary.set_group(self.btn_both)
        self.btn_corvettes.connect("toggled", lambda b: self.filter_corvettes() if b.get_active() else None)
        self.btn_planetary.connect("toggled", lambda b: self.filter_planetary() if b.get_active() else None)
        self.btn_both.connect("toggled", lambda b: self.filter_both() if b.get_active() else None)
        filter_box.append(self.btn_corvettes)
        filter_box.append(self.btn_planetary)
        filter_box.append(self.btn_both)
        left.append(filter_box)

        self.counts_lbl = Gtk.Label(label="")
        self.counts_lbl.set_xalign(0)
        self.counts_lbl.add_css_class("dim-label")
        self.counts_lbl.set_wrap(True)
        left.append(self.counts_lbl)

        btn_row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_row1.set_halign(Gtk.Align.CENTER)
        load_btn = Gtk.Button(label="Load")
        load_btn.add_css_class("suggested-action")
        load_btn.connect("clicked", lambda _: self.do_load())
        chdir_btn = Gtk.Button(label="Change dir")
        chdir_btn.connect("clicked", lambda _: self.do_chdir())
        btn_row1.append(load_btn)
        btn_row1.append(chdir_btn)
        left.append(btn_row1)

        btn_row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_row2.set_halign(Gtk.Align.CENTER)
        backup_btn = Gtk.Button(label="Backup")
        backup_btn.connect("clicked", lambda _: self.do_backup_save())
        restore_btn = Gtk.Button(label="Restore…")
        restore_btn.connect("clicked", lambda _: self.do_restore_save())
        btn_row2.append(backup_btn)
        btn_row2.append(restore_btn)
        left.append(btn_row2)

        self.save_status = Gtk.Label(label="")
        self.save_status.set_xalign(0)
        self.save_status.set_wrap(True)
        self.save_status.add_css_class("dim-label")
        left.append(self.save_status)

        # Right panel
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right.set_margin_top(8); right.set_margin_bottom(8); right.set_margin_start(8); right.set_margin_end(8)
        right.set_hexpand(True)
        paned.set_end_child(right)

        bases_title = Gtk.Label(label="Bases — pick one to Export → Base Builder")
        bases_title.set_xalign(0)
        bases_title.add_css_class("heading")
        right.append(bases_title)
        self.bases_title = bases_title

        # Bases TreeView
        self.bases_store = Gtk.ListStore(str, str, str, str, str, str)  # idx, name, type, objs, owner, key
        self.bases_tree = Gtk.TreeView(model=self.bases_store)
        for i, title in enumerate(["Idx", "Name", "Type", "Objects", "Owner UID"]):
            rend = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, rend, text=i)
            col.set_sort_column_id(i)
            col.set_resizable(True)
            if i == 1:
                col.set_expand(True)
            self.bases_tree.append_column(col)
        self.bases_tree.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self.bases_tree.get_selection().connect("changed", self.on_bases_selected)
        self.bases_tree.connect("row-activated", lambda tv, path, col: self.do_export())
        scrolled_bases = Gtk.ScrolledWindow()
        scrolled_bases.set_vexpand(True)
        scrolled_bases.set_child(self.bases_tree)
        right.append(scrolled_bases)

        # Action buttons
        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        action_row.set_halign(Gtk.Align.CENTER)
        export_btn = Gtk.Button(label="Export [e]")
        export_btn.add_css_class("suggested-action")
        export_btn.connect("clicked", lambda _: self.do_export())
        nmsbase_btn = Gtk.Button(label="NMSBASE [E]")
        nmsbase_btn.connect("clicked", lambda _: self.do_export_nmsbase())
        view_btn = Gtk.Button(label="View [v]")
        view_btn.connect("clicked", lambda _: self.do_view())
        import_btn = Gtk.Button(label="Import [i]")
        import_btn.add_css_class("destructive-action")
        import_btn.connect("clicked", lambda _: self.do_import())
        recompress_btn = Gtk.Button(label="Recompress [r]")
        recompress_btn.add_css_class("destructive-action")
        recompress_btn.connect("clicked", lambda _: self.do_recompress())
        action_row.append(export_btn)
        action_row.append(nmsbase_btn)
        action_row.append(view_btn)
        action_row.append(import_btn)
        action_row.append(recompress_btn)
        right.append(action_row)

        self.action_status = Gtk.Label(label="")
        self.action_status.set_xalign(0)
        self.action_status.set_wrap(True)
        self.action_status.set_selectable(True)
        self.action_status.add_css_class("dim-label")
        right.append(self.action_status)

        # Status bar
        self.status_bar = Gtk.Label(label="Ready. Autodetected Proton dir. Select save → Load.")
        self.status_bar.set_xalign(0)
        self.status_bar.set_margin_top(4); self.status_bar.set_margin_start(8); self.status_bar.set_margin_bottom(4)
        self.status_bar.add_css_class("dim-label")
        content.append(Gtk.Separator())
        content.append(self.status_bar)

        # Keyboard shortcuts
        self.add_controller(self.create_shortcuts())

        self.refresh_saves()
        self.update_status("Ready. Autodetected Proton dir. Select save → Load.")

    def create_shortcuts(self):
        ctrl = Gtk.ShortcutController()
        ctrl.set_scope(Gtk.ShortcutScope.MANAGED)
        # e, E, v, i, r, c, p, b, ?
        for key, cb in [
            ("e", self.do_export),
            ("E", self.do_export_nmsbase),
            ("v", self.do_view),
            ("i", self.do_import),
            ("r", self.do_recompress),
            ("c", self.filter_corvettes),
            ("p", self.filter_planetary),
            ("b", self.filter_both),
        ]:
            trig = Gtk.ShortcutTrigger.parse_string(key)
            act = Gtk.CallbackAction.new(lambda *a, cb=cb: (cb(), True)[1])
            sc = Gtk.Shortcut.new(trig, act)
            ctrl.add_shortcut(sc)
        return ctrl

    def update_status(self, msg: str):
        self.status_bar.set_label(msg)
        print(msg)

    def show_toast(self, msg: str):
        # Use notify via status bar for now
        self.action_status.set_label(msg)
        self.update_status(msg)

    def refresh_saves(self):
        self.saves_store.clear()
        self.save_files = []
        if not self.save_dir or not self.save_dir.exists():
            self.dir_value.set_label(f"Not found: {self.save_dir} — set $NMS_SAVE_DIR")
            return
        self.dir_value.set_label(str(self.save_dir))
        files = list_save_files(self.save_dir)
        self.save_files = files
        for p in files:
            try:
                sz = p.stat().st_size
                mt = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                szs = f"{sz/1024/1024:.2f} MB" if sz > 1024*1024 else f"{sz/1024:.0f} KB"
            except OSError:
                szs, mt = "?", "?"
            self.saves_store.append([p.name, szs, mt, str(p)])
        if files:
            sel = self.saves_tree.get_selection()
            sel.select_path(Gtk.TreePath.new_from_string("0"))
            self.selected_save = files[0]
        self.save_status.set_label(f"{len(files)} save(s)")

    def on_saves_selected(self, sel):
        model, itr = sel.get_selected()
        if itr:
            path = model[itr][3]
            self.selected_save = Path(path)
            self.update_status(f"Selected save: {Path(path).name} — press Load")

    def do_load(self):
        if not self.selected_save:
            if self.save_files:
                self.selected_save = self.save_files[0]
            else:
                self.show_toast("No save selected")
                return
        self.load_save(str(self.selected_save.name))

    def do_chdir(self):
        dialog = Gtk.FileChooserDialog(title="Select save directory", transient_for=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("_Cancel", Gtk.ResponseType.CANCEL, "_Open", Gtk.ResponseType.ACCEPT)
        if self.save_dir:
            dialog.set_current_folder(Gio.File.new_for_path(str(self.save_dir)))
        def on_resp(d, resp):
            if resp == Gtk.ResponseType.ACCEPT:
                f = d.get_file()
                if f:
                    p = Path(f.get_path())
                    if p.is_file():
                        p = p.parent
                    if p.exists() and p.is_dir():
                        self.save_dir = p
                        self.editor.save_file_directory = str(p)
                        self.editor.selected_save_file_dict = None
                        self.all_bases = []
                        self.filtered = []
                        self.bases_store.clear()
                        self.refresh_saves()
                        self.update_status(f"Save dir changed to {p}")
            d.destroy()
        dialog.connect("response", on_resp)
        dialog.show()

    def load_save(self, save_name: str):
        self.update_status(f"Decompressing {save_name}… (lz4 + mapping)")
        self.save_status.set_label("Decompressing…")
        # Run in thread
        def worker():
            try:
                self.editor.load_save_files(str(self.save_dir))
                self.editor.select_save_file(save_name)
                self.editor.decompress_save_file(save_name, apply_key_mapping=True)
                self.editor.load_bases()
                GLib.idle_add(self.on_load_done, save_name, None)
            except Exception as e:
                import traceback
                traceback.print_exc()
                GLib.idle_add(self.on_load_done, save_name, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def on_load_done(self, save_name, err):
        if err:
            self.save_status.set_label(f"Load failed: {err}")
            self.show_toast(f"Load failed: {err}")
            self.update_status(f"Error: {err}")
            return False
        self.all_bases = self.editor.all_bases
        self.selected_base_type = None
        self.btn_both.set_active(True)
        self.refresh_bases()
        self.update_status(f"Loaded {save_name}: {len(self.all_bases)} bases ✓  Backups in backups/")
        self.save_status.set_label(f"Loaded {save_name} • {len(self.all_bases)} bases")
        return False

    def refresh_bases(self):
        self.bases_store.clear()
        self.filtered = []
        if not self.all_bases:
            self.counts_lbl.set_label("No bases")
            return
        for idx, base in enumerate(self.all_bases):
            try:
                t = base.get("BaseType", {}).get("PersistentBaseTypes", "Unknown") if isinstance(base.get("BaseType"), dict) else "Unknown"
            except Exception:
                t = "Unknown"
            if self.selected_base_type:
                if self.selected_base_type == "PLANETARY":
                    if t not in self.PLANETARY_TYPES:
                        continue
                elif t != self.selected_base_type:
                    continue
            try:
                name = self.editor.get_base_display_name(base, idx)
            except Exception:
                name = base.get("Name") or f"Unnamed {idx}"
            raw_name = (base.get("Name") or "").strip()
            try:
                n = self.editor.get_numer_of_components_from_base(base)
            except Exception:
                n = len(base.get("Objects", [])) if isinstance(base.get("Objects"), list) else 0
            owner = ""
            try:
                owner = (base.get("Owner", {}) or {}).get("UID", "")[:10]
            except Exception:
                pass
            self.filtered.append((idx, base))
            shown = name[:40]
            if t == "PlayerShipBase" and raw_name == "Default" and name != "Default":
                shown = name[:32]
            self.bases_store.append([str(idx), shown, t, str(n), owner, str(idx)])
        # counts
        try:
            from collections import Counter
            cnt = Counter(b.get("BaseType", {}).get("PersistentBaseTypes", "Unknown") for b in self.all_bases)
            total_c = cnt.get("PlayerShipBase", 0)
            total_p = cnt.get("HomePlanetBase", 0) + cnt.get("ExternalPlanetBase", 0)
            total_f = cnt.get("FreighterBase", 0)
            total_s = cnt.get("PlayerSpaceBase", 0)
        except Exception:
            total_c = total_p = total_f = total_s = 0
        try:
            total_objs = self.editor.get_number_of_components_for_all_bases_in_save_file() if self.all_bases else 0
        except Exception:
            total_objs = sum(len(b.get("Objects", [])) if isinstance(b.get("Objects"), list) else 0 for b in self.all_bases)
        self.counts_lbl.set_label(f"Showing {len(self.filtered)}/{len(self.all_bases)} — Ship:{total_c} Planet:{total_p} Freighter:{total_f} Space:{total_s} — Total objs: {total_objs}")
        if self.filtered:
            sel = self.bases_tree.get_selection()
            sel.select_path(Gtk.TreePath.new_from_string("0"))
            self.selected_base_idx = self.filtered[0][0]
        else:
            self.selected_base_idx = None
        self.bases_title.set_label(f"Bases — {len(self.filtered)} shown (filter: {self.selected_base_type or 'Both'}) — select row, then [e]/[v]/[i]")

    def on_bases_selected(self, sel):
        model, itr = sel.get_selected()
        if itr:
            key = model[itr][5]
            try:
                self.selected_base_idx = int(key)
            except Exception:
                pass
            self.action_status.set_label(f"Selected base idx {self.selected_base_idx}")

    def filter_corvettes(self):
        self.selected_base_type = "PlayerShipBase"
        self.btn_corvettes.set_active(True)
        self.refresh_bases()
    def filter_planetary(self):
        self.selected_base_type = "PLANETARY"
        self.btn_planetary.set_active(True)
        self.refresh_bases()
    def filter_both(self):
        self.selected_base_type = None
        self.btn_both.set_active(True)
        self.refresh_bases()

    def on_help(self, _btn):
        dlg = Adw.MessageDialog(transient_for=self, heading="NMS Proton — Help")
        dlg.set_body(
            "Keys: [Enter] Load save • [c] Corvettes [p] Planetary [b] Both\n"
            "Actions: [e] Export JSON to output/bases + clipboard (Base Builder → Import from NMS)\n"
            "         [E] Export NMSBASE (objects-only .nmsbase for NomNom/NMSSE paste after ^BASE_FLAG)\n"
            "         [v] View JSON  [i] Import edited JSON (paste file path or clipboard)\n"
            "         [r] Recompress .hg (backup + atomic write) • [ctrl+b] Backup • [ctrl+r] Restore\n"
            "Workflow: Load save → pick base → Export → edit in Base Builder → Export to NMS → Import → Recompress\n"
            "Backups are in backups/save files/. Close NMS before overwriting."
        )
        dlg.add_response("close", "Close")
        dlg.set_default_response("close")
        dlg.set_close_response("close")
        dlg.present()

    # --- Backup / Restore ---
    def do_backup_save(self):
        if not self.save_dir or not Path(self.save_dir).exists():
            self.show_toast("No save directory — set $NMS_SAVE_DIR or Change dir")
            return
        try:
            candidates = list(Path(self.save_dir).glob("save*.hg"))
        except Exception:
            candidates = []
        if not candidates and self.selected_save and Path(self.selected_save).exists():
            candidates = [Path(self.selected_save)]
        if not candidates:
            self.show_toast(f"No save*.hg found in {self.save_dir}")
            return
        BACKUP_SAVE_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ok = 0
        last_dst = None
        errs = []
        for src in sorted(candidates):
            if not src.is_file():
                continue
            low = src.name.lower()
            if "backup" in low or "before_recompress" in low or "pre_restore" in low:
                continue
            try:
                if src.stat().st_size < 18:
                    continue
            except Exception:
                continue
            stem = src.stem
            dst = BACKUP_SAVE_DIR / f"{stem}_manual_backup_{ts}.hg"
            if dst.exists():
                dst = BACKUP_SAVE_DIR / f"{stem}_manual_backup_{ts}_{ok}.hg"
            try:
                shutil.copy2(src, dst)
                try:
                    os.utime(dst, None)
                except Exception:
                    pass
                if dst.stat().st_size != src.stat().st_size:
                    errs.append(f"{src.name}: size mismatch")
                else:
                    ok += 1
                    last_dst = dst
            except Exception as e:
                errs.append(f"{src.name}: {e}")
        if ok == 0:
            msg = f"Backup failed: {', '.join(errs) if errs else 'unknown error'}"
            self.show_toast(msg)
            self.action_status.set_label(msg)
            return
        msg = f"Backed up {ok} file(s) to {BACKUP_SAVE_DIR} (e.g. {last_dst.name} {last_dst.stat().st_size/1024:.0f} KB)"
        if errs:
            msg += f" — {len(errs)} error(s): {', '.join(errs)}"
        self.save_status.set_label(f"Backed up {ok} save(s) ✓")
        self.action_status.set_label(msg)
        self.show_toast(msg)
        self.update_status("Backup done — inject is memory-only until Recompress. Wrong inject? Just Load again.")
        try:
            if last_dst:
                from nms_tui.file_dialog import reveal_in_file_manager
                reveal_in_file_manager(last_dst)
        except Exception:
            pass

    def do_restore_save(self):
        if not self.selected_save:
            if self.save_files:
                self.selected_save = self.save_files[0]
            else:
                self.show_toast("No save selected to restore over")
                return
        save_name = Path(self.selected_save).name
        stem = Path(save_name).stem
        BACKUP_SAVE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            all_backups = sorted([p for p in BACKUP_SAVE_DIR.glob("*.hg") if stem in p.stem], key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            all_backups = []
        if not all_backups:
            try:
                all_backups = sorted(list(BACKUP_SAVE_DIR.glob("*.hg")), key=lambda p: p.stat().st_mtime, reverse=True)
            except Exception:
                all_backups = []
        if not all_backups:
            self.show_toast(f"No backups found in {BACKUP_SAVE_DIR}")
            try:
                from nms_tui.file_dialog import reveal_in_file_manager
                reveal_in_file_manager(BACKUP_SAVE_DIR)
            except Exception:
                pass
            return
        def on_restore(backup_path: Path):
            target = Path(self.save_dir) / save_name if self.save_dir else Path(self.selected_save)
            # Backup current live file first
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
            # Confirm
            dlg = Adw.MessageDialog(transient_for=self, heading=f"Restore '{save_name}'?")
            body = (f"Backup: {backup_path.name}\n  Size: {backup_path.stat().st_size/1024:.0f} KB\n"
                    f"  Modified: {datetime.fromtimestamp(backup_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Target: {target}\n\nCurrent live file will be backed up as {stem}_pre_restore_*.hg first.\nClose NMS before restoring!")
            dlg.set_body(body)
            dlg.add_response("cancel", "Cancel")
            dlg.add_response("restore", "Restore")
            dlg.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
            dlg.set_default_response("cancel")
            dlg.set_close_response("cancel")
            def on_resp(d, resp):
                if resp != "restore":
                    return
                try:
                    shutil.copy2(backup_path, target)
                    self.show_toast(f"Restored '{save_name}' from {backup_path.name} ✓")
                    self.save_status.set_label(f"Restored {save_name}")
                    self.action_status.set_label(f"Restored {save_name} ← {backup_path.name}")
                    try:
                        self.editor.selected_save_file_dict = None
                        self.all_bases = []
                        self.filtered = []
                        self.bases_store.clear()
                    except Exception:
                        pass
                    self.refresh_saves()
                    for p in self.save_files:
                        if p.name == save_name:
                            self.selected_save = p
                            break
                except Exception as e:
                    self.show_toast(f"Restore failed: {e}")
                d.destroy()
            dlg.connect("response", on_resp)
            dlg.present()
        dlg = RestoreDialog(self, save_name, all_backups, on_restore)
        dlg.present()

    # --- Export / NMSBASE / View / Import / Recompress ---
    def do_export(self):
        if self.selected_base_idx is None:
            self.show_toast("Select a base first")
            return
        idx = self.selected_base_idx
        base = self.all_bases[idx] if 0 <= idx < len(self.all_bases) else None
        if not base:
            self.show_toast("Invalid selection")
            return
        try:
            disp = self.editor.get_base_display_name(base, idx)
        except Exception:
            disp = base.get("Name") or f"base_{idx}"
        safe = safe_name(disp) or safe_name(base.get("Name") or f"base_{idx}")
        self.editor.selected_base = base
        self.editor.selected_base_index = idx
        try:
            raw = base.get("Name") or ""
            if raw and raw != "Default":
                self.editor.select_base(raw)
                self.editor.selected_base = base
                self.editor.selected_base_index = idx
        except Exception:
            pass
        out_dir = ROOT_WRITABLE / "output" / "bases"
        out_dir.mkdir(parents=True, exist_ok=True)
        docs_bases = Path.home() / "Documents" / "No Mans Sky Base Builder" / "bases"
        out_path = out_dir / f"{safe}.json"
        try:
            saved = self.editor.save_selected_base_to_json(str(out_path))
        except Exception:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(base, f, indent=2, ensure_ascii=False)
            saved = str(out_path)
        if docs_bases.exists() and docs_bases.is_dir():
            try:
                shutil.copy2(out_path, docs_bases / f"{safe}.json")
            except Exception:
                pass
        try:
            txt = json.dumps(base, indent=2, ensure_ascii=False)
            try:
                set_clipboard_gtk(txt)
                clip_msg = "copied via clipboard"
            except Exception:
                ok, backend = cli_copy_text(txt)
                clip_msg = f"copied via {backend}" if ok else f"clipboard failed ({backend}) — file saved instead"
        except Exception as e:
            clip_msg = f"clip fail: {e}"
        msg = f"Exported '{disp}' → {saved} | {clip_msg} — Paste in Base Builder: Import base from NMS"
        self.action_status.set_label(msg)
        self.show_toast(msg)

    def do_export_nmsbase(self):
        if self.selected_base_idx is None:
            self.show_toast("Select a base first")
            return
        idx = self.selected_base_idx
        base = self.all_bases[idx] if 0 <= idx < len(self.all_bases) else None
        if not base:
            self.show_toast("Invalid selection")
            return
        try:
            disp = self.editor.get_base_display_name(base, idx)
        except Exception:
            disp = base.get("Name") or f"base_{idx}"
        safe = safe_name(disp) or safe_name(base.get("Name") or f"base_{idx}")
        suggested = ROOT_WRITABLE / "output" / "nmsbase" / f"{safe}.nmsbase"
        suggested.parent.mkdir(parents=True, exist_ok=True)
        # Use GTK file chooser
        dialog = Gtk.FileChooserDialog(title=f"Export '{disp}' as NMSBASE", transient_for=self, action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons("_Cancel", Gtk.ResponseType.CANCEL, "_Save", Gtk.ResponseType.ACCEPT)
        dialog.set_current_name(f"{safe}.nmsbase")
        dialog.set_current_folder(Gio.File.new_for_path(str(suggested.parent)))
        def on_resp(d, resp):
            if resp != Gtk.ResponseType.ACCEPT:
                d.destroy()
                return
            f = d.get_file()
            if not f:
                d.destroy()
                return
            out_path = Path(f.get_path())
            if not out_path.suffix:
                out_path = out_path.with_suffix(".nmsbase")
            d.destroy()
            try:
                saved = self.editor.export_base_as_nmsbase(base, out_path)
            except Exception as e:
                self.show_toast(f"NMSBASE export failed: {e}")
                return
            # Also save copy to default output for history
            try:
                copy_dest = suggested
                if Path(saved).resolve() != copy_dest.resolve():
                    self.editor.export_base_as_nmsbase(base, copy_dest)
            except Exception:
                pass
            try:
                objs = base.get("Objects", [])
                txt = ",\n" + ",\n".join(json.dumps(o, indent=2, ensure_ascii=False) for o in objs) if objs else ""
                try:
                    set_clipboard_gtk(txt)
                    clip_msg = "copied via clipboard"
                except Exception:
                    ok, backend = cli_copy_text(txt)
                    clip_msg = f"copied via {backend}" if ok else f"clipboard failed ({backend})"
            except Exception as e:
                clip_msg = f"clip fail: {e}"
            msg = f"NMSBASE exported '{disp}' → {saved} | {clip_msg} — paste after ^BASE_FLAG"
            self.action_status.set_label(msg)
            self.show_toast(msg)
            try:
                from nms_tui.file_dialog import reveal_in_file_manager
                reveal_in_file_manager(Path(saved))
            except Exception:
                pass
        dialog.connect("response", on_resp)
        dialog.show()

    def do_view(self):
        if self.selected_base_idx is None:
            self.show_toast("Select a base first")
            return
        idx = self.selected_base_idx
        base = self.all_bases[idx]
        txt = json.dumps(base, indent=2, ensure_ascii=False)
        try:
            disp = self.editor.get_base_display_name(base, idx)
        except Exception:
            disp = base.get("Name", "Unnamed")
        dlg = JsonDialog(self, f"{disp} — idx {idx} • {len(txt)} chars", txt)
        dlg.present()

    def do_import(self):
        if not self.editor.selected_save_file_dict:
            self.show_toast("Load a save first")
            return
        if self.selected_base_idx is None:
            self.show_toast("Select target base to replace first (its slot will be overwritten)")
            return
        idx = self.selected_base_idx
        try:
            target_name = self.editor.get_base_display_name(self.all_bases[idx], idx)
        except Exception:
            target_name = self.all_bases[idx].get("Name") or f"idx {idx}"
        # File chooser first
        dialog = Gtk.FileChooserDialog(title=f"Import for '{target_name}' — pick JSON/NMSBASE/Objects", transient_for=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("_Cancel", Gtk.ResponseType.CANCEL, "_Open", Gtk.ResponseType.ACCEPT)
        # Set initial folder
        start = Path.home() / "Documents"
        bba = Path.home() / "Documents" / "No Mans Sky Base Builder" / "bases"
        nmsbase_out = ROOT_WRITABLE / "output" / "nmsbase"
        if bba.exists():
            start = bba
        elif nmsbase_out.exists():
            start = nmsbase_out
        dialog.set_current_folder(Gio.File.new_for_path(str(start)))
        # Add filters
        filt_json = Gtk.FileFilter()
        filt_json.set_name("JSON / NMSBASE (*.json, *.nmsbase, *.txt)")
        filt_json.add_pattern("*.json")
        filt_json.add_pattern("*.nmsbase")
        filt_json.add_pattern("*.txt")
        filt_json.add_pattern("*.JSON")
        filt_json.add_pattern("*.NMSBASE")
        dialog.add_filter(filt_json)
        filt_all = Gtk.FileFilter()
        filt_all.set_name("All files")
        filt_all.add_pattern("*")
        dialog.add_filter(filt_all)
        # Also add a button to paste from clipboard
        extra_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        paste_btn = Gtk.Button(label="Paste JSON from clipboard instead")
        extra_box.append(paste_btn)
        dialog.set_extra_widget(extra_box)
        def do_paste_clipboard(_btn):
            dialog.response(Gtk.ResponseType.NONE)
            # Use clipboard paste
            txt = get_clipboard_text_gtk()
            if not txt:
                txt = ""
            # We need to show an input dialog for paste
            self.do_import_from_text(idx, target_name, txt)
            dialog.destroy()
        paste_btn.connect("clicked", do_paste_clipboard)

        def on_resp(d, resp):
            if resp == Gtk.ResponseType.ACCEPT:
                f = d.get_file()
                if f:
                    path = f.get_path()
                    d.destroy()
                    self.do_import_from_path(idx, target_name, Path(path))
                    return
            elif resp == Gtk.ResponseType.NONE:
                # handled by paste button, don't destroy again
                return
            d.destroy()
            # If cancelled, offer manual paste dialog as fallback
            # Only if user explicitly wants to paste, they clicked paste button
        dialog.connect("response", on_resp)
        dialog.show()

    def do_import_from_path(self, idx: int, target_name: str, p: Path):
        self.do_import_common(idx, target_name, p=p, text=None)

    def do_import_from_text(self, idx: int, target_name: str, text: str):
        # Show an input dialog for pasting
        dlg = Adw.MessageDialog(transient_for=self, heading=f"Paste JSON for '{target_name}'")
        # Use a window with textview for larger paste
        # Simpler: use a dialog with TextView
        win = Adw.Window(transient_for=self, modal=True)
        win.set_title(f"Paste JSON for '{target_name}'")
        win.set_default_size(700, 500)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(12); box.set_margin_bottom(12); box.set_margin_start(12); box.set_margin_end(12)
        win.set_content(box)
        lbl = Gtk.Label(label=f"Paste JSON / Objects array for slot {idx} ('{target_name}'):\nObjects-only arrays like [{{...}}, {{...}}] and .nmsbase leading ',' are supported.")
        lbl.set_wrap(True)
        lbl.set_xalign(0)
        box.append(lbl)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        tv = Gtk.TextView()
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        tv.set_monospace(True)
        buf = tv.get_buffer()
        if text:
            buf.set_text(text)
        scrolled.set_child(tv)
        box.append(scrolled)
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_halign(Gtk.Align.CENTER)
        ok_btn = Gtk.Button(label="Import")
        ok_btn.add_css_class("suggested-action")
        cancel_btn = Gtk.Button(label="Cancel")
        btn_box.append(cancel_btn)
        btn_box.append(ok_btn)
        box.append(btn_box)
        def on_cancel(_b):
            win.close()
        def on_ok(_b):
            start_it = buf.get_start_iter()
            end_it = buf.get_end_iter()
            txt = buf.get_text(start_it, end_it, False)
            win.close()
            if txt.strip():
                self.do_import_common(idx, target_name, p=None, text=txt)
            else:
                # try clipboard
                pasted = get_clipboard_text_gtk()
                if pasted:
                    self.do_import_common(idx, target_name, p=None, text=pasted)
        cancel_btn.connect("clicked", on_cancel)
        ok_btn.connect("clicked", on_ok)
        win.present()

    def do_import_common(self, idx: int, target_name: str, p: Path | None, text: str | None):
        data = None
        def _parse_text(txt: str):
            t = txt.strip()
            if t.startswith(","):
                t = t.lstrip(",").strip()
                if t.startswith("{"):
                    t = "[" + t + "]" if not t.startswith("[") else t
            return json.loads(t)
        if p is not None and p.exists() and p.is_file():
            try:
                raw = p.read_text(encoding="utf-8", errors="ignore")
                try:
                    data = _parse_text(raw)
                except json.JSONDecodeError:
                    raw2 = p.read_text(encoding="utf-8-sig", errors="ignore")
                    data = _parse_text(raw2)
            except Exception as e:
                self.show_toast(f"Failed to load {p}: {e}")
                return
        elif text is not None:
            txt = text.strip()
            if len(txt) < 10:
                pasted = get_clipboard_text_gtk()
                if pasted:
                    txt = pasted
            try:
                data = _parse_text(txt)
            except Exception:
                pasted = get_clipboard_text_gtk()
                if pasted:
                    try:
                        data = _parse_text(pasted)
                    except Exception as e2:
                        self.show_toast(f"Not valid JSON (tried clipboard too): {e2}")
                        return
                else:
                    self.show_toast("Not a file and not valid JSON. Paste file path or JSON.")
                    return
        else:
            self.show_toast("No input")
            return
        # Normalize
        target_base = self.all_bases[idx] if 0 <= idx < len(self.all_bases) else {}
        if isinstance(data, list):
            if not data:
                self.show_toast("JSON list is empty")
                return
            first = data[0] if isinstance(data[0], dict) else None
            if first is not None and "ObjectID" in first:
                new_base = dict(target_base)
                new_base["Objects"] = data
                try:
                    new_base["LastUpdateTimestamp"] = int(datetime.now().timestamp())
                except Exception:
                    pass
                self.show_toast(f"Objects-only import: {len(data)} objects will replace '{target_name}'")
                data = new_base
            elif first is not None and "Objects" in first:
                self.show_toast("JSON was a list of bases — using first element")
                data = data[0]
            else:
                self.show_toast("JSON was a list — using first element")
                data = data[0]
        if not isinstance(data, dict):
            self.show_toast("JSON must be a base object (dict) or Objects array")
            return
        if "ObjectID" in data and "Objects" not in data:
            new_base = dict(target_base)
            new_base["Objects"] = [data]
            data = new_base
            self.show_toast("Single object import — wrapped to Objects")
        if "Objects" not in data:
            self.show_toast("Base JSON missing 'Objects' key — not a valid base")
            return
        # Setup editor
        try:
            try:
                self.editor.select_base(target_name)
            except Exception:
                pass
            self.editor.selected_base = data
            self.editor.selected_base_index = idx
        except Exception as e:
            self.show_toast(f"Setup failed: {e}")
            return
        # Confirm
        dlg = Adw.MessageDialog(transient_for=self, heading=f"Inject edited JSON into slot {idx}?")
        dlg.set_body(f"Target: '{target_name}'\nOriginal will be backed up to backups/bases/")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("inject", "Inject")
        dlg.set_response_appearance("inject", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        def on_resp(d, resp):
            if resp != "inject":
                d.destroy()
                return
            d.destroy()
            try:
                self.editor.inject_selected_base_into_save_file()
                self.all_bases = self.editor.all_bases
                self.refresh_bases()
                self.action_status.set_label(f"Injected into slot {idx} ('{target_name}') — backup in backups/bases/ — now Recompress [r] to write .hg")
                self.show_toast(f"Injected replacement for '{target_name}' (idx {idx}). Backed up original. Now Recompress.")
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.show_toast(f"Inject failed: {e}")
        dlg.connect("response", on_resp)
        dlg.present()

    def do_recompress(self):
        if not self.editor.selected_save_file_dict:
            self.show_toast("No save loaded to recompress")
            return
        if not self.editor.selected_save_file:
            self.show_toast("No save file selected")
            return
        orig_name = self.editor.selected_save_file
        orig_path = Path(self.editor.save_file_directory) / orig_name
        default_out = ROOT_WRITABLE / "output" / orig_name
        default_out.parent.mkdir(parents=True, exist_ok=True)
        msg = f"Recompress '{orig_name}'?\nOriginal: {orig_path}\n• Yes = overwrite live save (backs up to backups/save files/*_before_recompress_*.hg + atomic .tmp)\n• No = write to {default_out}\n\nClose NMS before overwriting!"
        dlg = Adw.MessageDialog(transient_for=self, heading=f"Recompress '{orig_name}'?")
        dlg.set_body(msg)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("output", f"Write to output/")
        dlg.add_response("overwrite", "Overwrite LIVE")
        dlg.set_response_appearance("overwrite", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("output")
        dlg.set_close_response("cancel")
        def on_resp(d, resp):
            d.destroy()
            if resp == "cancel":
                return
            if resp == "overwrite":
                # second confirm
                dlg2 = Adw.MessageDialog(transient_for=self, heading="OVERWRITE LIVE SAVE?")
                dlg2.set_body(f"{orig_path}\nBackup will be made. Ensure NMS is CLOSED.")
                dlg2.add_response("cancel", "Cancel")
                dlg2.add_response("overwrite", "OVERWRITE")
                dlg2.set_response_appearance("overwrite", Adw.ResponseAppearance.DESTRUCTIVE)
                dlg2.set_default_response("cancel")
                dlg2.set_close_response("cancel")
                def on_resp2(d2, resp2):
                    d2.destroy()
                    if resp2 != "overwrite":
                        return
                    self.run_recompress(str(orig_path))
                dlg2.connect("response", on_resp2)
                dlg2.present()
            elif resp == "output":
                self.run_recompress(str(default_out))
        dlg.connect("response", on_resp)
        dlg.present()

    def run_recompress(self, out_path: str):
        self.update_status(f"Recompressing → {out_path} … (reverse-map + lz4)")
        self.action_status.set_label(f"Recompressing → {out_path} …")
        def worker():
            try:
                self.editor.recompress_save_file(out_path, mapping_file=None)
                GLib.idle_add(self.on_recompress_done, out_path, None)
            except Exception as e:
                import traceback
                traceback.print_exc()
                GLib.idle_add(self.on_recompress_done, out_path, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def on_recompress_done(self, out_path, err):
        if err:
            self.show_toast(f"Recompress failed: {err}")
            self.update_status(f"Recompress error: {err}")
            self.action_status.set_label(f"Recompress error: {err}")
        else:
            self.action_status.set_label(f"Wrote {out_path} — backup in backups/save files/")
            self.show_toast(f"Recompressed to {out_path} ✓")
            self.update_status(f"Done → {out_path}")
        return False

class NMSAppGTK(Adw.Application):
    def __init__(self, save_dir: str | None = None):
        super().__init__(application_id="io.github.nms-proton-gtk", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.save_dir = save_dir
        self.connect("activate", self.on_activate)
    def on_activate(self, app):
        win = MainWindow(app, save_dir=Path(self.save_dir).expanduser() if self.save_dir else None)
        win.present()

def main():
    import argparse
    p = argparse.ArgumentParser(description="NMS Proton GTK — Base → Base Builder App")
    p.add_argument("--save-dir", help="Override save directory (else autodetect)")
    p.add_argument("--save-file", help="Save file name to auto-load (e.g. save.hg)")
    p.add_argument("--test", action="store_true", help="Headless test: decompress save and list bases (no GUI)")
    args = p.parse_args()
    if args.test:
        from nms_tui.editor import ProtonSaveEditor
        ed = ProtonSaveEditor(save_dir=args.save_dir)
        try:
            ed.load_save_files()
            print(f"Found saves: {ed.save_files}")
            if not ed.save_files:
                print("No saves found")
                return
            target = args.save_file or ed.save_files[0]
            print(f"Decompressing {target} ...")
            ed.select_save_file(target)
            ed.decompress_save_file(target, apply_key_mapping=True)
            ed.load_bases()
            print(f"Total bases: {len(ed.all_bases)}")
            from collections import Counter
            cnt = Counter(b.get('BaseType',{}).get('PersistentBaseTypes','?') for b in ed.all_bases)
            print("Types:", dict(cnt))
            for i,b in enumerate(ed.all_bases[:5]):
                print(f"  {i}: {ed.get_base_display_name(b,i)!r} type={b.get('BaseType',{}).get('PersistentBaseTypes')} objs={ed.get_numer_of_components_from_base(b)}")
            print("TEST OK")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"TEST FAILED: {e}")
            raise SystemExit(1)
        return
    app = NMSAppGTK(save_dir=args.save_dir)
    app.run(None)

if __name__ == "__main__":
    main()
