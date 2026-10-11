# -*- coding: utf-8 -*-
"""xinli 命令行入口。

  xinli init          初始化配置(复制 example) + 建目录
  xinli doctor        体检: 配置/模型/服务/索引/贴纸
  xinli fetch-model   下载本地模型(自愈+sha256)
  xinli serve-llm     启动本地 llama-server(硬件画像自动配参)
  xinli build         跑语料管线 s2→s8 (s1 需已导出的解密库)
  xinli run           启动本地聊天 UI
"""
import argparse
import subprocess
import sys
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def cmd_init(a):
    cfg = BASE / "config"
    for name in ("settings.yaml", "persona.yaml"):
        src, dst = cfg / f"{name.replace('.yaml', '.example.yaml')}", cfg / name
        if dst.exists():
            print(f"[init] {name} 已存在, 跳过")
        else:
            __import__("shutil").copy(src, dst)
            print(f"[init] 已创建 {dst.name} — 按注释填写 (人格内容必改)")
    for d in ("memory", "state", "data/index", "data/stickers", "channels/wechat"):
        (BASE / d).mkdir(parents=True, exist_ok=True)
    print("[init] 目录就绪。下一步: 编辑 config/persona.yaml, 然后 `xinli fetch-model`")


def cmd_doctor(a):
    ok = True
    from xinli.config import load_settings, load_persona, BASE as _B
    for name, fn in (("settings.yaml", load_settings), ("persona.yaml", load_persona)):
        try:
            fn(); print(f"[doctor] ✓ config/{name}")
        except Exception as e:
            ok = False; print(f"[doctor] ✗ config/{name}: {str(e)[:70]}")
    import urllib.request
    try:
        st = __import__("json").loads(__import__("urllib.request", fromlist=["urlopen"]).urlopen(
            "http://127.0.0.1:8081/health", timeout=4).read())["status"]
        print(f"[doctor] {'✓' if st=='ok' else '✗'} llama-server 8081 ({st})")
    except Exception:
        print("[doctor] △ llama-server 未运行 (xinli serve-llm 启动; 无它则回退 GLM 后端)")
    idx = _B / "data" / "index" / "index.pkl"
    print(f"[doctor] {'✓' if idx.exists() else '△'} 检索索引 (△=未 build, 空检索模式)")
    stk = _B / "data" / "stickers" / "manifest.json"
    print(f"[doctor] {'✓' if stk.exists() else '△'} 表情包库")
    sys.exit(0 if ok else 1)


def cmd_fetch_model(a):
    from xinli.fetch_model import fetch, resume_finalize
    if a.resume:
        resume_finalize(a.dest, a.sha256, a.size, a.name)
        return
    fetch(a.repo, a.file, a.dest, a.sha256, a.size)


def cmd_serve_llm(a):
    from xinli.launch import build_command
    from xinli.config import load_settings
    s = load_settings()
    model = BASE / "local_llm" / s.raw.get("model", {}).get("file", "")
    if not model.exists():
        print(f"[serve-llm] 模型不存在: {model} — 先 `xinli fetch-model`"); sys.exit(1)
    exe, args = build_command(model, port=s.raw.get("model", {}).get("port", 8081),
                              ctx=s.raw.get("model", {}).get("ctx", 8192))
    print("[serve-llm]", exe, " ".join(args))
    __import__("os").execv if hasattr(__import__("os"), "execv") else None
    sys.exit(subprocess.call([exe] + args))


def cmd_build(a):
    if a.demo:
        subprocess.call([sys.executable, str(BASE / "demo" / "make_demo_corpus.py")])
        steps = ["s3_profile", "s4_index", "s6_rhythm"]   # demo: 文本特征即可, 无需微信库
    else:
        steps = ["s2_clean", "s3_profile", "s3_story", "s4_index", "s5_holdout", "s6_rhythm",
                 "s7_stickers", "s8_sticker_tags", "s8b_sticker_vision"]
    for s in steps:
        print(f"\n===== {s} =====")
        rc = subprocess.call([sys.executable, str(BASE / "xinli" / "pipeline" / f"{s}.py")])
        if rc != 0:
            print(f"[build] {s} 失败 (rc={rc}) — 修复后重跑"); sys.exit(rc)
    print("\n[build] 管线完成 — `xinli run` 开始聊天")


def cmd_run(a):
    import os
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    print("[run] 本地聊天 UI 启动 — 浏览器将自动打开")
    p = subprocess.Popen([sys.executable, str(BASE / "xinli" / "ui" / "web.py")], env=env)
    try:
        webbrowser.open("http://127.0.0.1:8787")
    except Exception:
        pass
    p.wait()


def main():
    ap = argparse.ArgumentParser(prog="xinli", description="把真实聊天记录变成有血有肉的 AI 陪伴")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="初始化配置与目录").set_defaults(func=cmd_init)
    sub.add_parser("doctor", help="体检").set_defaults(func=cmd_doctor)
    p = sub.add_parser("fetch-model", help="下载本地模型")
    p.add_argument("repo"); p.add_argument("file"); p.add_argument("--dest", default="local_llm")
    p.add_argument("--sha256", default="0" * 64); p.add_argument("--size", type=int, default=0)
    p.add_argument("--resume", action="store_true")
    p.set_defaults(func=cmd_fetch_model)
    sub.add_parser("serve-llm", help="启动本地推理服务").set_defaults(func=cmd_serve_llm)
    p = sub.add_parser("build", help="跑语料管线")
    p.add_argument("--demo", action="store_true", help="用合成demo语料, 只跑文本特征步骤")
    p.set_defaults(func=cmd_build)
    sub.add_parser("run", help="启动聊天 UI").set_defaults(func=cmd_run)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
