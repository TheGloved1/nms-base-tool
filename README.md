# NMSBT — NMS Base Tool

Move No Man's Sky bases between saves and editing tools: pull a Corvette,
freighter, or planetary base out of your save, tweak it in
[djmonkeyuk's Base Builder](https://www.nexusmods.com/nomanssky/mods/2598),
and put it back — with a backup made at every step.

## Install

Download the latest build for your system from the
[Releases page](https://github.com/TheGloved1/nms-base-tool/releases):

- **Windows** — `.msi` installer (Steam and GOG saves)
- **Linux / Steam Deck** — `.AppImage` or `.deb` (Proton saves)
- **macOS** — `.dmg`

The app updates itself when new versions are published. Xbox Game Pass saves
are not supported (different save format).

## Typical workflow

1. **Close No Man's Sky completely.** Editing while the game runs (or with
   Steam Cloud syncing) can undo your changes.
2. Open NMSBT. Your saves are usually found automatically — pick one (e.g.
   `save.hg`) and press **Load**.
3. Find your base in the list. Use the **Corvettes / Planetary / Both**
   filter or the search box.
4. Press **Export**. The base is copied to your clipboard and saved to a file.
5. In Base Builder: *Import base from NMS* → paste → make your edits →
   *Export to NMS* → copy.
6. Back in NMSBT, select the same slot and press **Import…** → paste → **Inject**.
   The original is backed up first.
7. Press **Overwrite LIVE** to write the change into your save (a backup of
   the whole save is made first), or **Recompress** to write a separate file.
8. Launch the game and load that save. Your edited base should be there.

> Injecting only changes the app's memory copy — nothing touches your real
> save until you Recompress/Overwrite.

## Safety built in

- Exporting never modifies anything.
- Every import backs up the original base; every overwrite backs up the whole save.
- The **Backup** button copies all your `save*.hg` files; **Restore…** puts one back
  (your current file is backed up again first, just in case).

## If your saves aren't found

Press **Choose folder…** (or the folder button in the top bar) and point the
app at the folder containing your saves — picking the parent `NMS` folder also
works, it looks inside for you. Your choice is remembered; reset it any time
from Settings (gear icon) or the × next to the folder.

Where saves live, for reference:

- **Windows (Steam/GOG):** `C:\Users\<you>\AppData\Roaming\HelloGames\NMS\st_…`
- **macOS:** `~/Library/Application Support/HelloGames/NMS/st_…`
- **Linux/Deck (Proton):** `~/.local/share/Steam/steamapps/compatdata/275850/…/HelloGames/NMS/st_…`

## Keyboard shortcuts

`e` export · `E` NMSBASE export · `v` view · `i` import · `r` recompress ·
`c`/`p`/`b` Corvettes/Planetary/Both filter. Double-click a base to export it.

## Troubleshooting

- **My edit didn't show up in game** — NMS was probably open, or Steam Cloud
  restored the old file. Close the game, disable Cloud briefly, redo the
  Recompress step.
- **Import says invalid JSON** — paste the exact text Base Builder's *Export
  to NMS* gives you. Both full-base JSON and objects-only lists are accepted.
- **Something broke** — use **Restore…** to roll back to any automatic backup.
  Backups live in `~/.local/share/nms-base-tool/backups/` on Linux,
  `%AppData%\nms-base-tool\backups\` on Windows, and
  `~/Library/Application Support/nms-base-tool/backups/` on macOS.
- **Parts of an imported build are missing** — the save needs those building
  parts unlocked in-game.

Found a bug? [Open an issue](https://github.com/TheGloved1/nms-base-tool/issues).

## Credits

Save handling based on [NMS-Base-File-Editor](https://github.com/NightCodeOfficial/NMS-Base-File-Editor)
(MIT) — save decoding (Robert Maupin), key mapping
([MBINCompiler](https://github.com/monkeyman192/MBINCompiler)), base editing (djmonkeyuk).
