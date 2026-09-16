<!-- markdownlint-disable MD013 -->
# nms-save-editor — No Man's Sky Save Editor (Linux/Proton, Tauri + SvelteKit)

GTK4/Libadwaita GUI that replaces the Windows-only GUI from
[NMS-Base-File-Editor](https://github.com/NightCodeOfficial/NMS-Base-File-Editor)
for Proton saves at `steamapps/compatdata/275850/...`.

Built as a single binary with PyInstaller (`py-dist/nms-proton-gtk`, ~190 MB).

> Ported from Python/GTK to Tauri (Rust) + SvelteKit. The Python implementation
> is kept in `nms_gtk/`, `nms_tui/`, `vendor/` as `legacy reference` — see
> “Legacy Python app” below. New development happens in `src/` + `src-tauri/`.

## What it does

- **Autodetects** Proton save dirs (`~/.local/share/Steam/.../HelloGames/NMS/st_*`,
  Flatpak, `~/.steam/...`, `$NMS_SAVE_DIR` override).
- Lists `save.hg`/`save2.hg`, decompresses via `lz4.block` + deobfuscates via
  `MBINCompiler mapping.json` (cached 7d, now in `~/.local/share/nms-proton-tui/.nms_mapping_cache` when bundled).
- Lets you filter by `PlayerShipBase` (Corvette/Freighter) vs
  `ExternalPlanetBase` (Planetary) vs Both, pick a base by `Name`, and:

  - **Export** single-base JSON for
    [djmonkeyuk's NMS Base Builder](https://www.nexusmods.com/nomanssky/mods/2598)
    (“Import base from NMS” → paste)
  - **Copy** to clipboard (GTK clipboard → `wl-copy`/`xclip` fallback) +
    saves to `output/bases/<safe>.json` and optionally
    `~/Documents/No Mans Sky Base Builder/bases/`
  - **Export NMSBASE** objects-only `.nmsbase` (`,\n{...}`) for NomNom/NMSSE paste after `^BASE_FLAG`
  - **Import** edited JSON / Objects array / `.nmsbase` → `inject_selected_base_into_save_file()` + backup `backups/bases/*_backup_*.json`
  - **Recompress** to `.hg` (`recompressor.py` reverse-maps keys,
    `lz4.block.compress` blocks `0xFEEDA1E5`), atomic `.tmp`→`os.replace`,
    backup `*_before_recompress_*.hg` if overwriting live save.
  - **Backup / Restore** saves (`Backups/save files/`): manual `Backup` backs up all `save*.hg`, `Restore…` lists by `mtime` (fixed `shutil.copy2` + `os.utime` so `Modified` is backup time, not original).

## Saves location (autodetect only)

Probes in order:

1. `$NMS_SAVE_DIR` if set and exists
2. `~/.steam/steam/.../HelloGames/NMS`
3. `~/.local/share/Steam/.../HelloGames/NMS` ← your install
4. `~/.var/app/com.valvesoftware.Steam/...` (Flatpak)
5. `~/snap/steam/...`

Override: `NMS_SAVE_DIR=/custom/path nms-proton-gtk`

## Run (Tauri app - Recommended)

```bash
cd ~/git/nms-proton-tui
bun install
bun run tauri dev
# production bundle (.deb/.AppImage, plus msi/dmg on CI)
bun run tauri build
```

Needs Tauri system deps (same list as
[NoModsSky](https://github.com/TheGloved1/NoModsSky)): on Debian
`libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev libssl-dev
libayatana-appindicator3-dev librsvg2-dev`, plus Rust via `rustup`.
Per https://tauri.app/start/prerequisites/ and
https://tauri.app/start/frontend/sveltekit/ the frontend is SvelteKit in SPA
mode (`adapter-static`, `ssr = false`, `frontendDist: ../build`).

## Release (same workflow as NoModsSky)

```bash
bun run sync-version          # package.json -> Cargo.toml / tauri.conf.json
bun scripts/release.ts patch  # calver bump + CHANGELOG + tag + push; CI builds
```

CI (`.github/workflows/release.yml`, copied from NoModsSky) builds
windows/linux/macos bundles on `v*` tags and publishes `updater.json`.
Before the first release: `git init` + push to
`github.com/TheGloved1/nms-save-editor`, then
`bun tauri signer generate` and paste the public key into
`src-tauri/tauri.conf.json > plugins.updater.pubkey` (currently `TODO`).

## Run (Legacy Python binary)

Single binary, no venv needed:

```bash
./py-dist/nms-proton-gtk
# or via wrapper
./run.sh
# explicit dir
NMS_SAVE_DIR=/path/to/st_*/ nms-proton-gtk
# headless test (no GUI, verifies lz4 + mapping + decompress)
./py-dist/nms-proton-gtk --test
# old TUI fallback
./py-dist/nms-proton-gtk --tui
./run.sh --tui
```

If built binary is present, `run.sh` prefers it, else falls back to `venv` GTK.

## Run (Dev, no binary)

```bash
cd ~/git/nms-proton-tui
python -m venv .venv
source .venv/bin/activate
pip install -e .
# GTK (default)
python main.py
python -m nms_gtk.app
# TUI legacy
python main.py --tui
python -m nms_tui.app
```

Needs GTK4 + Libadwaita (`gtk4` `libadwaita` on CachyOS already present). Test: `python -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1'); print('ok')"`.

## Build Legacy Single Binary (Python/GTK)

```bash
./build.sh
# or manually
.venv/bin/pyinstaller nms-proton-gtk.spec --noconfirm --clean
# output
ls -lh py-dist/nms-proton-gtk  # ~190 MB, onefile, windowed (console=False)
./py-dist/nms-proton-gtk --help
./py-dist/nms-proton-gtk --test
```

Spec: `nms-proton-gtk.spec` bundles `vendor/upstream`, `nms_tui`, `nms_gtk`, `gi`, `lz4` (`collect_all`). Freeze-aware paths via `nms_tui/paths.py` (`get_writable_data_dir()` → `~/.local/share/nms-proton-tui` when exe not writable, else next to binary). `key_mapper` cache + `file_utils` settings patched to writable at runtime (`nms_gtk/app.py`).

## Workflow

1. Pick save (e.g. `save.hg`) → `Load` (decompress + `load_bases()`)
2. Toggle type: `Corvettes` / `Planetary` / `Both`
3. Select base → `Export` writes `output/bases/<Name>.json` + copies; paste into Base Builder → edit → “Export to NMS” → copy
4. Back in GUI: `Import` → pick file via GTK file chooser or `Paste JSON from clipboard` (supports full base JSON, Objects-only `[{ObjectID...}]`, `.nmsbase` leading `,`)
5. `Recompress` → choose overwrite live save (with backup) or new file in `output/`
6. `Backup` / `Restore…` for saves (manual). `Inject` is memory-only until `Recompress`.

Backups are under `backups/save files/`, `backups/bases/`,
`backups/decompressed files/` relative to writable data dir (`./` dev or `~/.local/share/nms-proton-tui` bundled). **Always manually back up saves before editing** (game closed is safest).

## Linux notes

- The upstream `utils/file_utils.py:get_default_save_directory()` is
  Windows-only → patched via `nms_tui/proton.py`.
- Run with NMS closed when recompressing; Steam Cloud may overwrite — disable
  briefly or let backup restore.
- Tested on CachyOS 7.1.8, Python 3.14, GTK 4.22, Libadwaita 1, PyGObject 3.58, lz4 4.4.5.

## Credits

Core logic vendored from `vendor/upstream` (MIT, © 2025 NightCodeOfficial) —
decompression (`NMS-Save-Decoder` by Robert Maupin), key mapping
(`MBINCompiler` monkeyman192), base editor djmonkeyuk.
GTK port + PyInstaller single-binary wrapping added.
