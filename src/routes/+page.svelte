<script lang="ts">
  import { onMount } from "svelte";
  import { open, save } from "@tauri-apps/plugin-dialog";
  import { readTextFile } from "@tauri-apps/plugin-fs";
  import { api } from "$lib/api";
  import type { BackupInfo, BaseSummary, SaveFileInfo, TypeCounts } from "$lib/types";

  let saveDir: string | null = $state(null);
  let saveFiles: SaveFileInfo[] = $state([]);
  let selectedSave: string | null = $state(null);
  let loading = $state(false);

  let bases: BaseSummary[] = $state([]);
  let filter: "Both" | "Corvettes" | "Planetary" = $state("Both");
  let counts: TypeCounts | null = $state(null);
  let selectedBase: number | null = $state(null);

  let status = $state("Ready. Autodetecting Proton dir…");
  let actionStatus = $state("");

  // modals
  let viewing: { title: string; text: string } | null = $state(null);
  let importing = $state(false);
  let importText = $state("");
  let restoring = $state(false);
  let backups: BackupInfo[] = $state([]);
  let selectedBackup: string | null = $state(null);

  function toast(msg: string) {
    actionStatus = msg;
    status = msg;
  }

  async function copyText(t: string): Promise<boolean> {
    try {
      await navigator.clipboard.writeText(t);
      return true;
    } catch {
      return false;
    }
  }

  async function refreshSaves() {
    if (!saveDir) return;
    try {
      saveFiles = await api.listSaveFiles(saveDir);
      if (saveFiles.length && !saveFiles.some((f) => f.name === selectedSave)) {
        selectedSave = saveFiles[0].name;
      }
      status = `${saveFiles.length} save(s) in ${saveDir}`;
    } catch (e) {
      toast(`List saves failed: ${e}`);
    }
  }

  async function detectDir() {
    try {
      saveDir = await api.findSaveDir(null);
      if (!saveDir) {
        const dirs = await api.findSaveDirs();
        status = dirs.length ? `No save with .hg found` : "No Proton save dir found — set NMS_SAVE_DIR or Change dir";
        return;
      }
      await refreshSaves();
      if (selectedSave) status = `Ready. Select save → Load.`;
    } catch (e) {
      status = `Autodetect failed: ${e}`;
    }
  }

  async function doChangeDir() {
    const picked = await open({ directory: true, title: "Select save directory (st_…)" });
    if (typeof picked === "string" && picked) {
      saveDir = picked;
      selectedSave = null;
      bases = [];
      selectedBase = null;
      counts = null;
      await refreshSaves();
    }
  }

  async function doLoad() {
    if (!saveDir || !selectedSave) {
      toast("No save selected");
      return;
    }
    loading = true;
    status = `Decompressing ${selectedSave}… (lz4 + mapping)`;
    try {
      const res = await api.decompressSave(saveDir, selectedSave);
      bases = res.bases;
      counts = res.counts;
      selectedBase = bases.length ? 0 : null;
      applyFilter();
      status = `Loaded ${selectedSave}: ${bases.length} bases ✓ backup ${res.backup_path.split("/").pop()}`;
    } catch (e) {
      toast(`Load failed: ${e}`);
    } finally {
      loading = false;
    }
  }

  let shown: BaseSummary[] = $state([]);
  function applyFilter() {
    if (filter === "Corvettes") shown = bases.filter((b) => b.base_type === "PlayerShipBase");
    else if (filter === "Planetary")
      shown = bases.filter((b) => b.base_type === "HomePlanetBase" || b.base_type === "ExternalPlanetBase");
    else shown = [...bases];
    if (shown.length && !shown.some((b) => b.idx === selectedBase)) selectedBase = shown[0].idx;
    if (!shown.length) selectedBase = null;
  }

  function selectedBaseObj(): BaseSummary | null {
    return bases.find((b) => b.idx === selectedBase) ?? null;
  }

  async function doExport() {
    const b = selectedBaseObj();
    if (!b) return toast("Select a base first");
    try {
      const res = await api.exportBase(b.idx);
      const text = await readTextFile(res.path);
      const ok = await copyText(text);
      toast(`Exported '${b.display_name}' → ${res.path} | ${ok ? "copied to clipboard" : "clipboard failed — file saved"} — paste in Base Builder: Import base from NMS`);
    } catch (e) {
      toast(`Export failed: ${e}`);
    }
  }

  async function doExportNmsbase() {
    const b = selectedBaseObj();
    if (!b) return toast("Select a base first");
    try {
      const dest = await save({
        title: `Export '${b.display_name}' as NMSBASE`,
        defaultPath: `${b.display_name.replace(/[^\w\- ]+/g, "").trim().replace(/ /g, "_") || "base"}.nmsbase`,
        filters: [{ name: "NMSBASE", extensions: ["nmsbase", "json", "txt"] }],
      });
      const res = await api.exportNmsbase(b.idx, dest);
      const text = await readTextFile(res.path);
      const ok = await copyText(text);
      toast(`NMSBASE '${b.display_name}' → ${res.path} | ${ok ? "copied" : "file only"} — paste after ^BASE_FLAG`);
    } catch (e) {
      toast(`NMSBASE export failed: ${e}`);
    }
  }

  async function doView() {
    const b = selectedBaseObj();
    if (!b) return toast("Select a base first");
    try {
      const res = await api.exportBase(b.idx);
      const text = await readTextFile(res.path);
      viewing = { title: `${b.display_name} — slot ${b.idx} • ${text.length} chars`, text };
    } catch (e) {
      toast(`View failed: ${e}`);
    }
  }

  async function doPickImportFile() {
    const picked = await open({
      title: "Import — pick JSON / NMSBASE / Objects",
      filters: [
        { name: "JSON / NMSBASE", extensions: ["json", "nmsbase", "txt"] },
        { name: "All", extensions: ["*"] },
      ],
    });
    if (typeof picked === "string" && picked) {
      try {
        importText = await readTextFile(picked);
      } catch (e) {
        toast(`Read file failed: ${e}`);
      }
    }
  }

  async function doImport() {
    const b = selectedBaseObj();
    if (!b) return toast("Select target base to replace first");
    if (!importText.trim()) return toast("Paste JSON or pick a file first");
    if (!confirm(`Inject into slot ${b.idx} ('${b.display_name}')? Original will be backed up.`)) return;
    try {
      const res = await api.importBase(b.idx, importText);
      importing = false;
      importText = "";
      bases = await api.listBases(null);
      const c = { ship: 0, planet: 0, freighter: 0, space: 0, total_objs: 0 };
      for (const x of bases) {
        c.total_objs += x.objects;
        if (x.base_type === "PlayerShipBase") c.ship++;
        else if (x.base_type === "HomePlanetBase" || x.base_type === "ExternalPlanetBase") c.planet++;
        else if (x.base_type === "FreighterBase") c.freighter++;
        else if (x.base_type === "PlayerSpaceBase") c.space++;
      }
      counts = c;
      applyFilter();
      toast(`Injected into slot ${res.idx} ('${b.display_name}', ${res.objects} objs) — backup saved — now Recompress to write .hg`);
    } catch (e) {
      toast(`Inject failed: ${e}`);
    }
  }

  async function doRecompress(mode: string) {
    if (!selectedSave) return toast("No save loaded");
    const label = mode === "overwrite" ? "OVERWRITE LIVE SAVE" : "write to output/";
    if (!confirm(`Recompress '${selectedSave}'? ${label}. Close NMS before overwriting!`)) return;
    if (mode === "overwrite" && !confirm(`Really overwrite ${selectedSave}? A backup will be made first.`)) return;
    try {
      status = `Recompressing…`;
      const out = await api.recompressSave(mode);
      toast(`Recompressed → ${out} ✓`);
    } catch (e) {
      toast(`Recompress failed: ${e}`);
    }
  }

  async function doBackup() {
    if (!saveDir) return toast("No save dir");
    try {
      const paths = await api.backupSaves(saveDir);
      toast(`Backed up ${paths.length} file(s) ✓`);
    } catch (e) {
      toast(`Backup failed: ${e}`);
    }
  }

  async function openRestore() {
    const stem = selectedSave?.replace(/\.hg$/, "") ?? null;
    try {
      backups = await api.listBackups(stem);
    } catch {
      backups = await api.listBackups(null);
    }
    if (!backups.length) return toast("No backups found");
    selectedBackup = backups[0].path;
    restoring = true;
  }

  async function doRestore() {
    if (!selectedBackup || !saveDir || !selectedSave) return;
    if (!confirm(`Restore '${selectedSave}' from backup? Current live file will be backed up first. Close NMS!`)) return;
    try {
      await api.restoreSave(selectedBackup, saveDir, selectedSave);
      restoring = false;
      bases = [];
      selectedBase = null;
      counts = null;
      await refreshSaves();
      toast(`Restored '${selectedSave}' ✓ — Load again to inspect`);
    } catch (e) {
      toast(`Restore failed: ${e}`);
    }
  }

  function onKey(e: KeyboardEvent) {
    const t = e.target as HTMLElement;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
    if (e.key === "e") doExport();
    else if (e.key === "E") doExportNmsbase();
    else if (e.key === "v") doView();
    else if (e.key === "i") (importing = true);
    else if (e.key === "r") doRecompress("output");
    else if (e.key === "c") (filter = "Corvettes", applyFilter());
    else if (e.key === "p") (filter = "Planetary", applyFilter());
    else if (e.key === "b") (filter = "Both", applyFilter());
    else if (e.key === "Enter" && document.activeElement?.id === "saves-list") doLoad();
  }

  onMount(() => {
    detectDir();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
</script>

<div class="flex flex-1 min-h-0">
  <!-- Left panel -->
  <div class="flex flex-col gap-2 p-2 overflow-y-auto" style="width: 340px; border-right: 1px solid var(--border);">
    <div class="text-xs font-semibold uppercase tracking-wide" style="color: var(--muted-foreground);">Save dir</div>
    <div class="text-xs break-all select-all" style="color: var(--muted-foreground);">{saveDir ?? "[no dir found]"}</div>

    <div class="text-xs font-semibold uppercase tracking-wide" style="color: var(--muted-foreground);">Saves</div>
    <div id="saves-list" class="overflow-auto border rounded" style="max-height: 150px; border-color: var(--border);" tabindex="0" role="listbox" aria-label="Saves" onkeydown={(e) => { if (e.key === "Enter") doLoad(); }}>
      <table>
        <thead><tr><th>Save</th><th>Size</th><th>Modified</th></tr></thead>
        <tbody>
          {#each saveFiles as f}
            <tr class:selected={f.name === selectedSave} onclick={() => (selectedSave = f.name)} ondblclick={doLoad} role="option" aria-selected={f.name === selectedSave} tabindex="0" onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectedSave = f.name; } }}>
              <td>{f.name}</td><td>{f.size_display}</td><td>{f.modified}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <div class="flex gap-2 justify-center">
      <button class:selected={filter === "Corvettes"} onclick={() => (filter = "Corvettes", applyFilter())} class="px-2 py-1 text-xs rounded border" style="border-color: var(--border);">Corvettes [c]</button>
      <button onclick={() => (filter = "Planetary", applyFilter())} class="px-2 py-1 text-xs rounded border" style="border-color: var(--border);">Planetary [p]</button>
      <button onclick={() => (filter = "Both", applyFilter())} class="px-2 py-1 text-xs rounded border" style="border-color: var(--border);">Both [b]</button>
    </div>
    {#if counts}
      <div class="text-xs" style="color: var(--muted-foreground);">
        Showing {shown.length}/{bases.length} — Ship:{counts.ship} Planet:{counts.planet} Freighter:{counts.freighter} Space:{counts.space} — Total objs: {counts.total_objs}
      </div>
    {/if}

    <div class="flex gap-2 justify-center">
      <button onclick={doLoad} disabled={loading || !selectedSave} class="px-3 py-1 text-sm rounded font-semibold" style="background: var(--primary); color: var(--primary-foreground); opacity: {loading || !selectedSave ? 0.5 : 1};">{loading ? "Loading…" : "Load"}</button>
      <button onclick={doChangeDir} class="px-3 py-1 text-sm rounded border" style="border-color: var(--border);">Change dir</button>
    </div>
    <div class="flex gap-2 justify-center">
      <button onclick={doBackup} class="px-3 py-1 text-sm rounded border" style="border-color: var(--border);">Backup</button>
      <button onclick={openRestore} class="px-3 py-1 text-sm rounded border" style="border-color: var(--border);">Restore…</button>
    </div>
    <div class="text-xs" style="color: var(--muted-foreground);">{saveFiles.length} save(s){selectedSave ? ` • selected ${selectedSave}` : ""}</div>
  </div>

  <!-- Right panel -->
  <div class="flex flex-col flex-1 min-w-0 gap-2 p-2">
    <div class="text-xs font-semibold uppercase tracking-wide" style="color: var(--muted-foreground);">Bases — pick one to Export → Base Builder ({shown.length} shown, filter: {filter})</div>
    <div class="flex-1 overflow-auto border rounded" style="border-color: var(--border);">
      <table>
        <thead><tr><th>Idx</th><th>Name</th><th>Type</th><th>Objects</th><th>Owner UID</th></tr></thead>
        <tbody>
          {#each shown as b}
            <tr class:selected={b.idx === selectedBase} onclick={() => (selectedBase = b.idx)} ondblclick={doExport} role="button" tabindex="0" onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectedBase = b.idx; } }}>
              <td>{b.idx}</td><td class="max-w-60 truncate" title={b.display_name}>{b.display_name}</td><td>{b.base_type}</td><td>{b.objects}</td><td class="font-mono text-xs">{b.owner_uid.slice(0, 10)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if !shown.length}<div class="p-8 text-center text-sm" style="color: var(--muted-foreground);">{bases.length ? "No bases match filter" : "Load a save to list bases"}</div>{/if}
    </div>

    <div class="flex gap-2 justify-center flex-wrap">
      <button onclick={doExport} class="px-3 py-1 text-sm rounded font-semibold" style="background: var(--primary); color: var(--primary-foreground);">Export [e]</button>
      <button onclick={doExportNmsbase} class="px-3 py-1 text-sm rounded border" style="border-color: var(--border);">NMSBASE [E]</button>
      <button onclick={doView} class="px-3 py-1 text-sm rounded border" style="border-color: var(--border);">View [v]</button>
      <button onclick={() => (importing = true)} class="px-3 py-1 text-sm rounded border" style="border-color: var(--destructive); color: #fca5a5;">Import [i]</button>
      <button onclick={() => doRecompress("output")} class="px-3 py-1 text-sm rounded border" style="border-color: var(--destructive); color: #fca5a5;">Recompress [r]</button>
      <button onclick={() => doRecompress("overwrite")} class="px-3 py-1 text-sm rounded border" style="border-color: var(--destructive); color: #fca5a5;">Overwrite LIVE</button>
    </div>
    <div class="text-xs break-all select-all" style="color: var(--muted-foreground);">{actionStatus}</div>
  </div>
