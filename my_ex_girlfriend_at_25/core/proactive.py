# -*- coding: utf-8 -*-
"""主动触达: tick 循环决定"她现在想不想找你"，生成消息进 outbox，UI 轮询取走。

抑制器: 睡觉/冷却90min/每日上限5/用户刚聊过不打扰。
触发源: 作息时段(早安/午休/下班/晚安) + 分离焦虑(你太久没理她) + 日程事件分享。
"""
import json
import random
import datetime
import time
from pathlib import Path

import urllib.request
import yaml

BASE = Path(__file__).resolve().parent.parent.parent
OUTBOX = BASE / "state" / "outbox.jsonl"
JOURNAL = BASE / "memory" / "journal.jsonl"

COOLDOWN_S = 90 * 60
DAILY_CAP = 5
USER_ACTIVE_S = 10 * 60
FOLLOWUP_KEYWORDS = ["面试", "考试", "体检", "出差", "面试完", "开会", "答辩"]


def _persona_name():
    try:
        import yaml as _y
        _p = BASE / "config" / "persona.yaml"
        if _p.exists():
            return (_y.safe_load(_p.read_text(encoding="utf-8")) or {}).get("name", "她")
    except Exception:
        pass
    return "她"


persona_name = _persona_name()


def _load_desire_cfg():
    """proactive.desire 配置（config/settings.yaml）；缺省 enabled: false——成人模块默认不启用。"""
    p = BASE / "config" / "settings.yaml"
    try:
        if p.exists():
            s = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            return (s.get("proactive") or {}).get("desire") or {}
    except Exception:
        pass
    return {}


_DESIRE = _load_desire_cfg()
IP_ENABLED = bool(_DESIRE.get("enabled", False))   # 需求驱动主动 intimate 总开关（默认关）
IP_THRESHOLD = float(_DESIRE.get("threshold", 0.65))   # 需求值门槛
IP_HOUR_START = int(_DESIRE.get("hour_start", 21))     # 只在夜间窗口主动开车
IP_HOUR_END = int(_DESIRE.get("hour_end", 1))
IP_DAILY_CAP = int(_DESIRE.get("daily_cap", 1))        # 每天最多主动 1 次
IP_IGNORE_COOLDOWN_H = int(_DESIRE.get("ignore_cooldown_h", 8))  # 她主动过你没接 → 8小时内不再试
IP_P_BASE = 0.3              # 过门槛后的基础掷骰概率


def _in_hour_window(h):
    if IP_HOUR_START > IP_HOUR_END:      # 跨零点窗口（如 21→1）
        return h >= IP_HOUR_START or h < IP_HOUR_END
    return IP_HOUR_START <= h < IP_HOUR_END


def _intimate_roll(inner, now):
    """需求驱动主动: 返回 True=这轮走 intimate 支线（proactive.desire.enabled 开关，默认关）。"""
    if not IP_ENABLED:
        return False
    d = inner.desire_now(now)
    if d < IP_THRESHOLD:
        return False
    if not _in_hour_window(now.hour):
        return False
    if inner.data.get("ip_today", 0) >= IP_DAILY_CAP:
        return False
    ts = int(now.timestamp())
    if ts - inner.data.get("last_ip_ts", 0) < IP_IGNORE_COOLDOWN_H * 3600:
        return False
    p = IP_P_BASE + 0.4 * (d - IP_THRESHOLD) / max(0.01, 1 - IP_THRESHOLD)
    return random.random() < p


def _llm(messages, max_tokens=300, temperature=0.9):
    import sys as _s
    _s.path.insert(0, str(Path(__file__).parent))
    import llm as _llmmod
    return _llmmod.call(messages, max_tokens=max_tokens, temperature=temperature)


def _last_user_msg_ts():
    if not JOURNAL.exists():
        return 0
    lines = JOURNAL.read_text(encoding="utf-8").strip().split("\n")
    if not lines or not lines[-1]:
        return 0
    try:
        return json.loads(lines[-1]).get("t", 0)
    except Exception:
        return 0


def _recent_history(n=8):
    """journal 尾部对话(供生成参考)。"""
    if not JOURNAL.exists():
        return []
    lines = JOURNAL.read_text(encoding="utf-8").strip().split("\n")[-n:]
    out = []
    for l in lines:
        try:
            j = json.loads(l)
            out.append(f"我: {j['user'][:80]}\n她: {j['her'][:80]}")
        except Exception:
            pass
    return out


def decide(inner, now=None):
    """返回 (reason, mode) 或 None。mode='intimate' 走需求驱动支线。"""
    now = now or datetime.datetime.now()
    ts = int(now.timestamp())
    if not inner.is_awake(now):
        return None
    if inner.data.get("proactive_today", 0) >= DAILY_CAP:
        return None
    if ts - inner.data.get("last_proactive", 0) < COOLDOWN_S:
        return None
    if ts - _last_user_msg_ts() < USER_ACTIVE_S:
        return None  # 刚聊过, 不打扰

    if _intimate_roll(inner, now):
        return ("需求", "intimate")

    slot = inner.slot(now)
    p = inner.free_prob(now) * 0.55
    silent_h = (ts - _last_user_msg_ts()) / 3600
    if silent_h > 3:  # 分离焦虑: 你太久没理她
        p = min(0.9, p + 0.25)
        slot = "想你"
    return (slot, None) if random.random() < p else None


