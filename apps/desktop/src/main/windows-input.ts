import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const USER32_TYPE = `
using System;
using System.Runtime.InteropServices;

public static class LikeTypelessUser32
{
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hWnd);
    [DllImport("user32.dll", EntryPoint="GetWindowThreadProcessId")]
    public static extern uint WindowProcess(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool BringWindowToTop(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, IntPtr processId);

    [DllImport("user32.dll")]
    public static extern bool AttachThreadInput(uint attachThreadId, uint attachToThreadId, bool attach);

    [DllImport("kernel32.dll")]
    public static extern uint GetCurrentThreadId();

    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);

    [DllImport("user32.dll")] static extern bool OpenClipboard(IntPtr owner);
    [DllImport("user32.dll")] static extern bool CloseClipboard();
    [DllImport("user32.dll")] static extern bool EmptyClipboard();
    [DllImport("user32.dll")] static extern uint EnumClipboardFormats(uint format);
    [DllImport("user32.dll")] static extern IntPtr GetClipboardData(uint format);
    [DllImport("user32.dll")] static extern IntPtr SetClipboardData(uint format, IntPtr data);
    [DllImport("user32.dll")] public static extern uint GetClipboardSequenceNumber();
    [DllImport("kernel32.dll")] static extern IntPtr GlobalAlloc(uint flags, UIntPtr bytes);
    [DllImport("kernel32.dll")] static extern IntPtr GlobalLock(IntPtr memory);
    [DllImport("kernel32.dll")] static extern bool GlobalUnlock(IntPtr memory);
    [DllImport("kernel32.dll")] static extern IntPtr GlobalFree(IntPtr memory);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern IntPtr CreateWindowEx(uint ex, string cls, string name, uint style, int x, int y, int w, int h, IntPtr parent, IntPtr menu, IntPtr instance, IntPtr param);
    [DllImport("user32.dll")] static extern bool DestroyWindow(IntPtr window);

    static void WriteText(string text) {
        byte[] bytes = System.Text.Encoding.Unicode.GetBytes(text + "\\0");
        IntPtr memory = GlobalAlloc(2, (UIntPtr)bytes.Length);
        if (memory == IntPtr.Zero) throw new Exception("Clipboard allocation failed");
        IntPtr data = GlobalLock(memory);
        if (data == IntPtr.Zero) { GlobalFree(memory); throw new Exception("Clipboard lock failed"); }
        Marshal.Copy(bytes, 0, data, bytes.Length); GlobalUnlock(memory);
        if (!EmptyClipboard() || SetClipboardData(13, memory) == IntPtr.Zero) {
            GlobalFree(memory); throw new Exception("Clipboard write failed");
        }
    }

    public static string ClipboardBegin(string text) {
        IntPtr owner = CreateWindowEx(0, "STATIC", "", 0, 0, 0, 0, 0, new IntPtr(-3), IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
        if (owner == IntPtr.Zero) throw new Exception("Clipboard owner unavailable");
        try {
            if (!OpenClipboard(owner)) throw new Exception("剪贴板正被占用，请手动复制结果。");
            try {
                uint format = 0; bool any = false;
                while ((format = EnumClipboardFormats(format)) != 0) {
                    any = true;
                    if (format != 1 && format != 7 && format != 13 && format != 16)
                        throw new Exception("剪贴板含图片或其他格式，已保留，请手动复制结果。");
                }
                string previous = "";
                IntPtr data = GetClipboardData(13);
                if (any && data == IntPtr.Zero) throw new Exception("剪贴板格式无法安全恢复，请手动复制结果。");
                if (data != IntPtr.Zero) {
                    IntPtr ptr = GlobalLock(data);
                    if (ptr == IntPtr.Zero) throw new Exception("Clipboard read failed");
                    try { previous = Marshal.PtrToStringUni(ptr) ?? ""; } finally { GlobalUnlock(data); }
                }
                WriteText(text);
                return GetClipboardSequenceNumber().ToString() + ":" + (any ? "1" : "0") + ":" + Convert.ToBase64String(System.Text.Encoding.Unicode.GetBytes(previous));
            } finally { CloseClipboard(); }
        } finally { DestroyWindow(owner); }
    }

    public static void ClipboardRestore(string lease) {
        string[] parts = lease.Split(':');
        uint expected = uint.Parse(parts[0]);
        IntPtr owner = CreateWindowEx(0, "STATIC", "", 0, 0, 0, 0, 0, new IntPtr(-3), IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
        if (owner == IntPtr.Zero) return;
        try {
            if (!OpenClipboard(owner)) return;
            try {
                // Compare and restore under the same OS clipboard lock. A new user copy wins.
                if (GetClipboardSequenceNumber() != expected) return;
                if (parts[1] == "1") WriteText(System.Text.Encoding.Unicode.GetString(Convert.FromBase64String(parts[2])));
                else EmptyClipboard();
            } finally { CloseClipboard(); }
        } finally { if (owner != IntPtr.Zero) DestroyWindow(owner); }
    }
}
`;

