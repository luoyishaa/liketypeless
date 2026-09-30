import {
  app,
  BrowserWindow,
  clipboard,
  dialog,
  globalShortcut,
  ipcMain,
  Menu,
  nativeImage,
  Notification,
  screen,
  Tray,
} from "electron";
import { join, resolve } from "node:path";
import type {
  DesktopState,
  HealthResponse,
  ModelStatus,
  RecentResult,
  VoiceFinishResponse,
} from "@liketypeless/shared";
import { deliverToWindow, getForegroundWindowHandle } from "./windows-input";
import { BackendProcess } from "./backend-process";
import { deliverText } from "./input-delivery";
import {
  loadDesktopSettings,
  saveDesktopSettings,
  type DesktopSettings,
} from "./settings-store";

let mainWindow: BrowserWindow | null = null;
let overlay: BrowserWindow | null = null;
let tray: Tray | null = null;
let backend: BackendProcess;
let settings: DesktopSettings;
let quitting = false;
let busy = false;
let recording = false;
let target: string | null = null;
let overlayTimer: ReturnType<typeof setTimeout> | null = null;
let state: DesktopState = { phase: "starting", message: "正在启动本机服务…" };

const legacyDataPath = app.getPath("userData");
app.setName("liketypeless");
app.setPath("userData", join(app.getPath("appData"), "liketypeless"));
if (process.env.LIKETYPELESS_TEST_DATA_DIR) {
  app.setPath("userData", process.env.LIKETYPELESS_TEST_DATA_DIR);
}

function publish(next: DesktopState) {
  state = next;
  mainWindow?.webContents.send("state:changed", state);
  if (overlayTimer) clearTimeout(overlayTimer);
  if (
    [
      "recording",
      "processing",
      "ready-to-copy",
      "paste-requested",
      "error",
    ].includes(next.phase)
  ) {
    if (!overlay || overlay.isDestroyed()) {
      const area = screen.getPrimaryDisplay().workArea;
      overlay = new BrowserWindow({
        width: 350,
        height: 88,
        x: area.x + area.width - 370,
        y: area.y + area.height - 110,
        frame: false,
        transparent: true,
        focusable: false,
        skipTaskbar: true,
        alwaysOnTop: true,
        resizable: false,
        webPreferences: {
          contextIsolation: true,
          nodeIntegration: false,
          sandbox: true,
        },
      });
      overlay.setIgnoreMouseEvents(true);
    }
    const titles: Record<string, string> = {
      recording: "正在聆听",
      processing: "正在识别",
      "ready-to-copy": "文字已保留",
      "paste-requested": "已发送粘贴",
      error: "需要处理",
    };
    const detail =
      next.phase === "recording"
        ? "再次按快捷键结束"
        : next.phase === "processing"
          ? "文字会先保存，再尝试输入"
          : "打开主窗口查看结果或处理提示";
    const html =
      '<!doctype html><meta charset="UTF-8"><style>body{margin:0;padding:17px 22px;background:#193c38;color:white;border-radius:16px;font:15px "Microsoft YaHei UI";box-sizing:border-box}b{display:block;margin-bottom:5px}small{color:#c3d7d1}</style><b>' +
      titles[next.phase] +
      "</b><small>" +
      detail +
      "</small>";
    void overlay.loadURL(
      "data:text/html;charset=utf-8," + encodeURIComponent(html),
    );
    overlay.showInactive();
    if (!["recording", "processing"].includes(next.phase))
      overlayTimer = setTimeout(() => overlay?.hide(), 4000);
  } else overlay?.hide();
}

function showWindow() {
  mainWindow?.show();
  mainWindow?.focus();
}

async function showRecoveryDialog(text: string | null, reason: string) {
  if (!settings.onboardingComplete) {
    showWindow();
    return;
  }
  try {
    const buttons = text
      ? ["复制文字", "打开最近结果", "稍后处理"]
      : ["打开最近结果", "稍后处理"];
    const { response } = await dialog.showMessageBox({
      type: "warning",
      title: text ? "liketypeless · 结果已保留" : "liketypeless · 需要处理",
      message: text ? "文字已保留，可以手动复制" : "语音输入需要处理",
      detail:
        reason +
        (text
          ? "\n\n" + text.slice(0, 240) + (text.length > 240 ? "…" : "")
          : ""),
      buttons,
      defaultId: 0,
      cancelId: buttons.length - 1,
      noLink: true,
    });
    if (text && response === 0) await clipboard.writeText(text);
    else if (response === (text ? 1 : 0)) showWindow();
  } catch {
    publish({
      phase: "error",
      message: "无法打开恢复提示或写入剪贴板，请到最近结果重试。",
    });
    showWindow();
  }
}

