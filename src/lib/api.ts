import { invoke } from "@tauri-apps/api/core";
import type {
  BackupInfo,
  BaseSummary,
  DecompressResult,
  ExportResult,
  ImportResult,
  SaveFileInfo,
  TypeCounts,
} from "./types";

export type { BackupInfo, BaseSummary, DecompressResult, ExportResult, ImportResult, SaveFileInfo, TypeCounts };

export const api = {
  findSaveDirs: () => invoke<string[]>("find_save_dirs"),
  findSaveDir: (prefer?: string | null) =>
    invoke<string | null>("find_save_dir", { prefer }),
  listSaveFiles: (saveDir: string) =>
    invoke<SaveFileInfo[]>("list_save_files", { saveDir }),
  listSaveSubdirs: (saveDir: string) =>
    invoke<string[]>("list_save_subdirs", { saveDir }),
  decompressSave: (saveDir: string, saveFile: string) =>
    invoke<DecompressResult>("decompress_save", { saveDir, saveFile }),
  listBases: (filter?: string | null) =>
    invoke<BaseSummary[]>("list_bases", { filter }),
  exportBase: (idx: number) => invoke<ExportResult>("export_base", { idx }),
  exportNmsbase: (idx: number, outPath?: string | null) =>
    invoke<ExportResult>("export_nmsbase", { idx, outPath }),
  importBase: (idx: number, payload: string) =>
    invoke<ImportResult>("import_base", { idx, payload }),
  recompressSave: (mode: string) => invoke<string>("recompress_save", { mode }),
  backupSaves: (saveDir: string) =>
    invoke<string[]>("backup_saves", { saveDir }),
  listBackups: (stem?: string | null) =>
    invoke<BackupInfo[]>("list_backups", { stem }),
  restoreSave: (backupPath: string, saveDir: string, saveFile: string) =>
    invoke<string>("restore_save", { backupPath, saveDir, saveFile }),
  openPath: (path: string) => invoke<void>("open_path", { path }),
  getDownloadsDir: () => invoke<string>("get_downloads_dir"),
};
