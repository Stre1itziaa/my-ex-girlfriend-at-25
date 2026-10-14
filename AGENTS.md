# AGENTS.md — agent 搭建与开发入口

面向被派来搭建/修改本项目的自动化 agent（人类新人请从 [docs/getting-started.md](docs/getting-started.md) 开始）。

## 项目一句话

我的 25 岁前女友（My Ex-Girlfriend at 25）：把聊天记录变成本地 AI 伴侣——检索复刻人格 + 内心系统 + 微信官方通道，零微调，本地推理。

## 标准搭建序列（幂等，按序执行，每步有验证）

```bash
pip install -e .[vision]                                   # ① 依赖
my-ex-girlfriend-at-25 init                                                 # ② 配置+目录
# ③ llama-server: 从 https://github.com/ggml-org/llama.cpp/releases/latest
#    取 llama-<b>-bin-win-vulkan-x64.zip, 解压 llama-server.exe → local_llm/vulkan/
my-ex-girlfriend-at-25 fetch-model <发布者>/<仓库> <文件>.gguf               # ④ 模型(首下不带校验参数, 会打印 sha256)
my-ex-girlfriend-at-25 serve-llm                                            # ⑤ 推理服务
curl http://127.0.0.1:8081/health                          #    → {"status":"ok"}
my-ex-girlfriend-at-25 build --demo                                         # ⑥ 合成语料建索引
my-ex-girlfriend-at-25 run                                                  # ⑦ http://127.0.0.1:8787
```

详细步骤/验证点/排障：**docs/getting-started.md**（唯一权威，与本节冲突以它为准）。

## 改代码后的验证门（全部通过才算完成）

```bash
ruff check my_ex_girlfriend_at_25 tools tests channels --select E9,F63,F7,F82
python -m pytest tests/ -q
python tools/scan_secrets.py --root . --tracked    # 脱敏扫描(CI 同款)
python tools/scan_secrets.py --root . --history    # 全 git 对象体检
```

## 红线（违反=事故）

1. **真实个人数据永不入库**：`wechat_data/ data/ memory/ state/ config/persona.yaml
   config/settings.yaml config/profile.yaml config/target.yaml channels/*/state.json
   tools/scan_patterns.local.txt` 全部 gitignored——不要 add、不要写进代码、不要写进文档。
2. 只能复刻**本人或已获明确同意者**的人格（docs/ethics.md）；不得提交任何真实化名/地点/账号。
3. 成人模块（intimate/desire）**必须保持默认关闭**（settings.example 的 `enabled: false`），
   任何改动不得改变默认值。
4. 文档承诺必须与代码行为一致（默认后端、默认开关、平台支持）——本仓库 CI 会扫 git 历史，
   失实声明和历史泄漏同样是一票否决。

## 结构速览

- `my_ex_girlfriend_at_25/core/` 大脑（chat 检索人格 / inner 内心 / proactive 主动触达 / consolidate 记忆固化 / llm 统一后端）
- `my_ex_girlfriend_at_25/pipeline/` s1导出→s2清洗→…→s8b视觉打标 语料管线
- `my_ex_girlfriend_at_25/ui/web.py` 本地 WebUI + 微信收发循环；`channels/agent2wechat/` 微信桥接（Node）
- `config/*.example.yaml` 配置模板（真实配置 gitignored）；`tools/scan_secrets.py` 脱敏扫描器
