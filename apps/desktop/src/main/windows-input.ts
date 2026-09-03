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
}
`;

async function runPowerShell(script: string): Promise<string> {
  const result = await execFileAsync(
    "powershell.exe",
    ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
    {
      windowsHide: true,
      timeout: 5000,
      maxBuffer: 1024 * 1024
    }
  );

  return result.stdout.trim();
}

export async function getForegroundWindowHandle(): Promise<string> {
  const script = `
$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @'
${USER32_TYPE}
'@
[Console]::Write([LikeTypelessUser32]::GetForegroundWindow().ToInt64())
`;

  const handle = await runPowerShell(script);
  if (!/^\d+$/.test(handle) || handle === "0") {
    throw new Error(`Unable to read the foreground window handle: ${handle || "empty"}`);
  }

  return handle;
}

export async function pasteIntoWindow(handle: string): Promise<void> {
  if (!/^\d+$/.test(handle) || handle === "0") {
    throw new Error(`Invalid foreground window handle: ${handle}`);
  }

  const script = `
$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @'
${USER32_TYPE}
'@
$window = [IntPtr]::new(${handle})
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
[LikeTypelessUser32]::keybd_event(0x11, 0, 0, [UIntPtr]::Zero)
[LikeTypelessUser32]::keybd_event(0x56, 0, 0, [UIntPtr]::Zero)
[LikeTypelessUser32]::keybd_event(0x56, 0, 2, [UIntPtr]::Zero)
[LikeTypelessUser32]::keybd_event(0x11, 0, 2, [UIntPtr]::Zero)
`;

  await runPowerShell(script);
}

export async function copySelectionFromWindow(handle: string): Promise<void> {
  if (!/^\d+$/.test(handle) || handle === "0") {
    throw new Error(`Invalid foreground window handle: ${handle}`);
  }
  const script = `
$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @'
${USER32_TYPE}
'@
$window = [IntPtr]::new(${handle})
[void][LikeTypelessUser32]::ShowWindowAsync($window, 9)
[void][LikeTypelessUser32]::BringWindowToTop($window)
[void][LikeTypelessUser32]::SetForegroundWindow($window)
Start-Sleep -Milliseconds 80
[LikeTypelessUser32]::keybd_event(0x11, 0, 0, [UIntPtr]::Zero)
[LikeTypelessUser32]::keybd_event(0x43, 0, 0, [UIntPtr]::Zero)
[LikeTypelessUser32]::keybd_event(0x43, 0, 2, [UIntPtr]::Zero)
[LikeTypelessUser32]::keybd_event(0x11, 0, 2, [UIntPtr]::Zero)
`;
  await runPowerShell(script);
}
