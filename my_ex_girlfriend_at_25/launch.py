# -*- coding: utf-8 -*-
"""硬件画像 → llama-server 启动参数生成。

原则:
  backend: auto = 有 CUDA 用 CUDA, 否则 Vulkan (AMD/Intel)
  分层策略按显存档位:
    ≥24G: 全显存 (最快, 无 -ot)
    12-24G: MoE 专家进内存 (-ot exps=CPU), 全量加载禁 mmap (--load-mode none)
    <12G: 建议换小模型 (IQ 量化), 同样专家进内存
实测基线 (16G VRAM + 32G RAM 参考机, Gemma4-26B-A4B Q4KM):
  prefill 180 tok/s / gen 17 tok/s / 冷启动 10s / 热轮 4.8-5.8s
"""
import platform
import shutil
import subprocess


def detect_vram_gb() -> float:
    """尽力探测显存; 失败回退 16。"""
    try:
        if platform.system() == "Windows":
            import ctypes
            # 简化: 用 nvidia-smi / wmic 失败则回退
            for cmd in (["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                        ["wmic", "path", "win32_VideoController", "get", "AdapterRAM"]):
                try:
                    out = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
                    vals = [int(x) for x in out.split() if x.strip().isdigit()]
                    if vals:
                        v = max(vals)
                        return v / (1024 * 1024) if v > 1024 * 1024 else v / 1024  # MiB or bytes
                except Exception:
                    continue
    except Exception:
        pass
    return 16.0


def detect_backend() -> str:
    """backend: auto — CUDA 优先(有 nvidia-smi), 否则 vulkan。"""
    if shutil.which("nvidia-smi"):
        return "cuda"
    return "vulkan"


def build_command(model_path, port=8081, ctx=8192, backend="auto", vram_gb="auto",
                  llama_dir=None, enable_thinking=False):
    """返回 (exe路径, 参数list)。"""
    vram = detect_vram_gb() if vram_gb in ("auto", None) else float(vram_gb)
    be = detect_backend() if backend in ("auto", None) else backend
    sub = "vulkan" if be == "vulkan" else "cpu"  # 本仓库只随附 vulkan 构建; cuda 用户自装
    exe = (Path(llama_dir) if llama_dir else Path(__file__).resolve().parent.parent / "local_llm" / sub) / "llama-server.exe"
    args = ["-m", str(model_path), "--port", str(port), "-c", str(ctx), "--jinja",
            "--load-mode", "none",
            "--chat-template-kwargs", '{"enable_thinking": %s}' % ("true" if enable_thinking else "false")]
    if vram >= 24:
        args += ["-ngl", "99"]                      # 全显存
    else:
        args += ["-ngl", "99", "-ot", "exps=CPU"]   # 专家进内存(16G 档实测最优)
    return str(exe), args


if __name__ == "__main__":
    import json
    from pathlib import Path
    exe, args = build_command(Path(__file__).resolve().parent.parent / "local_llm" /
                              "Gemma4-26B-A4B-Q4_K_M.gguf")
    print(json.dumps({"exe": exe, "args": args}, ensure_ascii=False, indent=1))
