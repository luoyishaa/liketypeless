# liketypeless

面向 Windows 的本地优先语音输入助手：按快捷键录音，停止后将语音转成文字，做保守的结构化整理，并自动粘贴到当前光标所在的输入框。

项目目标是做一个可持续共同维护的本地化 Typeless 类工具，优先保证隐私、响应速度和原意保留。

## 当前能力

- Windows Electron 桌面应用。
- 全局快捷键 `Shift+Space`：
  - 第一次按下：开始录音。
  - 第二次按下：停止录音、转写、结构化并自动粘贴。
- 自动记住原前台窗口，完成处理后恢复焦点并发送 `Ctrl+V`。
- 自动恢复之前的剪贴板文本。
- 本地 `faster-whisper` 语音识别，默认使用 `small` 模型。
- 自动检测 CUDA；GPU 可用时使用 CUDA/float16，否则回退 CPU/int8。
- 可选 SenseVoice/FunASR provider，用于对比中文识别质量。
- Ollama 本地 LLM 结构化，默认使用 `qwen3:8b`，关闭思考模式。
- 保守结构化：
  - 去掉部分“嗯、啊、呃、额”等填充词。
  - 保留原意和原有措辞。
  - 按“第一、第二”等结构分条。
  - 修正明显错字。
  - 补充中文句末标点。
  - LLM 输出不安全时回退到规则结果。
- Electron 窗口、托盘和手动测试界面。

## 工作流

```text
Shift+Space
    |
    v
记住当前前台窗口 -> Python 开始录音
    |
再次 Shift+Space
    |
    v
停止录音 -> faster-whisper 转写 -> Ollama 结构化
    |
    v
恢复原窗口 -> 粘贴文本 -> 恢复剪贴板
```

当前版本支持停止后批量识别，也支持主窗口中的实时转写预览。录音期间会在屏幕右下角显示一个不抢焦点、可穿透鼠标的悬浮状态窗；停止后它会切换为处理中，完成或失败后自动隐藏。预览每约 3 秒读取一次当前录音快照，不会停止或清空录音；最终转写仍以完整原始录音为准。

## 技术架构

```text
Electron main process
  - globalShortcut
  - Tray
  - Windows foreground window and paste
  - IPC

React renderer
  - settings and diagnostics UI
  - manual recording tests

Python FastAPI local API
  - sounddevice recording
  - faster-whisper / SenseVoice
  - conservative text structure

Ollama
  - local qwen3:8b
```

## 环境要求

- Windows 10/11
- Node.js 24+
- Python 3.12+
- Ollama
- 可选 NVIDIA GPU 和 CUDA runtime
- 至少一个本地 faster-whisper 模型
- 至少一个 Ollama 模型

## 安装

在仓库根目录执行：

```powershell
npm install

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r apps/local-api/requirements.txt
```

如果默认 Python 环境不适合安装依赖，可以使用项目内 `.venv`，不要混用 Anaconda 环境。

## 准备 Ollama 模型

安装 Ollama 后拉取默认模型：

```powershell
ollama pull qwen3:8b
```

应用使用 Ollama 的本地 HTTP 服务，默认地址是：

```text
http://127.0.0.1:11434
```

如果模型下载需要代理，注意：下载工作由后台 `ollama serve` 进程执行，不是当前 PowerShell 进程单独执行。先重启带代理的 Ollama 服务：

```powershell
.\scripts\start-ollama-proxy.ps1
ollama pull qwen3:8b
```

脚本默认使用：

```text
http://127.0.0.1:7897
```

也可以指定代理：

```powershell
.\scripts\start-ollama-proxy.ps1 -ProxyUrl "http://127.0.0.1:7897"
```

## 准备 faster-whisper 模型

推荐提前下载模型，不要等第一次录音时下载：

```powershell
npm run download:stt
```

当前应用会按以下顺序自动检测本地模型：

```text
D:\Models\faster-whisper-small
D:\Models\faster-whisper-base
D:\Models\faster-whisper-tiny
```

也可以显式指定路径：

```powershell
$env:LIKETYPELESS_STT_MODEL_PATH="D:\Models\faster-whisper-small"
```

常用配置：

```powershell
$env:LIKETYPELESS_STT_MODEL="small"
$env:LIKETYPELESS_STT_DEVICE="auto"
$env:LIKETYPELESS_STT_COMPUTE_TYPE="auto"
$env:LIKETYPELESS_STT_BEAM_SIZE="1"
```

