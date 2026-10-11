# -*- coding: utf-8 -*-
"""微信通道适配器: 桥接文件队列(inbox/outbox) <-> 她的大脑。

桥接=channels/agent2wechat (官方 iLink Bot API)。收: inbox/*.json; 发: outbox/*.json。
主动消息无需入站配对——to_user_id 缺省发绑定人; 有 context_token 则带上增强会话连续性。
"""
import json
import random
import re
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
BRIDGE = BASE / "channels" / "agent2wechat"
INBOX = BRIDGE / "inbox"
OUTBOX = BRIDGE / "outbox"
PROCESSED = BRIDGE / "processed"
CH_STATE = BASE / "channels" / "wechat_state.json"
_last_outbox_ts = 0.0
STK_MANIFEST = BASE / "data" / "stickers" / "manifest.json"
_stk_cache = None


STK_RE = re.compile(r"\[表情包[:：]?\s*(\d+)?\]")
STK_RE_BARE = re.compile(r"^\[(\d{1,2})\]$")  # 模型简写 [16] 也算表情包标记


def pick_sticker(idx=None):
    """按编号或历史频次加权选表情包, 避免重复最近3个。返回绝对路径或 None。"""
    global _stk_cache
    if _stk_cache is None:
        if not STK_MANIFEST.exists():
            return None
        _stk_cache = json.loads(STK_MANIFEST.read_text(encoding="utf-8"))
    if not _stk_cache:
        return None
    if idx:
        try:
            f = _stk_cache[int(idx) - 1]["file"]
            return f if Path(f).exists() else None
        except Exception:
            return None
    st = _load_ch_state()
    recent = set(st.get("recent_stickers", []))
    pool = [s for s in _stk_cache if s["file"] not in recent] or _stk_cache
    pick = random.choices(pool, weights=[s["count"] for s in pool], k=1)[0]
    st["recent_stickers"] = (st.get("recent_stickers", []) + [pick["file"]])[-3:]
    CH_STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return pick["file"]


def wechat_bound() -> bool:
    return (BRIDGE / "state.json").exists()


def _load_ch_state():
    if CH_STATE.exists():
        return json.loads(CH_STATE.read_text(encoding="utf-8"))
    return {"context_token": None, "from_user_id": None}


def save_ctx(context_token, from_user_id):
    st = _load_ch_state()
    st.update({"context_token": context_token, "from_user_id": from_user_id})
    CH_STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


def poll_inbox():
    """取走所有入站文本消息, 文件移入 processed/。返回 [{id,text,ctx}]。"""
    if not INBOX.exists():
        return []
    out = []
    for f in sorted(INBOX.glob("*.json")):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue  # 可能还在写
        if f.name.endswith(".reply.json"):
            continue
        text = (j.get("text") or "").strip()
        ctx = j.get("context_token")
        uid = j.get("from_user_id")
        if ctx:
            save_ctx(ctx, uid)
        PROCESSED.mkdir(exist_ok=True)
        try:
            f.rename(PROCESSED / f.name)
        except Exception:
            pass
        media = [m.get("path") for m in (j.get("media_files") or []) if m.get("path") and Path(m["path"]).exists()]
        if text or media:
            out.append({"id": j.get("id", f.name), "text": text, "ctx": ctx, "uid": uid,
                        "images": media})
    return out


def send(bubbles, context_token=None, tag="msg", stagger=(2.5, 7.0)):
    """逐气泡出站（模拟连发），用 _next_attempt_at 做打字间隔。
    气泡 "[表情包]" 转成真表情包附件。返回文件名列表。"""
    if (BASE / "channels" / "agent2wechat" / "PAUSED").exists():
        print("[bridge_io] PAUSED 标记存在 — 微信发送已冻结")
        return []
    if isinstance(bubbles, str):
        bubbles = [bubbles]
    bubbles = [b.strip() for b in bubbles if b and b.strip()]
    if not bubbles:
        return []
    st = _load_ch_state()
    ctx = context_token or st.get("context_token")
    OUTBOX.mkdir(exist_ok=True)
    names, t0 = [], time.time()
    delay = 0.0
    # 全局节奏锁: 任何两条出站消息(跨回复序列)强制最小间隔——
    # 两条回复交错爆发曾触发微信风控静默吞尾——教训固化为节奏锁
    global _last_outbox_ts
    gap_base = max(time.time(), _last_outbox_ts + 4.0)
    t0 = gap_base
    delay = 0.0

    def emit(job, i):
        nonlocal delay
        if i > 0:
            delay += random.uniform(*stagger)
        job["_next_attempt_at"] = int((t0 + delay) * 1000)
        global _last_outbox_ts
        _last_outbox_ts = t0 + delay
        name = f"{tag}-{int(t0*1000)}-{i}.json"
        (OUTBOX / name).write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        names.append(name)

    seq = []  # [(kind, payload)]
    for b in bubbles:
        m = STK_RE.search(b)
        if not m and STK_RE_BARE.match(b.strip()):
            m = STK_RE_BARE.match(b.strip())
        if m:
            rest = (b[: m.start()] + b[m.end():]).strip()
            if rest:
                seq.append(("text", rest))
            seq.append(("sticker", m.group(1)))
        else:
            seq.append(("text", b))
    for i, (kind, payload) in enumerate(seq):
        job = {"binding": "default"}
        if kind == "sticker":
            att = pick_sticker(int(payload) if payload else None)
            if not att:
                continue
            job["attachments"] = [att]
        else:
            job["text"] = payload
        if ctx:
            job["context_token"] = ctx
        emit(job, i)
    return names


if __name__ == "__main__":
    print("bound:", wechat_bound())
    print("inbox:", poll_inbox())
