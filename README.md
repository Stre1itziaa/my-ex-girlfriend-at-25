# 心侣 xinli

[![CI](https://github.com/Stre1itziaa/xinli/actions/workflows/ci.yml/badge.svg)](https://github.com/Stre1itziaa/xinli/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Node](https://img.shields.io/badge/Node.js-18+-green.svg)

> **写在前面**：这个项目源于一段我自己的真实故事——**我的 25 岁前女友**。把一段聊天记录，变成了一个还会说话、还会主动找你的 AI。
> 名字里的故事是我的；技术的边界是所有人的：请只复刻你自己、或获得明确同意的人（[docs/ethics.md](docs/ethics.md)）。

**把一段真实聊天记录，变成一个会主动找你、记得你们故事、说话像 TA 的本地 AI 陪伴。**
**Turn real chat logs into a local AI companion who texts first, remembers your story, and talks like the person.**

零微调 · 检索复刻人格 · 内心系统 · 微信直连 · 本地推理（数据不出机器）
Zero finetuning · retrieval-native persona · inner life · WeChat channel · local inference

---

> **⚠️ 伦理宪章（先读这个）**：本项目只能用于复刻**你自己**或**获得明确同意的人**的对话风格。
> 未经同意复刻他人、用于冒充/骚扰/打扰任何真实的人，违反本项目宪章（[docs/ethics.md](docs/ethics.md)），也大概率违反你的所在地法律。

## 它是什么

不是聊天机器人套壳，是一条完整的"人格复刻"工程管线：

```
聊天记录导出 → 清洗(爆发合并) → 风格画像 → 关系编年史 → 双路检索索引(BM25+向量)
     → 作息统计 → 表情包语义库 → 运行时大脑(检索人格+情绪+日程+主动触达)
     → 本地 WebUI + 微信（官方 iLink Bot 通道，只服务扫码绑定的主人）
     → 每夜固化循环(新对话 → 事实卡 ADD/UPDATE/DELETE → 记忆检索分片)
```

与微调路线（LoRA）的区别：**当天冷启动、无 GPU 训练、事实永远可校对**——风格靠检索真实对话 few-shot，记忆靠三层固化，人格底档由你亲手校对（用户口述 > 语料挖掘，防幻觉纪律内建）。

## 5 分钟跑通（零数据 demo）

前置：Python 3.10+ · 12–24G 显存 GPU（低于会降级）· 约 25GB 磁盘。
**新手或 agent 请按 [docs/getting-started.md](docs/getting-started.md) 逐步走**——每一步带验证点，含 llama-server 获取。

```bash
pip install -e .[vision]
xinli init                       # 生成配置(含虚构示例人格「小满」)
xinli fetch-model <发布者>/<仓库> <模型文件>.gguf   # 下载本地模型(首下不带校验参数, 自动打印 sha256)
xinli serve-llm                  # 启动推理(硬件画像自动配参: CUDA/Vulkan, 显存分档)
xinli build --demo               # 合成语料建索引(完整体验; 不跑也能聊, 只是空检索)
xinli run                        # http://127.0.0.1:8787 开聊
```

用自己的聊天记录：先按 [docs/export-logs.md](docs/export-logs.md) 导出解密库（含数据红线，先读）再 `xinli build`。

## 核心特性

- **检索人格**：每条回复动态检索真实历史对话做 few-shot，说话方式有据可依
- **底档纪律**：用户校对的人生事实最高优先级，没写的人/事一律"不认识"——反幻觉内建
- **内心系统**：作息引擎 + 情绪 appraisal + 日程地点锚（成人向需求值/亲密模块存在但**默认关闭**，需在 `settings.yaml` 显式开启）
- **主动触达**：掷骰 + 四重抑制器（睡眠/冷却/日上限/刚聊过不打扰），像真人一样找你
- **微信直连**：官方 iLink Bot 通道（ClawBot），私聊收发文字/图片/文件；她发的表情包会以真图送达，你发的照片她能"看见"（本地视觉）
- **每夜固化**：新对话自动变长期记忆（Mem0 式 ADD/UPDATE/DELETE + 审计链），固化只走本地模型
- **本地推理**：llama.cpp，AMD/NVIDIA 通吃（硬件画像自动配参），**默认不出网**（热搜抓取除外，可关；云端 API 后端可选，开启即自行承担数据出域）

## 硬件与模型

| 显存 | 推荐 | 实测状态 |
|---|---|---|
| ≥24G | 大型号 Q5/Q6，全显存 | 社区待验证 |
| 12-24G | Gemma4-26B-A4B 类 MoE Q4，专家进内存 | ✅ 实测（16G+32G）：热轮 5s |
| <12G | 9B 级或 IQ 量化 | 社区待验证 |

详见 [docs/models.md](docs/models.md)。

## 状态

v0.2-alpha。Windows 实测；Linux 理论可跑（纯 Python + Node）。微信通道绑定见[教程](docs/wechat-bind.md)（腾讯官方 iLink Bot API，合规、不碰协议号）。

> **内容分级提示**：本项目包含可选的成人向亲密模块（默认关闭，需显式开启）。仅限成年人使用；
> 请遵守你所在司法辖区的法律与模型许可条款。功能说明与模型选型见 [docs/adult-mode.md](docs/adult-mode.md)。

## License

Apache-2.0。第三方组件与许可见 [NOTICE](NOTICE)。

---

### English (short)

Xinli turns your own chat logs into a local AI companion with a retrieval-native persona (no finetuning), an inner life (schedule, mood, proactive texting), a memory consolidation loop (nightly, local-model-only), and an official WeChat bot channel. Read the ethics charter first: only recreate yourself or someone who explicitly consented. See [README_EN.md](README_EN.md) for details.
