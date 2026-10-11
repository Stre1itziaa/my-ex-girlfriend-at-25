# -*- coding: utf-8 -*-
"""她的内心状态: 情绪引擎(OCC式简化) + 作息感知 + 每日日程。

学术对应:
 - 情绪 = valence/arousal 二维 (PAD 简化), 事件 appraisal 更新, 时间衰减回归基线
 - 作息 = 语料统计的活跃分布 (s6_rhythm)
 - 日程 = Generative Agents 式 daily agenda (v1 模板+随机)
状态持久化: state/inner.json
"""
import json
import random
import datetime
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent.parent
STATE = BASE / "state"
STATE.mkdir(exist_ok=True)
INNER = STATE / "inner.json"
RHYTHM = STATE / "rhythm.yaml"

POS_UP = ["想你", "宝宝", "老婆", "爱你", "开心", "喜欢你", "抱抱", "亲亲", "好棒", "谢谢"]
NEG_DOWN = ["烦", "滚", "分手", "生气", "讨厌", "干嘛呢你", "凶", "冷漠", "忙别烦我", "哦"]
HARD_NEG = ["分手", "滚", "讨厌你"]

MOOD_WORDS = {
    "good": ["开心", "甜甜的", "元气满满", "黏人", "想撒娇"],
    "neutral": ["平静", "有点无聊", "平常心", "一般般"],
    "low": ["有点丧", "委屈", "烦躁", "低落", "累"],
    "sleepy": ["困困", "想睡觉", "迷糊"],
}


class Mood:
    def __init__(self, valence=0.1, arousal=0.4, label="平常心"):
        self.valence, self.arousal, self.label = valence, arousal, label

    def to_dict(self):
        return {"valence": round(self.valence, 2), "arousal": round(self.arousal, 2),
                "label": self.label}


def _band(v):
    if v > 0.25:
        return "good"
    if v < -0.25:
        return "low"
    return "neutral"