async function runPowerShell(script: string): Promise<string> {
  try {
    const result = await execFileAsync(
      "powershell.exe",
      [
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); try { " +
          script +
          " } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }",
      ],
      {
        windowsHide: true,
        timeout: 5000,
        maxBuffer: 1024 * 1024,
      },
    );

    return result.stdout.trim();
  } catch (error) {
    const failure = error as { stderr?: string };
    throw new Error(
      failure.stderr?.trim() ||
        "无法操作目标窗口或剪贴板，请手动复制最近结果。",
    );
  }
}

export async function getForegroundWindowHandle(): Promise<string> {
  const script = `
$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @'
${USER32_TYPE}
'@
$window = [LikeTypelessUser32]::GetForegroundWindow()
$targetProcess = [uint32]0
[void][LikeTypelessUser32]::WindowProcess($window, [ref]$targetProcess)
[Console]::Write(("{0}:{1}" -f $window.ToInt64(), $targetProcess))
`;

  const handle = await runPowerShell(script);
  if (!/^[1-9]\d*:[1-9]\d*$/.test(handle)) {
    throw new Error(
      `Unable to read the foreground window handle: ${handle || "empty"}`,
    );
  }

  return handle;
}

// One native transaction avoids launching three more PowerShell processes after
// recognition. The clipboard lease stays in this process and is restored in
// finally only when its sequence still matches; a newer user copy wins.
export async function deliverToWindow(
  handle: string,
  text: string,
): Promise<void> {
  if (!/^[1-9]\d*:[1-9]\d*$/.test(handle))
    throw new Error("无效的目标窗口，文字已保存，请手动复制。");
  const [windowId, processId] = handle.split(":");
  const encoded = Buffer.from(text, "utf16le").toString("base64");
  await runPowerShell(`
$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @'
${USER32_TYPE}
'@
$window = [IntPtr]::new(${windowId})
$targetProcess = [uint32]0
[void][LikeTypelessUser32]::WindowProcess($window, [ref]$targetProcess)
if (-not [LikeTypelessUser32]::IsWindow($window) -or $targetProcess -ne ${processId}) { throw "目标窗口已关闭，请手动复制结果。" }
if ([LikeTypelessUser32]::GetForegroundWindow() -ne $window) { throw "录音后切换了窗口，文字已保留，请手动复制。" }
$lease = $null
try {
    $lease = [LikeTypelessUser32]::ClipboardBegin([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('${encoded}')))
    $actualProcess = [uint32]0
    [void][LikeTypelessUser32]::WindowProcess($window, [ref]$actualProcess)
    if ($actualProcess -ne ${processId} -or [LikeTypelessUser32]::GetForegroundWindow() -ne $window) { throw "输入焦点已改变，文字已保留，请手动复制。" }
    if ([LikeTypelessUser32]::GetClipboardSequenceNumber() -ne [uint32]::Parse($lease.Split(':')[0])) { throw "剪贴板已被更新，已取消自动粘贴。" }
    [LikeTypelessUser32]::keybd_event(0x11, 0, 0, [UIntPtr]::Zero)
    [LikeTypelessUser32]::keybd_event(0x56, 0, 0, [UIntPtr]::Zero)
    [LikeTypelessUser32]::keybd_event(0x56, 0, 2, [UIntPtr]::Zero)
    [LikeTypelessUser32]::keybd_event(0x11, 0, 2, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 250
} finally {
    if ($null -ne $lease) { [LikeTypelessUser32]::ClipboardRestore($lease) }
}
`);
}

