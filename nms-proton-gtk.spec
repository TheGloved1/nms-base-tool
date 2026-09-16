# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata
import os

# Collect gi and related
gi_datas, gi_binaries, gi_hidden = collect_all('gi', include_py_files=True)
cairo_datas, cairo_binaries, cairo_hidden = collect_all('cairo', include_py_files=True) if True else ([], [], [])

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=gi_binaries + cairo_binaries,
    datas=[
        ('vendor', 'vendor'),
        ('nms_tui', 'nms_tui'),
        ('nms_gtk', 'nms_gtk'),
    ] + gi_datas + cairo_datas + collect_data_files('lz4'),
    hiddenimports=[
        'gi', 'gi.repository.Gtk', 'gi.repository.Adw', 'gi.repository.Gio', 'gi.repository.Gdk', 'gi.repository.GLib', 'gi.repository.Pango', 'gi.repository.GtkSource',
        'cairo', 'pycairo',
        'lz4', 'lz4.block',
        'save_editor', 'key_mapper', 'recompressor',
        'utils', 'utils.file_utils', 'utils.save_extractor', 'utils.base_or_corvette_detection', 'utils.save_file_manager', 'utils.save_metadata',
        'nms_tui.proton', 'nms_tui.editor', 'nms_tui.clipboard', 'nms_tui.file_dialog', 'nms_tui.paths',
        'nms_gtk.app',
    ] + gi_hidden + cairo_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Filter out large unnecessary data if needed, keep as is for now
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='nms-proton-gtk',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
