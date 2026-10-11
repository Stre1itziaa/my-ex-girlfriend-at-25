# -*- coding: utf-8 -*-
"""S1 导出: 解密库 -> 目标联系人双人对话真相源 raw.jsonl (只写不改——导出文件只追加, 是后续一切重建的真相源)。

v4 库要点:
 - 表名 = Msg_ + md5(wxid), 归属 = real_sender_id 对 Name2Id.rowid。
 - WCDB_CT_message_content != 0 时 message_content 为 zstd 压缩字节。
 - local_type 高位打包了标志位, 取 & 0xFFFFFFFF 为基础类型 (1文字/3图/34语音/47表情/...)。
"""
import hashlib
import json
import sqlite3
import time
import datetime
from pathlib import Path

import yaml
import zstandard

BASE = Path(__file__).resolve().parent.parent.parent
DEC = BASE / "wechat_data" / "decrypted"
OUT = BASE / "data" / "corpus" / "raw.jsonl"

BURST_WINDOW = 60  # S2 预览用: 同发送者 N 秒内连发算一个逻辑消息

cfg = yaml.safe_load((BASE / "config" / "target.yaml").read_text(encoding="utf-8"))
WXID = cfg["target"]["wxid"]
NAME = cfg["target"]["name"]
SRC = cfg["target"]["source_db"]


def decode_content(raw, ct):
    if raw is None:
        return None
    if isinstance(raw, bytes):
        if ct:  # WCDB zstd 压缩（帧头无内容大小，须流式解）
            try:
                raw = zstandard.ZstdDecompressor().decompressobj().decompress(raw)
            except Exception:
                return None
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return raw if isinstance(raw, str) else None


def main():
    con = sqlite3.connect(DEC / SRC)
    table = "Msg_" + hashlib.md5(WXID.encode()).hexdigest()
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
        raise SystemExit(f"表不存在: {table}")

    # 归属映射: rowid -> 用户名, 找到自己
    id2user = {rid: un for rid, un in con.execute("SELECT rowid, user_name FROM Name2Id")}
    me_ids = {rid for rid, un in id2user.items() if un != WXID and un.startswith("wxid_")}
    # 1v1 表里 real_sender_id 只会是自己或对方; 用"非对方"兜底判自己
    rows = con.execute(
        f"SELECT local_id, local_type, real_sender_id, create_time, "
        f"message_content, WCDB_CT_message_content FROM {table} ORDER BY create_time, local_id"
    ).fetchall()
    con.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    n_comp, n_fail, by_type = 0, 0, {}
    meta_written = False
    idx = 0
    tmp_lines = []
    for local_id, ltype, sender_id, ts, content, ct in rows:
        base_ty = ltype & 0xFFFFFFFF
        by_type[base_ty] = by_type.get(base_ty, 0) + 1
        if ct:
            n_comp += 1
        text = decode_content(content, ct)
        if ct and text is None:
            n_fail += 1
        sender = "other" if sender_id not in me_ids and sender_id != 2 else "self"
        # 1v1: 对方 id = 出现次数最多的非我 id; 直接按上面启发即可, 但更稳妥:
        sender = "self" if sender_id == 2 else "other"
        tmp_lines.append(json.dumps({
            "i": idx, "lid": local_id, "t": ts, "s": sender,
            "ty": base_ty, "ty_raw": ltype, "c": text,
        }, ensure_ascii=False))
        idx += 1

    meta = {
        "schema_version": 1,
        "contact": NAME, "wxid": WXID, "source_db": SRC, "table": table,
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n_messages": idx, "n_zstd": n_comp, "n_decode_fail": n_fail,
        "types": by_type,
        "t_from": rows[0][3] if rows else None,
        "t_to": rows[-1][3] if rows else None,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps({"meta": meta}, ensure_ascii=False) + "\n")
        f.write("\n".join(tmp_lines) + "\n")

    # ---- G-C1 统计 ----
    print(f"真相源: {OUT}  ({OUT.stat().st_size/1e6:.1f}MB)")
    print(f"消息 {meta['n_messages']} 条 | zstd压缩 {n_comp} | 解压失败 {n_fail}")
    t0, t1 = meta["t_from"], meta["t_to"]
    fmt = lambda t: datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M")
    print(f"时间跨度: {fmt(t0)} -> {fmt(t1)}")
    top_types = sorted(by_type.items(), key=lambda kv: -kv[1])[:8]
    print("类型分布(基础码):", top_types)

    # 解析后的行做爆发合并预览
    recs = [json.loads(l) for l in tmp_lines]
    texts = [r for r in recs if r["ty"] == 1 and r["c"]]
    print(f"文本消息 {len(texts)} 条 (other {sum(1 for r in texts if r['s']=='other')} / self {sum(1 for r in texts if r['s']=='self')})")
    for who in ("other", "self"):
        seq = [r for r in texts if r["s"] == who]
        bursts, cnt, last = 0, 0, None
        dist = []
        for r in seq:
            if last is None or r["t"] - last > BURST_WINDOW:
                if cnt:
                    dist.append(cnt)
                bursts += 1
                cnt = 1
            else:
                cnt += 1
            last = r["t"]
        if cnt:
            dist.append(cnt)
        avg = sum(dist) / len(dist) if dist else 0
        print(f"  {who}: 文本 {len(seq)} 条 -> {BURST_WINDOW}s爆发合并 {bursts} 条逻辑消息 (均值 {avg:.2f} 条/条, 最多 {max(dist) if dist else 0} 连发)")

    # 月度分布
    monthly = {}
    for r in recs:
        m = datetime.datetime.fromtimestamp(r["t"]).strftime("%Y-%m")
        monthly[m] = monthly.get(m, 0) + 1
    print("月度:", dict(sorted(monthly.items())))


if __name__ == "__main__":
    main()