export async function focusWindow(handle: string): Promise<void> {
  if (!/^[1-9]\d*:[1-9]\d*$/.test(handle)) {
    throw new Error(`Invalid foreground window handle: ${handle}`);
  }

  const script = `
$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @'
${USER32_TYPE}
'@
$window = [IntPtr]::new(${handle.split(":")[0]})
$targetProcess = [uint32]0
[void][LikeTypelessUser32]::WindowProcess($window, [ref]$targetProcess)
if (-not [LikeTypelessUser32]::IsWindow($window) -or $targetProcess -ne ${handle.split(":")[1]}) { throw "目标窗口已关闭，请手动复制结果。" }
$foreground = [LikeTypelessUser32]::GetForegroundWindow()
$foregroundThread = [LikeTypelessUser32]::GetWindowThreadProcessId($foreground, [IntPtr]::Zero)
$currentThread = [LikeTypelessUser32]::GetCurrentThreadId()
$attached = $false

try {
    if ($foregroundThread -ne 0 -and $foregroundThread -ne $currentThread) {
        $attached = [LikeTypelessUser32]::AttachThreadInput($currentThread, $foregroundThread, $true)
    }

    [void][LikeTypelessUser32]::ShowWindowAsync($window, 9)
    [void][LikeTypelessUser32]::BringWindowToTop($window)
    $focused = [LikeTypelessUser32]::SetForegroundWindow($window)
    if (-not $focused) {
        Start-Sleep -Milliseconds 80
        $focused = [LikeTypelessUser32]::SetForegroundWindow($window)
    }
    if (-not $focused) {
        throw "SetForegroundWindow failed"
    }
} finally {
    if ($attached) {
        [void][LikeTypelessUser32]::AttachThreadInput($currentThread, $foregroundThread, $false)
    }
}
Start-Sleep -Milliseconds 120
if ([LikeTypelessUser32]::GetForegroundWindow() -ne $window) { throw "无法确认目标窗口焦点，请手动复制结果。" }
`;
  await runPowerShell(script);
}

export async function pasteIntoWindow(
  handle: string,
  lease: string,
): Promise<void> {
  if (!/^[1-9]\d*:[1-9]\d*$/.test(handle)) throw new Error("无效的目标窗口");
  if (!/^\d+:[01]:[A-Za-z0-9+/=]*$/.test(lease))
    throw new Error("Invalid clipboard lease");
  await runPowerShell(`
$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @'
${USER32_TYPE}
'@
$window = [IntPtr]::new(${handle.split(":")[0]})
$targetProcess = [uint32]0
[void][LikeTypelessUser32]::WindowProcess($window, [ref]$targetProcess)
if ($targetProcess -ne ${handle.split(":")[1]} -or [LikeTypelessUser32]::GetForegroundWindow() -ne $window) { throw "输入焦点已改变，文字已保留，请手动复制。" }
if ([LikeTypelessUser32]::GetClipboardSequenceNumber() -ne ${lease.split(":")[0]}) { throw "剪贴板已被更新，已取消自动粘贴。" }
[LikeTypelessUser32]::keybd_event(0x11, 0, 0, [UIntPtr]::Zero)
[LikeTypelessUser32]::keybd_event(0x56, 0, 0, [UIntPtr]::Zero)
[LikeTypelessUser32]::keybd_event(0x56, 0, 2, [UIntPtr]::Zero)
[LikeTypelessUser32]::keybd_event(0x11, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 250
`);
}

export async function beginClipboard(text: string): Promise<string> {
  const encoded = Buffer.from(text, "utf16le").toString("base64");
  return runPowerShell(`$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @'
${USER32_TYPE}
'@
[Console]::Write([LikeTypelessUser32]::ClipboardBegin([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('${encoded}'))))`);
}

export async function restoreClipboard(lease: string): Promise<void> {
  if (!/^\d+:[01]:[A-Za-z0-9+/=]*$/.test(lease))
    throw new Error("Invalid clipboard lease");
  await runPowerShell(`$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @'
${USER32_TYPE}
'@
[LikeTypelessUser32]::ClipboardRestore('${lease}')`);
}
