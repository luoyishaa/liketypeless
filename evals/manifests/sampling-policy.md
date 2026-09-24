# 公开语料采样规则

每次基线评测固定随机种子 `20260924`，按 manifest 的 `id` 排序后抽样；同一评测版本不得更换样本。

| 来源 | 首版数量 | 切分与规则 | 目的 |
|---|---:|---|---|
| AISHELL-1 | 300 | 官方 test；按说话人分层 | 干净普通话 CER 基线 |
| Common Voice zh-CN | 150 | validated/test；一个说话人最多 3 条 | 麦克风、口音和说话人泛化 |
| Common Voice spontaneous zh-CN | 100 | 官方自由口语评测切分 | 非朗读口语 |
| WenetSpeech | 150 | 官方 test_net/test_meeting；每类至少 50 条 | 长句、新闻与会议 |

不把任何来源的训练切分混入评测。长音频另写 `duration_seconds`，按 `0-10s`、`10-30s`、`30s+` 分桶报告 CER 与延迟。
