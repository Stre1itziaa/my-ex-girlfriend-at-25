# 从零搭建指南（Getting Started）

> 本指南面向首次接触本项目的人与 agent：从零开始，只靠本文即可完成全部搭建并开始对话。
> 每一步都带 **✅ 验证** 检查点——执行后核对输出，通过了再进下一步。

## 0. 你将得到什么

一个跑在本机的 AI 伴侣：本地大模型推理（数据不出机器），检索复刻人格，WebUI 聊天，
可选微信通道。全程约 1–2 小时（大头是 17GB 模型下载）。

## 1. 前置条件

| 项 | 要求 | 检查命令 |
|---|---|---|
| 操作系统 | Windows 10/11（实测）；Linux 理论可跑 | — |
| Python | ≥ 3.10 | `python --version` |
| pip | 随 Python | `pip --version` |
| GPU | 12–24G 显存最佳；<12G 体验降级；无 GPU 可用 CPU 小模型（慢） | — |
| 磁盘 | ≥ 25GB 空闲（模型 17GB + 依赖 + 数据） | — |
| Node.js | ≥ 18，**仅微信通道需要**，可后装 | `node --version`（可选） |
| 网络 | 能访问 hf-mirror.com（默认模型源）与 github.com（下 llama.cpp） | — |

## 2. 安装项目

```bash
git clone https://github.com/Stre1itziaa/my-25-ex.git
cd my-25-ex
pip install -e .[vision]
```

（没有 git 可在 GitHub 页面 Code → Download ZIP 解压后进入目录执行同样命令。）

**✅ 验证**：`python -c "import xinli; print('ok')"` 输出 `ok`。

## 3. 初始化

```bash
xinli init
```

生成 `config/settings.yaml` 与 `config/persona.yaml`（复制自 example，内置虚构示例人格「小满」），
并创建 `memory/ state/ data/ channels/` 等目录。

**✅ 验证**：`xinli doctor` 显示 `✓ config/settings.yaml` 与 `✓ config/persona.yaml`
（此时 llama-server / 检索索引为 △ 属正常）。

## 4. 获取 llama-server（推理引擎）

本项目不带二进制，从 llama.cpp 官方发布下载预编译包：

1. 打开 <https://github.com/ggml-org/llama.cpp/releases/latest>
2. 下载对应你硬件的 Windows 包（资产名格式 `llama-<build>-bin-win-<backend>-x64.zip`）：
   - AMD/Intel/通用 GPU → **`...bin-win-vulkan-x64.zip`**（推荐，单文件自带运行时）
   - NVIDIA → `...bin-win-cuda-12.4-x64.zip`
   - 纯 CPU → `...bin-win-cpu-x64.zip`
3. 解压，把其中的 **`llama-server.exe`** 放到项目目录下（目录不存在就新建）：
   - Vulkan → `local_llm/vulkan/llama-server.exe`
   - CUDA → `local_llm/cuda/llama-server.exe`
   - CPU → `local_llm/cpu/llama-server.exe`

（命令行动手版：`curl -s https://api.github.com/repos/ggml-org/llama.cpp/releases/latest | findstr browser_download_url` 列出全部资产链接。Linux 用户从同一页面取对应 Linux 包或自行编译，把可执行文件按同样目录放置。）

**✅ 验证**：`local_llm/vulkan/llama-server.exe --version`（或你选择的目录）能打印版本号。

## 5. 获取模型（约 17GB，一次性）

```bash
xinli fetch-model <发布者>/<模型仓库> <模型文件>.gguf
```

- 选型见 [models.md](models.md)（12–24G 显存 → 26B 级 MoE Q4_K_M 档）。
- **首次下载不带 `--sha256/--size`**：下载完成后会自动打印实际 sha256 与字节数，
  把这两个值记下来；之后重新下载时带上它们即可复检。
- 默认源是 `hf-mirror.com`（国内直连）；海外可设环境变量 `HF_ENDPOINT=https://huggingface.co`
  （在 huggingface.co 下载 Gemma 系模型需先在模型页接受 Google 许可条款）。
- 模型文件的完整获取步骤（含 repo_id/文件名怎么找）见 [models.md §从零获取模型](models.md)。

**✅ 验证**：命令末行出现 `[fetch] OK`，且 `local_llm/<模型文件>.gguf` 存在且大小正确。
然后把 `config/settings.yaml` 里 `model.file` 改成你的模型文件名（保持与磁盘一致）。

## 6. 启动推理

```bash
xinli serve-llm
```

**✅ 验证**（另开一个终端）：

```bash
curl http://127.0.0.1:8081/health        # 期望 {"status":"ok"}
# 或
xinli doctor                             # llama-server 一行变 ✓
```

## 7. 建索引（demo 语料，一次性）

```bash
xinli build --demo
```

用合成示例语料跑画像/索引/作息统计（不需要任何真实聊天记录）。
不跑也能聊（空检索模式），但跑了她才有"记忆"。

**✅ 验证**：末行 `管线完成`；`xinli doctor` 的检索索引一行变 ✓。

## 8. 开始对话

```bash
xinli run
```

浏览器自动打开 <http://127.0.0.1:8787>。发一句话，等她的回复
（首次回复需加载模型，热轮约 5 秒/条）。她每 2 分钟掷骰子决定要不要主动找你。

**✅ 验证**：WebUI 能收到非空回复，无 500 报错。

## 9. 排障速查

| 现象 | 处理 |
|---|---|
| `serve-llm` 报模型不存在 | `config/settings.yaml` 的 `model.file` 与磁盘文件名不一致；先 `xinli fetch-model` |
| `run` 报 500 / refusal | llama-server 没起：先 `serve-llm`，用第 6 步验证 |
| 回复很慢 | 显存不足换了低档参数；看 `serve-llm` 启动日志的分层策略 |
| 下载中断/挂起 | 重跑同一条 `fetch-model`（huggingface_hub 有缓存）；>20G 建议带 `--sha256 --size` 复检 |
| 其他 | `xinli doctor` 逐项体检 |

## 10. 进阶路线

- **喂她你自己的聊天记录** → [export-logs.md](export-logs.md)（含数据红线，先读）
- **接到微信** → [wechat-bind.md](wechat-bind.md)（需要 Node 18+，官方 iLink Bot 通道）
- **成人向模块**（亲密/需求值）：存在但**默认关闭**，见 `config/settings.yaml` 的 `intimate.enabled`；
  仅限成年人，请遵守当地法律与模型许可（[models.md](models.md)）
- 修改/贡献代码 → [../CONTRIBUTING.md](../CONTRIBUTING.md)；行为红线 → [ethics.md](ethics.md)
