<script lang="ts">
  import { onMount } from "svelte";
  import { open, save } from "@tauri-apps/plugin-dialog";
  import { api } from "$lib/api";
  import type { BackupInfo, BaseSummary, SaveFileInfo, TypeCounts } from "$lib/types";
  import { FONTS, THEMES, applyUiSettings, clearSaveDirOverride, loadSaveDirOverride, loadUiSettings, saveSaveDirOverride, saveUiSettings } from "$lib/settings";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Badge } from "$lib/components/ui/badge";
  import * as Dialog from "$lib/components/ui/dialog";
  import * as Table from "$lib/components/ui/table";
  import { Textarea } from "$lib/components/ui/textarea";
  import { Separator } from "$lib/components/ui/separator";
  import * as Empty from "$lib/components/ui/empty";
  import * as Select from "$lib/components/ui/select";
  import {
    CircleAlert,
    CircleCheck,
    Copy,
    Database,
    Download,
    Eye,
    FileJson,
    FolderOpen,
    HardDriveDownload,
    Info,
    LoaderCircle,
    Save,
    Search,
    Settings,
    Upload,
    X,
  } from "lucide-svelte";

  // --- saves ---
  let saveDir: string | null = $state(null);
  let saveDirManual = $state(false);
  let saveFiles: SaveFileInfo[] = $state([]);
  let selectedSave: string | null = $state(null);
  let loading = $state(false);

  // --- bases ---
  let bases: BaseSummary[] = $state([]);
  let filter: "Both" | "Corvettes" | "Planetary" = $state("Both");
  let counts: TypeCounts | null = $state(null);
  let selectedBase: number | null = $state(null);
  let search = $state("");
  let sortMode = $state("name");

  // --- status + toasts ---
  let status = $state("Ready. Autodetecting Proton dir…");
  interface Toast {
    id: number;
    kind: "success" | "error" | "info";
    msg: string;
  }
  let toasts: Toast[] = $state([]);
  let toastId = 0;
  function pushToast(kind: Toast["kind"], msg: string) {
    const id = ++toastId;
    toasts = [...toasts, { id, kind, msg }];
    status = msg;
    setTimeout(() => {
      toasts = toasts.filter((t) => t.id !== id);
    }, 6000);
  }
  const toastOk = (m: string) => pushToast("success", m);
  const toastErr = (m: string) => pushToast("error", m);

  // --- dialogs ---
  let viewing: { title: string; text: string } | null = $state(null);
  let exportOpen = $state(false);
  let exportFormat: "json" | "nmsbase" = $state("json");
  let importing = $state(false);
  let importText = $state("");
  let importingBusy = $state(false);
  let restoring = $state(false);
  let backups: BackupInfo[] = $state([]);
  let selectedBackup: string | null = $state(null);
  let recompressMode: "output" | "overwrite" | null = $state(null);
  let settingsOpen = $state(false);
  let theme = $state("default");
  let font = $state("inter");

  async function copyText(t: string): Promise<boolean> {
    try {
      await navigator.clipboard.writeText(t);
      return true;
    } catch {
      return false;
    }
  }

  // --- derived list ---
  let shown = $derived.by(() => {
    let list = [...bases];
    if (filter === "Corvettes") list = list.filter((b) => b.base_type === "PlayerShipBase");
    else if (filter === "Planetary")
      list = list.filter((b) => b.base_type === "HomePlanetBase" || b.base_type === "ExternalPlanetBase");
    const q = search.trim().toLowerCase();
    if (q)
      list = list.filter((b) =>
        `${b.display_name} ${b.name} ${b.base_type}`.toLowerCase().includes(q),
      );
    if (sortMode === "objects") list.sort((a, b) => b.objects - a.objects);
    else if (sortMode === "type")
      list.sort(
        (a, b) => a.base_type.localeCompare(b.base_type) || a.display_name.localeCompare(b.display_name),
      );
    else list.sort((a, b) => a.display_name.localeCompare(b.display_name));
    return list;
  });
  $effect(() => {
    if (shown.length && !shown.some((b) => b.idx === selectedBase)) selectedBase = shown[0].idx;
    if (!shown.length) selectedBase = null;
  });

  function selectedBaseObj(): BaseSummary | null {
    return bases.find((b) => b.idx === selectedBase) ?? null;
  }

  function typeBadgeVariant(t: string): "default" | "secondary" | "outline" {
    if (t === "PlayerShipBase") return "default";
    if (t === "HomePlanetBase" || t === "ExternalPlanetBase") return "secondary";
    return "outline";
  }
  function typeBadgeClass(t: string): string {
    if (t === "HomePlanetBase" || t === "ExternalPlanetBase")
      return "border-emerald-500/40 text-emerald-400";
    if (t === "FreighterBase") return "border-amber-500/40 text-amber-400";
    return "";
  }
  function shortType(t: string): string {
    if (t === "PlayerShipBase") return "Corvette";
    if (t === "HomePlanetBase" || t === "ExternalPlanetBase") return "Planetary";
    if (t === "FreighterBase") return "Freighter";
    if (t === "PlayerSpaceBase") return "Space";
    return t;
  }

  // --- actions ---
  async function refreshSaves() {
    if (!saveDir) return;
    try {
      saveFiles = await api.listSaveFiles(saveDir);
      if (saveFiles.length && !saveFiles.some((f) => f.name === selectedSave)) {
        selectedSave = saveFiles[0].name;
      }
      status = `${saveFiles.length} save(s) in ${saveDir}`;
    } catch (e) {
      toastErr(`List saves failed: ${e}`);
    }
  }

  async function detectDir() {
    // 1. remembered manual location wins (persisted in settings store)
    try {
      const manual = await loadSaveDirOverride();
      if (manual) {
        const files = await api.listSaveFiles(manual).catch(() => []);
        if (files.length) {
          saveDir = manual;
          saveDirManual = true;
          await refreshSaves();
          status = "Ready. Select a save, then press Load.";
          return;
        }
        // maybe they picked the parent NMS folder — drill into first child with saves
        const kids = await api.listSaveSubdirs(manual).catch(() => []);
        for (const kid of kids) {
          const kf = await api.listSaveFiles(kid).catch(() => []);
          if (kf.length) {
            saveDir = kid;
            saveDirManual = true;
            await refreshSaves();
            toastOk(`Using saves found in ${kid.split("/").slice(-1)}`);
            return;
          }
        }
        toastErr(`Remembered save folder has no saves: ${manual} — pick again or reset to auto`);
      }
    } catch (e) {
      toastErr(`Saved location failed: ${e}`);
    }
    // 2. platform autodetect (Proton/Steam/GOG/macOS — see README)
    try {
      saveDir = await api.findSaveDir(null);
      saveDirManual = false;
      if (!saveDir) {
        const dirs = await api.findSaveDirs();
        status = dirs.length
          ? "No save with .hg found"
          : "No save folder detected — choose it manually";
        return;
      }
      await refreshSaves();
      if (selectedSave) status = "Ready. Select a save, then press Load.";
    } catch (e) {
      toastErr(`Autodetect failed: ${e}`);
    }
  }

  async function doChangeDir() {
    const picked = await open({ directory: true, title: "Select save folder (st_… or DefaultUser)" });
    if (typeof picked === "string" && picked) {
      let dir = picked;
      // parent NMS folder picked? drill into first child that has saves
      const direct = await api.listSaveFiles(dir).catch(() => []);
      if (!direct.length) {
        const kids = await api.listSaveSubdirs(dir).catch(() => []);
        for (const kid of kids) {
          const kf = await api.listSaveFiles(kid).catch(() => []);
          if (kf.length) {
            dir = kid;
            toastOk(`Using saves found in ${kid.split("/").slice(-1)}`);
            break;
          }
        }
      }
      saveDir = dir;
      saveDirManual = true;
      try {
        await saveSaveDirOverride(dir);
      } catch (e) {
        toastErr(`Could not remember location: ${e}`);
      }
      selectedSave = null;
      bases = [];
      selectedBase = null;
      counts = null;
      await refreshSaves();
      if (!saveFiles.length) toastErr("No save*.hg files in that folder — try the st_… folder itself");
    }
  }

  async function resetSaveDir() {
    try {
      await clearSaveDirOverride();
    } catch {}
    saveDir = null;
    saveDirManual = false;
    selectedSave = null;
    bases = [];
    selectedBase = null;
    counts = null;
    await detectDir();
  }

  async function doLoad() {
    if (!saveDir || !selectedSave) {
      toastErr("No save selected");
      return;
    }
    loading = true;
    status = `Decompressing ${selectedSave}… (lz4 + mapping)`;
    try {
      const res = await api.decompressSave(saveDir, selectedSave);
      bases = res.bases;
      counts = res.counts;
      toastOk(`Loaded ${selectedSave}: ${bases.length} bases · backup ${res.backup_path.split("/").pop()}`);
    } catch (e) {
      toastErr(`Load failed: ${e}`);
    } finally {
      loading = false;
    }
  }

  function safeFileStem(name: string, ext: string): string {
    const stem = name.replace(/[^\w\- ]+/g, "").trim().replace(/ /g, "_") || "base";
    return `${stem}.${ext}`;
  }

  function openExportDialog() {
    if (selectedBaseObj()) {
      exportFormat = "json";
      exportOpen = true;
    } else {
      toastErr("Select a base first");
    }
  }

  async function doExportConfirm() {
    const b = selectedBaseObj();
    if (!b) return toastErr("Select a base first");
    exportOpen = false;
    if (exportFormat === "nmsbase") {
      await doExportNmsbase(b);
    } else {
      await doExportJson(b);
    }
  }

  async function doExportJson(b: BaseSummary) {
    try {
      const dest = await save({
        title: `Export '${b.display_name}' as JSON`,
        defaultPath: safeFileStem(b.display_name, "json"),
        filters: [
          { name: "JSON", extensions: ["json"] },
          { name: "All", extensions: ["*"] },
        ],
      });
      if (!dest) return;
      const res = await api.exportBase(b.idx, dest);
      const ok = await copyText(res.content);
      toastOk(
        `Exported '${b.display_name}' → ${res.path} · ${ok ? "copied — paste in Base Builder: Import base from NMS" : "clipboard copy failed"}`,
      );
    } catch (e) {
      toastErr(`Export failed: ${e}`);
    }
  }

  async function doExportNmsbase(b?: BaseSummary) {
    b ??= selectedBaseObj() ?? undefined;
    if (!b) return toastErr("Select a base first");
    try {
      const dest = await save({
        title: `Export '${b.display_name}' as NMSBASE`,
        defaultPath: safeFileStem(b.display_name, "nmsbase"),
        filters: [{ name: "NMSBASE", extensions: ["nmsbase", "json", "txt"] }],
      });
      if (!dest) return;
      const res = await api.exportNmsbase(b.idx, dest);
      const ok = await copyText(res.content);
      toastOk(`NMSBASE '${b.display_name}' → ${res.path} · ${ok ? "copied — paste after ^BASE_FLAG" : "file only"}`);
    } catch (e) {
      toastErr(`NMSBASE export failed: ${e}`);
    }
  }

  async function doView() {
    const b = selectedBaseObj();
    if (!b) return toastErr("Select a base first");
    try {
      const text = await api.getBaseJson(b.idx);
      viewing = { title: `${b.display_name} — slot ${b.idx}`, text };
    } catch (e) {
      toastErr(`View failed: ${e}`);
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
        importText = await api.readTextFile(picked);
      } catch (e) {
        toastErr(`Read file failed: ${e}`);
      }
    }
  }

  async function doImport() {
    const b = selectedBaseObj();
    if (!b) return toastErr("Select target base to replace first");
    if (!importText.trim()) return toastErr("Paste JSON or pick a file first");
    importingBusy = true;
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
      toastOk(
        `Injected ${res.objects} objects into '${b.display_name}' · original backed up — now Recompress to write .hg`,
      );
    } catch (e) {
      toastErr(`Inject failed: ${e}`);
    } finally {
      importingBusy = false;
    }
  }

  async function doRecompress() {
    if (!recompressMode || !selectedSave) return;
    const mode = recompressMode;
    recompressMode = null;
    try {
      status = "Recompressing…";
      const out = await api.recompressSave(mode);
      toastOk(`Recompressed → ${out}`);
    } catch (e) {
      toastErr(`Recompress failed: ${e}`);
    }
  }

  async function doBackup() {
    if (!saveDir) return toastErr("No save dir");
    try {
      const paths = await api.backupSaves(saveDir);
      toastOk(`Backed up ${paths.length} save file(s)`);
    } catch (e) {
      toastErr(`Backup failed: ${e}`);
    }
  }

  async function openRestore() {
    const stem = selectedSave?.replace(/\.hg$/, "") ?? null;
    try {
      backups = await api.listBackups(stem);
    } catch {
      backups = await api.listBackups(null);
    }
    if (!backups.length) return toastErr("No backups found");
    selectedBackup = backups[0].path;
    restoring = true;
  }

  async function doRestore() {
    if (!selectedBackup || !saveDir || !selectedSave) return;
    try {
      await api.restoreSave(selectedBackup, saveDir, selectedSave);
      restoring = false;
      bases = [];
      selectedBase = null;
      counts = null;
      await refreshSaves();
      toastOk(`Restored '${selectedSave}' — press Load to inspect`);
    } catch (e) {
      toastErr(`Restore failed: ${e}`);
    }
  }

  async function onThemeChange(v: string) {
    theme = v ?? "default";
    applyUiSettings(theme, font);
    await saveUiSettings({ theme, font });
  }
  async function onFontChange(v: string) {
    font = v ?? "inter";
    applyUiSettings(theme, font);
    await saveUiSettings({ theme, font });
  }

  function onKey(e: KeyboardEvent) {
    const t = e.target as HTMLElement;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
    if (viewing || importing || restoring || recompressMode || settingsOpen || exportOpen) return;
    if (e.key === "e" || e.key === "E") openExportDialog();
    else if (e.key === "v") doView();
    else if (e.key === "i") importing = true;
    else if (e.key === "r") recompressMode = "output";
    else if (e.key === "c") filter = "Corvettes";
    else if (e.key === "p") filter = "Planetary";
    else if (e.key === "b") filter = "Both";
  }

  onMount(() => {
    (async () => {
      try {
        const s = await loadUiSettings();
        theme = s.theme;
        font = s.font;
      } catch {}
    })();
    detectDir();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
</script>

<div class="flex h-screen min-w-0 flex-1 flex-col bg-background text-foreground">
  <!-- header -->
  <header class="flex h-13 shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2">
    <div class="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-xs font-black text-primary-foreground">
      BT
    </div>
    <div class="leading-tight">
      <div class="text-sm font-semibold tracking-tight">NMSBT</div>
      <div class="text-[11px] text-muted-foreground">NMS Base Tool</div>
    </div>
    <Separator orientation="vertical" class="mx-1 h-6" />
    <button
      class="flex min-w-0 items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
      onclick={doChangeDir}
      title={saveDir ? `${saveDir}${saveDirManual ? " (manual — click to change)" : " (auto-detected — click to override)"}` : "No save dir — click to choose"}
    >
      <FolderOpen class="size-3.5 shrink-0" />
      <span class="max-w-110 truncate font-mono">
        {saveDir ? saveDir.split("/").slice(-2).join("/") : "No save dir"}
      </span>
      {#if saveDirManual}
        <Badge variant="default" class="h-4 px-1 text-[10px]">manual</Badge>
      {/if}
    </button>
    {#if saveDirManual}
      <Button
        variant="ghost"
        size="icon-sm"
        onclick={resetSaveDir}
        title="Forget manual folder, go back to auto-detect"
      >
        <X class="size-3.5" />
      </Button>
    {/if}
    <div class="ml-auto flex items-center gap-2">
      {#if counts}
        <div class="hidden items-center gap-1.5 md:flex">
          <Badge variant="default">{counts.ship} ship</Badge>
          <Badge variant="secondary" class="border-emerald-500/40 text-emerald-400">{counts.planet} planet</Badge>
          <Badge variant="outline" class="border-amber-500/40 text-amber-400">{counts.freighter} fr</Badge>
          <Badge variant="outline">{counts.total_objs.toLocaleString()} objs</Badge>
        </div>
      {/if}
      <Button variant="ghost" size="icon-sm" onclick={() => (settingsOpen = true)} title="Appearance">
        <Settings class="size-4" />
      </Button>
    </div>
  </header>

  <div class="flex min-h-0 flex-1">
    <!-- sidebar -->
    <aside class="flex w-70 shrink-0 flex-col gap-3 overflow-y-auto border-r border-border bg-card p-3">
      <section>
        <div class="mb-1.5 flex items-center justify-between">
          <h2 class="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">Saves</h2>
          <span class="text-[11px] text-muted-foreground">{saveFiles.length}</span>
        </div>
        {#if saveFiles.length === 0}
          <div class="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
            No save files found.<br />Check the save folder above.
          </div>
        {:else}
          <div class="flex flex-col gap-1">
            {#each saveFiles as f}
              <button
                class="rounded-lg border px-2.5 py-1.5 text-left transition {f.name === selectedSave
                  ? 'border-primary bg-primary/10'
                  : 'border-border bg-background hover:bg-muted'}"
                onclick={() => (selectedSave = f.name)}
                ondblclick={doLoad}
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="truncate text-[13px] font-medium">{f.name}</span>
                  <span class="shrink-0 font-mono text-[11px] text-muted-foreground">{f.size_display}</span>
                </div>
                <div class="font-mono text-[11px] text-muted-foreground">{f.modified}</div>
              </button>
            {/each}
          </div>
        {/if}
        <div class="mt-2 flex gap-2">
          <Button class="flex-1" size="sm" onclick={doLoad} disabled={loading || !selectedSave}>
            {#if loading}<LoaderCircle class="size-3.5 animate-spin" />Loading…{:else}<Download class="size-3.5" />Load{/if}
          </Button>
          <Button variant="outline" size="sm" onclick={doChangeDir} title="Change save directory">
            <FolderOpen class="size-3.5" />
          </Button>
        </div>
      </section>

      <Separator />

      <section>
        <h2 class="mb-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">Filter</h2>
        <div class="grid grid-cols-3 gap-1 rounded-lg border border-border bg-background p-1">
          {#each [["Corvettes", "c"], ["Planetary", "p"], ["Both", "b"]] as [label, key]}
            <button
              class="rounded-md px-1 py-1 text-xs font-medium transition {filter === label
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground'}"
              onclick={() => (filter = label as typeof filter)}
              title="Shortcut [{key}]"
            >
              {label}
            </button>
          {/each}
        </div>
        {#if counts}
          <p class="mt-1.5 text-[11px] text-muted-foreground">
            Showing {shown.length}/{bases.length} · Ship {counts.ship} · Planet {counts.planet} ·
            Freighter {counts.freighter} · Space {counts.space}
          </p>
        {/if}
      </section>

      <Separator />

      <section>
        <h2 class="mb-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">Save safety</h2>
        <div class="flex gap-2">
          <Button variant="outline" size="sm" class="flex-1" onclick={doBackup}>
            <Save class="size-3.5" />Backup
          </Button>
          <Button variant="outline" size="sm" class="flex-1" onclick={openRestore}>
            <HardDriveDownload class="size-3.5" />Restore…
          </Button>
        </div>
        <p class="mt-1.5 text-[11px] leading-snug text-muted-foreground">
          Close NMS before overwriting a live save. Steam Cloud can revert edits — disable it briefly.
        </p>
      </section>
    </aside>

    <!-- main -->
    <main class="flex min-w-0 flex-1 flex-col">
      <div class="flex shrink-0 items-center gap-2 border-b border-border px-3 py-2">
        <div class="relative max-w-xs flex-1">
          <Search class="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input bind:value={search} placeholder="Search bases…" class="h-7 pl-7 text-xs" />
        </div>
        <Select.Root type="single" value={sortMode} onValueChange={(v) => (sortMode = v ?? "name")}>
          <Select.Trigger class="h-7 w-36 text-xs">
            <Select.Value placeholder="Sort" />
          </Select.Trigger>
          <Select.Content>
            <Select.Item value="name">Name A–Z</Select.Item>
            <Select.Item value="objects">Most objects</Select.Item>
            <Select.Item value="type">Type</Select.Item>
          </Select.Content>
        </Select.Root>
        <span class="ml-auto hidden text-xs text-muted-foreground sm:inline">{shown.length} shown</span>
      </div>

      <div class="min-h-0 flex-1 overflow-auto">
        {#if bases.length === 0}
          <Empty.Root class="mx-auto mt-16 max-w-sm border-0">
            <Empty.Header>
              <Empty.Media variant="icon">
                <Database />
              </Empty.Media>
              <Empty.Title>{loading ? "Decompressing save…" : "No save loaded"}</Empty.Title>
              <Empty.Description>
                {#if loading}
                  Reading LZ4 blocks and deobfuscating keys — this takes a few seconds.
                {:else if !saveDir}
                  No Proton save directory found. Point the app at your <span class="font-mono">st_…</span> folder.
                {:else}
                  Pick a save on the left and press Load to list its bases.
                {/if}
              </Empty.Description>
            </Empty.Header>
            {#if !loading && !saveDir}
              <Empty.Content>
                <Button size="sm" onclick={doChangeDir}>
                  <FolderOpen class="size-3.5" />Choose save folder…
                </Button>
              </Empty.Content>
            {:else if !loading && saveDir}
              <Empty.Content>
                <div class="flex justify-center gap-2">
                  <Button size="sm" onclick={doLoad} disabled={!selectedSave}>
                    <Download class="size-3.5" />Load {selectedSave ?? "save"}
                  </Button>
                  <Button size="sm" variant="outline" onclick={doChangeDir}>
                    <FolderOpen class="size-3.5" />Choose folder…
                  </Button>
                </div>
              </Empty.Content>
            {/if}
          </Empty.Root>
        {:else if shown.length === 0}
          <Empty.Root class="mx-auto mt-16 max-w-sm border-0">
            <Empty.Header>
              <Empty.Media variant="icon">
                <Search />
              </Empty.Media>
              <Empty.Title>No matches</Empty.Title>
              <Empty.Description>
                Nothing matches "{search}" in this filter. Try clearing the search or switching to Both.
              </Empty.Description>
            </Empty.Header>
            <Empty.Content>
              <Button
                size="sm"
                variant="outline"
                onclick={() => {
                  search = "";
                  filter = "Both";
                }}
              >
                Clear search & filter
              </Button>
            </Empty.Content>
          </Empty.Root>
        {:else}
          <Table.Root>
            <Table.Header>
              <Table.Row>
                <Table.Head class="w-10">Idx</Table.Head>
                <Table.Head>Name</Table.Head>
                <Table.Head class="w-28">Type</Table.Head>
                <Table.Head class="w-20 text-right">Objects</Table.Head>
                <Table.Head class="w-28">Owner</Table.Head>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {#each shown as b}
                <Table.Row
                  class="cursor-pointer {b.idx === selectedBase ? 'bg-primary/10 hover:bg-primary/15' : ''}"
                  onclick={() => (selectedBase = b.idx)}
                  ondblclick={openExportDialog}
                >
                  <Table.Cell class="font-mono text-muted-foreground">{b.idx}</Table.Cell>
                  <Table.Cell>
                    <div class="truncate font-medium" title={b.display_name}>{b.display_name}</div>
                    {#if b.name && b.name !== b.display_name}
                      <div class="truncate font-mono text-[11px] text-muted-foreground" title={b.name}>
                        {b.name}
                      </div>
                    {/if}
                  </Table.Cell>
                  <Table.Cell>
                    <Badge variant={typeBadgeVariant(b.base_type)} class={typeBadgeClass(b.base_type)}>
                      {shortType(b.base_type)}
                    </Badge>
                  </Table.Cell>
                  <Table.Cell class="text-right font-mono">{b.objects.toLocaleString()}</Table.Cell>
                  <Table.Cell class="font-mono text-xs text-muted-foreground">
                    {b.owner_uid ? b.owner_uid.slice(0, 10) : "—"}
                  </Table.Cell>
                </Table.Row>
              {/each}
            </Table.Body>
          </Table.Root>
        {/if}
      </div>

      <!-- action bar -->
      <div class="flex shrink-0 flex-wrap items-center gap-2 border-t border-border bg-card px-3 py-2">
        <Button size="sm" onclick={openExportDialog} disabled={selectedBase === null} title="Shortcut [e]">
          <Upload class="size-3.5" />Export…
        </Button>
        <Button size="sm" variant="outline" onclick={doView} disabled={selectedBase === null} title="Shortcut [v]">
          <Eye class="size-3.5" />View
        </Button>
        <Button size="sm" variant="outline" onclick={() => (importing = true)} disabled={selectedBase === null} title="Shortcut [i]">
          <Download class="size-3.5" />Import…
        </Button>
        <div class="ml-auto flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onclick={() => (recompressMode = "output")}
            disabled={selectedBase === null}
            title="Shortcut [r]"
          >
            Recompress
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onclick={() => (recompressMode = "overwrite")}
            disabled={selectedBase === null}
          >
            Overwrite LIVE
          </Button>
        </div>
      </div>
      <div class="shrink-0 truncate border-t border-border px-3 py-1 font-mono text-[11px] text-muted-foreground">
        {status}
      </div>
    </main>
  </div>

  <!-- toasts -->
  <div class="pointer-events-none fixed right-3 bottom-8 z-50 flex w-100 max-w-[calc(100vw-1.5rem)] flex-col gap-2">
    {#each toasts as t}
      <div
        class="pointer-events-auto flex items-start gap-2 rounded-lg border bg-card p-2.5 text-xs shadow-lg {t.kind === 'success'
          ? 'border-emerald-500/40'
          : t.kind === 'error'
            ? 'border-destructive/50'
            : 'border-border'}"
      >
        {#if t.kind === "success"}<CircleCheck class="mt-0.5 size-4 shrink-0 text-emerald-400" />
        {:else if t.kind === "error"}<CircleAlert class="mt-0.5 size-4 shrink-0 text-destructive" />
        {:else}<Info class="mt-0.5 size-4 shrink-0 text-muted-foreground" />{/if}
        <span class="break-words">{t.msg}</span>
      </div>
    {/each}
  </div>

  <!-- export format dialog -->
  <Dialog.Root bind:open={exportOpen}>
    <Dialog.Content class="max-w-md">
      <Dialog.Header>
        <Dialog.Title>Export '{selectedBaseObj()?.display_name ?? ""}'</Dialog.Title>
        <Dialog.Description>Choose a format — you'll pick where to save it next.</Dialog.Description>
      </Dialog.Header>
      <div class="flex flex-col gap-2 py-1">
        <button
          class="rounded-lg border p-3 text-left transition {exportFormat === 'json'
            ? 'border-primary bg-primary/10'
            : 'border-border hover:bg-muted'}"
          onclick={() => (exportFormat = "json")}
        >
          <div class="flex items-center gap-2 text-sm font-medium">
            <FileJson class="size-4 text-primary" />Full JSON <Badge variant="default">.json</Badge>
          </div>
          <p class="mt-1 text-xs text-muted-foreground">
            Complete base data. Paste into Base Builder via <span class="font-medium">Import base from NMS</span>.
          </p>
        </button>
        <button
          class="rounded-lg border p-3 text-left transition {exportFormat === 'nmsbase'
            ? 'border-primary bg-primary/10'
            : 'border-border hover:bg-muted'}"
          onclick={() => (exportFormat = "nmsbase")}
        >
          <div class="flex items-center gap-2 text-sm font-medium">
            <FileJson class="size-4 text-amber-400" />NMSBASE <Badge variant="outline">.nmsbase</Badge>
          </div>
          <p class="mt-1 text-xs text-muted-foreground">
            Objects only. Paste into NomNom / NMSSE after the <span class="font-mono">^BASE_FLAG</span> entry.
          </p>
        </button>
      </div>
      <Dialog.Footer>
        <Button variant="outline" onclick={() => (exportOpen = false)}>Cancel</Button>
        <Button onclick={doExportConfirm}>
          <Upload class="size-3.5" />Save…
        </Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>

  <!-- view dialog -->
  <Dialog.Root open={viewing !== null} onOpenChange={(o) => !o && (viewing = null)}>
    <Dialog.Content class="max-h-[85vh] max-w-3xl overflow-hidden">
      <Dialog.Header>
        <Dialog.Title>{viewing?.title ?? ""}</Dialog.Title>
        <Dialog.Description>Full base JSON as stored in the save.</Dialog.Description>
      </Dialog.Header>
      <pre class="max-h-[55vh] overflow-auto rounded-md border border-border bg-background p-3 font-mono text-[11px] break-all whitespace-pre-wrap">{viewing?.text ?? ""}</pre>
      <Dialog.Footer>
        <Button
          variant="outline"
          onclick={() => (viewing = null)}
        >
          Close
        </Button>
        <Button
          onclick={async () => {
            if (await copyText(viewing?.text ?? "")) toastOk("Base JSON copied to clipboard");
            viewing = null;
          }}
        >
          <Copy class="size-3.5" />Copy & close
        </Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>

  <!-- import dialog -->
  <Dialog.Root bind:open={importing}>
    <Dialog.Content class="max-h-[85vh] max-w-2xl overflow-hidden">
      <Dialog.Header>
        <Dialog.Title>Import into '{selectedBaseObj()?.display_name ?? ""}' (slot {selectedBase})</Dialog.Title>
        <Dialog.Description>
          Replaces the base's objects. The original is backed up automatically. Full base JSON,
          objects-only arrays, and .nmsbase leading-comma text are all accepted.
        </Dialog.Description>
      </Dialog.Header>
      <Textarea
        bind:value={importText}
        rows={14}
        class="font-mono text-xs"
        placeholder="Paste base JSON here, or pick a file…"
      />
      <Dialog.Footer class="sm:justify-between">
        <Button variant="ghost" onclick={doPickImportFile}>Pick file…</Button>
        <div class="flex gap-2">
          <Button variant="outline" onclick={() => (importing = false)}>Cancel</Button>
          <Button onclick={doImport} disabled={!importText.trim() || importingBusy}>
            {#if importingBusy}<LoaderCircle class="size-3.5 animate-spin" />Injecting…{:else}Inject{/if}
          </Button>
        </div>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>

  <!-- restore dialog -->
  <Dialog.Root bind:open={restoring}>
    <Dialog.Content class="max-h-[85vh] max-w-2xl overflow-hidden">
      <Dialog.Header>
        <Dialog.Title>Restore '{selectedSave}'</Dialog.Title>
        <Dialog.Description>
          The current live file is backed up again before restoring. Close NMS first!
        </Dialog.Description>
      </Dialog.Header>
      <div class="max-h-[50vh] overflow-auto rounded-md border border-border">
        <Table.Root>
          <Table.Header>
            <Table.Row>
              <Table.Head>Backup file</Table.Head>
              <Table.Head class="w-20">Size</Table.Head>
              <Table.Head class="w-36">Modified</Table.Head>
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {#each backups as bk}
              <Table.Row
                class="cursor-pointer {bk.path === selectedBackup ? 'bg-primary/10 hover:bg-primary/15' : ''}"
                onclick={() => (selectedBackup = bk.path)}
              >
                <Table.Cell class="font-mono text-xs">{bk.name}</Table.Cell>
                <Table.Cell>{bk.size_display}</Table.Cell>
                <Table.Cell class="font-mono text-xs">{bk.modified}</Table.Cell>
              </Table.Row>
            {/each}
          </Table.Body>
        </Table.Root>
      </div>
      <Dialog.Footer>
        <Button variant="outline" onclick={() => (restoring = false)}>Cancel</Button>
        <Button variant="destructive" onclick={doRestore}>Restore selected</Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>

  <!-- recompress confirm -->
  <Dialog.Root open={recompressMode !== null} onOpenChange={(o) => !o && (recompressMode = null)}>
    <Dialog.Content class="max-w-md">
      <Dialog.Header>
        <Dialog.Title>
          {recompressMode === "overwrite" ? "Overwrite live save?" : "Write recompressed save?"}
        </Dialog.Title>
        <Dialog.Description>
          {#if recompressMode === "overwrite"}
            Writes directly over <span class="font-mono">{selectedSave}</span>. A
            <span class="font-mono">*_before_recompress_*.hg</span> backup is made first. Make sure NMS is closed —
            Steam Cloud can revert the change.
          {:else}
            Writes a recompressed copy of <span class="font-mono">{selectedSave}</span> to the output folder,
            leaving the live save untouched.
          {/if}
        </Dialog.Description>
      </Dialog.Header>
      <Dialog.Footer>
        <Button variant="outline" onclick={() => (recompressMode = null)}>Cancel</Button>
        <Button variant={recompressMode === "overwrite" ? "destructive" : "default"} onclick={doRecompress}>
          {recompressMode === "overwrite" ? "Overwrite LIVE" : "Write to output/"}
        </Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>

  <!-- settings dialog -->
  <Dialog.Root bind:open={settingsOpen}>
    <Dialog.Content class="max-w-sm">
      <Dialog.Header>
        <Dialog.Title>Settings</Dialog.Title>
        <Dialog.Description>Save location, theme, and font.</Dialog.Description>
      </Dialog.Header>
      <div>
        <div class="mb-1 text-xs font-medium">Save location {saveDirManual ? "(manual)" : "(auto-detected)"}</div>
        <div class="rounded-md border border-border bg-background px-2 py-1.5 font-mono text-[11px] break-all">
          {saveDir ?? "Not detected yet"}
        </div>
        <div class="mt-1.5 flex gap-2">
          <Button size="sm" variant="outline" class="flex-1" onclick={doChangeDir}>
            <FolderOpen class="size-3.5" />Choose…
          </Button>
          {#if saveDirManual}
            <Button
              size="sm"
              variant="ghost"
              class="flex-1"
              onclick={() => {
                resetSaveDir();
              }}
            >
              Reset to auto
            </Button>
          {/if}
        </div>
      </div>
      <Separator />
      <div class="flex flex-col gap-3 py-1">
        <div>
          <div class="mb-1 text-xs font-medium">Theme</div>
          <Select.Root type="single" value={theme} onValueChange={onThemeChange}>
            <Select.Trigger class="w-full">
              <Select.Value placeholder="Theme" />
            </Select.Trigger>
            <Select.Content>
              {#each THEMES as t}
                <Select.Item value={t.id}>{t.label}</Select.Item>
              {/each}
            </Select.Content>
          </Select.Root>
        </div>
        <div>
          <div class="mb-1 text-xs font-medium">Font</div>
          <Select.Root type="single" value={font} onValueChange={onFontChange}>
            <Select.Trigger class="w-full">
              <Select.Value placeholder="Font" />
            </Select.Trigger>
            <Select.Content>
              {#each FONTS as f}
                <Select.Item value={f.id}>{f.label}</Select.Item>
              {/each}
            </Select.Content>
          </Select.Root>
        </div>
      </div>
      <Dialog.Footer>
        <Button onclick={() => (settingsOpen = false)}>Done</Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>
</div>
