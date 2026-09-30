# v1 候选包的 Windows 交互验证规程

此规程只用于记录最终安装包的实际行为；自动化后台结果不能替代目标应用中的可见文字。当前包为 `0.1.0-rc.3`，未签名；遇到系统的未知发布者提示，应核对 SHA-256 与来源，不关闭 Windows 安全功能。独立测试环境应为 Windows 11 x64、无 Python/Node/Ollama；安装路径包含空格，另覆盖中文用户名。

## 准备与记录

1. 校验安装包哈希，安装为当前用户。首次启动从官方来源准备 Whisper small，选定麦克风，完成一条试录；关闭网络后再完成一条基础输入。SenseVoice 是独立可选下载，不准备时短句应回退 Whisper。
2. 复制 `evals/fixtures/desktop-trials-template.csv` 到忽略的 `evals/local/desktop-trials.csv`。每次填写实际口述、原始识别、目标框最终文字、`direct`/`manual_copy`/`wrong_target`/`lost`。只有在目标框内看到文字才能标 `direct`；界面显示“已发送粘贴”本身不算。
3. 分别在记事本、浏览器普通输入框和 Word 文档做 20 次，共 60 次。建议每组混入日期、数字、否定和中英术语。至少 59/60 次直接输入且没有误入其他窗口、没有不可恢复内容，才通过该门槛。切换或关闭目标窗口的故障用例单独记录，预期是结果可找回且不误粘。
4. `stop_to_usable_ms` 从结束录音的动作算到文字在目标框可见，或恢复结果可复制。诊断页显示的是“停止到可复制/发出粘贴请求”的内部耗时，**不能**代填目标框实测。可用屏幕录制的时间戳取帧；没有可核对时间戳就留空，不计算完整交互 P95。
5. 运行 30 条自然口述任务（`evals/fixtures/natural-review-tasks.jsonl`）。题目只给表达意图，实际说法、参考文本与原始转写逐条记录。将**同一份原始转写文本**固定后分别提交基础和可选增强整理；不要把两次重新口述当成配对。填报每种输出达到可用文本所需的修改次数，并单列日期、数字、人名、否定变化。模型回退不记为模型成功。私人录音和逐条表格不上传仓库。
6. 累计 100 次实际麦克风录音处理，可由上述 60 次跨应用、30 条自然口述及另 10 次故障/重试组成，逐次核对结果保存、处理状态与退出后残留；不要把文件转写循环算作麦克风循环。完整应用启动/退出另做 20 次，退出后确认后台进程消失。

## 故障与维护检查

逐项记录预期与实际：断网下载后续传、录音中拔出麦克风、快捷键被其他程序占用、后台意外退出与恢复、录音后目标窗口关闭、用户期间复制新的内容、Ollama 不可用、GPU 不可用。预期是基础识别仍可用或明确降级，结果不丢失，且不误粘、不覆盖新剪贴板。验证覆盖安装保留设置/最近结果、卸载后无运行进程；应用数据按说明由用户决定是否保留。

填完表后运行：

```powershell
.\.venv-release\Scripts\python.exe evals/scripts/summarize_desktop_trials.py --trials evals/local/desktop-trials.csv --output evals/local/desktop-trials-summary.json
.\.venv-release\Scripts\python.exe evals/scripts/summarize_natural_review.py --review evals/local/natural-review-scoring.csv --output evals/local/natural-review-v1-summary.json
```

自然口述空白表用 `evals/scripts/make_natural_review_sheet.py --output evals/local/natural-review-v1.csv` 生成。填完 30 条 `raw_transcript` 后，在开发机固定输入并运行同版产品整理接口：

```powershell
.\.venv-release\Scripts\python.exe evals/scripts/natural_review_modes.py --review evals/local/natural-review-v1.csv --manifest-output evals/local/natural-modes-input.jsonl
.\.venv-release\Scripts\python.exe evals/scripts/benchmark_cleanup_modes.py --manifest evals/local/natural-modes-input.jsonl --output evals/local/natural-modes-result.json --enhanced --prewarm-enhanced
.\.venv-release\Scripts\python.exe evals/scripts/natural_review_modes.py --review evals/local/natural-review-v1.csv --modes-report evals/local/natural-modes-result.json --output evals/local/natural-review-scoring.csv
```

最后在 `natural-review-scoring.csv` 中人工填写可用率、修正次数、事实变化及审阅者，再用汇总器统计这份表。模式对照属于开发机产品接口层，不冒充安装包桌面延迟。若独立环境没有 Python，CSV 可在测试机填写后带回开发机统计；安装版的使用本身不需要 Python。缺失记录、时间戳或环境证明时对应指标保持“未测”，不宣称发布门槛通过。
