# -*- coding: utf-8 -*-
"""S8b 表情包视觉校准: GLM-4.6V 逐张看图修正 desc（用途 tags 保留语境挖掘结果）。

GIF 取首帧缩到 256px 转 JPEG。tags.json 的 desc 字段更新为视觉真值, 其余不动。
"""
import base64
import io
import json
import re
from pathlib import Path

import urllib.request
from PIL import Image

BASE = Path(__file__).resolve().parent.parent.parent
STK = BASE / "data" / "stickers"
TAGS = STK / "tags.json"


def describe(path):
    im = Image.open(path).convert("RGB")
    im.thumbnail((256, 256))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    key = (BASE / "config" / "glm.key").read_text().strip()
    body = {"model": "glm-4.6v", "max_tokens": 1024, "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
                {"type": "text", "text": "一句话描述这张表情包的画面（含图中文字），10-20字，直接回答不要思考"}]}]}
    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=90))
    return r["choices"][0]["message"]["content"].strip()


def main():
    tags = json.loads(TAGS.read_text(encoding="utf-8"))
    for t in tags:
        f = Path(t["file"])
        if not f.exists():
            continue
        try:
            d = describe(f)
            old = t.get("desc", "")
            t["desc"] = d
            t["desc_context"] = old  # 保留语境推断备用
            TAGS.write_text(json.dumps(tags, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  #{t['idx']:02d} {d}")
        except Exception as e:
            print(f"  #{t['idx']:02d} 失败: {str(e)[:60]}")
    print("视觉校准完成")


if __name__ == "__main__":
    main()