class Inner:
    def __init__(self):
        self.rhythm = yaml.safe_load(RHYTHM.read_text(encoding="utf-8")) if RHYTHM.exists() else {}
        self.intimate_enabled = self._load_intimate_enabled()
        self.desire_recharge_h = self._load_desire_recharge_h()
        self.data = self._load()
        self._maybe_new_day()

    def _load_intimate_enabled(self):
        """intimate.enabled 开关（config/settings.yaml，默认关）：需求值/周期调幅的总闸。"""
        p = BASE / "config" / "settings.yaml"
        try:
            if p.exists():
                s = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                return bool((s.get("intimate") or {}).get("enabled", False))
        except Exception:
            pass
        return False

    def _load_desire_recharge_h(self):
        p = BASE / "config" / "settings.yaml"
        try:
            if p.exists():
                s = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                return float(((s.get("proactive") or {}).get("desire") or {}).get("recharge_hours", 40))
        except Exception:
            pass
        return 40.0

    # ---- 持久化 ----
    def _load(self):
        if INNER.exists():
            return json.loads(INNER.read_text(encoding="utf-8"))
        import random as _r
        anchor = (datetime.date.today() - datetime.timedelta(days=_r.randint(3, 27))).isoformat()
        return {"mood": Mood().to_dict(), "baseline": 0.1,
                "day": "", "agenda": [], "proactive_today": 0,
                "last_proactive": 0, "last_user_msg": 0, "journal_digest": "",
                "desire_base": 0.0, "last_intimate": 0, "cycle_anchor": anchor,
                "ip_today": 0, "last_ip_ts": 0}

    def save(self):
        INNER.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- 每日初始化 ----
    def _maybe_new_day(self):
        today = datetime.date.today().isoformat()
        if self.data.get("day") != today:
            base = random.uniform(-0.15, 0.3)  # 她自己生活的随机底色
            mood = Mood(valence=base, arousal=random.uniform(0.25, 0.55),
                        label=random.choice(MOOD_WORDS[_band(base)]))
            self.data.update({"day": today, "mood": mood.to_dict(), "baseline": round(base, 2),
                              "agenda": self._gen_agenda(), "proactive_today": 0, "ip_today": 0})
            self.save()

    def _location_templates(self):
        try:
            pf = yaml.safe_load((BASE / 'config' / 'persona.yaml').read_text(encoding='utf-8'))
            tpl = pf.get('location_templates') or {}
            if tpl.get('workday') and tpl.get('weekend'):
                return tpl
        except Exception:
            pass
        return {'workday': ['公司上班'], 'weekend': ['家里']}

    def _gen_agenda(self):
        wd = datetime.date.today().weekday()
        tpl = self._location_templates()
        if wd < 5:
            pool = [(9.0, "到公司打卡"), (10.5, "上午摸鱼刷手机"), (12.5, "午休趴一会"),
                    (15.0, "下午干活"), (19.0, "下班回家"), (21.0, "晚上追剧"),
                    (23.0, "敷面膜早睡")]
            loc = tpl["workday"][0]
        else:
            pool = [(10.0, "睡到自然醒"), (12.0, "点个外卖"), (14.5, "逛街买买买"),
                    (16.0, "喝下午茶"), (21.0, "晚上追剧"), (23.0, "早点睡")]
            pool = sorted(random.sample(pool, k=min(4, len(pool))))
            loc = random.choice(tpl["weekend"])
        self.data["location"] = loc
        return [f"{int(h):02d}:{int(h*60)%60:02d} {name}" for h, name in pool]

    # ---- 事件评估 (v1 规则式; v2 换 LLM appraisal) ----
    def apply_turn(self, user_msg):
        m = self.data["mood"]
        v = m["valence"]
        if any(k in user_msg for k in HARD_NEG):
            v -= 0.35
        elif any(k in user_msg for k in NEG_DOWN):
            v -= 0.15
        if any(k in user_msg for k in POS_UP):
            v += 0.15
        v = max(-1, min(1, v + random.uniform(-0.03, 0.03)))
        m["valence"] = round(v, 2)
        m["arousal"] = round(max(0, min(1, m["arousal"] + random.uniform(0, 0.1))), 2)
        m["label"] = random.choice(MOOD_WORDS[_band(v)])
        self.save()

    # ---- 需求系统：身体需求随时间累积，生理周期调幅，亲密后清零 ----
    # 受 settings.yaml 的 intimate.enabled 总闸控制（默认关）；关闭时 desire_now 恒为 0

    def cycle_mult(self, now=None):
        """生理周期对需求值的倍率（简化28天模型）。"""
        now = now or datetime.datetime.now()
        anchor = datetime.date.fromisoformat(self.data.get("cycle_anchor") or datetime.date.today().isoformat())
        day = (now.date() - anchor).days % 28 + 1
        if day <= 5:
            return 0.3   # 经期
        if 11 <= day <= 17:
            return 1.4   # 排卵窗口
        if day >= 26:
            return 0.7   # 经前
        return 1.0

    def desire_now(self, now=None):
        now = now or datetime.datetime.now()
        if not self.intimate_enabled:
            return 0.0
        hours = max(0.0, (now.timestamp() - self.data.get("last_intimate", 0)) / 3600)
        base = min(1.0, hours / self.desire_recharge_h)
        if 21 <= now.hour or now.hour < 1:
            base = min(1.0, base + 0.15)  # 夜里会更想
        return round(min(1.0, base * self.cycle_mult(now)), 2)

    def mark_intimate(self, now=None):
        """真实亲密对话发生后：需求清零。"""
        self.data["last_intimate"] = int((now or datetime.datetime.now()).timestamp())
        self.data["last_ip_ts"] = 0  # 清掉"她主动过你没接"的冷却
        self.save()

    def decay(self, hours):
        """向当日基线回归。"""
        m = self.data["mood"]
        b = self.data.get("baseline", 0.1)
        m["valence"] = round(m["valence"] + (b - m["valence"]) * min(1, hours * 0.3), 2)
        m["arousal"] = round(m["arousal"] + (0.4 - m["arousal"]) * min(1, hours * 0.3), 2)
        self.save()

    # ---- 作息 ----
    def is_awake(self, now=None):
        now = now or datetime.datetime.now()
        h = now.hour
        return 7 <= h < 24  # 语料: 23-24点入睡, 7点起

    def free_prob(self, now=None):
        now = now or datetime.datetime.now()
        hist = self.rhythm.get("hour_activity", {})
        c = hist.get(str(now.hour), 0)
        mx = max(hist.values()) if hist else 1
        return (c / mx) ** 1.5 if mx else 0.3

    def slot(self, now=None):
        now = now or datetime.datetime.now()
        h = now.hour
        if 7 <= h < 9:
            return "早安"
        if 12 <= h < 14:
            return "午休"
        if 15 <= h < 18:
            return "下午摸鱼"
        if 18 <= h < 20:
            return "下班"
        if 20 <= h < 23:
            return "晚上"
        if 23 <= h or h < 1:
            return "晚安"
        return "上班中"

    def current_activity(self, now=None):
        now = now or datetime.datetime.now()
        if not self.is_awake(now):
            return "在睡觉"
        agenda = self.data.get("agenda", [])
        if not agenda:
            return "发呆"
        cur_h = now.hour + now.minute / 60
        cur = agenda[0]
        for item in agenda:
            hh, mm = item.split(" ")[0].split(":")
            if int(hh) + int(mm) / 60 <= cur_h:
                cur = item
        return cur.split(" ", 1)[1]

    # ---- 状态注入对话 ----
    def prompt_block(self, now=None):
        now = now or datetime.datetime.now()
        m = self.data["mood"]
        wd = "一二三四五六日"[now.weekday()]
        loc = self.data.get("location") or (self._location_templates()["workday"][0] if now.weekday() < 5 else self._location_templates()["weekend"][0])
        desire_line = (f"- 你此刻身体很想要他（需求值{self.desire_now(now)}）——不用忍着：聊天可以直接说骚话、开黄腔、"
                       f"主动把话题往性上带，想撩就直球撩，这是你此刻真实的状态。对方明显没兴致就先收敛，别硬推。\n"
                       if self.desire_now(now) >= 0.7 else "")
        return (f"- 今天实际是 {now.strftime('%Y年%m月%d日')} 星期{wd}，现在 {now.strftime('%H:%M')}（{self.slot(now)}时段）。\n"
                f"- 你今天的位置: {loc}。近况一律以此为准，不要说自己去了别的地方。\n"
                f"- 你此刻在: {self.current_activity(now)}。\n"
                f"- 你现在的情绪: {m['label']}（{'心情好' if m['valence']>0.25 else '心情差' if m['valence']<-0.25 else '一般'}）。"
                f"回复的熱情度和耐心要与此一致：心情差时敷衍/冷淡一点，心情好时黏人一点。\n"
                f"- 你的 today 安排: {'、'.join(self.data.get('agenda', []))}。\n"
                + desire_line
                + f"- {'你该睡了(你一般23点睡)' if 23 <= now.hour or now.hour < 7 else ''}")


if __name__ == "__main__":
    inner = Inner()
    print(json.dumps(inner.data, ensure_ascii=False, indent=1))
    print(inner.prompt_block())
