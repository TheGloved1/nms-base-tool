export interface SaveFileInfo {
  name: string;
  size_bytes: number;
  size_display: string;
  modified: string;
  mtime_ms: number;
}

export interface BaseSummary {
  idx: number;
  name: string;
  display_name: string;
  base_type: string;
  objects: number;
  owner_uid: string;
}

export interface TypeCounts {
  ship: number;
  planet: number;
  freighter: number;
  space: number;
  total_objs: number;
}

export interface DecompressResult {
  bases: BaseSummary[];
  counts: TypeCounts;
  backup_path: string;
}

export interface ExportResult {
  path: string;
  clipboard_hint: string;
}

export interface ImportResult {
  idx: number;
  objects: number;
  backup_path: string;
}

export interface BackupInfo {
  name: string;
  size_display: string;
  modified: string;
  path: string;
}
