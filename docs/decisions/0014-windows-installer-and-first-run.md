# 0014. Windows 使用 NSIS 安装程序，首次启动检查本地服务

## 决策

桌面应用使用 `electron-builder` 生成 x64 NSIS 安装程序。桌面主窗口启动时请求本地 API health endpoint，并显示 Ollama 可达状态；无法连通时保留可操作的本地 API 启动指引。

## 原因

Electron 壳可独立安装，但本项目的 Python ASR 运行时和本地模型体积很大、且与机器 GPU 环境相关，不适合静默塞进首个轻量安装包。先让安装程序可靠分发桌面端，再以明确检查引导本地依赖准备。

## 验证

运行 `npm run dist`，确认 `apps/desktop/release/` 产出 NSIS 安装程序；安装后启动应用，确认健康状态会反映 API 与 Ollama 状态。
