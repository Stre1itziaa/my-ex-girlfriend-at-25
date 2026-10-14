# -*- coding: utf-8 -*-
"""记忆固化循环 (三层记忆 L0→L1→L2)。

每夜运行:
  1. 备份 journal/facts/索引 → memory/backups/YYYY-MM-DD/
  2. 取 journal 自上次固化以来的新条目(跳过 test 标记)
  3. Stage A: 本地LLM 从对话中提取候选事实卡(类型/重要性/日期)
  4. Stage B: 每个候选对照现有事实(子串+BM25) → ADD/UPDATE/DELETE, 旧事实标记 superseded_by(审计链)
  5. 新对话窗口化 → 并入 journal_index.pkl 分片(与语料索引同构)
  6. state 记录 last_ts; 检索器经 mtime 热重载自动生效

原则: journal 是唯一真相源(只追加), facts 是可维护视图, 一切可从备份+L0重建。
隐私: 摘要只走本地模型(8081), 对话内容不出机器。
"""
import json
import math
import re
import shutil
import sys
import time
import datetime
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "brain"))

JOURNAL = BASE / "memory" / "journal.jsonl"
FACTS = BASE / "memory" / "facts.jsonl"
STATE = BASE / "memory" / "consolidate_state.json"
JIDX = BASE / "memory" / "journal_index.pkl"
BACKUPS = BASE / "memory" / "backups"
BACKUP_KEEP_DAYS = 14
CHUNK = 30          # 每次LLM调用最多处理的journal条数
WINDOW = 6          # 索引窗口大小(条)
GAP_S = 30 * 60     # 窗口切分: 间隔超30分钟另起窗口

K1, B = 1.5, 0.75


def tokens(text):
    clean = "".join(ch.lower() for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    ascii_words = [w.lower() for w in text.split() if w.isascii() and len(w) > 1]
    return [clean[i:i + 2] for i in range(len(clean) - 1)] + ascii_words


def _llm(messages, max_tokens=1400, temperature=0.3):
    import llm as _llmmod
    return _llmmod.call(messages, max_tokens=max_tokens, temperature=temperature)


def _parse_json(text):
    """容错解析: 剥```json 围栏, 抓第一个 JSON 对象/数组。"""
    text = re.sub(r"```(?:json)?", "", text).strip()
    # 先抓最外层: 文本以 [ 开头优先数组, 否则优先对象 (数组内含 dict 不能被抓成 dict)
    pats = (r"\[.*\]", r"\{.*\}") if text.startswith("[") else (r"\{.*\}", r"\[.*\]")
    for pat in pats:
        m = re.search(pat, text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                continue
    raise ValueError("no json in llm output")


def load_journal():
    out = []
    for l in JOURNAL.read_text(encoding="utf-8").split("\n"):
        if not l.strip():
            continue
        try:
            out.append(json.loads(l))
        except Exception:
            pass
    return out


def load_facts():
    if not FACTS.exists():
        return []
    return [json.loads(l) for l in FACTS.read_text(encoding="utf-8").split("\n") if l.strip()]


def save_facts(facts):
    FACTS.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in facts) + "\n", encoding="utf-8")


def backup():
    BACKUPS.mkdir(parents=True, exist_ok=True)
    day = BACKUPS / datetime.date.today().isoformat()
    day.mkdir(exist_ok=True)
    for f in (JOURNAL, FACTS, JIDX):
        if f.exists():
            shutil.copy2(f, day / f.name)
    # 清过期备份
    for d in BACKUPS.iterdir():
        if d.is_dir() and d.name[:10].isdigit():
            try:
                if (datetime.date.today() - datetime.date.fromisoformat(d.name[:10])).days > BACKUP_KEEP_DAYS:
                    shutil.rmtree(d)
            except Exception:
                pass
    return day


