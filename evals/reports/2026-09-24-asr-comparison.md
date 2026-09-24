# ASR 候选对照与下一步决策

## 结论

暂不切换默认 ASR，也不将 beam 从 1 提高到 5。SenseVoice 在朗读、会议和短句上明显优于当前 Whisper small 配置，但现有产品路径在长录音上退步；beam=5 的局部改善也伴随短句退步。它们不是可以无条件替换默认配置的候选。

本轮完成 3 个配置 × 4 个分层 × 3 轮真实推理，共 7,740 次计分转写，另有暖机。不把三次重复当成三倍的独立样本。代码、数据、模型哈希与设备说明见 [诊断报告](2026-09-24-diagnostic-findings.md) 和 [环境记录](2026-09-24-runtime-provenance.json)。

## 三轮结果

每格为 **CER / P95 毫秒**，分别取三轮指标的中位数；不是将所有耗时混在一起后重新计算分位数。越低越好。Whisper 使用 CUDA float16，SenseVoice 是现有 CPU 工作进程，不能当作同硬件算法速度排名。

| 分层 | 样本 | Whisper small beam=1 | Whisper small beam=5 | SenseVoice small CPU |
|---|---:|---:|---:|---:|
| 公开朗读 | 600 | 13.861% / 287.5 | 13.084% / 304.6 | 7.530% / 660.2 |
| 远场会议片段 | 150 | 36.967% / 399.3 | 35.045% / 326.2 | 12.264% / 466.8 |
| 1–4 字短句 | 100 | 57.143% / 269.5 | 60.058% / 242.5 | 32.653% / 210.8 |
| 人工拼接长录音 | 10 | 13.975% / 5473.5 | 13.688% / 7930.0 | 30.240% / 8707.0 |

基于 CTranslate2 4.6.0 的八个 Whisper 实验均在完整写完报告后异常退出（`0xC0000409`）；四个 SenseVoice 实验正常退出。表中完整预测可以用于质量诊断，但 Whisper 的原环境不能因此标为稳定性通过。每个比较 JSON 都保留进程退出状态。

各轮数值、范围、首轮配对改善/退步与按来源分解见：

- beam=5：[朗读](asr-beam5-read.json)、[会议](asr-beam5-meeting.json)、[短句](asr-beam5-short.json)、[长录音](asr-beam5-longform.json)。
- SenseVoice：[朗读](asr-sensevoice-read.json)、[会议](asr-sensevoice-meeting.json)、[短句](asr-sensevoice-short.json)、[长录音](asr-sensevoice-longform.json)。

首轮的配对分析中，SenseVoice 在短句集改善 50 条、退步 9 条，CER 差值为 -24.49 个百分点；按 96 位说话人聚类的 95% bootstrap 区间为 [-33.52, -16.36] 个百分点。beam=5 在短句集的差值区间为 [-1.43, +7.62] 个百分点，跨过零，不能声称其短句退步已具有统计显著性，但也没有切换它的短句质量证据。

会议只有三场，FLEURS 没有可靠的说话人 ID，人工拼接音频也不是自然口述；这些分层及含 FLEURS 的总分不提供说话人置信区间。速度受本机负载、模型驻留状态影响，三轮范围仅描述这次本地重复测量。

## 运行时与声道对照

这部分另做了 5 个分层 × 3 轮，共 3,030 次计分转写。模型文件、beam=1 与产品代码不变，运行时从当前 Anaconda 基础的 Python 3.12.4 / CTranslate2 4.6.0，换成独立 CPython 3.12.13 / CTranslate2 4.8.2。NumPy 仍为 1.26.4，其他应用包复用原 site-packages；只对实验进程设置导入路径，未替换主环境。

| 运行组合 | 实测结果 |
|---|---|
| 主环境 Python 3.12.4 + CT2 4.6.0 | 原八个 Whisper 实验完整计分后均异常退出 `0xC0000409` |
| 主环境 Python 3.12.4 + 隔离 CT2 4.8.2 | 暖机加载模型时访问冲突 `0xC0000005`；CPU 加载也复现，不能只归因于 CUDA |
| 主环境 Python 3.12.4 + 隔离 CT2 4.7.2 | 最小 CPU 加载探针也出现访问冲突 |
| 独立 Python 3.12.13 + 隔离 CT2 4.8.2 | 相同模型可加载；朗读、会议、短句、长录音、固定声道五个实验均完成三轮，全部退出码为 0 |

