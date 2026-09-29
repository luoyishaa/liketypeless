import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type {
  AudioDevice,
  DesktopState,
  HealthResponse,
  ModelStatus,
  RecentResult,
} from "@liketypeless/shared";
import type { DesktopSettings } from "../main/settings-store";
import type { LikeTypelessApi } from "../preload";
import "./styles.css";

declare global {
  interface Window {
    liketypeless: LikeTypelessApi;
  }
}
const api = window.liketypeless;
const phases: Record<DesktopState["phase"], string> = {
  starting: "正在启动",
  ready: "准备就绪",
  recording: "正在聆听",
  processing: "正在识别",
  "ready-to-copy": "文字已保留",
  "paste-requested": "已发送粘贴",
  error: "需要处理",
};
function message(error: unknown) {
  return error instanceof Error
    ? error.message.replace(
        /^Error invoking remote method '[^']+': Error: /,
        "",
      )
    : String(error);
}

function App() {
  const [page, setPage] = useState<"home" | "settings" | "diagnostics">("home");
  const [settings, setSettings] = useState<DesktopSettings | null>(null);
  const [draft, setDraft] = useState<DesktopSettings | null>(null);
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [state, setState] = useState<DesktopState>({
    phase: "starting",
    message: "正在启动本机服务…",
  });
  const [results, setResults] = useState<RecentResult[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [working, setWorking] = useState(false);
  const [step, setStep] = useState(1);
  const [endpoint, setEndpoint] = useState("https://huggingface.co");
  const locked =
    working || state.phase === "recording" || state.phase === "processing";
  const modelBusy =
    model?.state === "downloading" || model?.state === "verifying";

  async function refresh() {
    const [nextHealth, nextModel, nextResults, nextState] = await Promise.all([
      api.health(),
      api.modelStatus(),
      api.results(),
      api.state(),
    ]);
    setHealth(nextHealth);
    setModel(nextModel);
    setResults(nextResults);
    setState(nextState);
  }
  useEffect(() => {
    let stopped = false;
    let polling = false;
    api
      .settings()
      .then((value) => {
        if (!stopped) {
          setSettings(value);
          setDraft(value);
        }
      })
      .catch((e) => setError(message(e)));
    const poll = async () => {
      if (polling || stopped) return;
      polling = true;
      try {
        await refresh();
      } catch (e) {
        if (!stopped) {
          setHealth(null);
          setError(message(e));
        }
      } finally {
        polling = false;
      }
    };
    void poll();
    api
      .audioDevices()
      .then(setDevices)
      .catch((e) => setError(message(e)));
    const timer = setInterval(() => void poll(), 1500);
    const off = api.onState(setState);
    return () => {
      stopped = true;
      clearInterval(timer);
      off();
    };
  }, []);

  async function act(action: () => Promise<unknown>, success = "") {
    setError("");
    setNotice("");
    setWorking(true);
    try {
      await action();
      await refresh();
      if (success) setNotice(success);
    } catch (e) {
      setError(message(e));
    } finally {
      setWorking(false);
    }
  }
  async function save(next: DesktopSettings) {
    const value = await api.updateSettings(next);
    setSettings(value);
    setDraft(value);
  }
  function modelPanel() {
    return (
      <section className="card model-card">
        <div className="section-title">
          <div>
            <span className="eyebrow">本地语音模型</span>
            <h2>先准备好，再开口</h2>
          </div>
          <span className={"badge " + (model?.state === "ready" ? "good" : "")}>
            {model?.state === "ready"
              ? "已校验 · 可离线使用"
              : modelBusy
                ? "准备中"
                : "尚未就绪"}
          </span>
        </div>
        <p>
          Whisper small · 约 486
          MB。首次准备需要网络，之后基础输入无需联网，也不需要 Ollama。
        </p>
        {modelBusy && (
          <>
            <progress
              max={model?.totalBytes || 1}
              value={model?.downloadedBytes || 0}
            />
            <small>
              {model?.state === "verifying"
                ? "正在校验模型完整性…"
                : Math.round((model?.downloadedBytes || 0) / 1000000) +
                  " / " +
                  Math.round((model?.totalBytes || 0) / 1000000) +
                  " MB"}
            </small>
          </>
        )}
        {model?.error && (
          <p role="alert" className="inline-error">
            {model.error}
          </p>
        )}
        {model?.state !== "ready" && (
          <div className="controls">
            <select
              aria-label="模型下载来源"
              value={endpoint}
              disabled={modelBusy}
              onChange={(e) => setEndpoint(e.target.value)}
            >
              <option value="https://huggingface.co">官方 Hugging Face</option>
              <option value="https://hf-mirror.com">
                第三方镜像 hf-mirror.com（自行选择）
              </option>
            </select>
            <button
              disabled={locked || modelBusy}
              onClick={() => void act(() => api.prepareModel(endpoint))}
            >
              下载 / 继续准备
            </button>
            <button
              className="secondary"
              disabled={locked || modelBusy}
              onClick={() => void act(() => api.importModel())}
            >
              导入已有模型
            </button>
          </div>
        )}
      </section>
    );
  }
  const onboarding = settings && !settings.onboardingComplete;

  return (
    <div className="layout">
      <aside>
        <div className="brand">
          <span className="brand-symbol">声</span>
          <div>
            liketypeless<small>本地中文语音输入</small>
          </div>
        </div>
        <nav aria-label="主导航">
          {(
            [
              ["home", "语音输入"],
              ["settings", "偏好设置"],
              ["diagnostics", "状态与帮助"],
            ] as const
          ).map(([id, label]) => (
            <button
              className={page === id ? "nav-item selected" : "nav-item"}
              key={id}
              onClick={() => setPage(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="privacy-dot" />
          基础模式 · 本机处理
          <p>
            关闭窗口后继续在托盘运行。
            <br />
            需要停止服务时，从托盘退出。
          </p>
          <small>v0.1 候选版 · Windows x64</small>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <span className="eyebrow">说出来，留下来</span>
            <h1>
              {page === "home"
                ? "把想法变成文字"
                : page === "settings"
                  ? "按你的习惯输入"
                  : "知道它正在做什么"}
            </h1>
          </div>
          <span className={"badge " + (health ? "good" : "")}>
            {health ? "本机服务在线" : "服务未就绪"}
          </span>
        </header>
        {error && (
          <div role="alert" className="alert">
            {error}
            <button className="text-button" onClick={() => setError("")}>
              关闭提示
            </button>
          </div>
        )}
        {notice && (
          <div role="status" className="notice">
            {notice}
          </div>
        )}

        {page === "home" && (
          <>
            {onboarding && (
              <section className="card onboarding">
                <span className="eyebrow">首次使用 · 第 {step} / 4 步</span>
                <h2>
                  {
                    [
                      "",
                      "准备语音模型",
                      "选择麦克风并试录",
                      "确认录音快捷键",
                      "在真实输入框试一次",
                    ][step]
                  }
                </h2>
                <p>
                  {
                    [
                      "",
                      "下方完成下载或导入，校验通过后继续。",
                      "先到偏好设置选择麦克风，再用下方按钮录一句话，确认最近结果出现文字。",
                      "当前快捷键：" +
                        settings.globalHotkey +
                        "。若与中文输入法冲突，请到偏好设置改为 Ctrl+Shift+Space。",
                      "打开记事本，点击输入框，用快捷键开始并结束录音。检查文字位置和内容。确认后完成引导。",
                    ][step]
                  }
                </p>
                <div className="controls">
                  {step > 1 && (
                    <button
                      className="secondary"
                      disabled={locked}
                      onClick={() => setStep(step - 1)}
                    >
                      上一步
                    </button>
                  )}
                  {step < 4 ? (
                    <button
                      disabled={
                        locked ||
                        (step === 1 && !health?.modelReady) ||
                        (step === 2 && !results.some((item) => item.text))
                      }
                      onClick={() => setStep(step + 1)}
                    >
                      下一步
                    </button>
                  ) : (
                    <button
                      disabled={locked}
                      onClick={() =>
                        void act(async () => {
                          await save({ ...settings, onboardingComplete: true });
                          await api.hideWindow();
                        }, "引导完成，应用将留在托盘。")
                      }
                    >
                      完成并收起到托盘
                    </button>
                  )}
                </div>
              </section>
            )}
            {!health?.modelReady && modelPanel()}
            <section
              className={
                "card recorder " +
                (state.phase === "recording" ? "listening" : "")
              }
            >
              <div className="record-symbol" aria-hidden="true">
                {state.phase === "recording" ? "■" : "●"}
              </div>
              <span className="eyebrow">{phases[state.phase]}</span>
              <h2>
                {state.phase === "recording"
                  ? "慢慢说，我在听"
                  : "按一下，开始说话"}
              </h2>
              <p>
                在其他应用中按{" "}
                <kbd>{settings?.globalHotkey || "Shift+Space"}</kbd>{" "}
                录音，再按一次结束。
              </p>
              <button
                className="primary record-button"
                disabled={
                  working || state.phase === "processing" || !health?.modelReady
                }
                onClick={() => void act(() => api.toggleRecording())}
              >
                {state.phase === "recording" ? "结束并识别" : "在这里试录"}
              </button>
              <small>这里试录只保存结果，不向其他窗口粘贴。</small>
              <div className="workflow-status" role="status">
                {state.message}
                {state.elapsedMs !== undefined && (
                  <span>
                    {" "}
                    · 停止后到文字可复制或发出粘贴请求{" "}
                    {(state.elapsedMs / 1000).toFixed(2)} 秒
                  </span>
                )}
              </div>
            </section>
            <section className="history">
              <div className="section-title">
                <div>
                  <span className="eyebrow">先保存，再输入</span>
                  <h2>最近结果</h2>
                </div>
                <span className="subtle">{results.length} 条</span>
              </div>
              {!results.length && (
                <div className="empty-state">
                  第一句话，从这里开始。<p>录音识别后，文字副本会留在这里。</p>
                </div>
              )}
              {results.map((item) => (
                <article className="card result" key={item.id}>
                  <div className="result-meta">
                    <time>
                      {new Date(item.created * 1000).toLocaleString("zh-CN")}
                    </time>
                    <span>
                      {item.status === "failed"
                        ? "可重试"
                        : item.status === "empty"
                          ? "未识别到文字"
                          : item.text
                            ? "已保存"
                            : "处理中 / 待恢复"}
                    </span>
                  </div>
                  <p className="result-text">
                    {item.text ||
                      item.transcript ||
                      item.error ||
                      "没有文字结果；若处理已中断，可尝试恢复录音。"}
                  </p>
                  <div className="controls">
                    {(item.text || item.transcript) && (
                      <button
                        className="secondary"
                        onClick={() =>
                          void act(
                            () => api.copyResult(item.id),
                            "已复制。请粘贴到需要的位置。",
                          )
                        }
                      >
                        复制文字
                      </button>
                    )}
                    {["failed", "processing", "recognized"].includes(
                      item.status,
                    ) && (
                      <button
                        disabled={locked}
                        className="secondary"
                        onClick={() => void act(() => api.retryResult(item.id))}
                      >
                        重试识别
                      </button>
                    )}
                    {item.transcript && (
                      <details>
                        <summary>查看原始识别</summary>
                        <p>{item.transcript}</p>
                      </details>
                    )}
                  </div>
                </article>
              ))}
            </section>
          </>
        )}

        {page === "settings" && draft && (
          <>
            <section className="card">
              <h2>输入偏好</h2>
              <label>
                录音快捷键
                <input
                  value={draft.globalHotkey}
                  disabled={locked}
                  onChange={(e) =>
                    setDraft({ ...draft, globalHotkey: e.target.value })
                  }
                />
              </label>
              <small>例如 Ctrl+Shift+Space。若注册失败，会保留原快捷键。</small>
              <label>
                输入设备
                <select
                  value={draft.inputDeviceId ?? ""}
                  disabled={locked}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      inputDeviceId: e.target.value
                        ? Number(e.target.value)
                        : null,
                    })
                  }
                >
                  <option value="">系统默认麦克风</option>
                  {devices.map((device) => (
                    <option key={device.id} value={device.id}>
                      {device.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="text-button"
                disabled={locked}
                onClick={() =>
                  void act(async () => setDevices(await api.audioDevices()))
                }
              >
                重新检测设备
              </button>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={draft.cleanupMode === "enhanced"}
                  disabled={locked}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      cleanupMode: e.target.checked ? "enhanced" : "basic",
                    })
                  }
                />
                启用 Ollama 智能整理（可选）
              </label>
              <p>
                默认仅做本地识别与规则整理。增强模式需要另行准备 Ollama 和
                qwen3:8b，可能增加等待；失败时保留基础结果。日期、数字和人名仍需核对。
              </p>
              <button
                disabled={locked}
                onClick={() => void act(() => save(draft), "设置已保存。")}
              >
                保存设置
              </button>
            </section>
            <section className="card">
              <h2>记录与隐私</h2>
              <p>
                最近 50 条文字保存在本机。成功处理的录音会删除；失败录音最多保留
                24 小时，应用运行或下次启动时清理。没有遥测或云端同步。
              </p>
              <button
                className="secondary danger"
                disabled={locked}
                onClick={() => {
                  if (
                    window.confirm("清除最近文字和暂存录音？此操作无法恢复。")
                  )
                    void act(() => api.clearResults(), "本机记录已清除。");
                }}
              >
                清除本机记录
              </button>
            </section>
          </>
        )}

        {page === "diagnostics" && (
          <>
            {modelPanel()}
            <section className="card">
              <h2>运行状态</h2>
              <dl>
                <dt>识别模型</dt>
                <dd>Whisper small · beam 1</dd>
                <dt>当前计算设备</dt>
                <dd>{health?.runtime.device || "首次识别后显示"}</dd>
                <dt>基础输入</dt>
                <dd>无需 Ollama · 模型就绪后离线可用</dd>
                <dt>最近一次后台处理</dt>
                <dd>{state.backendElapsedMs === undefined ? "尚未测量" : `${(state.backendElapsedMs / 1000).toFixed(2)} 秒`}</dd>
                <dt>最近一次输入投递</dt>
                <dd>{state.deliveryElapsedMs === undefined ? "尚未测量" : `${(state.deliveryElapsedMs / 1000).toFixed(2)} 秒`}</dd>
                <dt>智能整理</dt>
                <dd>
                  {settings?.cleanupMode === "enhanced"
                    ? "已开启（请求时检查服务）"
                    : "未开启"}
                </dd>
              </dl>
              {health?.runtime.fallbackReason && (
                <p className="notice">{health.runtime.fallbackReason}</p>
              )}
              <button
                className="secondary"
                disabled={locked}
                onClick={() =>
                  void act(() => api.restart(), "服务已重新启动。")
                }
              >
                重新启动服务
              </button>
            </section>
            <section className="card">
              <h2>使用边界</h2>
              <p>
                这是 Windows 11 x64
                候选版。管理员窗口、密码框、远程桌面可能阻止输入；请从最近结果手动复制。不确定目标焦点或剪贴板含非文本内容时，不自动粘贴。
              </p>
              <p>
                “已发送粘贴”不代表已验证写入。短句、人名、远场声音仍可能识别错误，请核对重要内容。翻译与会议功能暂不作为本版承诺。
              </p>
              <button
                className="text-button"
                disabled={locked || !settings}
                onClick={() => {
                  if (settings)
                    void act(async () => {
                      await save({ ...settings, onboardingComplete: false });
                      setStep(1);
                      setPage("home");
                    });
                }}
              >
                重新查看首次使用引导
              </button>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