def stage_a_extract(entries):
    """对话 → 候选事实卡。分块防超窗。"""
    cands = []
    for i in range(0, len(entries), CHUNK):
        seg = entries[i:i + CHUNK]
        convo = "\n".join(
            f"[{datetime.datetime.fromtimestamp(e['t']).strftime('%m-%d %H:%M')}] 我: {str(e.get('user',''))[:120]}\n"
            f"           她: {str(e.get('her',''))[:120]}" for e in seg)
        prompt = (
            "下面是你({NAME})和男朋友最近的真实聊天记录。请从中提取值得长期记住的【事实】, "
            "用于更新你的长期记忆。只提取有信息量的事实: 约定/计划、他的近况与偏好、你们的共同经历、"
            "关系动态、重要的情绪事件。寒暄/吃了吗级别的日常不要提取。\n"
            "每条输出: date(事件所属日期YYYY-MM-DD)、type(约定|事件|偏好|人物|状态)、fact(一句话, 第三人称, "
            "具体含关键细节)、importance(1-10, 越影响后续相处越高)。\n"
            "输出JSON数组, 没有值得记的就输出 []。只输出JSON。\n\n聊天记录:\n" + convo)
        raw = _llm([{"role": "system", "content": "你是记忆管理器, 只输出严格合法的JSON。"},
                    {"role": "user", "content": prompt}])
        try:
            arr = _parse_json(raw)
            if isinstance(arr, dict):
                arr = arr.get("facts", [])
            for a in arr:
                if isinstance(a, dict) and a.get("fact"):
                    a.setdefault("date", datetime.date.today().isoformat())
                    a.setdefault("type", "事件")
                    a.setdefault("importance", 5)
                    cands.append(a)
        except Exception as e:
            print(f"[consolidate] stage A 块{i//CHUNK}解析失败: {str(e)[:80]}")
    return cands


def _find_match(fact_text, active, bm_scores):
    """在现有事实中找该候选对应的旧条目: 子串优先, BM25 兜底。"""
    key = re.sub(r"[，。！？、\s]", "", fact_text)[:20]
    for i, f in enumerate(active):
        if key and key[:8] in re.sub(r"[，。！？、\s]", "", f["fact"]):
            return i
    if bm_scores:
        scores = bm_scores(fact_text)
        top = sorted(range(len(scores)), key=lambda i: -scores[i])[:1]
        if top and scores[top[0]] > 3:
            return top[0]
    return None


