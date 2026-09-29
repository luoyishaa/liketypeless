# 桌面语音输入产品与评测边界

核查日期：2026-09-29。只采用项目官方仓库、官方文档和原始研究；本次未安装或实测竞品，因此下表描述公开能力，不构成准确率、速度或稳定性排名。

## 可以直接比较的产品能力

| 产品 | 桌面平台与安装 | 识别在哪里运行 | 文本整理与翻译 | 对 v1 的参考价值 |
| --- | --- | --- | --- | --- |
| Handy | Windows、macOS、Linux；提供发行安装包 | 语音识别在本机；模型需先下载 | 支持可选 AI 后处理，可接本地服务或云端供应商；本次未核实独立翻译模式，不据此断言没有 | 已实现快捷键录音、转写、向当前输入框粘贴这一基本闭环；本地识别本身不是独有优势。[官方仓库](https://github.com/cjpais/Handy)、[隐私及后处理说明](https://handy.computer/privacy) |
| VoiceInk（Beingpax/VoiceInk） | 原生 macOS，当前文档要求 macOS 15+；提供应用下载、试用和许可，也公开源码供自行构建 | 可选本地或云端转写；Intel Mac 的本地模型可靠性有限，官方建议使用云端 | 可选本地 Refine、Ollama 或云端增强；Modes 可按应用/网站切换转写、提示词及上下文；本次未核实独立翻译操作 | 可参考安装引导、模式设置和模型配置如何分开。它不是 Windows 上可直接安装的对照产品。[仓库](https://github.com/Beingpax/VoiceInk)、[安装](https://tryvoiceink.com/docs/installation)、[模型目录](https://tryvoiceink.com/docs/ai-models)、[Modes](https://tryvoiceink.com/docs/modes) |
| OpenWhispr | macOS、Windows、Linux；分别提供 DMG、EXE、AppImage/DEB/RPM 等 | 支持本地离线模型与云端模型/BYOK | 官方明确有清理后翻译并粘贴的独立快捷键，也有 AI 助手、会议和笔记功能 | 可参考跨应用粘贴与安装交付；功能覆盖较广不能推出中文转写更准或本机响应更快。[仓库](https://github.com/OpenWhispr/openwhispr)、[下载](https://openwhispr.com/download)、[翻译发布记录](https://github.com/OpenWhispr/openwhispr/blob/main/CHANGELOG.md) |

“本地识别”与“整个流程都不联网”要分开核实。例如 VoiceInk 明确区分音频转写、文本增强和词典自动学习；开启云端增强后，即使音频在本机识别，文字及启用的上下文仍可能发送给供应商。Handy 同样允许用户显式启用云端后处理。[VoiceInk 数据说明](https://tryvoiceink.com/docs/privacy-and-data)、[Handy 数据说明](https://handy.computer/privacy)

上述产品均已有成品安装入口；这足以说明它们在公开交付形态上超出了源码演示，但不能代替安装成功率和日常使用稳定性的实测。Handy 的官方 README 还列有 Linux/Wayland 热键、焦点与粘贴限制，因此不能把“支持平台”解释成“所有应用无条件可靠”。[Handy 已知限制](https://github.com/cjpais/Handy#known-issues--current-limitations)

## 哪些评测能回答哪些问题

| 证据 | 能回答 | 不能直接回答 |
| --- | --- | --- |
| Open ASR Leaderboard | 在指定语料、文本归一化与运行配置下，对比识别模型的 WER（词错误率）和 RTFx（音频时长/推理耗时）；当前覆盖英语及多语种、短音频及长音频 | 某个 Windows 应用的麦克风、热键、文本整理、跨应用粘贴和人工修正是否可靠；服务器吞吐不能直接当作用户电脑上的响应时间 |
| AISHELL-1 | 公开普通话语料上的识别误差；原论文采用 CER（字错误率）报告结果 | 任意真实口述、中英混说、专业名词、噪声或整理后的语义保真；更不是桌面成品综合分数 |
| 人机交互中的文字输入实验 | 可以把输入速度、修正行为、最终错误率和使用负担一起考察 | 某篇手机实验的结论不能直接用于当下桌面产品排名 |

Open ASR 当前仓库列出的短音频可复现评测环境为 H200，并同时存在公开与私有测试集；应保留数据集、硬件与版本条件，不引用脱离条件的“倍速”。[官方评测仓库](https://github.com/huggingface/open_asr_leaderboard)、[原始论文](https://arxiv.org/abs/2510.06961)

AISHELL-1 原论文描述了普通话语料、录音设备和划分，并用字符错误率评价基线；CER 的比较仍需一致的参考文本和归一化规则。[AISHELL-1 原论文](https://arxiv.org/html/1709.05522)

Stanford、Washington 与 Baidu 的原始手机文字输入研究记录转写后的修正行为和耗时，并同时分析输入率、错误率、主观评价等；可借鉴实验方法，但本笔记不把它的手机速度结论外推到桌面。[研究项目页](https://hci.stanford.edu/research/speech/)、[正式论文](https://faculty.washington.edu/wobbrock/pubs/ubicomp-17.pdf)

截至本次检索，**未找到同时覆盖中文识别、口语整理、停止录音后的等待、跨应用粘贴、人工修正和安装体验的通用权威桌面语音输入综合榜单**。这是检索范围内的结论，不等于证明这样的评测不存在。模型榜单和特定任务研究可作为分项证据。

## 本项目 v1 的桌面评测设计（非行业标准）

固定测试设备、麦克风、应用版本、模型及处理模式，用同一批自然口述录音作对比，至少包含普通中文、中英术语、数字/日期、人名、停顿重说和背景噪声。分别保存原始识别和整理结果，避免整理模块掩盖识别错误。

每条记录四件事：识别错了哪些字；整理是否改了原意、数字或专有名词；停止录音后多久得到可用文字；最后还要修多少才能直接使用。原始识别可计算 CER；整理输出允许合理改写，应另标遗漏、编造和关键事实变化，不强行用逐字一致作为唯一正确标准。

再用真正的麦克风与快捷键在至少三个目标输入框验证完整闭环，统计成功写入、失败恢复、粘贴错位置和用户是否能找回原文。这个小样本可证明“本机这些场景可用”，不能证明“行业领先”。若比较竞品，应同样记录模型、云端/本地设置与冷启动/热启动条件。
