# -*- coding: utf-8 -*-
"""今日热点: 抓微博热搜(公开ajax, 免key), 缓存 memory/news.json, 注入她的 prompt。

多源降级: 微博ajax -> 百度热榜HTML解析。全部失败则用缓存旧数据(标日期), 再不行就没有。
她的世界里这不是"新闻联播"而是"刷手机看到的瓜", 注入措辞按这个来。
"""
import json
import re
import datetime
from pathlib import Path
import urllib.request

BASE = Path(__file__).resolve().parent.parent.parent
CACHE = BASE / "memory" / "news.json"
TTL_H = 6


def _get(url, timeout=8):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def from_weibo():
    d = json.loads(_get("https://weibo.com/ajax/side/hotSearch"))
    out = []
    for it in (d.get("data", {}) or {}).get("realtime", [])[:12]:
        w = it.get("word") or (it.get("note") or "").replace("#", "")
        if w:
            out.append(w)
    return out


def from_baidu():
    html = _get("https://top.baidu.com/board?tab=realtime").decode("utf-8", "replace")
    words = re.findall(r'"word":"([^"]{4,30})"', html)
    seen, out = set(), []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out[:12]


def load(force=False):
    """返回 {date, items}; 过期则刷新, 全失败则回退缓存。"""
    cache = None
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = None
    today = datetime.date.today().isoformat()
    now_h = datetime.datetime.now().timestamp()
    if not force and cache and cache.get("date") == today and \
            now_h - cache.get("ts", 0) < TTL_H * 3600 and cache.get("items"):
        return cache
    items = []
    for src in (from_weibo, from_baidu):
        try:
            items = src()
            if items:
                break
        except Exception:
            continue
    if items:
        data = {"date": today, "ts": int(now_h), "items": items[:10]}
        CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return data
    return cache or {"date": today, "items": []}


def prompt_block():
    """注入她 prompt 的热搜块; 没数据返回空串。"""
    try:
        d = load()
    except Exception:
        return ""
    items = d.get("items") or []
    if not items:
        return ""
    return "- 你刚刷到的微博热搜（可自然提及，别罗列）: " + "、".join(items[:5])


if __name__ == "__main__":
    d = load(force=True)
    print(d["date"], len(d["items"]), "条")
    for i in d["items"][:8]:
        print(" -", i)
    print()
    print(prompt_block()[:200])
