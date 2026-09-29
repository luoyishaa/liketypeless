import { app } from "electron";
import { readFile, writeFile, rename, mkdir } from "node:fs/promises";
import { join } from "node:path";

export type DesktopSettings = {
  globalHotkey: string;
  inputDeviceId: number | null;
  outputMode: "zh";
  cleanupMode: "basic" | "enhanced";
  onboardingComplete: boolean;
};

const DEFAULT_SETTINGS: DesktopSettings = {
  globalHotkey: process.env.LIKETYPELESS_GLOBAL_HOTKEY ?? "Shift+Space",
  inputDeviceId: null,
  outputMode: "zh",
  cleanupMode: "basic",
  onboardingComplete: false,
};

function settingsPath(): string {
  return join(app.getPath("userData"), "settings.json");
}

function normalize(candidate: Partial<DesktopSettings>): DesktopSettings {
  return {
    globalHotkey:
      candidate.globalHotkey?.trim() || DEFAULT_SETTINGS.globalHotkey,
    inputDeviceId: Number.isInteger(candidate.inputDeviceId)
      ? (candidate.inputDeviceId ?? null)
      : null,
    outputMode: "zh",
    cleanupMode: candidate.cleanupMode === "enhanced" ? "enhanced" : "basic",
    onboardingComplete: candidate.onboardingComplete === true,
  };
}

export async function loadDesktopSettings(
  legacyDataPath?: string,
): Promise<DesktopSettings> {
  try {
    return normalize(
      JSON.parse(
        await readFile(settingsPath(), "utf-8"),
      ) as Partial<DesktopSettings>,
    );
  } catch {
    if (legacyDataPath && legacyDataPath !== app.getPath("userData")) {
      try {
        const previous = normalize(
          JSON.parse(
            await readFile(join(legacyDataPath, "settings.json"), "utf-8"),
          ),
        );
        return await saveDesktopSettings(previous);
      } catch {
        /* No legacy settings to migrate. */
      }
    }
    return { ...DEFAULT_SETTINGS };
  }
}

export async function saveDesktopSettings(
  settings: DesktopSettings,
): Promise<DesktopSettings> {
  const normalized = normalize(settings);
  await mkdir(app.getPath("userData"), { recursive: true });
  await writeFile(
    settingsPath() + ".tmp",
    `${JSON.stringify(normalized, null, 2)}\n`,
    "utf-8",
  );
  await rename(settingsPath() + ".tmp", settingsPath());
  return normalized;
}
