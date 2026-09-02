import { app } from "electron";
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

export type DesktopSettings = {
  globalHotkey: string;
  inputDeviceId: number | null;
  outputMode: "zh" | "zh-to-en";
};

const DEFAULT_SETTINGS: DesktopSettings = {
  globalHotkey: process.env.LIKETYPELESS_GLOBAL_HOTKEY ?? "Shift+Space",
  inputDeviceId: null,
  outputMode: "zh"
};

function settingsPath(): string {
  return join(app.getPath("userData"), "settings.json");
}

function normalize(candidate: Partial<DesktopSettings>): DesktopSettings {
  return {
    globalHotkey: candidate.globalHotkey?.trim() || DEFAULT_SETTINGS.globalHotkey,
    inputDeviceId: Number.isInteger(candidate.inputDeviceId) ? candidate.inputDeviceId ?? null : null,
    outputMode: candidate.outputMode === "zh-to-en" ? "zh-to-en" : "zh"
  };
}

export async function loadDesktopSettings(): Promise<DesktopSettings> {
  try {
    return normalize(JSON.parse(await readFile(settingsPath(), "utf-8")) as Partial<DesktopSettings>);
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export async function saveDesktopSettings(settings: DesktopSettings): Promise<DesktopSettings> {
  const normalized = normalize(settings);
  await writeFile(settingsPath(), `${JSON.stringify(normalized, null, 2)}\n`, "utf-8");
  return normalized;
}
