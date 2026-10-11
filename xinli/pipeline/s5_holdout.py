# -*- coding: utf-8 -*-
"""S5 留出考卷: 时间后 20% 轮次中抽 30 道「我方发言 -> 她方真实回复」题。

供 eval/blind_test.py 做真假混排盲评（G-C3 风格门）。
"""
import json
import random
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
CLEAN = BASE / "data" / "corpus" / "clean.jsonl"
OUT = BASE / "eval" / "holdout_exam.jsonl"
N_EXAM, CTX = 30, 6

random.seed(42)


def fmt(r):
    return ("她" if r["s"] == "other" else "我") + ": " + r["text"]


def main():
    lines = CLEAN.read_text(encoding="utf-8").split("\n")
    rounds = [json.loads(l) for l in lines[1:] if l.strip()]
    n_train = int(len(rounds) * 0.8)
    hold = rounds[n_train:]
    print(f"留出段轮次 {len(hold)} (从 {hold[0]['t_start']} 起)")

    def is_text(r):
        return not r["text"].startswith("[")

    cands = []
    for j in range(1, len(hold)):
        prev, cur = hold[j - 1], hold[j]
        if prev["s"] == "self" and cur["s"] == "other" and is_text(prev) and is_text(cur):
            if 2 <= len(cur["text"]) <= 120:  # 排除过短/过长
                cands.append(j)
    step = max(1, len(cands) // N_EXAM)
    picks = cands[::step][:N_EXAM]
    print(f"候选题 {len(cands)}, 抽 {len(picks)} 道")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps({"meta": {"n_holdout_rounds": len(hold), "n_train_boundary": n_train,
                                     "t_holdout_start": hold[0]["t_start"]}}, ensure_ascii=False) + "\n")
        for k, j in enumerate(picks):
            ctx = hold[max(0, j - CTX):j]
            f.write(json.dumps({
                "id": k, "context": [fmt(r) for r in ctx],
                "my_line": hold[j - 1]["text"], "gold_reply": hold[j]["text"],
            }, ensure_ascii=False) + "\n")
    print(f"考卷 -> {OUT}")


if __name__ == "__main__":
    main()