_stk_menu_cache = None


def _stk_menu():
    global _stk_menu_cache
    if _stk_menu_cache is None:
        try:
            p = BASE / "data" / "stickers" / "tags.json"
            tags = json.loads(p.read_text(encoding="utf-8"))
            _stk_menu_cache = " ".join(
                f"[{t['idx']}]{t.get('desc','')}({'/'.join(t.get('tags', [])[:3])})"
                for t in tags)
        except Exception:
            _stk_menu_cache = ""
    return _stk_menu_cache


def generate(inner, reason, now=None, mode=None):
    now = now or datetime.datetime.now()
    m = inner.data["mood"]
    brief = (
        f"现在是 {now.strftime('%H:%M')}，{reason}时段。你在: {inner.current_activity(now)}。"
        f"你情绪: {m['label']}。今天你安排了: {'、'.join(inner.data.get('agenda', []))}。\n"
        + (f"他最近对你说过的原话:\n" + "\n".join(_recent_history(6)) if _recent_history(6) else "你们今天还没聊过。")
    )
    if mode == "intimate":
        d = inner.desire_now(now)
        brief += f"\n你的身体需求值已经到 {d} 了——你现在很想要他。"
        sys = (
            f"你是{persona_name}（一个真实女生），现在夜里身体有需求，要【主动】给男朋友发微信撩他。"
            "用她的口吻：短句、连发（换行）、句尾带呀/啦/嘛/呢、用「…」。\n"
            "起手规则：这是第一句，像真人女生一样【暧昧试探级】起手——暗示你睡不着/一个人躺着/想他身体了，"
            "勾着他自己把话往那边带，绝不第一句就开车、绝不直说需求；他接了你会越来越不老实。\n"
            "禁止：表情包、[图片]占位符、旁白解释。2-3行，总共30-50字，结尾留一个让他必须接的话头。"
        )
    else:
        menu = _stk_menu()
        sys = (
            f"你是{persona_name}（一个真实女生），现在要【主动】给男朋友发微信。用她的口吻：短句、爱连发（换行）、"
            "句尾带呀/啦/嘛/呢。禁止输出\"[图片]\"\"[语音]\"这类占位符文字（微信会显示成字），"
            "想表达表情最多用一个普通 emoji（😂🥺😭）。"
            "想发表情包就单独一行写「[表情包:编号]」，从菜单挑贴合语境的（你大约每4-6轮发一个，没有贴 合的就不发）："
            + (menu or "（无）") + "。"
            "只输出你发出的消息本身，可多行，30字以内为宜，不要解释不要旁白。内容要贴合你此刻在做的事和情绪。"
        )
    text = _llm([{"role": "system", "content": sys}, {"role": "user", "content": brief}])
    import re as _re
    import emoji_map
    text = _re.sub(r"\[(图片|语音|视频|链接/?引用|位置|类型\d+)\]", "", text)
    text = emoji_map.outbound(text)
    parts = [p.strip() for p in text.split("\n") if p.strip()][:4]
    while len(parts) > 4:
        parts = parts[:-2] + ["".join(parts[-2:])]
    return parts


def tick(inner):
    """被 UI 线程定时调用; 触发则写 outbox 并返回 bubbles, 否则 None。"""
    d = decide(inner)
    if not d:
        return None
    reason, mode = d
    try:
        bubbles = generate(inner, reason, mode=mode)
    except Exception as e:
        print("[proactive] gen fail:", str(e)[:120])
        return None
    if not bubbles:
        return None
    now = datetime.datetime.now()
    ts = int(now.timestamp())
    rec = {"t": ts, "reason": reason, "mode": mode, "bubbles": bubbles, "delivered": False}
    with open(OUTBOX, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    inner.data["proactive_today"] = inner.data.get("proactive_today", 0) + 1
    inner.data["last_proactive"] = ts
    if mode == "intimate":
        inner.data["ip_today"] = inner.data.get("ip_today", 0) + 1
        inner.data["last_ip_ts"] = ts  # 发出后进"他没接"冷却; 他接了由 chat.mark_intimate 清零
    inner.save()
    return rec


def poll_outbox():
    """取未投递的主动消息, 标记已投递（只投一次）。"""
    if not OUTBOX.exists():
        return []
    recs, out_lines = [], []
    for l in OUTBOX.read_text(encoding="utf-8").split("\n"):
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except Exception:
            continue
        if not r.get("delivered"):
            r["delivered"] = True
            recs.append(r)
        out_lines.append(json.dumps(r, ensure_ascii=False))
    if recs:
        OUTBOX.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return recs


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from inner import Inner
    inner = Inner()
    if "--force" in sys.argv:
        # 强制触发一轮, 用于测试
        r = generate(inner, "想你")
        print("TEST 主动消息:", r)
    else:
        print("decide ->", decide(inner))