function createWindow() {
  const showInitially =
    !settings.onboardingComplete &&
    (!process.env.LIKETYPELESS_TEST_DATA_DIR ||
      process.env.LIKETYPELESS_TEST_SHOW_WINDOW === "1");
  mainWindow = new BrowserWindow({
    width: 1060,
    height: 780,
    minWidth: 840,
    minHeight: 640,
    title: "liketypeless",
    show: showInitially,
    backgroundColor: "#f4f6f2",
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  mainWindow.webContents.on("will-navigate", (event) => event.preventDefault());
  mainWindow.on("close", (event) => {
    if (!quitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });
  if (process.env.ELECTRON_RENDERER_URL)
    void mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL);
  else void mainWindow.loadFile(join(__dirname, "../renderer/index.html"));
}

function trayIcon() {
  const bytes = Buffer.alloc(32 * 32 * 4);
  for (let y = 0; y < 32; y++)
    for (let x = 0; x < 32; x++) {
      const i = (y * 32 + x) * 4;
      const mic =
        (x >= 12 && x <= 19 && y >= 5 && y <= 19) ||
        (y >= 22 && y <= 24 && x >= 8 && x <= 23) ||
        (x >= 15 && x <= 17 && y >= 19 && y <= 28);
      const inside = (x - 15.5) ** 2 + (y - 15.5) ** 2 <= 245;
      bytes[i] = mic ? 245 : 36;
      bytes[i + 1] = mic ? 249 : 94;
      bytes[i + 2] = mic ? 241 : 80;
      bytes[i + 3] = inside ? 255 : 0;
    }
  return nativeImage.createFromBitmap(bytes, { width: 32, height: 32 });
}

function updateTray() {
  if (!tray) {
    tray = new Tray(trayIcon());
    tray.on("double-click", showWindow);
  }
  tray.setToolTip("liketypeless · 中文语音输入");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "设置与最近结果", click: showWindow },
      { label: "录音快捷键：" + settings.globalHotkey, enabled: false },
      { type: "separator" },
      { label: "退出应用", click: () => app.quit() },
    ]),
  );
}

function prepareOptionalCleanup() {
  if (settings.cleanupMode === "enhanced") {
    void backend.request("/llm/prepare", {}).catch(() => {
      // Basic offline cleanup remains usable; diagnostics show the optional state.
    });
  }
}

async function toggleRecording(fromHotkey: boolean) {
  if (busy) return state;
  busy = true;
  try {
    if (!recording) {
      target = fromHotkey ? await getForegroundWindowHandle() : null;
      if (target?.split(":")[1] === String(process.pid)) target = null;
      await backend.request("/audio/recording/start", {
        deviceId: settings.inputDeviceId,
      });
      recording = true;
      publish({
        phase: "recording",
        message: "正在录音，再按一次快捷键结束。",
      });
    } else {
      const started = performance.now();
      publish({ phase: "processing", message: "正在识别并保存结果…" });
      const result = await backend.request<VoiceFinishResponse>(
        "/voice/recording/finish",
        { outputMode: "zh", cleanupMode: settings.cleanupMode },
      );
      const backendElapsedMs = Math.round(performance.now() - started);
      recording = false;
      const text = result.structuredText.trim() || result.transcript.trim();
      if (!text)
        throw new Error("没有识别到文字。请检查麦克风，再说一句完整的话。");
      const deliveryStarted = performance.now();
      const delivery = await deliverText(text, target, {
        deliver: deliverToWindow,
      });
      publish({
        phase: delivery.status,
        message: [delivery.reason, result.degradationReason,
          result.sttFallbackReason?.includes("未准备") ? null : result.sttFallbackReason]
          .filter(Boolean)
          .join(" "),
        elapsedMs: Math.round(performance.now() - started),
        backendElapsedMs,
        deliveryElapsedMs: Math.round(performance.now() - deliveryStarted),
      });
      if (
        delivery.status === "ready-to-copy" &&
        (fromHotkey || !mainWindow?.isVisible())
      )
        void showRecoveryDialog(text, delivery.reason);
    }
  } catch (error) {
    const status = await backend
      .request<{ isRecording: boolean }>("/audio/recording/status")
      .catch(() => null);
    recording = status?.isRecording ?? false;
    publish({
      phase: "error",
      message: error instanceof Error ? error.message : String(error),
    });
    if (Notification.isSupported())
      new Notification({ title: "liketypeless", body: state.message }).show();
    if (fromHotkey || !mainWindow?.isVisible())
      void showRecoveryDialog(null, state.message);
  } finally {
    if (!recording) target = null;
    busy = false;
  }
  return state;
}

