# 可复现评测

本目录把产品的三个能力分开测量：中文语音识别、保守整理、中译英。`reports/` 中的数值来自真实推理；`fixtures/` 是人工编写的回归用例，不是公开语音集，也不能代替真人审阅。

## 当前数据与边界

| 测试集 | 本地抽样 | 来源与作用 |
|---|---:|---|
| AISHELL-1 test | 300 | 官方测试切分的社区 Parquet 镜像；干净朗读普通话 |
| Common Voice 21 zh-CN test | 150 | 社区镜像；不同说话人及设备的朗读普通话 |
| FLEURS cmn_hans_cn test | 150 | Google 发布的测试集；跨领域朗读普通话 |
| AISHELL-4 test | 150 | 官方仓库三个会议录音；剔除明显重叠的片段，单独作为远场会议诊断 |
| FLORES-200 zho_Hans→eng_Latn devtest | 100 | Meta 发布的平行句；中英翻译 |
| WenetSpeech test_net/test_meeting | 0 | 解析器已就绪，但官方评测数据需要申请，未授权时不纳入报告 |

完整来源、许可证、下载链接及本次归档校验值见 [data-sources.md](data-sources.md)。不提交原始音频、Parquet、逐条参考译文或本机绝对路径；这些材料保存在忽略的 `evals/local/`。仓库中的报告保存样本与预测哈希、样本数和指标，既可核对来源，也避免误把 CI 的 28 条文字用例当成 ASR 基线。

## 指标定义

- CER = 全部样本的编辑距离总和 / 参考字数总和。计算前做 NFKC、大小写折叠，并去除空白和 Unicode 标点；保留数字及英文字母。不是逐句 CER 的简单平均。
- 延迟 P50/P95 为每条录音处理耗时的最近秩分位数。语音评测中的 `end_to_end_ms` 从本地文件交给产品 ASR 到返回结果；不包含录音时长、转换、快捷键、粘贴或 UI。翻译报告则从文本交给产品翻译服务到返回结果。不能把这两个数当作完整用户交互延迟。
- RTF = 所有 ASR 耗时之和 / 音频总时长。按数据源及 `<10s`、`10–30s`、`≥30s` 分组；冷启动会影响首次样本，请同时查看 P95 与模型/硬件说明。
- 整理安全红线：每条标注的保护词必须存在，禁止短语不得出现。报告给出保护词召回率及自动违规率；这只是可自动检查的下界，不保证语义忠实。含否定、数字、时间、姓名、条件、列表的语义变化需要真人审阅。
- 翻译用 sacreBLEU 的语料级 chrF++（word_order=2）。它衡量与参考译文的表面相似度，不能单独判定事实是否完整；人工忠实度与自然度分开打分。

空指标一律为 `null`，绝不将缺失预测或推理异常按满分处理。比较脚本要求相同的 manifest 哈希、样本数和来源，并显示绝对与相对变化。自动安全违规率比基线升高时失败。

## 复现

先安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r evals/requirements-data.txt
```

将 [data-sources.md](data-sources.md) 中的下载文件置于 `evals/local/`。`extract_parquet_corpus.py` 负责社区镜像中已嵌入的音频；`make_manifest.py` 也支持 AISHELL-1 原始目录、Common Voice 原始 `test.tsv`/`clips` 和 WenetSpeech 原始 JSON。原始数据的分区不得混用。以下为本次 600 条语音抽样的主要步骤：

```powershell
python evals/scripts/extract_parquet_corpus.py --corpus aishell-1 --shards evals/local/aishell1/test-00000-of-00003.parquet evals/local/aishell1/test-00001-of-00003.parquet evals/local/aishell1/test-00002-of-00003.parquet --count 300 --output evals/local/aishell1/manifest.jsonl --audio-dir evals/local/aishell1/audio
python evals/scripts/extract_parquet_corpus.py --corpus common-voice-zh-cn --shards evals/local/common-voice-21/test-00000-of-00001.parquet --count 150 --output evals/local/common-voice-21/manifest.jsonl --audio-dir evals/local/common-voice-21/audio
python evals/scripts/make_manifest.py --fleurs-root evals/local/fleurs --fleurs-count 150 --output evals/local/fleurs/manifest.jsonl
```

对各 manifest 用 `prepare_audio.py --manifest ... --output ... --cache ...` 转成 16 kHz 单声道 PCM16 WAV，再用 `make_manifest.py --include-manifest ... --output evals/local/public-asr-manifest.jsonl` 合并。运行产品真实 ASR，并按同一份 manifest 出报告：

```powershell
python evals/scripts/run_pipeline.py --manifest evals/local/public-asr-manifest.jsonl --output evals/local/public-asr-predictions.jsonl
python evals/scripts/evaluate.py --manifest evals/local/public-asr-manifest.jsonl --predictions evals/local/public-asr-predictions.jsonl --output evals/reports/public-asr-baseline.json
```

会议语音不混入上面的朗读均值。下载 AISHELL-4 官方仓库的三段 `test/wav/*.flac` 与同名 `test/TextGrid/*.TextGrid` 后，用 `make_aishell4_manifest.py --root evals/local/aishell4 --count 150` 生成不含明显说话人重叠的片段，再走统一转换/推理/出报告流程。即便剔除重叠，它仍是远场会议语音，不能直接和朗读 CER 比为同等难度。

`make_longform.py` 从 FLEURS test 的不重复样本拼成 10 条超过 90 秒的控制组，用来暴露分块与解码遗漏。它是真实语音片段的人工拼接，不是自然长篇口述；[长录音前后对照](reports/constructed-longform-fixed.json)仅用于检验长音频路径，不并入公开语料总 CER。

翻译用 `make_translation_manifest.py --root evals/local/flores200 --count 100` 生成对齐的 devtest 清单，再用 `run_translation.py --manifest ... --output ...` 与 `evaluate.py`。`run_translation.py` 每条落盘，可中断后续跑；先保证 Ollama 中已安装配置的模型。FLORES 的隐藏 test 不在这里使用。

人工审阅流程是 `make_review_sheet.py` 生成含原文、预测、保护词的 CSV；两位审阅者独立填写 `reviewer` 及适用项；分歧由第三位以 `reviewer=adjudicator` 裁决；`merge_reviews.py` 合并后重新出报告。没有真实审阅者时保持 `human_reviewed=0`，不可由模型自评冒充。

## CI 与版本门槛

CI 每次运行产品真实的离线保守整理规则，比较固定 28 条回归用例；修改模型、提示词或核心推理文件时，还要求在该变更中更新同一份公开 manifest 的候选报告，并与基线逐项比较。GitHub Runner 不下载数 GB 数据，也不假装运行本机 Ollama；真实语音及翻译报告由本地跑完后作为可审查证据提交。候选结果若缺失、样本不一致、自动整理安全率恶化，检查失败。
