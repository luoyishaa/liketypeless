import { contextBridge, ipcRenderer } from "electron";
import type {
  AudioDevice,
  DesktopState,
  HealthResponse,
  ModelStatus,
  RecentResult,
} from "@liketypeless/shared";
import type { DesktopSettings } from "../main/settings-store";

const api = {
  health: (): Promise<HealthResponse> => ipcRenderer.invoke("api:health"),
  audioDevices: (): Promise<AudioDevice[]> =>
    ipcRenderer.invoke("api:audio-devices"),
  state: (): Promise<DesktopState> => ipcRenderer.invoke("desktop:state"),
  hideWindow: (): Promise<void> => ipcRenderer.invoke("desktop:hide"),
  toggleRecording: (): Promise<DesktopState> =>
    ipcRenderer.invoke("desktop:toggle"),
  restart: (): Promise<void> => ipcRenderer.invoke("desktop:restart"),
  settings: (): Promise<DesktopSettings> => ipcRenderer.invoke("settings:get"),
  updateSettings: (settings: DesktopSettings): Promise<DesktopSettings> =>
    ipcRenderer.invoke("settings:update", settings),
  modelStatus: (): Promise<ModelStatus> => ipcRenderer.invoke("models:status"),
  prepareModel: (endpoint: string): Promise<ModelStatus> =>
    ipcRenderer.invoke("models:prepare", endpoint),
  importModel: (): Promise<ModelStatus | null> =>
    ipcRenderer.invoke("models:import"),
  results: (): Promise<RecentResult[]> => ipcRenderer.invoke("results:list"),
  clearResults: (): Promise<void> => ipcRenderer.invoke("results:clear"),
  copyResult: (id: string): Promise<void> =>
    ipcRenderer.invoke("results:copy", id),
  retryResult: (id: string): Promise<void> =>
    ipcRenderer.invoke("results:retry", id),
  onState: (listener: (state: DesktopState) => void): (() => void) => {
    const wrapped = (_event: Electron.IpcRendererEvent, state: DesktopState) =>
      listener(state);
    ipcRenderer.on("state:changed", wrapped);
    return () => ipcRenderer.removeListener("state:changed", wrapped);
  },
};
export type LikeTypelessApi = typeof api;
contextBridge.exposeInMainWorld("liketypeless", api);
