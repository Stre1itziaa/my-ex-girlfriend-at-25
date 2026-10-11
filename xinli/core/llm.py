# -*- coding: utf-8 -*-
"""统一 LLM 后端: 默认 local(本地 llama-server, OpenAI 兼容); glm(智谱API) 可选。

后端从 config/settings.yaml 的 llm 段读取（兼容旧 config/llm.yaml 整文件配置）。
缺省 = local，与 README 的「本地推理」承诺一致；需要云端时显式配 backend: glm。
"""
import json
import urllib.request
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent.parent
GLM_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"


def _load_cfg():
    for name in ("settings.yaml", "llm.yaml"):
        p = BASE / "config" / name
        if not p.exists():
            continue
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if name == "settings.yaml":
            if isinstance(data.get("llm"), dict):
                return data["llm"]
        elif isinstance(data, dict):
            return data
    return {}


def call(messages, max_tokens=600, temperature=0.85, timeout=120):
    cfg = _load_cfg()
    backend = cfg.get("backend", "local")
    if backend == "local":
        lc = cfg.get("local", {})
        # qwen3.5/3.8 模板要求 system 只能在开头: 把散落的 system 归并到首位
        _merged, _sys = [], []
        for m in messages:
            if m["role"] == "system":
                _sys.append(m["content"])
            else:
                _merged.append(m)
        if _sys:
            _merged = [{"role": "system", "content": "\n\n".join(_sys)}] + _merged
        messages = _merged
        body = {"model": lc.get("model", "qwen3-8b"), "messages": messages,
                "max_tokens": max_tokens, "temperature": temperature}
        if lc.get("no_think"):
            messages = [dict(m) for m in messages]
            for m in reversed(messages):
                if m["role"] == "system":
                    m["content"] = m["content"] + "\n/no_think"
                    break
        req = urllib.request.Request(
            lc.get("base", "http://127.0.0.1:8081/v1") + "/chat/completions",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=timeout))["choices"][0]["message"]["content"].strip()
    # glm
    key = (BASE / "config" / "glm.key").read_text().strip()
    body = {"model": cfg.get("glm", {}).get("model", "glm-4.6"), "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature,
            "thinking": {"type": "disabled"}}
    req = urllib.request.Request(GLM_URL, data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))["choices"][0]["message"]["content"].strip()
