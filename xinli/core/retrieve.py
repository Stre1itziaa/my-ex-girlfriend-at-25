# -*- coding: utf-8 -*-
"""检索器: BM25 + 向量 RRF 融合（窗口）+ 事实 BM25。"""
import json
import math
import time
import pickle
from collections import Counter
from pathlib import Path

import datetime

BASE = Path(__file__).resolve().parent.parent.parent
IDX = BASE / "data" / "index" / "index.pkl"
JIDX = BASE / "memory" / "journal_index.pkl"
FACTS = BASE / "memory" / "facts.jsonl"

_vec_model = None


def tokens(text):
    clean = "".join(ch.lower() for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    ascii_words = [w.lower() for w in text.split() if w.isascii() and len(w) > 1]
    return [clean[i:i + 2] for i in range(len(clean) - 1)] + ascii_words


class BM25:
    def __init__(self, idf, avgdl, doc_tfs, doc_len, k1=1.5, b=0.75):
        self.idf, self.avgdl, self.tfs, self.lens = idf, avgdl, doc_tfs, doc_len
        self.k1, self.b = k1, b

    def scores(self, query):
        q = tokens(query)
        out = []
        for i, tf in enumerate(self.tfs):
            s, dl = 0.0, self.lens[i]
            for t in q:
                if t in tf:
                    s += self.idf.get(t, 0) * tf[t] * (self.k1 + 1) / (
                        tf[t] + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out


def load_all():
    if not IDX.exists():
        # 全新安装: 还没跑 build, 空索引模式(检索返回空, 不影响启动)
        print("[retrieve] 未找到检索索引 (先运行 xinli build) — 空检索模式")
        return {"version": 0, "windows": [], "embeddings": None}, None, [], None
    payload = pickle.loads(IDX.read_bytes())
    bm = BM25(payload["bm25"]["idf"], payload["bm25"]["avgdl"], payload["bm25"]["doc_tfs"],
              payload["bm25"]["doc_len"], payload["bm25"]["k1"], payload["bm25"]["b"])
    facts, fact_bm = Retriever._reload_facts()
    return payload, bm, facts, fact_bm


def _embed(texts):
    global _vec_model
    from fastembed import TextEmbedding
    if _vec_model is None:
        _vec_model = TextEmbedding("BAAI/bge-small-zh-v1.5")
    import numpy as np
    return np.array(list(_vec_model.embed(texts, batch_size=8)))


def rrf(rank_lists, k=60, weights=None):
    """rank_lists: [[doc_idx 排名表], ...] -> {doc_idx: score}"""
    weights = weights or [1.0] * len(rank_lists)
    score = Counter()
    for ri, ranks in enumerate(rank_lists):
        for pos, doc in enumerate(ranks):
            score[doc] += weights[ri] / (k + pos + 1)
    return score


class Retriever:
    def __init__(self):
        FACTS.parent.mkdir(parents=True, exist_ok=True)
        if not FACTS.exists():
            FACTS.write_text('', encoding='utf-8')
        self.payload, self.bm, self.fact_list, self.fact_bm = load_all()
        self.emb = self.payload.get("embeddings")
        ws = self.payload.get("windows", [])
        self.t0 = ws[0]["t_start"] if ws else 0
        self.t1 = ws[-1]["t_end"] if ws else 1
        self.jidx = self._load_jidx()
        self._mt = {"idx": IDX.stat().st_mtime if IDX.exists() else 0,
                    "facts": FACTS.stat().st_mtime if FACTS.exists() else 0,
                    "jidx": JIDX.stat().st_mtime if JIDX.exists() else 0}

    def _load_jidx(self):
        if not JIDX.exists():
            return None
        try:
            payload = pickle.loads(JIDX.read_bytes())
            bm = BM25(payload["bm25"]["idf"], payload["bm25"]["avgdl"], payload["bm25"]["doc_tfs"],
                      payload["bm25"]["doc_len"], payload["bm25"]["k1"], payload["bm25"]["b"])
            return {"payload": payload, "bm": bm, "emb": payload.get("embeddings")}
        except Exception:
            return None

    def _maybe_reload(self):
        """facts/索引被固化循环更新后热重载(下次查询自动生效)。"""
        try:
            mt_f = FACTS.stat().st_mtime
            mt_j = JIDX.stat().st_mtime if JIDX.exists() else 0
            if mt_f != self._mt["facts"]:
                self.fact_list, self.fact_bm = self._reload_facts()
                self._mt["facts"] = mt_f
            if mt_j != self._mt["jidx"]:
                self.jidx = self._load_jidx()
                self._mt["jidx"] = mt_j
        except Exception:
            pass

    @staticmethod
    def _reload_facts():
        facts = [json.loads(l) for l in FACTS.read_text(encoding="utf-8").split("\n") if l.strip()]
        act = [f for f in facts if not f.get("superseded_by")]
        fact_bm = None
        if act:
            dts = [tokens(f["fact"]) for f in act]
            df = Counter(t for dt in dts for t in set(dt))
            idf = {t: math.log(1 + (len(dts) - c + 0.5) / (c + 0.5)) for t, c in df.items()}
            fact_bm = BM25(idf, sum(len(d) for d in dts) / len(dts),
                           [dict(Counter(d)) for d in dts], [len(d) for d in dts])
        return facts, fact_bm

    def _top(self, scores, n):
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:n]
        return order

    def _rank_source(self, payload, bm, emb, query, top_n=30):
        """单源双路(BM25+向量) → RRF 融合后的 [(窗口, 分), ...]。"""
        rank_lists = [self._top(bm.scores(query), top_n)]
        weights = [1.0]
        if emb is not None:
            import numpy as np
            qv = _embed([query])[0]
            sims = emb @ qv / (np.linalg.norm(emb, axis=1) * np.linalg.norm(qv) + 1e-9)
            rank_lists.append(self._top(list(sims), top_n))
            weights = [1.0, 1.2]
        fused = rrf(rank_lists, weights=weights)
        return sorted(fused.items(), key=lambda kv: -kv[1])

    def windows(self, query, top_k=3, recency_boost=0.15):
        self._maybe_reload()
        now = time.time()
        cboost = {}
        # 语料源: 窗口在语料内部的位置即时近性
        if self.bm is None:
            return []
        corpus = self._rank_source(self.payload, self.bm, self.emb, query)
        c_rank = []
        for doc, s in corpus:
            w = self.payload["windows"][doc]
            frac = (w["t_start"] - self.t0) / max(1, self.t1 - self.t0)
            cboost[("c", doc)] = s * (1 + recency_boost * frac)
            c_rank.append(("c", doc))
        # journal源: 绝对时近性(越新越强, 14天半衰)
        j_rank = []
        if self.jidx and self.jidx["payload"]["windows"]:
            jd = self._rank_source(self.jidx["payload"], self.jidx["bm"], self.jidx["emb"], query)
            for doc, s in jd:
                w = self.jidx["payload"]["windows"][doc]
                days = max(0.0, (now - w["t_start"]) / 86400)
                cboost[("j", doc)] = s * (1 + 0.4 * math.exp(-days / 14))
                j_rank.append(("j", doc))
        # 跨源 RRF: journal 稍加权(新鲜)
        fused = rrf([c_rank, j_rank], weights=[1.0, 1.4]) if j_rank else rrf([c_rank])
        boosted = {k: cboost[k] * (1 + fused.get(k, 0) * 8) for k in cboost}
        top = sorted(boosted.items(), key=lambda kv: -kv[1])[:top_k]
        out = []
        for (src, doc), _ in top:
            w = dict(self.payload["windows"][doc] if src == "c" else self.jidx["payload"]["windows"][doc])
            w["source"] = "corpus" if src == "c" else "journal"
            out.append(w)
        return out

    def facts(self, query, top_k=8):
        self._maybe_reload()
        if not self.fact_bm:
            return []
        act = [f for f in self.fact_list if not f.get("superseded_by")]
        scores = self.fact_bm.scores(query)
        # fact_bm 建于活跃条; 对回原列表下标
        act_scores = sorted(zip([f for f in self.fact_list if not f.get("superseded_by")],
                                scores), key=lambda kv: -kv[1])
        return [f for f, s in act_scores[:top_k] if s > 0]


if __name__ == "__main__":
    r = Retriever()
    for w in r.windows("宝宝你在干嘛呀"):
        print("---", datetime.datetime.fromtimestamp(w["t_start"]).strftime("%m-%d %H:%M"))
        print(w["text"][:200])
    print("=== facts ===")
    for f in r.facts("宝宝你在干嘛呀"):
        print(f["date"], f["fact"][:60])