长录音默认每 90 秒分块后依次转写，以避免单次离线识别占用过久或内存峰值过高；短于该阈值的录音仍走原来的单次识别路径。可调整或关闭分块：

```powershell
$env:LIKETYPELESS_STT_CHUNK_SECONDS="120" # 每 120 秒一块
$env:LIKETYPELESS_STT_CHUNK_SECONDS="0"   # 关闭分块
```

如果需要通过代理下载 Hugging Face 模型：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7897"
$env:HTTPS_PROXY="http://127.0.0.1:7897"
$env:ALL_PROXY="http://127.0.0.1:7897"
$env:HF_HUB_DISABLE_XET="1"
npm run download:stt
```

## 运行

先确认 Ollama 服务正在运行，然后在仓库根目录执行：

```powershell
npm run dev
```

这会同时启动：

- Python API：`http://127.0.0.1:8716`
- Electron renderer：默认 `http://localhost:5173`

如果 `5173` 已被其他项目占用：

```powershell
$env:LIKETYPELESS_RENDERER_PORT="5183"
$env:ELECTRON_RENDERER_URL="http://localhost:5183"
npm run dev:desktop
```

如果快捷键和中文输入法冲突，可以改用：

```powershell
$env:LIKETYPELESS_GLOBAL_HOTKEY="Ctrl+Shift+Space"
npm run dev:desktop
```

## 验证

运行 TypeScript 检查：

```powershell
npm run check
```

运行 Python 编译检查：

```powershell
npm run check:api
```

检查 API：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8716/health"
```

实际使用测试：

1. 打开记事本、浏览器输入框或其他普通文本输入框。
2. 按一次 `Shift+Space` 开始录音。
3. 正常说话。
4. 再按一次 `Shift+Space`。
5. 等待转写和结构化完成，文本会自动粘贴。

## 常见问题

### 快捷键注册失败

`Shift+Space` 可能和中文输入法的全角/半角切换冲突。改用：

```powershell
$env:LIKETYPELESS_GLOBAL_HOTKEY="Ctrl+Shift+Space"
```

某些应用以管理员权限运行时，普通权限的 liketypeless 可能无法恢复焦点或模拟粘贴。可以让两者使用相同权限级别后再测试。

### 录音结束后等待较久

当前流程是批量识别，耗时主要来自：

1. faster-whisper 处理整段音频。
2. Ollama 对完整文本做结构化。

短文本和短录音会更快。长录音已经按默认 90 秒分块转写；后续会增加实时预览。

### API 找不到模块或启动到旧代码

不要混用 Anaconda 和项目 `.venv`。推荐：

```powershell
.\.venv\Scripts\python.exe apps/local-api/scripts/run_api.py
```

如果 `8716` 被旧进程占用，先检查：

```powershell
netstat -ano | Select-String ":8716"
Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
  Select-Object ProcessId,CommandLine
```

### 模型没有下载或 Ollama 拉取超时

先运行：

```powershell
.\scripts\start-ollama-proxy.ps1
```

然后再执行 `ollama pull`。下载日志会写入：

```text
ollama.proxy.out.log
ollama.proxy.err.log
```

## 项目结构

```text
apps/
  desktop/
    src/main/       Electron 主进程、快捷键、托盘、自动粘贴
    src/preload/    安全 IPC bridge
    src/renderer/   React 设置和测试界面
  local-api/
    app/            FastAPI、录音、ASR、结构化
    scripts/        模型下载和独立 provider runner
packages/
  shared/           前后端共享类型
docs/
  decisions/        架构决策记录
scripts/
  start-ollama-proxy.ps1
```

## 路线图

- [x] 本地录音和 faster-whisper 转写
- [x] GPU/CPU 自动回退
- [x] Ollama 保守结构化
- [x] 全局快捷键录音
- [x] 自动粘贴到原输入框
- [x] 中文句末标点补全
- [x] 录音状态悬浮窗
- [x] 长录音分块转写
- [x] 实时转写预览
- [ ] 可配置快捷键和输入设备界面
- [ ] 浏览器和文档划线翻译
- [ ] 中文转英文语音输入模式
- [ ] 打包安装程序和首次启动检查

## 协作

请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。架构取舍记录在 `docs/decisions/`，涉及核心流程的修改应同步更新对应决策记录。

## 许可证

当前仓库尚未选择开源许可证。许可证确定前，请不要将代码用于商业分发或发布衍生版本。
