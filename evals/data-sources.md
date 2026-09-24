# 数据来源与校验（2026-09-24）

只下载公开可获取的数据；大文件在 `evals/local/`，不进入 Git。下表 SHA-256 是本次实际下载文件的校验值，不是发布者承诺的全部官方校验值。复现时先校验下载文件，再运行采样脚本。社区镜像要与原发布方区分，不能据此宣称“官方逐条验证”。

| 数据 | 下载页与固定版本 | 本次文件 SHA-256 | 说明 |
|---|---|---|---|
| AISHELL-1 | [OpenSLR 官方](https://www.openslr.org/33/)；[测试集社区镜像](https://huggingface.co/datasets/TwinkStart/AISHELL-1/tree/2a509ef3a7a88d3234205eaeecba39fdd9d50518/data) | shard 0 `09f19facaad4f8847244eca7034beb5fab7dfa4aaae9c6021f9b14a276fa6f06`；shard 1 `2bfee721098cc0b525a7d5d56c9e033916eaf5968088c13ecf459babc705c6e0`；shard 2 `3ab41a9c876f83b34d1bb936fd7dcc3cf4c1d4b30f7fbe5908540fe46181d696` | 原语料 Apache-2.0；社区镜像标记为 test，未与 OpenSLR 全量压缩包逐字节比对 |
| Common Voice 21 zh-CN | [Mozilla Common Voice](https://commonvoice.mozilla.org/zh-CN/datasets)；[2025-03-14 社区镜像](https://huggingface.co/datasets/keeve101/common-voice-21.0-2025-03-14-zh-CN-split/tree/03ef725ccccbe73aa1a23972ff8b85f0bc7cb97f/data) | `22ccad29fbb33e8263171c24d6c980e17e7cca68abea1bf70d5a296add3e8ff` | Common Voice 语音按 CC0 发布；该镜像 README 为空，test 分区归属未与 Mozilla 原包独立核对，应视为次级来源 |
| FLEURS cmn_hans_cn | [Google 数据集](https://huggingface.co/datasets/google/fleurs/tree/70bb2e84b976b7e960aa89f1c648e09c59f894dd/data/cmn_hans_cn) | `test.tar.gz`: `09d19ad18f5d7e91076880807e866cd16abd924c7052b55f71cdae91714fc166`；`test.tsv`: `5734461648f816181d7dab5fc79204b18c4b9bc2cd5138225b25c72d18385d21` | CC BY 4.0；直接从发布仓库获取，test 共 945 条 |
| AISHELL-4 test | [OpenSLR 官方说明](https://www.openslr.org/111/)；[AISHELL 发布账号单文件仓库](https://huggingface.co/datasets/AISHELL/AISHELL-4/tree/aada72727856313b19d4a030383c426364931dbf/test) | L/M/S FLAC: `93125b2c8f9f73c042ccd63178d1fec6db2d3047af4078834da7c6c1aa118e72` / `26b4cd2045077e3db7170c376db3cb63b469d208e1d474155721911b3fe9866a` / `e4a8a76315b7dabe63f43e2364486d9dee989ddcf111d73dc3eae47d86838cd0`；同名 TextGrid: `a7e060c87f76f6ad51ca1bcd6ae7243942757f25bdcbfc9a628c552d03dcbc4c` / `35eaaab7f13e594393adacdabbacac5779e2850992277d72fbcfd12320c5782` / `fe1ac420affae1e377e1a254c72c992b560ea02d3a5d3c7e22b89f5faacf283b` | 原始 OpenSLR 页面标 CC BY-SA 4.0；HF 页面许可标签不同，按更严格的原始条款处理；只取大/中/小房间各一场，不声称覆盖完整 test |
| FLORES-200 | [Meta FLORES-200](https://github.com/facebookresearch/flores/tree/main/flores200)；[原始归档](https://dl.fbaipublicfiles.com/nllb/flores200_dataset.tar.gz) | `b8b0b76783024b85797e5cc75064eb83fc5288b41e9654dabc7be6ae944011f6` | CC BY-SA 4.0；使用公开 devtest 中英逐行对齐的 100 条，隐藏 test 不可用 |
| WenetSpeech | [官方仓库](https://github.com/wenet-e2e/WenetSpeech) | 未下载 | test_net/test_meeting 需按官方流程申请下载权限；当前只能测试导入器，不纳入数值基线 |

下载路径及对应文件名：

- `evals/local/aishell1/test-00000-of-00003.parquet` 至 `test-00002-of-00003.parquet`；从上表社区镜像同名 `data/` 文件取得。
- `evals/local/common-voice-21/test-00000-of-00001.parquet`；从上表镜像 `data/` 取得。
- `evals/local/fleurs/test.tar.gz`、`test.tsv`；均为上表 Google 仓库 `data/cmn_hans_cn/audio/test.tar.gz` 及 `data/cmn_hans_cn/test.tsv`。将归档解到 `evals/local/fleurs/`，得到 `test/` WAV。
- `evals/local/aishell4/test/wav/` 与 `test/TextGrid/`：上表仓库的 `L_R003S01C02`、`M_R003S01C01`、`S_R003S01C01` 同名音频/标注，各 1 个。
- `evals/local/flores200/flores200_dataset.tar.gz`；仅提取 `flores200_dataset/devtest/zho_Hans.devtest` 与 `eng_Latn.devtest`。

Mozilla 2025 年之后的版本改由 Mozilla Data Collective 发布；若日后获得其正式包，应单独建立新的版本报告，不能默默替换此处的 21.0 社区镜像。数据许可证、平台条款和再分发规则分别遵守；本仓库只保存衍生指标和少量人工编写的回归用例。