function registerIpc() {
  function handle(channel: string, action: (...args: any[]) => unknown) {
    ipcMain.handle(channel, (event, ...args) => {
      if (event.sender !== mainWindow?.webContents)
        throw new Error("无效的桌面会话");
      return action(...args);
    });
  }
  handle("api:health", () => backend.request<HealthResponse>("/health"));
  handle("api:audio-devices", () => backend.request("/audio/devices"));
  handle("desktop:state", () => state);
  handle("desktop:hide", () => mainWindow?.hide());
  handle("desktop:toggle", () => toggleRecording(false));
  handle("desktop:restart", async () => {
    if (busy || recording) throw new Error("请先结束录音和处理。");
    busy = true;
    try {
      await backend.restart();
      prepareOptionalCleanup();
      publish({ phase: "ready", message: "本机服务已就绪。" });
    } finally {
      busy = false;
    }
  });
  handle("settings:get", () => settings);
  handle("settings:update", async (next: DesktopSettings) => {
    if (busy || recording) throw new Error("请先结束录音，再修改设置。");
    const hotkey =
      typeof next.globalHotkey === "string" ? next.globalHotkey.trim() : "";
    if (!hotkey || hotkey.length > 100) throw new Error("请输入有效快捷键。");
    const previous = settings.globalHotkey;
    if (
      hotkey !== previous &&
      !globalShortcut.register(hotkey, () => void toggleRecording(true))
    )
      throw new Error("快捷键被占用或无效，请换一组组合键。");
    try {
      settings = await saveDesktopSettings({ ...next, globalHotkey: hotkey });
      if (previous !== hotkey) globalShortcut.unregister(previous);
    } catch (error) {
      if (previous !== hotkey) globalShortcut.unregister(hotkey);
      throw error;
    }
    updateTray();
    prepareOptionalCleanup();
    return settings;
  });
  handle("models:status", () => backend.request<ModelStatus>("/models/status"));
  handle("models:prepare", (endpoint: string) =>
    backend.request("/models/prepare", { endpoint }),
  );
  handle("models:import", async () => {
    const selection = await dialog.showOpenDialog(mainWindow!, {
      title: "选择 faster-whisper-small 模型文件夹",
      properties: ["openDirectory"],
    });
    if (selection.canceled) return null;
    return backend.request("/models/prepare", {
      sourcePath: selection.filePaths[0],
    });
  });
  handle("models:short:status", () => backend.request<ModelStatus>("/models/short/status"));
  handle("models:short:prepare", () => backend.request("/models/short/prepare", {}));
  handle("models:short:import", async () => {
    const selection = await dialog.showOpenDialog(mainWindow!, {
      title: "选择已下载的 SenseVoice GGUF 模型和便携运行程序所在文件夹",
      properties: ["openDirectory"],
    });
    if (selection.canceled) return null;
    return backend.request("/models/short/prepare", { sourcePath: selection.filePaths[0] });
  });
  handle("results:list", () => backend.request<RecentResult[]>("/results"));
  handle("results:clear", () => backend.request("/results/clear", {}));
  handle("results:copy", async (id: string) => {
    const result = (await backend.request<RecentResult[]>("/results")).find(
      (item) => item.id === id,
    );
    if (!result || !(result.text || result.transcript))
      throw new Error("这条记录没有可复制的文字。");
    await clipboard.writeText(result.text || result.transcript);
  });
  handle("results:retry", async (id: string) => {
    if (busy || recording || !/^[a-f0-9]{32}$/.test(id))
      throw new Error("当前无法重试，请先结束录音。");
    busy = true;
    try {
      publish({ phase: "processing", message: "正在重试识别…" });
      await backend.request("/results/" + id + "/retry", {
        outputMode: "zh",
        cleanupMode: settings.cleanupMode,
      });
      publish({
        phase: "ready-to-copy",
        message: "重试完成，文字已保留，请手动复制。",
      });
    } catch (error) {
      publish({
        phase: "error",
        message: error instanceof Error ? error.message : String(error),
      });
      throw error;
    } finally {
      busy = false;
    }
  });
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on("second-instance", showWindow);
  app.whenReady().then(async () => {
    settings = await loadDesktopSettings(
      process.env.LIKETYPELESS_TEST_DATA_DIR ? undefined : legacyDataPath,
    );
    const root = resolve(__dirname, "../../../..");
    backend = app.isPackaged
      ? new BackendProcess(
          join(process.resourcesPath, "backend", "liketypeless-api.exe"),
          [],
          app.getPath("userData"),
        )
      : new BackendProcess(
          join(root, ".venv-release", "Scripts", "python.exe"),
          [join(root, "apps", "local-api", "scripts", "serve_product.py")],
          app.getPath("userData"),
        );
    registerIpc();
    createWindow();
    updateTray();
    const registered = globalShortcut.register(
      settings.globalHotkey,
      () => void toggleRecording(true),
    );
    try {
      await backend.start();
      prepareOptionalCleanup();
      publish(
        registered
          ? {
              phase: "ready",
              message: settings.onboardingComplete
                ? "本机服务已就绪，按快捷键开始录音。"
                : "本机服务已就绪，请完成模型与麦克风准备。",
            }
          : { phase: "error", message: "录音快捷键注册失败，请到设置中更换。" },
      );
      if (!registered) void showRecoveryDialog(null, state.message);
    } catch (error) {
      publish({
        phase: "error",
        message: error instanceof Error ? error.message : String(error),
      });
      void showRecoveryDialog(null, state.message);
    }
    app.on("activate", showWindow);
  });
}
app.on("before-quit", (event) => {
  if (quitting) return;
  event.preventDefault();
  quitting = true;
  globalShortcut.unregisterAll();
  overlay?.destroy();
  tray?.destroy();
  void (backend?.stop() ?? Promise.resolve()).finally(() => app.quit());
});
app.on("window-all-closed", () => {
  /* Closing the main window intentionally leaves the tray running. */
});
