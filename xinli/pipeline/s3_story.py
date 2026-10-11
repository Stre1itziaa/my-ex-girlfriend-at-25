# -*- coding: utf-8 -*-
"""S3b 关系编年史: clean.jsonl -> (LLM) -> memory/chronicle.md + memory/facts.jsonl。

map: 逐日聊天 -> 日摘要JSON(摘要/事实列表/情绪/原话) ; reduce: 按月合成章节。
断点续跑: memory/chronicle_days/YYYY-MM-DD.json 存在即跳过。
出网点 = config/settings.yaml llm 段配置的后端（默认 local 本地模型; 换云端自行承担数据出域）。
"""
import json
import datetime
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
CLEAN = BASE / "data" / "corpus" / "clean.jsonl"
DAYS_DIR = BASE / "memory" / "chronicle_days"
DAYS_DIR.mkdir(parents=True, exist_ok=True)
MAX_CHARS = 28000
WORKERS = 6

SYS = """你是关系编年史助手。输入是某一天微信聊天记录（说话人「她」是主角，「我」是用户）。
请提取客观事实型日摘要，输出严格 JSON（不要 markdown 代码块）：
{"summary": "≤120字当天概述", "facts": ["具体可查证的事实，含事件/她的生活状态/偏好/关系动态/内部梗，每条独立成句，禁止空话"], "tone": "当日情绪走向几个词", "quotes": ["最多3条有记忆价值的原话，保留她的用词"]}
要求：只输出 JSON；facts 里出现具体名词（人名/地点/食物/作品/时间）；她提到的生活信息（工作/家人/朋友/身体/情绪原因）优先记录。"""


def call_llm(messages, max_tokens=2000, temperature=0.2):
    """走 core/llm.py 统一后端（默认 local），带退避重试。"""
    import sys as _s
    _s.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
    import llm as _llmmod
    last = None
    for attempt in range(4):
        try:
            return _llmmod.call(messages, max_tokens=max_tokens,
                                temperature=temperature, timeout=180)
        except Exception as e:  # 429/5xx/网络 退避重试
            last = e
            time.sleep(2 ** attempt * 2)
    raise RuntimeError(f"LLM调用失败: {last}")


def parse_json(text):
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def day_transcript(rounds):
    out, size = [], 0
    for r in rounds:
        who = "她" if r["s"] == "other" else "我"
        line = f"{datetime.datetime.fromtimestamp(r['t_start']).strftime('%H:%M')} {who}: {r['text'][:160]}"
        out.append(line)
        size += len(line)
    return out


def process_day(date_str, rounds):
    lines = day_transcript(rounds)
    # 分块
    chunks, cur, size = [], [], 0
    for l in lines:
        if size + len(l) > MAX_CHARS and cur:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(l)
        size += len(l)
    if cur:
        chunks.append(cur)

    parts = []
    for ci, chunk in enumerate(chunks):
        head = f"日期：{date_str}" + (f"（第{ci+1}/{len(chunks)}段）" if len(chunks) > 1 else "")
        text = call_llm([{"role": "system", "content": SYS},
                         {"role": "user", "content": head + "\n\n" + "\n".join(chunk)}])
        parts.append(parse_json(text))
    if len(parts) == 1:
        day = parts[0]
    else:
        merged = call_llm([
            {"role": "system", "content": SYS},
            {"role": "user", "content": f"把同一天（{date_str}）的分段摘要合并为一个JSON对象：\n\n" +
                                         json.dumps(parts, ensure_ascii=False)}])
        day = parse_json(merged)
    day["date"] = date_str
    day["n_rounds"] = len(rounds)
    return day


def main():
    lines = CLEAN.read_text(encoding="utf-8").split("\n")
    rounds = [json.loads(l) for l in lines[1:] if l.strip()]
    by_day = {}
    for r in rounds:
        d = datetime.datetime.fromtimestamp(r["t_start"]).strftime("%Y-%m-%d")
        by_day.setdefault(d, []).append(r)
    days = sorted(by_day)
    todo = [d for d in days if not (DAYS_DIR / f"{d}.json").exists()]
    print(f"共 {len(days)} 天, 已有 {len(days)-len(todo)} 天缓存, 待跑 {len(todo)} 天")

    done = fail = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(process_day, d, by_day[d]): d for d in todo}
        for f in as_completed(futs):
            d = futs[f]
            try:
                day = f.result()
                (DAYS_DIR / f"{d}.json").write_text(
                    json.dumps(day, ensure_ascii=False, indent=1), encoding="utf-8")
                done += 1
                if done % 10 == 0:
                    print(f"  进度 {done+fail}/{len(todo)}")
            except Exception as e:
                fail += 1
                print(f"[!] {d} 失败: {str(e)[:120]}")
    print(f"map 完成: 成功 {done}, 失败 {fail}")

    # ---- 汇编 facts.jsonl + chronicle.md ----
    facts, day_summaries = [], []
    for d in days:
        p = DAYS_DIR / f"{d}.json"
        if not p.exists():
            continue
        day = json.loads(p.read_text(encoding="utf-8"))
        day_summaries.append(day)
        for fact in day.get("facts", []):
            facts.append({"date": d, "fact": fact})
    with open(BASE / "memory" / "facts.jsonl", "w", encoding="utf-8") as f:
        for x in facts:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    md = [f"# 关系编年史（{PERSONA_NAME}）", "",
          f"> 生成 {datetime.datetime.now().strftime('%Y-%m-%d')}，来源 data/corpus/clean.jsonl 逐日摘要。", ""]
    by_month = {}
    for day in day_summaries:
        by_month.setdefault(day["date"][:7], []).append(day)
    for month in sorted(by_month):
        md.append(f"## {month}")
        md.append("")
        for day in sorted(by_month[month], key=lambda x: x["date"]):
            md.append(f"### {day['date']}（{day.get('tone','')}）")
            md.append(f"- {day.get('summary','')}")
            for q in day.get("quotes", [])[:2]:
                md.append(f"- 「{q}」")
            md.append("")
    (BASE / "memory" / "chronicle.md").write_text("\n".join(md), encoding="utf-8")
    print(f"facts.jsonl {len(facts)} 条事实; chronicle.md {len(day_summaries)} 天")


if __name__ == "__main__":
    main()


# ---- 身份配置（来自 config/persona.yaml，开源版零硬编码）----
def _persona_name():
    try:
        import yaml as _y
        _p = BASE / 'config' / 'persona.yaml'
        if _p.exists():
            return (_y.safe_load(_p.read_text(encoding='utf-8')) or {}).get('name', '她')
    except Exception:
        pass
    return '她'

persona_name = _persona_name()
PERSONA_NAME = persona_name  # 提示词模板用
