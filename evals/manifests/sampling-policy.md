# 公开语料抽样规则

`make_manifest.py`、`extract_parquet_corpus.py`、`make_translation_manifest.py` 使用固定 SHA-256 排序种子 `20260924`。所有选择只来自官方 test，或 FLORES-200 的公开 devtest，不混入 train。相同文件及脚本版本会选出相同 ID；`prepare_audio.py` 在清单中记录原始和 16 kHz PCM16 音频 SHA-256，报告用不含本机路径的 manifest 哈希核对样本。

| 来源 | 当前目标 | 说话人规则 | 场景 |
|---|---:|---|---|
| AISHELL-1 test | 300 | 20 个 test 说话人，每人至多 15 条 | 干净朗读 |
| Common Voice 21 zh-CN test | 150 | 每位说话人至多 3 条 | 众包朗读 |
| FLEURS cmn_hans_cn test | 150 | 每位说话人至多 3 条 | 多领域朗读 |
| AISHELL-4 test | 150 | 大/中/小房间各一场；剔除与其他说话人重叠超过 0.1 秒的片段 | 远场会议诊断，单独报告 |
| WenetSpeech test_net/test_meeting | 待授权 | 两类分别抽样、单独报告 | 网络/会议语音 |

这些公开测试集还不能充分代表实时口语、重叠发言、远场噪声或长篇录音。不能将 WenetSpeech 未授权测试集或 Common Voice spontaneous 的单条无验证录音凑入当前基线。新增场景须新建独立分层，不能悄悄改变既有样本集。
