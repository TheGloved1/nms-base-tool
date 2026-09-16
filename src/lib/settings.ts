import { LazyStore } from "@tauri-apps/plugin-store";

const store = new LazyStore("settings.json");

export const THEMES = [
  { id: "default", label: "NMS Default" },
  { id: "rose-pine", label: "Rosé Pine" },
  { id: "rose-pine-moon", label: "Rosé Pine Moon" },
  { id: "rose-pine-dawn", label: "Rosé Pine Dawn" },
  { id: "catppuccin-mocha", label: "Catppuccin Mocha" },
  { id: "catppuccin-macchiato", label: "Catppuccin Macchiato" },
  { id: "catppuccin-frappe", label: "Catppuccin Frappé" },
  { id: "catppuccin-latte", label: "Catppuccin Latte" },
];

export const FONTS = [
  { id: "inter", label: "Inter" },
  { id: "jetbrains", label: "JetBrains Mono" },
  { id: "geist", label: "Geist" },
  { id: "space", label: "Space Grotesk" },
  { id: "manrope", label: "Manrope" },
  { id: "sora", label: "Sora" },
];

export interface UiSettings {
  theme: string;
  font: string;
}

const DEFAULTS: UiSettings = { theme: "default", font: "inter" };

export function applyUiSettings(theme: string, font: string) {
  const t = THEMES.some((x) => x.id === theme) ? theme : "default";
  const f = FONTS.some((x) => x.id === font) ? font : "inter";
  document.documentElement.setAttribute("data-theme", t);
  document.documentElement.setAttribute("data-font", f);
}

export async function loadUiSettings(): Promise<UiSettings> {
  try {
    const theme = await store.get<string>("nmsbt-theme");
    const font = await store.get<string>("nmsbt-font");
    return {
      theme: theme ?? DEFAULTS.theme,
      font: font ?? DEFAULTS.font,
    };
  } catch {
    return { ...DEFAULTS };
  }
}

export async function saveUiSettings(s: UiSettings): Promise<void> {
  await store.set("nmsbt-theme", s.theme);
  await store.set("nmsbt-font", s.font);
  await store.save();
}
