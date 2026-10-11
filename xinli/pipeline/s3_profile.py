# -*- coding: utf-8 -*-
"""S3a 风格画像: clean.jsonl -> config/profile.yaml（纯本地统计, 不出网）。

产出说话风格 KV: 爆发节奏/句长/口癖/语气词/表情习惯/活跃时段/回复延迟。
"""
import json
import datetime
from collections import Counter
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent.parent
CLEAN = BASE / "data" / "corpus" / "clean.jsonl"
OUT = BASE / "config" / "profile.yaml"

PARTICLES = list("呢吧啦呀嘛咯哦噢哈嘿呜滴哒~")
STOPISH = set("的了是不我你他她它们在有就都也很要人啊好吧嗯哦这那你们自己一个什么没就是")


def ngrams(text, n):
    return [text[i:i + n] for i in range(len(text) - n + 1)]


def style_stats(rounds):
    """对一个说话人的轮次集合做风格统计。rounds 已过滤为含文本的。"""
    texts = [r["text"] for r in rounds]
    joined = "\n".join(texts)
    n = len(texts)
    lens = sorted(len(t.replace("\n", "")) for t in texts)
    burst = sorted(r["n_msgs"] for r in rounds)
    q = lambda p: lens[int(len(lens) * p)] if lens else 0
    bq = lambda p: burst[int(len(burst) * p)] if burst else 0
    emoji = sum(1 for ch in joined if 0x1F300 <= ord(ch) <= 0x1FAFF or 0x2600 <= ord(ch) <= 0x27BF)
    # 口癖: 2-gram 频次(去标点/占位/停用字主导的)
    clean = "".join(ch for ch in joined if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    g2 = Counter(g for g in ngrams(clean, 2) if not (g[0] in STOPISH and g[1] in STOPISH))
    g3 = Counter(g for g in ngrams(clean, 3) if g.count("哈") < 2)
    ends = sum(1 for t in texts if t and t[-1] in PARTICLES)
    return {
        "n_rounds": n,
        "chars_p50": q(0.5), "chars_p90": q(0.9),
        "burst_mean": round(sum(burst) / max(1, n), 2),
        "burst_p90": bq(0.9), "burst_max": burst[-1] if burst else 0,
        "sticker_rate": None,  # 由调用方补
        "laugh_count": joined.count("哈哈") // 2,
        "emoji_count": emoji,
        "ending_particle_rate": round(ends / max(1, n), 3),
        "top_bigrams": [w for w, _ in g2.most_common(30)],
        "top_trigrams": [w for w, _ in g3.most_common(15)],
    }


def main():
    lines = CLEAN.read_text(encoding="utf-8").split("\n")
    meta = json.loads(lines[0])["meta"]
    rounds = [json.loads(l) for l in lines[1:] if l.strip()]
    has_text = lambda r: not r["text"].startswith("[")
    other = [r for r in rounds if r["s"] == "other" and has_text(r)]
    self_ = [r for r in rounds if r["s"] == "self" and has_text(r)]

    sticker_other = sum(1 for r in rounds if r["s"] == "other" and r["text"] == "[表情包]")
    sticker_self = sum(1 for r in rounds if r["s"] == "self" and r["text"] == "[表情包]")

    # 活跃时段 & 回复延迟
    hours_o = Counter(datetime.datetime.fromtimestamp(r["t_start"]).hour for r in other)
    gaps = {"other": [], "self": []}
    for a, b in zip(rounds, rounds[1:]):
        if a["s"] != b["s"]:
            gaps[b["s"]].append(b["t_start"] - a["t_end"])
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None

    prof = {
        "meta": meta,
        "other_style": style_stats(other),
        "self_style": style_stats(self_),
        "sticker_per_100_rounds": {
            "other": round(sticker_other * 100 / max(1, len(other)), 1),
            "self": round(sticker_self * 100 / max(1, len(self_)), 1),
        },
        "active_hours_other": {str(h): c for h, c in sorted(hours_o.items())},
        "reply_latency_median_s": {"other": med(gaps["other"]), "self": med(gaps["self"])},
    }
    OUT.write_text(yaml.dump(prof, allow_unicode=True, sort_keys=False), encoding="utf-8")

    o = prof["other_style"]
    print(f"profile.yaml 已生成 ({OUT.stat().st_size}B)")
    print(f"她: {o['n_rounds']} 轮 | 句长 p50={o['chars_p50']} p90={o['chars_p90']} 字 | "
          f"爆发均值 {o['burst_mean']} p90={o['burst_p90']} max={o['burst_max']}")
    print(f"   哈哈 {o['laugh_count']} 次 | 句尾语气词率 {o['ending_particle_rate']:.0%} | "
          f"表情包 {prof['sticker_per_100_rounds']['other']}/100轮 | 回复延迟中位 {prof['reply_latency_median_s']['other']}s")
    print(f"   口癖bigram: {' '.join(o['top_bigrams'][:15])}")
    peak = max(prof['active_hours_other'].items(), key=lambda kv: kv[1])
    print(f"   最活跃时段: {peak[0]}点 ({peak[1]}轮)")


if __name__ == "__main__":
    main()
