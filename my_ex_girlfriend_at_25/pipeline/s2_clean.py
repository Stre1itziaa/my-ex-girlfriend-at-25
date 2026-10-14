# -*- coding: utf-8 -*-
"""S2 清洗: raw.jsonl -> clean.jsonl（可从 raw 重建）。

清洗规则:
 - type 1 文本保留; 47/3/34/43/49/... 转占位符保持时间线连续; 10000/10002 系统与撤回剔除。
 - 同发送者 BURST_WINDOW 秒内连发合并为一条逻辑消息（保留 n_msgs 供后处理模仿节奏）。
 - 归属 sanity: self/other 逻辑消息比例报告。
输出: data/corpus/clean.jsonl = 每行一个 round（说话人轮次）。
"""
import json
from pathlib import Path
import datetime

BASE = Path(__file__).resolve().parent.parent.parent
RAW = BASE / "data" / "corpus" / "raw.jsonl"
OUT = BASE / "data" / "corpus" / "clean.jsonl"
BURST_WINDOW = 60

PLACEHOLDER = {3: "[图片]", 34: "[语音]", 43: "[视频]", 47: "[表情包]",
               48: "[位置]", 49: "[链接/引用]", 51: "[状态]"}


def main():
    # 注意: 不能用 splitlines()——消息里的 \u2028 会被当换行, 切碎 JSON 行
    lines = RAW.read_text(encoding="utf-8").split("\n")
    meta = json.loads(lines[0])["meta"]
    recs = [json.loads(l) for l in lines[1:] if l.strip()]

    kept, dropped_sys, ph = [], 0, 0
    for r in recs:
        ty = r["ty"]
        if ty in (10000, 10002):
            dropped_sys += 1
            continue
        if ty == 1 and r["c"]:
            text = r["c"].strip()
            if not text:
                continue
            # 归一化异体行分隔符, 保证 jsonl 单行完整性
            text = text.replace("\u2028", " ").replace("\u2029", " ").replace("\x85", " ")
        elif ty in PLACEHOLDER:
            text, ph = PLACEHOLDER[ty], ph + 1
        else:
            text, ph = f"[类型{ty}]", ph + 1
        kept.append({"t": r["t"], "s": r["s"], "text": text})

    # 爆发合并: 同发送者且与上一条间隔<=60s
    rounds = []
    for r in kept:
        if rounds and rounds[-1]["s"] == r["s"] and r["t"] - rounds[-1]["t_end"] <= BURST_WINDOW:
            cur = rounds[-1]
            cur["text"] += "\n" + r["text"]
            cur["t_end"] = r["t"]
            cur["n_msgs"] += 1
        else:
            rounds.append({"t_start": r["t"], "t_end": r["t"], "s": r["s"],
                           "text": r["text"], "n_msgs": 1})

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps({"meta": {**{k: v for k, v in meta.items() if k != "types"},
                                      "cleaned_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                      "burst_window_s": BURST_WINDOW,
                                      "n_raw": len(recs), "n_kept_msgs": len(kept),
                                      "n_dropped_sys": dropped_sys, "n_placeholder": ph,
                                      "n_rounds": len(rounds)}}, ensure_ascii=False) + "\n")
        for i, rd in enumerate(rounds):
            rd["i"] = i
            f.write(json.dumps(rd, ensure_ascii=False) + "\n")

    # ---- G-C2 sanity ----
    o = [r for r in rounds if r["s"] == "other"]
    x = [r for r in rounds if r["s"] == "self"]
    ratio = len(o) / max(1, len(x))
    print(f"原始 {len(recs)} -> 保留 {len(kept)} 条 (系统/撤回剔除 {dropped_sys}, 占位符 {ph})")
    print(f"逻辑轮次 {len(rounds)}: other {len(o)} / self {len(x)} (比例 1:{1/ratio:.2f}, 合理域 0.5~2)")
    print(f"clean.jsonl {OUT.stat().st_size/1e6:.1f}MB")
    print("\n--- 合并抽样(供人工过 G-C2, 各取3条) ---")
    for who, pool in (("other", o), ("self", x)):
        for r in pool[len(pool)//2:len(pool)//2+3]:
            preview = r["text"][:100].replace("\n", " ⏎ ")
            print(f"[{who} n={r['n_msgs']}] {preview}")


if __name__ == "__main__":
    main()
