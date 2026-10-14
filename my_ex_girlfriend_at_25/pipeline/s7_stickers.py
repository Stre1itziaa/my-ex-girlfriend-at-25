# -*- coding: utf-8 -*-
"""S7 表情包库: 从语料提取"她"的表情包 CDN 地址, 按频次加权下载 -> data/stickers/。

- 她侧 (real_sender_id=1) ty=47 消息; cdnurl 属性带空格, 正则须 \s*=\s*。
- type=2 动图通常加密: cdnurl(ef=1) 直接下; 若非 GIF/图头, 用 encrypturl+aeskey AES-128-ECB 解。
- 产物: data/stickers/*.gif + manifest.json [{file, md5, count}] (按 count 降序)。
"""
import html
import json
import re
from collections import Counter
from pathlib import Path

import urllib.request
import zstandard
from Crypto.Cipher import AES

BASE = Path(__file__).resolve().parent.parent.parent
RAW = BASE / "data" / "corpus" / "raw.jsonl"
STK = BASE / "data" / "stickers"
TOP_N = 40

RE_MD5 = re.compile(r'md5\s*=\s*"([0-9a-f]{32})"')
RE_CDN = re.compile(r'cdnurl\s*=\s*"([^"]+)"')
RE_ENC = re.compile(r'encrypturl\s*=\s*"([^"]+)"')
RE_AES = re.compile(r'aeskey\s*=\s*"([^"]+)"')


def unescape(u):
    return html.unescape(u).replace("http://", "https://")


def fetch(u):
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/4.0"})
    return urllib.request.urlopen(req, timeout=20).read()


def looks_image(d):
    return d[:4] in (b"GIF8",) or d[:3] == b"\xff\xd8\xff" or d[:8] == b"\x89PNG\r\n\x1a\n"


def main():
    # 1. 提取她侧表情包清单
    lib = {}
    for line in RAW.read_text(encoding="utf-8").split("\n")[1:]:
        if not line.strip():
            continue
        r = json.loads(line)
        if r["ty"] != 47 or r["s"] != "other" or not r["c"]:
            continue
        c = r["c"]
        m = RE_MD5.search(c)
        if not m:
            continue
        md5 = m.group(1)
        e = lib.setdefault(md5, {"count": 0, "cdn": None, "enc": None, "aes": None, "type": None})
        e["count"] += 1
        if e["cdn"] is None:
            u = RE_CDN.search(c)
            e["cdn"] = unescape(u.group(1)) if u else None
            ue = RE_ENC.search(c)
            e["enc"] = unescape(ue.group(1)) if ue else None
            ka = RE_AES.search(c)
            e["aes"] = ka.group(1) if ka else None
            t = re.search(r'type="(\d)"', c)
            e["type"] = t.group(1) if t else ""
    ranked = sorted(lib.items(), key=lambda kv: -kv[1]["count"])[:TOP_N]
    print(f"她侧唯一表情 {len(lib)} 个, 取 top {len(ranked)}")

    # 2. 下载
    STK.mkdir(exist_ok=True)
    manifest, ok = [], 0
    for rank, (md5, e) in enumerate(ranked):
        fn = STK / f"{rank:02d}_{md5[:8]}.gif"
        if fn.exists() and looks_image(fn.read_bytes()):
            manifest.append({"file": str(fn), "md5": md5, "count": e["count"]})
            ok += 1
            continue
        data = None
        for url in filter(None, [e["cdn"], e["enc"]]):
            try:
                d = fetch(url)
                if looks_image(d):
                    data = d
                    break
                if e["aes"]:  # 密文: AES-128-ECB + pkcs7 去 padding
                    key = bytes.fromhex(e["aes"])
                    dec = AES.new(key, AES.MODE_ECB).decrypt(d)
                    pad = dec[-1]
                    dec = dec[:-pad] if 1 <= pad <= 16 else dec
                    if looks_image(dec):
                        data = dec
                        break
            except Exception:
                continue
        if data:
            fn.write_bytes(data)
            manifest.append({"file": str(fn), "md5": md5, "count": e["count"]})
            ok += 1
            print(f"  #{rank:02d} {e['count']:3d}次 {len(data):7d}B {data[:4]}")
        else:
            print(f"  #{rank:02d} {e['count']:3d}次 下载失败")
    (STK / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"表情包库: {ok}/{len(ranked)} 个 -> {STK}/manifest.json")


if __name__ == "__main__":
    main()