</div>

<div class="shrink-0 px-2 py-1 text-xs border-t" style="border-color: var(--border); color: var(--muted-foreground);">{status}</div>

<!-- View modal -->
{#if viewing}
  <div class="fixed inset-0 flex items-center justify-center p-8" style="background: rgba(0,0,0,0.7);" role="dialog" aria-modal="true" aria-label="Base JSON">
    <div class="flex flex-col gap-2 p-4 rounded w-full h-full overflow-hidden" style="background: var(--card);">
      <div class="font-semibold">{viewing.title}</div>
      <pre class="flex-1 overflow-auto text-xs font-mono p-2 rounded" style="background: var(--background);">{viewing.text}</pre>
      <div class="flex gap-2 justify-center">
        <button onclick={async () => { await copyText(viewing?.text ?? ""); viewing = null; }} class="px-3 py-1 text-sm rounded font-semibold" style="background: var(--primary); color: var(--primary-foreground);">Copy & Close</button>
        <button onclick={() => (viewing = null)} class="px-3 py-1 text-sm rounded border" style="border-color: var(--border);">Close</button>
      </div>
    </div>
  </div>
{/if}

<!-- Import modal -->
{#if importing}
  <div class="fixed inset-0 flex items-center justify-center p-8" style="background: rgba(0,0,0,0.7);" role="dialog" aria-modal="true" aria-label="Import JSON">
    <div class="flex flex-col gap-2 p-4 rounded w-full h-full overflow-hidden" style="background: var(--card);">
      <div class="font-semibold">Paste JSON / Objects array for slot {selectedBase} ('{selectedBaseObj()?.display_name ?? ""}')</div>
      <div class="text-xs" style="color: var(--muted-foreground);">Objects-only arrays and .nmsbase leading-comma text are supported.</div>
      <textarea bind:value={importText} class="flex-1 font-mono text-xs p-2 rounded" style="background: var(--background); color: var(--foreground); border: 1px solid var(--border);" placeholder='Paste here, or pick a file…'></textarea>
      <div class="flex gap-2 justify-center">
        <button onclick={doPickImportFile} class="px-3 py-1 text-sm rounded border" style="border-color: var(--border);">Pick file…</button>
        <button onclick={doImport} class="px-3 py-1 text-sm rounded font-semibold" style="background: var(--primary); color: var(--primary-foreground);">Import</button>
        <button onclick={() => (importing = false)} class="px-3 py-1 text-sm rounded border" style="border-color: var(--border);">Cancel</button>
      </div>
    </div>
  </div>
{/if}

<!-- Restore modal -->
{#if restoring}
  <div class="fixed inset-0 flex items-center justify-center p-8" style="background: rgba(0,0,0,0.7);" role="dialog" aria-modal="true" aria-label="Restore backup">
    <div class="flex flex-col gap-2 p-4 rounded w-full max-w-2xl max-h-full overflow-hidden" style="background: var(--card);">
      <div class="font-semibold">Restore '{selectedSave}' — pick a backup (live file will be backed up again; close NMS first!)</div>
      <div class="overflow-auto border rounded" style="border-color: var(--border);">
        <table>
          <thead><tr><th>Backup file</th><th>Size</th><th>Modified</th></tr></thead>
          <tbody>
            {#each backups as bk}
              <tr class:selected={bk.path === selectedBackup} onclick={() => (selectedBackup = bk.path)} role="button" tabindex="0" onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectedBackup = bk.path; } }}>
                <td class="font-mono text-xs">{bk.name}</td><td>{bk.size_display}</td><td>{bk.modified}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <div class="flex gap-2 justify-center">
        <button onclick={doRestore} class="px-3 py-1 text-sm rounded font-semibold" style="background: var(--destructive); color: white;">Restore</button>
        <button onclick={() => (restoring = false)} class="px-3 py-1 text-sm rounded border" style="border-color: var(--border);">Cancel</button>
      </div>
    </div>
  </div>
{/if}

<style>
  button.selected {
    outline: 2px solid var(--primary);
  }
</style>
