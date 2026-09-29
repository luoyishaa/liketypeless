import { spawn, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";

export class BackendProcess {
  private child: ChildProcess | null = null;
  private address = "";
  private token = "";
  private pending: Promise<void> | null = null;
  private command: string;
  private args: string[];
  private dataDir: string;
  error: string | null = null;

  constructor(command: string, args: string[], dataDir: string) {
    this.command = command;
    this.args = args;
    this.dataDir = dataDir;
  }

  async start(): Promise<void> {
    if (this.pending) return this.pending;
    if (this.child && this.address) return;
    if (this.error) throw new Error(this.error);
    this.pending = this.launch();
    try {
      await this.pending;
    } finally {
      this.pending = null;
    }
  }

  private async launch(): Promise<void> {
    this.token = randomBytes(32).toString("hex");
    const child = spawn(this.command, this.args, {
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONPATH: "",
        PYTHONUTF8: "1",
        LIKETYPELESS_DATA_DIR: this.dataDir,
        LIKETYPELESS_SESSION_TOKEN: this.token,
        LIKETYPELESS_STT_MODEL_PATH: "",
        LIKETYPELESS_PARENT_PID: String(process.pid),
        LIKETYPELESS_STT_PROVIDER: "local-faster-whisper",
        LIKETYPELESS_STT_MODEL: "small",
        LIKETYPELESS_STT_BEAM_SIZE: "1",
        LIKETYPELESS_STT_CHUNK_SECONDS: "90",
        LIKETYPELESS_STT_WITHOUT_TIMESTAMPS: "1",
        LIKETYPELESS_STT_VAD_FILTER: "0",
      },
    });
    this.child = child;
    let diagnostics = "";
    child.stderr?.on("data", (chunk) => {
      diagnostics = (diagnostics + String(chunk)).slice(-4000);
    });
    child.on("exit", (code) => {
      if (this.child === child) {
        this.child = null;
        this.address = "";
        this.error = `本机服务已退出（${code}）。请点击“重新启动服务”。`;
      }
    });
    try {
      const port = await new Promise<number>((resolve, reject) => {
        const timer = setTimeout(
          () => reject(new Error("服务启动超时，请重试。")),
          30000,
        );
        let buffer = "";
        child.stdout?.on("data", (chunk) => {
          buffer = (buffer + String(chunk)).slice(-4000);
          const match = buffer.match(/LIKETYPELESS_READY:(\d+)/);
          if (match) {
            clearTimeout(timer);
            resolve(Number(match[1]));
          }
        });
        child.once("error", (error) => {
          clearTimeout(timer);
          reject(error);
        });
        child.once("exit", () => {
          clearTimeout(timer);
          reject(new Error(`服务无法启动：${diagnostics}`));
        });
      });
      this.address = `http://127.0.0.1:${port}`;
      for (let attempt = 0; attempt < 50; attempt++) {
        try {
          const response = await fetch(`${this.address}/health`, {
            headers: this.headers(),
            signal: AbortSignal.timeout(1000),
          });
          if (response.ok) return;
        } catch {
          /* The listener can precede ASGI startup by a few milliseconds. */
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      throw new Error("服务未通过启动检查，请重新启动服务。");
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error);
      child.kill();
      this.child = null;
      this.address = "";
      throw error;
    }
  }

  private headers() {
    return {
      Authorization: `Bearer ${this.token}`,
      "Content-Type": "application/json",
    };
  }

  async request<T>(path: string, body?: unknown): Promise<T> {
    await this.start();
    const response = await fetch(`${this.address}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: this.headers(),
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(180000),
    });
    if (!response.ok) {
      const result = (await response.json().catch(() => ({}))) as {
        detail?: unknown;
      };
      throw new Error(
        typeof result.detail === "string"
          ? result.detail
          : `操作失败（${response.status}），请检查设置后重试。`,
      );
    }
    return (await response.json()) as T;
  }

  async stop(): Promise<void> {
    const child = this.child;
    if (!child) return;
    this.child = null;
    try {
      await fetch(`${this.address}/system/shutdown`, {
        method: "POST",
        headers: this.headers(),
        signal: AbortSignal.timeout(1500),
      });
    } catch {
      /* A crashed backend has no shutdown endpoint. */
    }
    if (child.exitCode === null)
      await new Promise<void>((resolve) => {
        const timer = setTimeout(() => {
          child.kill();
          resolve();
        }, 3000);
        child.once("exit", () => {
          clearTimeout(timer);
          resolve();
        });
      });
    this.address = "";
  }

  async restart(): Promise<void> {
    await this.stop();
    this.error = null;
    await this.start();
  }
}
