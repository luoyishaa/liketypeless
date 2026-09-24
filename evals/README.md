# liketypeless 评测集

这里的评测分为两部分：公开 ASR 语料评测，以及产品输出评测。

## 目录

- `manifests/`：AISHELL-1、Common Voice、WenetSpeech 的本地采样清单格式。
- `fixtures/`：可提交的小型脱敏样例，供 CI 验证指标逻辑。
- `predictions/`：模型输出，按 `id` 对应样例。
- `reports/`：可比较的指标基线。
- `review/`：人工审阅表与标注规则。
- `scripts/`：标准库 Python 脚本；不依赖网络或模型。

## 数据格式

每行都是 JSON：

```json
{"id":"aishell-test-0001","audio_path":"D:/datasets/aishell/test/S0001.wav","reference":"今天天气很好","source":"aishell-1","split":"test","tags":["read"]}
```

预测文件至少包含 `id`、`asr_text` 和 `end_to_end_ms`。如需评估整理与翻译，再增加 `structured_text`、`source_text`、`protected_terms`、`translation`、`translation_reference`。

## 本地运行

先复制 `manifests/dataset-roots.example.json` 为 `dataset-roots.json`，填写本机数据集目录，再按官方切分生成或编辑 JSONL 清单。不要提交下载的音频、原始数据集或 `dataset-roots.json`。

```powershell
python evals/scripts/evaluate.py --manifest evals/fixtures/manifest.jsonl --predictions evals/predictions/baseline.jsonl --output evals/reports/latest.json
python evals/scripts/compare_baseline.py --baseline evals/reports/baseline.json --candidate evals/reports/latest.json
```

`evaluate.py` 计算中文 CER、端到端 P50/P95、整理安全红线和翻译精确匹配/人工审阅覆盖率。真实模型评测应把同一份 manifest 跑过候选配置后再写入 predictions。

## 公开语料的使用边界

- AISHELL-1：使用官方 `test` 切分作为普通话基准。
- Common Voice：按 speaker 去重后抽样 validated/test，单独标记朗读与自由口语。
- WenetSpeech：使用官方评测切分，单独统计新闻、会议和长音频。

请遵守各数据集的许可证、下载条款与禁止再分发要求。仓库只保存清单、衍生指标和必要的脱敏 fixture。
