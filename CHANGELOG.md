# Changelog



## [26.9.2] - 2026-09-16

### Other

- rename to nms-base-tool (NMSBT)

## [26.9.1] - 2026-09-16

### Added

- Tauri (Rust) + SvelteKit rewrite of NMS save editor

### Other

- add updater public key
- update paths for folder rename
- remove legacy Python app, debug artifacts, and build outputs
- drop stray pycache files, restore pyc ignores

## [26.9.0] - 2026-09-16

### Added

- Tauri (Rust) + SvelteKit rewrite of the Python/GTK app, scaffolded with `bunx create-tauri-app --template svelte-ts`
- Native Rust save engine: LZ4 `.hg` decompress, MBINCompiler key mapping (7-day cache), base list/export/import/recompress, backup/restore
- NoModsSky release workflow (`scripts/release.ts`, `sync-version.js`, `generate-updater-json.sh`, `.github/workflows/release.yml`)
