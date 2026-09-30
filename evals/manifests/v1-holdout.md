# v1 工程保留集（2026-09-30 冻结）

本保留集只用于相同音频、相同机器上的产品版本配对比较，不是 AISHELL-1 官方 test 榜单分数。音频来自 [AISHELL 发布方仓库](https://huggingface.co/datasets/AISHELL/AISHELL-1) 的 `train` 切分，固定仓库版本 `bbe295d530192a4cd41644b711c9aecd087df653`；原语料在 [OpenSLR SLR33](https://www.openslr.org/33/) 标注 Apache-2.0。原始音频、参考文本和逐条预测保留在忽略的 `evals/local/`，不提交仓库。没有使用 WenetSpeech 未授权测试集或 Common Voice 社区镜像来构造新的保留集。

| 层 | 样本 | 说话人 | 限定 | 便携清单 SHA-256 | 首轮发布环境产品接口 Whisper small 原始 CER |
|---|---:|---:|---|---|---:|
| 朗读 | 300 | 10（S0002–S0011） | 发布方 train 切分、与旧集及短句层按说话人隔离 | `8bd29d9f203779abe38a3a9d7edac197ac2ddb99ed8d33e752c0faa7800a5360` | 14.2691% |
| 短句 v2 | 100 | 11（S0012–S0022） | 规范化参考长度 1–8 字；与旧集及朗读层隔离 | `4e0c95cac242bfcdfc2198d1b79d5605b5e27229aef004fd8036c9fd09009b96` | 19.8571% |

两层均按 ID、原始音频 SHA-256 和同一语料的说话人排除已用样本；`build_holdout.py` 在缺失说话人或音频指纹时拒绝生成。锁定记录分别为 `holdout-read-aishell1-official.lock.json` 和 `holdout-short-aishell1-official-v2.lock.json`。第一版短句清单中的一段音频曾用于便携程序启动检查；为避免已检查样本进入最终比较，v2 明确剔除该 ID 并补足 100 条，第一版锁和结果保留作审计而不用于优化收益。短句集与旧 Common Voice 1–4 字诊断集分布不同，两个 CER **不能**直接相减为优化效果。真正的提升只在本清单上成对测量同一版本的 Whisper 与候选识别器。

## 复现材料

使用 `hf download AISHELL/AISHELL-1` 固定上述版本，取转写文件和 S0002 至 S0022 各说话人的 `data_aishell/wav/Sxxxx.tar.gz`。发布方原始包逐个校验后解压至 `data_aishell/wav/train/Sxxxx/`。`make_manifest.py` 以 `--aishell-split train` 和重复的 `--aishell-speaker` 参数限定说话人：朗读用 S0002–S0011、`--aishell-count 300`；短句 v2 用 S0012–S0022、`--aishell-count 105 --aishell-max-reference-chars 8`。随后依次运行 `prepare_audio.py`（16 kHz 单声道 PCM16）和 `build_holdout.py`，以旧 `public-asr-manifest.jsonl`、旧短句清单及已锁定朗读清单为 `--exclude`，v2 另加 `--exclude-id aishell-1:BAC009S0012W0228`，取 100 条生成最终清单。发布方仓库的 `hf cache verify` 已校验本次下载的转写文件与说话人包；复现者仍须核对各自下载结果。

基线经认证的产品 `/stt/transcribe` 路径执行，使用锁定的 Python 3.12.13 发布环境及同一份已校验 Whisper small 模型，尚非 PyInstaller 封装的后台进程；beam=1、实际 CUDA float16。朗读请求 P50/P95 为 143.102/204.060 ms，首次请求 8129.648 ms；短句 v2 为 136.006/163.579 ms，首次请求 10622.833 ms。这些数不含麦克风采集、整理、焦点检查和粘贴；冷启动与暖机分列。基线逐条结果保存在本机 `evals/local/holdout-read-whisper-baseline.json` 与 `evals/local/holdout-short-v2-whisper-baseline.json`，安装版将在封装后另测。
