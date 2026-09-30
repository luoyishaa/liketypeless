# 可选短句模型来源与校验

LikeTypeless 不把 SenseVoice 权重或 FunASR 便携程序打进安装包。用户在设置页明确选择准备后，后台分别从发布方固定地址下载到用户数据目录；断网时已校验的文件仍可运行。默认 Whisper 基础输入不依赖该下载。

| 组件 | 固定来源 | 本地校验 | 权利信息 |
|---|---|---|---|
| SenseVoiceSmall-GGUF q8，254,208,320 字节 | [发布方模型仓库](https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF)，修订 `90c1c61912018b70ada0fcc024ea24aca62f2e63` | SHA-256 `4ae45c94422de949b387e2e0fb10d7e14e4c42c69db30c3444ecc7d4b844b7c5` | GGUF 模型页标示 Apache-2.0 |
| Windows x64 CPU 便携运行 ZIP，4,967,457 字节 | [FunASR 发布标签](https://github.com/modelscope/FunASR/releases/tag/runtime-llamacpp-v0.2.6) | ZIP SHA-256 `f6a73a548413ba9fbaf2145263ea66ec53cbdad1fb11790dbeeee493e339492e`；提取出的 `llama-funasr-sensevoice.exe` SHA-256 `e92b69bc3b0d395dc611572566f91abcf5318ef7a54b27dcdf445bd231ded426` | [FunASR 源码许可](https://github.com/modelscope/FunASR/blob/main/LICENSE)为 MIT；许可原文随安装包保留 |

下载仅接受固定 URL、大小和 SHA-256；续传时检查 `Content-Range`，完整 ZIP 只提取指定程序，不展开其他条目。下载中断保留进度，校验失败不得变为“就绪”。运行端再次识别实际提供者及回退原因。

许可复核边界：[原始 SenseVoiceSmall 模型页](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)标示 `model-license`；[FunASR 模型协议](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE)另列模型权重的使用、署名与分享条件。这与发布方 GGUF 仓库的 Apache-2.0 元数据并不一致，不能仅凭 GGUF 标签推断原始权重已经改为 Apache-2.0。公开再分发或正式许可结论须进一步核对权利人条款；本候选版仅按用户请求从发布方下载，保留模型名称和来源，不把模型权重作为安装包内容。此记录不是法律意见。
