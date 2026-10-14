# -*- coding: utf-8 -*-
"""S6 作息表: 从 clean.jsonl 统计她的生活节奏 -> state/rhythm.yaml。

产出: 小时x星期活跃热力、醒来/入睡时间估计、各时段回复延迟、睡眠时段。
"""
import json
import datetime
from collections import Counter, defaultdict
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent.parent
CLEAN = BASE / "data" / "corpus" / "clean.jsonl"
OUT = BASE / "state" / "rhythm.yaml"
OUT.parent.mkdir(parents=True, exist_ok=True)


def main():
    lines = CLEAN.read_text(encoding="utf-8").split("\n")
    rounds = [json.loads(l) for l in lines[1:] if l.strip()]
    her = [r for r in rounds if r["s"] == "other"]

    hour_hist = Counter(datetime.datetime.fromtimestamp(r["t_start"]).hour for r in her)
    wd_hist = Counter(datetime.datetime.fromtimestamp(r["t_start"]).weekday() for r in her)
    hour_wd = defaultdict(Counter)
    for r in her:
        dt = datetime.datetime.fromtimestamp(r["t_start"])
        hour_wd[dt.hour][dt.weekday()] += 1

    # 回复延迟(她收到我消息->她回)按小时
    lat = defaultdict(list)
    for a, b in zip(rounds, rounds[1:]):
        if a["s"] == "self" and b["s"] == "other":
            lat[datetime.datetime.fromtimestamp(b["t_start"]).hour].append(
                b["t_start"] - a["t_end"])
    lat_med = {h: int(sorted(v)[len(v)//2]) for h, v in lat.items() if len(v) >= 5}

    # 活跃日(>5轮)的最早/最晚消息 -> 起床/入睡分布
    by_day = defaultdict(list)
    for r in her:
        by_day[datetime.datetime.fromtimestamp(r["t_start"]).date()].append(r["t_start"])
    wake, sleep = Counter(), Counter()
    for d, ts in by_day.items():
        if len(ts) > 5:
            wake[datetime.datetime.fromtimestamp(min(ts)).hour] += 1
            last = datetime.datetime.fromtimestamp(max(ts))
            sleep[last.hour if last.hour < 18 else last.hour] += 1  # 跨零点算晚睡
    wk = wake.most_common()
    sp = sleep.most_common()

    rhythm = {
        "meta": {"generated": datetime.datetime.now().strftime("%Y-%m-%d"),
                 "note": "统计自当前语料; 手工可改"},
        "hour_activity": {str(h): hour_hist.get(h, 0) for h in range(24)},
        "weekday_activity": {str(d): wd_hist.get(d, 0) for d in range(7)},
        "wake_hour_top": [[h, c] for h, c in wk[:4]],
        "sleep_hour_top": [[h, c] for h, c in sp[:4]],
        "reply_latency_median_s_by_hour": {str(k): v for k, v in sorted(lat_med.items())},
    }
    OUT.write_text(yaml.dump(rhythm, allow_unicode=True, sort_keys=False), encoding="utf-8")

    total = sum(hour_hist.values())
    print("小时活跃占比(她发起轮次):")
    for h in range(24):
        c = hour_hist.get(h, 0)
        bar = "#" * int(c / total * 300)
        print(f"  {h:02d}时 {c/total:5.1%} {bar}")
    print(f"醒来小时 top: {wk[:3]}  入睡小时 top: {sp[:3]}")


if __name__ == "__main__":
    main()
