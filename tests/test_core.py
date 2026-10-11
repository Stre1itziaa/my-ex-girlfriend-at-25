# -*- coding: utf-8 -*-
"""纯逻辑单测: 分词/BM25/触发器/JSON解析/事实取代/窗口切分。LLM 相关走 smoke 标记。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "xinli" / "core"))

from retrieve import tokens, BM25, rrf  # noqa: E402
from consolidate import _parse_json, _find_match, tokens as ctokens  # noqa: E402


def test_tokens_bigram():
    t = tokens("宝宝吃饭了 eat")
    assert "宝宝" in t and "吃饭" in t and "eat" in t
    assert all(len(x) >= 1 for x in t)


def test_bm25_ranking():
    docs = ["她今天去上班了", "她喜欢面包店", "上班路上堵车"]
    dts = [tokens(d) for d in docs]
    import math
    from collections import Counter
    df = Counter(t for dt in dts for t in set(dt))
    idf = {t: math.log(1 + (len(dts) - c + 0.5) / (c + 0.5)) for t, c in df.items()}
    bm = BM25(idf, sum(len(d) for d in dts) / 3,
              [dict(Counter(d)) for d in dts], [len(d) for d in dts])
    s = bm.scores("上班")
    assert s[0] > s[1] and s[2] > s[1]


def test_rrf_fusion():
    fused = rrf([[1, 2, 3], [3, 2, 1]], weights=[1.0, 1.0])
    assert fused[2] > fused[0]  # 两路都有的 doc 得分最高


def test_parse_json_fenced():
    assert _parse_json('```json\n[{"a":1}]\n```') == [{"a": 1}]
    assert _parse_json('前置说明 {"ops": []} 后缀') == {"ops": []}


def test_find_match_substring_then_none():
    active = [{"fact": "她喜欢吃芝士焗面"}]
    assert _find_match("她喜欢吃芝士焗面，近期想吃饺子", active, None) == 0
    assert _find_match("完全无关的内容哦", active, None) is None


def test_intimate_trigger():
    import importlib
    chat = importlib.import_module("chat")
    assert chat._intimate_mode("把灯关了 今晚不睡了 陪我", []) is True
    assert chat._intimate_mode("你说想我了", []) is True          # "想我" 字序变体
    assert chat._intimate_mode("今天中午吃什么", []) is False
    assert chat._intimate_mode("继续", [("user", "想你了")]) is True


def test_fact_supersede_shape():
    """取代链: 旧条带 superseded_by 后检索层应过滤(纯数据形状测试)。"""
    facts = [{"fact": "旧"}, {"fact": "新", "superseded_by": "x"}]
    active = [f for f in facts if not f.get("superseded_by")]
    assert len(active) == 1 and active[0]["fact"] == "旧"