def stage_b_resolve(cands, facts):
    """候选 vs 现有事实 → ADD/UPDATE/DELETE 决策, 返回应用后的 (facts, ops)。
    每个候选由本地 BM25 先取 top-3 相似旧条随行, 提示词不随库容增长。"""
    active_idx = [i for i, f in enumerate(facts) if not f.get("superseded_by")]
    active = [facts[i] for i in active_idx]
    bm_scores = None
    if active:
        dts = [tokens(f["fact"]) for f in active]
        df = Counter(t for dt in dts for t in set(dt))
        idf = {t: math.log(1 + (len(dts) - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        avgdl = sum(len(x) for x in dts) / len(dts)

        def bm_scores(q):
            qtk = tokens(q)
            out = []
            for dt in dts:
                tf = Counter(dt)
                dl = len(dt)
                s = sum(idf.get(t, 0) * tf.get(t, 0) * (K1 + 1) /
                        (tf.get(t, 0) + K1 * (1 - B + B * dl / avgdl))
                        for t in qtk if t in tf)
                out.append(s)
            return out

    if not cands:
        return facts, []
    # 每候选预取 top-3 相似旧条
    cand_blocks, match_map = [], {}
    for k, c in enumerate(cands):
        ms = []
        if bm_scores:
            sc = bm_scores(c["fact"])
            order = sorted(range(len(sc)), key=lambda i: -sc[i])[:3]
            ms = [i for i in order if sc[i] > 2]
        lines = [f"M{k}-{n}: ({active[i].get('date','?')}) {active[i]['fact'][:70]}" for n, i in enumerate(ms)]
        match_map[k] = ms
        cand_blocks.append(f"{k}. [{c['type']}|{c['date']}|重要{c['importance']}] {c['fact']}"
                           + (("\n   相似旧条: " + " ; ".join(lines)) if lines else "\n   相似旧条: 无"))
    prompt = (
        "你在维护 {NAME} 的长期记忆库。下面每个【候选事实】附带从库里检索到的相似旧条。\n"
        "对每个候选做决策:\n"
        "- ADD: 新信息, 相似旧条里没有它\n"
        "- UPDATE: 某相似旧条已过时/被取代, match 填该旧条的编号(如 M0-1), fact 给新的完整表述\n"
        "- DELETE: 某相似旧条现在明确错误, match 同上, 给 reason\n"
        "- NOOP: 重复或无价值\n"
        '输出JSON: {"ops":[{"k":候选序号,"op":"ADD|UPDATE|DELETE|NOOP","match":"旧条编号或空","'
        'fact":"新完整表述(UPDATE填)","reason":"一句话理由"}]}\n\n'
        "候选:\n" + "\n".join(cand_blocks) + "\n\n只输出JSON。")
    raw = _llm([{"role": "system", "content": "你是记忆管理器, 只输出严格合法的JSON。"},
                {"role": "user", "content": prompt}])
    try:
        ops = _parse_json(raw)
        ops = ops.get("ops", []) if isinstance(ops, dict) else ops
    except Exception as e:
        print(f"[consolidate] stage B 解析失败, 全部按ADD处理: {str(e)[:80]}")
        ops = [{"k": k, "op": "ADD"} for k in range(len(cands))]

    now = int(time.time())
    today = datetime.date.today().isoformat()
    applied = []

    def resolve_match(k, match):
        m = match_map.get(k) or []
        if isinstance(match, str) and match.startswith("M"):
            try:
                _, n = match.split("-")
                return m[int(n)]
            except Exception:
                pass
        # 关键词兜底
        key = re.sub(r"[，。！？、\s]", "", str(match))[:10]
        for i in m:
            if key and key in active[i]["fact"]:
                return i
        return None

    for op in ops:
        try:
            k = int(op.get("k", -1))
            c = cands[k]
        except Exception:
            continue
        act = op.get("op", "ADD").upper()
        if act == "NOOP":
            applied.append(("NOOP", c["fact"], op.get("reason", "")))
            continue
        match_i = resolve_match(k, op.get("match")) if act in ("UPDATE", "DELETE") else None
        if act == "UPDATE" and match_i is not None:
            old = active[match_i]
            old["superseded_by"] = f"{today}:{c['fact'][:30]}"
            facts.append({"id": f"f{now}_{k}", "date": c["date"], "type": c.get("type", "事件"),
                          "fact": op.get("fact") or c["fact"], "importance": int(c.get("importance", 5)),
                          "source": "journal", "t": now, "replaces": old.get("id", "")})
            applied.append(("UPDATE", c["fact"], op.get("reason", "")))
        elif act == "DELETE" and match_i is not None:
            old = active[match_i]
            old["superseded_by"] = f"{today}:deleted:{op.get('reason', '')[:30]}"
            applied.append(("DELETE", old["fact"][:50], op.get("reason", "")))
        else:  # ADD (或匹配失败按新增)
            facts.append({"id": f"f{now}_{k}", "date": c["date"], "type": c.get("type", "事件"),
                          "fact": c["fact"], "importance": int(c.get("importance", 5)),
                          "source": "journal", "t": now})
            applied.append(("ADD", c["fact"], ""))
    return facts, applied


# ---- 索引分片 ----

def _build_bm25(windows):
    dts = [tokens(w["text"]) for w in windows]
    df = Counter(t for dt in dts for t in set(dt))
    n = len(dts)
    idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
    return {"idf": idf, "avgdl": sum(len(d) for d in dts) / n, "k1": K1, "b": B,
            "doc_tfs": [dict(Counter(d)) for d in dts], "doc_len": [len(d) for d in dts]}


def _embed(texts):
    try:
        from fastembed import TextEmbedding
        import numpy as np
        model = TextEmbedding("BAAI/bge-small-zh-v1.5")
        return np.array(list(model.embed(texts, batch_size=32)))
    except Exception as e:
        print(f"[consolidate] 向量降级: {str(e)[:80]}")
        return None


def index_journal(entries):
    """新条目窗口化 → 合并进 journal_index.pkl(全量重建, 分片很小)。"""
    old = {"windows": []}
    if JIDX.exists():
        try:
            old = _load_pickle(JIDX)
        except Exception:
            old = {"windows": []}
    have_ts = {w["t_start"] for w in old["windows"]}
    entries = [e for e in entries if e["t"] not in have_ts]
    if not entries and not old["windows"]:
        return 0
    if not entries:
        return len(old["windows"])
    # 窗口化: 间隔>GAP_S 或满 WINDOW 条则切段
    windows, cur = [], []
    for e in entries:
        if cur and (e["t"] - cur[-1]["t"] > GAP_S or len(cur) >= WINDOW):
            windows.append(cur)
            cur = []
        cur.append(e)
    if cur:
        windows.append(cur)
    for seg in windows:
        text = "\n".join(f"我: {str(e.get('user',''))[:150]}\n她: {str(e.get('her',''))[:150]}" for e in seg)
        old["windows"].append({"t_start": seg[0]["t"], "t_end": seg[-1]["t"], "text": text,
                               "source": "journal"})
    ws = old["windows"]
    payload = {"version": 1, "windows": ws, "bm25": _build_bm25(ws),
               "embeddings": _embed([w["text"] for w in ws]),
               "embed_model": "BAAI/bge-small-zh-v1.5"}
    import pickle as _p
    JIDX.write_bytes(_p.dumps(payload))
    return len(ws)


def _load_pickle(p):
    import pickle as _p
    return _p.loads(p.read_bytes())


def main(daily=True):
    t0 = time.time()
    bdir = backup()
    entries = load_journal()
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"last_ts": 0}
    last_ts = st.get("last_ts", 0)
    new = [e for e in entries if e.get("t", 0) > last_ts and not e.get("test")]
    print(f"[consolidate] journal总{len(entries)}, 新{len(new)} (since {datetime.datetime.fromtimestamp(last_ts).strftime('%m-%d %H:%M')}), 备份→{bdir.name}")
    if not new:
        print("[consolidate] 无新对话, 完毕")
        return

    facts = load_facts()
    n_old = len(facts)
    cands = stage_a_extract(new)
    print(f"[consolidate] 提取候选事实 {len(cands)} 条")
    facts, applied = stage_b_resolve(cands, facts)
    save_facts(facts)
    adds = sum(1 for a in applied if a[0] == "ADD")
    ups = sum(1 for a in applied if a[0] == "UPDATE")
    dels = sum(1 for a in applied if a[0] == "DELETE")
    print(f"[consolidate] 事实: {n_old}→{len(facts)} (ADD {adds} / UPDATE {ups} / DELETE {dels} / NOOP {sum(1 for a in applied if a[0]=='NOOP')})")
    for a in applied:
        if a[0] != "NOOP":
            print(f"   [{a[0]}] {a[1][:60]}" + (f" — {a[2][:40]}" if a[2] else ""))

    n_win = index_journal(new)
    print(f"[consolidate] journal索引窗口 {n_win} 个 → {JIDX.name}")

    st["last_ts"] = max(e["t"] for e in new)
    st["last_run"] = datetime.datetime.now().isoformat()
    st["last_stats"] = {"adds": adds, "updates": ups, "deletes": dels, "windows": n_win}
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[consolidate] 完成, 耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main(daily="--daily" in sys.argv)
