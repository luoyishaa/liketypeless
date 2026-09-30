# v1 工程保留集（2026-09-30 冻结）

本保留集只用于相同音频、相同机器上的产品版本配对比较，不是 AISHELL-1 官方 test 榜单分数。音频来自 [AISHELL 发布方仓库](https://huggingface.co/datasets/AISHELL/AISHELL-1) 的 `train` 切分，固定仓库版本 `bbe295d530192a4cd41644b711c9aecd087df653`；原语料在 [OpenSLR SLR33](https://www.openslr.org/33/) 标注 Apache-2.0。原始音频、参考文本和逐条预测保留在忽略的 `evals/local/`，不提交仓库。没有使用 WenetSpeech 未授权测试集或 Common Voice 社区镜像来构造新的保留集。

| 层 | 样本 | 说话人 | 限定 | 便携清单 SHA-256 | 首轮发布环境产品接口 Whisper small 原始 CER |
|---|---:|---:|---|---|---:|
| 朗读 | 300 | 10（S0002–S0011） | 发布方 train 切分、与旧集及短句层按说话人隔离 | `8bd29d9f203779abe38a3a9d7edac197ac2ddb99ed8d33e752c0faa7800a5360` | 14.2691% |
| 短句 | 100 | 11（S0012–S0022） | 规范化参考长度 1–8 字；与旧集及朗读层隔离 | `3ce4571842c56a2b074fe08b62ef9e16aa3ecaee1804b1b0f92769e3a2bf8767` | 19.7143% |

两层均按 ID、原始音频 SHA-256 和同一语料的说话人排除已用样本；`build_holdout.py` 在缺失说话人或音频指纹时拒绝生成。锁定记录分别为 `holdout-read-aishell1-official.lock.json` 和 `holdout-short-aishell1-official.lock.json`。短句集与旧 Common Voice 1–4 字诊断集分布不同，两个 CER **不能**直接相减为优化效果。真正的提升只在本清单上成对测量同一版本的 Whisper 与候选识别器。

## 复现材料

使用 `hf download AISHELL/AISHELL-1` 固定上述版本，取转写文件和 S0002 至 S0022 各说话人的 `data_aishell/wav/Sxxxx.tar.gz`。发布方原始包逐个校验后解压至 `data_aishell/wav/train/Sxxxx/`。`make_manifest.py` 以 `--aishell-split train` 和重复的 `--aishell-speaker` 参数限定说话人：朗读用 S0002–S0011、`--aishell-count 300`；短句用 S0012–S0022、`--aishell-count 100 --aishell-max-reference-chars 8`。随后依次运行 `prepare_audio.py`（16 kHz 单声道 PCM16）和 `build_holdout.py`，以旧 `public-asr-manifest.jsonl`、旧短句清单及已锁定朗读清单为 `--exclude`，生成最终清单。发布方仓库的 `hf cache verify` 已校验本次下载的转写文件与说话人包；复现者仍须核对各自下载结果。

基线经认证的产品 `/stt/transcribe` 路径执行，使用锁定的 Python 3.12.13 发布环境及同一份已校验 Whisper small 模型，尚非 PyInstaller 封装的后台进程；beam=1、实际 CUDA float16。朗读请求 P50/P95 为 143.102/204.060 ms，首次请求 8129.648 ms；短句为 109.176/140.036 ms，首次请求 5178.956 ms。这些数不含麦克风采集、整理、焦点检查和粘贴；冷启动与暖机分列。基线逐条结果保存在本机 `evals/local/holdout-{read,short}-whisper-baseline.json`，安装版将在封装后另测。
