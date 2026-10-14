# -*- coding: utf-8 -*-
"""S4 检索索引: clean.jsonl -> data/index/index.pkl。

- 时间 80/20 切分: 前 80% 轮次入索引（G-C3 通过后才用全量重建）。
- 检索单元 = 多轮滑窗（W=8 步长 4），文本 "她: ...\n我: ..."。
- 双路: BM25(字符二元组) + 向量(fastembed/bge-small-zh, 失败自动降级单路), 查询时 RRF 融合。
"""
import json
import math
import pickle
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
CLEAN = BASE / "data" / "corpus" / "clean.jsonl"
IDX_DIR = BASE / "data" / "index"
IDX_DIR.mkdir(parents=True, exist_ok=True)

W, STEP = 8, 4
K1, B = 1.5, 0.75


def tokens(text):
    """字符二元组 + ascii 词。"""
    clean = "".join(ch.lower() for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    ascii_words = [w.lower() for w in text.split() if w.isascii() and len(w) > 1]
    return [clean[i:i + 2] for i in range(len(clean) - 1)] + ascii_words


def try_embed(texts):
    """fastembed 本地向量; 失败返回 None（降级 BM25 单路）。"""
    try:
        from fastembed import TextEmbedding
    except ImportError:
        print("[i] 未装 fastembed, 向量路降级（BM25 单路）")
        return None
    try:
        model = TextEmbedding("BAAI/bge-small-zh-v1.5")
        import numpy as np
        vecs = np.array(list(model.embed(texts, batch_size=64)))
        print(f"[+] 向量路就绪: {vecs.shape}")
        return vecs
    except Exception as e:
        print(f"[i] 向量模型加载失败({str(e)[:80]}), 降级 BM25 单路")
        return None


def main():
    lines = CLEAN.read_text(encoding="utf-8").split("\n")
    rounds = [json.loads(l) for l in lines[1:] if l.strip()]
    n_train = int(len(rounds) * 0.8)
    train = rounds[:n_train]
    print(f"轮次 {len(rounds)}, 训练段 {n_train} (至 "
          f"{__import__('datetime').datetime.fromtimestamp(train[-1]['t_start']).strftime('%Y-%m-%d')})")

    windows = []
    for i in range(0, len(train) - W + 1, STEP):
        seg = train[i:i + W]
        text = "\n".join(("她" if r["s"] == "other" else "我") + ": " + r["text"] for r in seg)
        windows.append({"rounds": list(range(i, i + W)), "t_start": seg[0]["t_start"],
                        "t_end": seg[-1]["t_end"], "text": text})
    print(f"检索窗口 {len(windows)} 个 (W={W}, step={STEP})")

    # BM25
    doc_tokens = [tokens(w["text"]) for w in windows]
    df = Counter(t for dt in doc_tokens for t in set(dt))
    n_docs = len(doc_tokens)
    avgdl = sum(len(dt) for dt in doc_tokens) / n_docs
    idf = {t: math.log(1 + (n_docs - c + 0.5) / (c + 0.5)) for t, c in df.items()}
    bm25 = {"idf": idf, "avgdl": avgdl, "k1": K1, "b": B,
            "doc_tfs": [dict(Counter(dt)) for dt in doc_tokens],
            "doc_len": [len(dt) for dt in doc_tokens]}
    print(f"BM25 就绪: {n_docs} 窗口, 词表 {len(idf)}")

    vecs = try_embed([w["text"] for w in windows])
    payload = {"version": 1, "split_train_n": n_train, "windows": windows,
               "bm25": bm25, "embeddings": vecs,
               "embed_model": "BAAI/bge-small-zh-v1.5" if vecs is not None else None}
    out = IDX_DIR / "index.pkl"
    out.write_bytes(pickle.dumps(payload))
    print(f"索引 -> {out} ({out.stat().st_size/1e6:.1f}MB)")


if __name__ == "__main__":
    main()
