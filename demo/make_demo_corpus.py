# -*- coding: utf-8 -*-
"""生成虚构 demo 语料（角色=小满, 全部合成, 无任何真人数据）。

产出 data/corpus/clean.jsonl (S2 清洗后格式): meta 行 + 轮次行。
demo 模式下运行 `my-ex-girlfriend-at-25 build --demo` 只跑 s3/s4/s6 (文本特征, 无需微信库)。
"""
import json
import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# (日期偏移, 时:分, 发送方 self=用户/other=小满, 文本) —— 合成对话, 两周跨度
ROUND_TEXTS = [
    (0,"08:12","self","起床了没"),(0,"08:15","other","刚起呀"),(0,"08:16","other","你这么早 就上班啦"),
    (0,"08:17","self","9点打卡 冲了"),(0,"08:18","other","路上小心呀 买杯咖啡撑住"),
    (0,"12:20","self","午休了 趴一会"),(0,"12:23","other","好好午睡呀 我也在吃饭"),
    (0,"18:35","self","下班啦 加班到七点"),(0,"18:37","other","辛苦辛苦 回家吃好的"),
    (0,"23:40","self","睡了晚安"),(0,"23:43","other","晚安宝宝 今晚早点睡哦"),
    (1,"09:05","self","地铁上 人挤人"),(1,"09:07","other","哈哈抱紧扶手 别挤扁了"),
    (1,"19:50","self","刚到家 陪我妈看会电视"),(1,"19:53","other","陪妈妈看电视的乖儿子"),
    (2,"00:45","self","这局打完就睡"),(2,"00:47","other","又打游戏！不许超过一点"),
    (3,"10:11","other","周六愉快呀 我去逛街啦"),(3,"10:13","self","买到好东西拍照汇报"),
    (3,"16:28","other","看中一条裙子 好纠结买不买"),(3,"16:30","self","买！好看就买"),
    (4,"11:02","other","今天想吃烤鱼 你说呢"),(4,"11:04","self","走 老地方"),(4,"11:05","other","好耶 那晚上见"),
    (5,"13:15","self","午睡了没"),(5,"13:18","other","正打算睡 十五分钟"),
    (6,"21:12","other","在追剧啦 看到你说的那部了"),(6,"21:15","self","好看吧 我说没错"),
    (7,"10:30","self","周六愉快 我去打球"),(7,"10:33","other","运动完拍照 不许偷懒"),
    (8,"09:40","self","今天好忙 开会开一天"),(8,"09:42","other","那你加油 我不打扰你 中午记得吃饭"),
    (9,"22:20","self","这周好累啊"),(9,"22:23","other","那这周末好好休息 我陪你躺平"),
    (10,"15:44","other","在咖啡店写点东西 环境不错"),(10,"15:46","self","拍照看看"),
    (11,"20:18","self","刚下班 你吃了没"),(11,"20:20","other","刚吃完 我今天做了粥"),
    (12,"08:50","self","早 今天降温 多穿"),(12,"08:52","other","知道啦 你也是 大懒虫记得吃早餐"),
    (13,"23:05","other","今天很开心呀 虽然没见面"),(13,"23:08","self","下周见 下周见"),(13,"23:09","other","拉钩"),
]

def main():
    t0 = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=13)
    rows = []
    for off, hm, s, text in ROUND_TEXTS:
        hh, mm = hm.split(":")
        t = t0 + datetime.timedelta(days=off, hours=int(hh), minutes=int(mm))
        rows.append({"t_start": int(t.timestamp()), "t_end": int(t.timestamp()) + 20,
                     "s": s, "text": text, "n_msgs": 1, "i": len(rows)})
    meta = {"meta": {"schema_version": 1, "contact": "小满(demo)", "wxid": "demo_synthetic",
                     "source_db": "SYNTHETIC", "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
                     "note": "完全合成的示例语料, 不含任何真人数据"}}
    out = BASE / "data" / "corpus" / "clean.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[demo] 合成语料 {len(rows)} 轮 → {out}")
    print("[demo] 下一步: my-ex-girlfriend-at-25 build --demo  (只跑 s3/s4/s6, 无需微信库)")

if __name__ == "__main__":
    main()
