<!-- markdownlint-disable MD013 -->
# NMSBT — NMS Base Tool (No Man's Sky, Linux/Proton, Tauri + SvelteKit)

Tauri (Rust) + SvelteKit GUI for extracting and editing No Man's Sky bases
(Corvettes, freighters, planetary bases) in Proton saves at
`steamapps/compatdata/275850/...`. Ported from the Python/GTK implementation
(removed; preserved in git history) and the Windows-only GUI from
[NMS-Base-File-Editor](https://github.com/NightCodeOfficial/NMS-Base-File-Editor).

## What it does

- **Autodetects** save folders on Windows (Steam + GOG: `%AppData%\HelloGames\NMS`),
  macOS (`~/Library/Application Support/HelloGames/NMS`), and Linux/Steam Deck
  (Proton `steamapps/compatdata/275850/...`, Flatpak, snap) — Steam `st_*` and
  GOG `DefaultUser` containers. Xbox Game Pass (`wgs` containers) is not supported.
- **Manual location**: if nothing is detected you can pick the folder yourself;
  it is remembered (change/reset anytime via the header or Settings). `$NMS_SAVE_DIR`
  still overrides everything.
- Lists `save.hg`/`save2.hg`, decompresses via `lz4_flex` + deobfuscates via
  `MBINCompiler mapping.json` (cached 7d in `~/.local/share/nms-base-tool/.nms_mapping_cache`).
- Lets you filter by `PlayerShipBase` (Corvette/Freighter) vs
  `ExternalPlanetBase` (Planetary) vs Both, pick a base by `Name`, and:

  - **Export** single-base JSON for
    [djmonkeyuk's NMS Base Builder](https://www.nexusmods.com/nomanssky/mods/2598)
    (“Import base from NMS” → paste). Copies to clipboard + saves to
    `output/bases/<safe>.json` and optionally
    `~/Documents/No Mans Sky Base Builder/bases/`
  - **Export NMSBASE** objects-only `.nmsbase` (`,\n{...}`) for NomNom/NMSSE paste after `^BASE_FLAG`
  - **Import** edited JSON / Objects array / `.nmsbase` into the selected slot
    (original backed up to `backups/bases/`)
  - **Recompress** to `.hg` (keys reverse-mapped, compact JSON, `0xFEEDA1E5`
    LZ4 blocks, atomic `.tmp`→rename, backup `*_before_recompress_*.hg`
    when overwriting the live save)
  - **Backup / Restore** saves (`backups/save files/`)

## Saves location

Autodetected per platform (see above), or picked manually in the app
(remembered until reset). `$NMS_SAVE_DIR` overrides everything:

```bash
NMS_SAVE_DIR=/custom/path bun run tauri dev
```

Proton probes in order (Linux/Deck):

1. `$NMS_SAVE_DIR` if set and exists
2. `~/.steam/steam/.../HelloGames/NMS`
3. `~/.local/share/Steam/.../HelloGames/NMS` ← your install
4. `~/.var/app/com.valvesoftware.Steam/...` (Flatpak)
5. `~/snap/steam/...`

## Run

```bash
cd ~/git/nms-base-tool
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

Backend checks (no GUI, uses the live save read-only):

```bash
cargo test --manifest-path src-tauri/Cargo.toml
```

## Release (same workflow as NoModsSky)

```bash
bun run sync-version          # package.json -> Cargo.toml / tauri.conf.json
bun scripts/release.ts patch  # calver bump + CHANGELOG + tag + push; CI builds
```

CI (`.github/workflows/release.yml`) builds windows/linux/macos bundles on
`v*` tags and publishes `updater.json` (signed with `TAURI_SIGNING_PRIVATE_KEY`).

## Workflow

1. Pick save (e.g. `save.hg`) → `Load` (decompress + list bases)
2. Toggle type: `Corvettes` / `Planetary` / `Both`
3. Select base → `Export` writes `output/bases/<Name>.json` + copies; paste into Base Builder → edit → “Export to NMS” → copy
4. Back in app: `Import` → pick file or paste JSON (supports full base JSON, Objects-only arrays, `.nmsbase` leading `,`)
5. `Recompress` → overwrite live save (with backup) or write to `output/`
6. `Backup` / `Restore…` for saves (manual). `Inject` is memory-only until `Recompress`.

Keys: `[e]` export `[E]` NMSBASE `[v]` view `[i]` import `[r]` recompress
`[c]/[p]/[b]` filters. App data (backups, output, mapping cache) lives in
`~/.local/share/nms-base-tool/`. **Back up saves before editing**
(game closed is safest).

## Linux notes

- Run with NMS closed when recompressing; Steam Cloud may overwrite — disable
  briefly or restore from backup.

## Credits

Save format logic ported from `NMS-Base-File-Editor` (MIT, © 2025
NightCodeOfficial) — decompression (`NMS-Save-Decoder` by Robert Maupin), key
mapping (`MBINCompiler` monkeyman192), base editor djmonkeyuk.
