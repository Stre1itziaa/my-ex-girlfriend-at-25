# -*- coding: utf-8 -*-
"""S8 表情包语义标注: 语料挖掘每个表情包的真实使用场景 -> GLM 归纳标签。

- 挖掘: manifest 里 30 个表情包, 在 raw.jsonl 中找"她发送该 md5"的记录,
  收集 发送小时 / 前一条(我方)文本 / 后一条(她方)文本。
- 标注: GLM 文本归纳 (不走视觉, 91 次使用记录就是 91 个上下文标注样本)。
- 产物: data/stickers/tags.json [{idx, file, desc, tags, mood}] (idx=manifest 序号, 1-based)。
断点续跑: 单个标注失败跳过, 重跑只补缺失。
"""
import json
import re
import datetime
from collections import Counter
from pathlib import Path

import urllib.request

BASE = Path(__file__).resolve().parent.parent.parent
RAW = BASE / "data" / "corpus" / "raw.jsonl"
STK = BASE / "data" / "stickers"
OUT = STK / "tags.json"

SYS = (
    "你是表情包标注员。给你某女生聊天中一张常用表情包的使用档案（发送时间分布、"
    "发它前对方说的话、发它后她说的话）。请推断这张表情包的画面与用途，输出严格 JSON：\n"
    '{"desc":"画面内容,10字内","tags":["使用场景词",3-6个,如 晚安/撒娇/想你/开心/无语/骂人/吃饭/早安],"mood":"主要情绪,2字"}\n'
    "只输出 JSON。"
)


def mine_contexts():
    """{md5: {hours:Counter, prev:[], next:[]}} 只看她侧发送。"""
    recs = [json.loads(l) for l in RAW.read_text(encoding="utf-8").split("\n")[1:] if l.strip()]
    lib = {}
    manifest = json.loads((STK / "manifest.json").read_text(encoding="utf-8"))
    wanted = {m["md5"]: i for i, m in enumerate(manifest)}
    for i, r in enumerate(recs):
        if r["ty"] != 47 or r["s"] != "other" or not r["c"]:
            continue
        m = re.search(r'md5\s*=\s*"([0-9a-f]{32})"', r["c"])
        if not m or m.group(1) not in wanted:
            continue
        e = lib.setdefault(m.group(1), {"hours": Counter(), "prev": [], "next": []})
        e["hours"][datetime.datetime.fromtimestamp(r["t"]).hour] += 1
        for j in range(i - 1, max(-1, i - 4), -1):
            if recs[j]["s"] == "self" and recs[j]["ty"] == 1 and recs[j]["c"]:
                e["prev"].append(recs[j]["c"][:30])
                break
        for j in range(i + 1, min(len(recs), i + 4)):
            if recs[j]["s"] == "other" and recs[j]["ty"] == 1 and recs[j]["c"]:
                e["next"].append(recs[j]["c"][:30])
                break
    return manifest, lib


def label_one(e):
    hours = sorted(e["hours"].items(), key=lambda kv: -kv[1])[:3]
    brief = (
        "发送时间分布(小时:次数): " + ", ".join(f"{h}点x{c}" for h, c in hours) + "\n"
        + "发它之前对方说: " + " | ".join(e["prev"][:5] or ["(无)"]) + "\n"
        + "发它之后她说: " + " | ".join(e["next"][:5] or ["(无)"])
    )
    body = {"model": "glm-4.6",
            "messages": [{"role": "system", "content": SYS},
                         {"role": "user", "content": brief}],
            "max_tokens": 300, "temperature": 0.2, "thinking": {"type": "disabled"}}
    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + (BASE / "config" / "glm.key").read_text().strip(),
                 "Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=90))
    text = re.sub(r"^```(json)?|```$", "", r["choices"][0]["message"]["content"].strip(), flags=re.M)
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0))


def main():
    manifest, lib = mine_contexts()
    tags = []
    if OUT.exists():
        tags = json.loads(OUT.read_text(encoding="utf-8"))
    done = {t["md5"]: t for t in tags}
    for i, m in enumerate(manifest):
        md5 = m["md5"]
        if md5 in done:
            continue
        e = lib.get(md5)
        if not e:
            print(f"  #{i+1:02d} 语料中无使用记录, 跳过")
            continue
        try:
            t = label_one(e)
            t.update({"idx": i + 1, "md5": md5, "file": m["file"], "count": m["count"]})
            tags.append(t)
            done[md5] = t
            print(f"  #{i+1:02d} {t.get('desc','')} | {'/'.join(t.get('tags', [])[:4])}")
        except Exception as ex:
            print(f"  #{i+1:02d} 标注失败: {str(ex)[:60]}")
    tags.sort(key=lambda t: t["idx"])
    OUT.write_text(json.dumps(tags, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"标注完成: {len(tags)}/{len(manifest)} -> {OUT}")


if __name__ == "__main__":
    main()