上游 [4.7.2 发布说明](https://github.com/OpenNMT/CTranslate2/blob/master/CHANGELOG.md)包含 GPU 随机状态释放修复，但这里同时改变了 Python 基础运行时与 CT2，不能把本机成功唯一归因于该补丁，也没有定位主环境加载崩溃的具体原生函数。因此不直接更新应用依赖锁定，更不通过强制成功退出掩盖错误。迁移主环境需要单独验证启动、GPU/CPU 回退、录音和完整输入链路。

新运行组合的 CER 中位数分别为朗读 13.886%、会议 37.177%、短句 58.017%、长录音 14.003%，不是识别质量提升。对应的完整比较为 [朗读](asr-runtime-read.json)、[会议](asr-runtime-meeting.json)、[短句](asr-runtime-short.json)、[长录音](asr-runtime-longform.json)。

在同一新运行组合下，只将会议音频的默认混音改成固定第 0 声道，CER 中位数由 37.177% 降至 35.395%。只预先选择第 0 声道，没有遍历后挑最好的一路；参考、片段及 ID 完全不变。这说明预处理值得核对，但仍有大量错误，也不足以证明一个通道对其他会议更优。见 [声道比较](asr-meeting-channel0.json)。

复现时使用独立解释器和全新输出目录；不要直接覆盖当前应用环境：

```powershell
# 先用 uv 安装/定位独立 CPython 3.12.13；主环境依赖及语料须已就绪。
uv python install 3.12.13
$evalPython = uv python find 3.12.13
.venv\Scripts\python.exe -m pip install --no-deps --target evals/local/ct482 ctranslate2==4.8.2
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = "$(Resolve-Path evals/local/ct482);$(Resolve-Path .venv/Lib/site-packages)"
    & $evalPython evals/scripts/run_asr_matrix.py --suite read=evals/local/public-asr-manifest.jsonl --suite meeting=evals/local/aishell4/prepared-single-speaker.jsonl --suite short=evals/local/short/prepared.jsonl --suite longform=evals/local/longform-manifest.jsonl --profiles whisper-small-beam1 --repeats 3 --output-dir evals/local/runtime-reproduction
} finally {
    $env:PYTHONPATH = $previousPythonPath
}
```

声道清单可通过 `prepare_audio.py --manifest evals/local/aishell4/manifest-single-speaker.jsonl --output evals/local/aishell4/prepared-channel0.jsonl --cache evals/local/aishell4/pcm16-channel0 --channel 0` 重建，再以独立 suite 跑三轮。比较时必须显式传 `--candidate-manifest`，工具会要求 ID 和参考完全一致，并将其标为音频预处理比较，不能混作同音频模型对照。

## 优化方向

1. **SenseVoice 长录音处理**：现有工作进程直接把整段音频交给模型，而 Whisper 已有长录音分块。先为 SenseVoice 做独立分块候选，对同一长录音及短音频回归，再判断是否能作为中文优先配置；目前的观察只是方向，不是已证实根因。
2. **短句和关键事实**：即便当前较好的候选，短句 CER 仍有 32.65%。优先听辨同音词、姓名和参考标注问题，不能靠提高 beam 或归一化数字把分数修好看。
3. **翻译忠实度**：32 条风险文字发现日期误译；追加 8 条日期关联回归又有 2 条把“后天”译成“明天”。这是明确的语义风险。保留失败用例，改进时同时跑 FLORES 和高风险文字，不接受只修一个句子的硬编码替换。

本轮没有改变默认模型、提示词或应用主环境的依赖。另行补齐了缺失的 SenseVoice Python 运行时，并把待测 CTranslate2 安装在忽略的评测目录中。真人审阅尚未完成，不能称为正式产品验收或官方榜单复现。
