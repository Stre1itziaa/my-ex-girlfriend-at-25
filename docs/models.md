# 模型推荐与实测

> 以下"实测"数据来自作者的参考机：16G VRAM + 32G RAM，llama.cpp Vulkan。
> 其他档位标注"社区待验证"——欢迎 issue 反馈实测数据，我们会更新表格。

## 显存分档推荐（角色扮演/陪伴用途）

| 显存 | 推荐 | 状态 | 备注 |
|---|---|---|---|
| ≥24G | 26B 级 Q5/Q6 全显存，或 70B IQ3 | 社区待验证 | 无需 -ot 分层 |
| 12-24G | **Gemma4-26B-A4B 类 MoE Q4_K_M**（~17GB） | ✅ 实测 | `exps=CPU` 专家进内存 |
| 8-12G | 9B 级 dense 或 12B MoE IQ4 | 社区待验证 | |
| <8G | 4B 级 + 严格的上下文预算 | 社区待验证 | 体验会明显降级 |

## 从零获取模型（完整步骤）

`my-ex-girlfriend-at-25 fetch-model <发布者>/<模型仓库> <模型文件>.gguf` 的四个信息这样拿：

1. **选型号**：按上表确定档位（如 12–24G → 26B 级 MoE Q4_K_M）。
2. **找仓库**：在 <https://hf-mirror.com>（国内，免登录）或 <https://huggingface.co>（海外）
   搜索模型名；Gemma 系官方权重在 huggingface.co 需先点同意 Google 许可条款（hf-mirror 无此门槛）。
   量化发布者的仓库页会列出 `.gguf` 文件——确认你的显存档位对应的量化等级与文件大小。
3. **首次下载**：不带校验参数直接跑，结束后自动打印实际 `size` 与 `sha256`：
   ```bash
   my-ex-girlfriend-at-25 fetch-model <发布者>/<模型仓库> <模型文件>.gguf
   # [fetch] OK (未提供校验参数) → local_llm/<模型文件>.gguf
   # [fetch] size = 17xxxxxxxx bytes
   # [fetch] sha256 = 3f9a...（记录这两个值）
   ```
4. **把模型文件名填进配置**：`config/settings.yaml` → `model.file` 与 `llm.local.model`。
5. **以后重下/换机器**：带上记录的两个值复检（>20G 强烈建议，hf-mirror 大文件偶有坏缓存）：
   ```bash
   my-ex-girlfriend-at-25 fetch-model <发布者>/<模型仓库> <模型文件>.gguf --sha256 3f9a... --size 17xxxxxxxx
   ```

模型放哪？`--dest` 默认 `local_llm/`。注意 `model.file` 是相对 `local_llm/` 的路径，
放子目录就把文件名写成 `子目录/xxx.gguf`。

## 许可与选型提醒

- Gemma 系列权重自带 Google 的使用条款，分发与商用前请自行确认；第三方量化文件同样受其约束。
- 本项目不附带、不分发任何模型权重；请从官方/可信渠道下载，并按 `my-ex-girlfriend-at-25 fetch-model` 的 sha256 校验。
- "去审查"(abliteration/uncensored) 权重涉及对原模型许可的二次使用，合规风险自担；陪伴用途请优先考虑
  遵守当地法律与平台规则的选型。

## 16G 档实测基线（Gemma4-26B-A4B-Balanced Q4_K_M）

- prefill 180 tok/s / gen 17 tok/s / 冷启动 10s / 热轮 4.8-5.8s
- 底档纪律（反幻觉）✓ 中文人设 ✓ 尺度：无对齐硬拒

## 关键经验（踩坑沉淀）

1. **`--load-mode none`（禁 mmap）是 Vulkan+CPU-offload 的命门**：mmap 页故障会把 prefill 压到 15 tok/s（差 12 倍）
2. **线性注意力架构（Qwen3.5/3.8 家族）在 llama.cpp Vulkan 上 prefill 灾难**（13 tok/s、不支持 cache-reuse）——即使量化合适也不建议做低延迟陪伴
3. **`-ot "exps=CPU"` 按型号验证**：部分第三方量化文件名不匹配 `.ffn_.*_exps.` 正则
4. **去审查权重选型**：Heretic 法（最小 KL 移除拒绝方向）优于 abliteration（实测会伤指令服从）；英文向 "ultra-uncensored" 对中文骚话表达力无增益
5. **下载纪律**：>20G 文件必过 sha256；hf_hub 收尾挂起是常态（看门狗+手动校验兜底，见 `my_ex_girlfriend_at_25/fetch_model.py`）

## 微调（LoRA）路线说明

本项目刻意走零微调路线。若你在 RAG 人格之上叠加 LoRA：风格会更内化，但记忆仍需检索层；
训练建议用云 GPU（消费级 A 卡 Windows 训练不现实），数据配比需保留底模的指令能力。
